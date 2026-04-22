"""
Database Health Monitor - Refactored Version
Secure, maintainable MCP server for multi-database health checks
"""
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import text, bindparam
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
class DBType(str, Enum):
    """Supported database types"""
    MSSQL = "mssql"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"

# Health score thresholds
INDEX_RATIO_HIGH_THRESHOLD = 80  # Indexes shouldn't exceed 80% of data size
INDEX_RATIO_LOW_THRESHOLD = 5    # Should have at least 5% indexing
PENALTY_HIGH_INDEX = 15
PENALTY_LOW_INDEX = 10
PENALTY_NO_DATA = 20

# Connection pool settings
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30

# Engine cache for connection reuse
_engine_cache: Dict[str, sa.engine.Engine] = {}

# Initialize MCP server
mcp = FastMCP("SREDBA-DB-Insight-Server")


def get_engine(connection_string: str) -> sa.engine.Engine:
    """
    Get or create a cached SQLAlchemy engine with connection pooling.
    
    Args:
        connection_string: Database connection string
        
    Returns:
        SQLAlchemy Engine instance
    """
    if connection_string not in _engine_cache:
        logger.info("Creating new database engine")
        _engine_cache[connection_string] = sa.create_engine(
            connection_string,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT
        )
    return _engine_cache[connection_string]


def execute_query_safe(
    conn: sa.engine.Connection,
    query: str,
    params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Execute a query safely with error handling.
    
    Args:
        conn: Active database connection
        query: SQL query string
        params: Query parameters
        
    Returns:
        List of result dictionaries
        
    Raises:
        sa.exc.DatabaseError: On query execution failure
    """
    try:
        result = conn.execute(text(query), params or {})
        return [dict(row) for row in result.mappings()]
    except sa.exc.DatabaseError as e:
        logger.error(f"Query execution failed: {e}")
        raise


def validate_db_type(db_type: str) -> bool:
    """Check if database type is supported."""
    try:
        DBType(db_type.lower())
        return True
    except ValueError:
        return False


@mcp.tool()
def inspect_db_health(
    db_type: str,
    connection_string: str,
    target_database: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified health check for SQL Server, PostgreSQL, and MySQL.
    
    Args:
        db_type: One of 'mssql', 'postgresql', or 'mysql'
        connection_string: SQLAlchemy connection string
        target_database: Optional database name for detailed inspection
    
    Returns:
        Dictionary containing health status and metrics
        
    Example:
        >>> inspect_db_health('postgresql', 'postgresql://user:pass@localhost/mydb')
        {'status': 'success', 'health_score': 95.5, ...}
    """
    # Validate input
    if not validate_db_type(db_type):
        supported = [t.value for t in DBType]
        return {
            "status": "error",
            "type": "validation",
            "message": f"Unsupported database type '{db_type}'. Must be one of: {supported}"
        }
    
    db_type_enum = DBType(db_type.lower())
    
    try:
        engine = get_engine(connection_string)
        report = {
            "status": "success",
            "db_type": db_type_enum.value,
            "target": target_database or "server-wide",
            "data": {},
            "health_score": 100
        }

        with engine.connect() as conn:
            if db_type_enum == DBType.MSSQL:
                report = _inspect_mssql(conn, report)
            elif db_type_enum == DBType.POSTGRESQL:
                report = _inspect_postgresql(conn, report)
            elif db_type_enum == DBType.MYSQL:
                report = _inspect_mysql(conn, report, target_database)

        logger.info(f"Health check completed for {db_type_enum.value}")
        return report

    except sa.exc.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return {
            "status": "error",
            "type": "connection",
            "message": "Unable to connect to database. Check connection string and credentials."
        }
    except sa.exc.DatabaseError as e:
        logger.error(f"Database query failed: {e}")
        return {
            "status": "error",
            "type": "query",
            "message": "Database query failed. Check permissions and database availability."
        }
    except Exception as e:
        logger.exception("Unexpected error during health check")
        return {
            "status": "error",
            "type": "unexpected",
            "message": "An unexpected error occurred during health check."
        }


def _inspect_mssql(conn: sa.engine.Connection, report: Dict[str, Any]) -> Dict[str, Any]:
    """Perform SQL Server specific health checks."""
    try:
        # Database sizes (excluding system databases)
        db_query = """
            SELECT name, (size*8/1024) as size_mb 
            FROM sys.master_files 
            WHERE database_id > 4
        """
        report["data"]["databases"] = execute_query_safe(conn, db_query)
        
        # IO hotspots
        io_query = """
            SELECT TOP 5 
                DB_NAME(database_id) as db, 
                io_stall_read_ms 
            FROM sys.dm_io_virtual_file_stats(NULL, NULL) 
            ORDER BY io_stall_read_ms DESC
        """
        report["data"]["io_hotspots"] = execute_query_safe(conn, io_query)
        
    except Exception as e:
        logger.error(f"MSSQL inspection failed: {e}")
        report["warnings"] = [f"Partial data: {str(e)}"]
    
    return report


def _inspect_postgresql(conn: sa.engine.Connection, report: Dict[str, Any]) -> Dict[str, Any]:
    """Perform PostgreSQL specific health checks."""
    try:
        # Database sizes
        db_query = """
            SELECT datname, pg_size_pretty(pg_database_size(datname)) as size 
            FROM pg_database 
            WHERE datistemplate = false
        """
        report["data"]["databases"] = execute_query_safe(conn, db_query)
        
        # Cache hit ratio (key performance indicator)
        cache_query = """
            SELECT 
                sum(heap_blks_read) as reads, 
                sum(heap_blks_hit) as hits 
            FROM pg_statio_user_tables
        """
        result = execute_query_safe(conn, cache_query)
        
        if result:
            reads = result[0].get('reads') or 0
            hits = result[0].get('hits') or 0
            total = reads + hits
            
            if total > 0:
                hit_ratio = (hits / total) * 100
                report["health_score"] = round(hit_ratio, 2)
                report["data"]["cache_hit_ratio"] = f"{hit_ratio:.2f}%"
            else:
                report["health_score"] = 0
                report["warnings"] = ["No cache statistics available"]
                
    except Exception as e:
        logger.error(f"PostgreSQL inspection failed: {e}")
        report["warnings"] = [f"Partial data: {str(e)}"]
    
    return report


def _inspect_mysql(
    conn: sa.engine.Connection,
    report: Dict[str, Any],
    target_database: Optional[str]
) -> Dict[str, Any]:
    """Perform MySQL specific health checks."""
    try:
        if not target_database:
            # Discovery mode: List available databases
            db_list = execute_query_safe(conn, "SHOW DATABASES")
            report["data"]["available_databases"] = [list(d.values())[0] for d in db_list]
            report["note"] = "Provide 'target_database' parameter for detailed table analysis"
        else:
            # Drill-down mode: Table sizes with proper parameterization
            query = text("""
                SELECT 
                    table_name, 
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) as size_mb 
                FROM information_schema.TABLES 
                WHERE table_schema = :db_name
                ORDER BY (data_length + index_length) DESC 
                LIMIT 10
            """).bindparams(bindparam("db_name"))
            
            result = conn.execute(query, {"db_name": target_database})
            report["data"]["table_sizes"] = [dict(row) for row in result.mappings()]
            
    except Exception as e:
        logger.error(f"MySQL inspection failed: {e}")
        report["warnings"] = [f"Partial data: {str(e)}"]
    
    return report


@mcp.tool()
def get_mysql_database_sizes(connection_string: str) -> Dict[str, Any]:
    """
    Get all database sizes for MySQL server.
    
    Args:
        connection_string: MySQL connection string
    
    Returns:
        Dictionary with database sizes and total count
    """
    try:
        engine = get_engine(connection_string)
        
        with engine.connect() as conn:
            query = """
                SELECT 
                    table_schema as database_name, 
                    ROUND(SUM((data_length + index_length) / 1024 / 1024), 2) as size_mb 
                FROM information_schema.TABLES 
                WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys') 
                GROUP BY table_schema 
                ORDER BY size_mb DESC
            """
            
            databases = execute_query_safe(conn, query)
            
            return {
                "status": "success",
                "databases": databases,
                "total_count": len(databases)
            }
    
    except sa.exc.OperationalError as e:
        logger.error(f"Connection failed: {e}")
        return {
            "status": "error",
            "type": "connection",
            "message": "Unable to connect to MySQL server"
        }
    except Exception as e:
        logger.exception("Unexpected error getting database sizes")
        return {
            "status": "error",
            "type": "unexpected",
            "message": "Failed to retrieve database sizes"
        }


@mcp.tool()
def get_mysql_health_prediction(
    connection_string: str,
    database_name: str
) -> Dict[str, Any]:
    """
    Comprehensive health analysis and prediction for a MySQL database.
    
    Analyzes table statistics, storage metrics, indexing efficiency,
    and provides a health score with actionable warnings.
    
    Args:
        connection_string: MySQL connection string
        database_name: Name of the database to analyze
    
    Returns:
        Dictionary containing health score, metrics, and recommendations
    """
    try:
        engine = get_engine(connection_string)
        
        with engine.connect() as conn:
            # Table Statistics with parameterized query
            tables_query = text("""
                SELECT 
                    TABLE_NAME, 
                    TABLE_ROWS, 
                    ROUND((DATA_LENGTH / 1024 / 1024), 2) as data_size_mb,
                    ROUND((INDEX_LENGTH / 1024 / 1024), 2) as index_size_mb,
                    ENGINE
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = :db_name
                ORDER BY DATA_LENGTH DESC
            """).bindparams(bindparam("db_name"))
            
            result = conn.execute(tables_query, {"db_name": database_name})
            tables = [dict(row) for row in result.mappings()]
            
            # Storage Summary
            storage_query = text("""
                SELECT 
                    COUNT(*) as table_count,
                    ROUND(SUM(DATA_LENGTH) / 1024 / 1024, 2) as data_mb,
                    ROUND(SUM(INDEX_LENGTH) / 1024 / 1024, 2) as index_mb,
                    ROUND((SUM(DATA_LENGTH) + SUM(INDEX_LENGTH)) / 1024 / 1024, 2) as total_mb,
                    SUM(TABLE_ROWS) as total_rows
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = :db_name
            """).bindparams(bindparam("db_name"))
            
            result = conn.execute(storage_query, {"db_name": database_name})
            storage_data = dict(result.mappings().fetchone())
            
            # Index Count
            index_query = text("""
                SELECT COUNT(*) as index_count
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = :db_name
            """).bindparams(bindparam("db_name"))
            
            result = conn.execute(index_query, {"db_name": database_name})
            index_count = dict(result.mappings().fetchone())['index_count']
            
            # Calculate health score
            health_score, warnings = _calculate_health_score(storage_data)
            
            return {
                "status": "success",
                "database": database_name,
                "health_score": health_score,
                "summary": {
                    "tables": storage_data.get('table_count', 0),
                    "total_rows": storage_data.get('total_rows', 0),
                    "data_size_mb": storage_data.get('data_mb', 0),
                    "index_size_mb": storage_data.get('index_mb', 0),
                    "total_size_mb": storage_data.get('total_mb', 0),
                    "index_count": index_count
                },
                "metrics": {
                    "index_to_data_ratio_percent": _calculate_index_ratio(
                        storage_data.get('index_mb', 0),
                        storage_data.get('data_mb', 0)
                    )
                },
                "tables": tables,
                "warnings": warnings if warnings else ["No issues detected"],
                "recommendations": _generate_recommendations(health_score, warnings)
            }
    
    except sa.exc.OperationalError as e:
        logger.error(f"Connection failed: {e}")
        return {
            "status": "error",
            "type": "connection",
            "message": "Unable to connect to MySQL server"
        }
    except Exception as e:
        logger.exception("Unexpected error during health prediction")
        return {
            "status": "error",
            "type": "unexpected",
            "message": "Failed to complete health analysis"
        }


def _calculate_index_ratio(index_mb: float, data_mb: float) -> float:
    """Calculate index-to-data ratio safely."""
    if data_mb > 0:
        return round((index_mb / data_mb) * 100, 2)
    return 0.0


def _calculate_health_score(storage_data: Dict[str, Any]) -> tuple[int, List[str]]:
    """
    Calculate health score based on database metrics.
    
    Returns:
        Tuple of (health_score, warnings_list)
    """
    health_score = 100
    warnings = []
    
    data_mb = storage_data.get('data_mb') or 0
    index_mb = storage_data.get('index_mb') or 0
    total_rows = storage_data.get('total_rows') or 0
    
    # Check for empty database
    if total_rows == 0:
        health_score -= PENALTY_NO_DATA
        warnings.append("Database contains no data")
        return health_score, warnings
    
    # Analyze index-to-data ratio
    index_ratio = _calculate_index_ratio(index_mb, data_mb)
    
    if data_mb > 0:
        if index_ratio > INDEX_RATIO_HIGH_THRESHOLD:
            health_score -= PENALTY_HIGH_INDEX
            warnings.append(
                f"High index-to-data ratio ({index_ratio:.1f}%). "
                f"Indexes may be oversized or redundant."
            )
        elif index_ratio < INDEX_RATIO_LOW_THRESHOLD:
            health_score -= PENALTY_LOW_INDEX
            warnings.append(
                f"Low index-to-data ratio ({index_ratio:.1f}%). "
                f"Database may lack proper indexes for query optimization."
            )
    
    return health_score, warnings


def _generate_recommendations(health_score: int, warnings: List[str]) -> List[str]:
    """Generate actionable recommendations based on health analysis."""
    recommendations = []
    
    if health_score >= 90:
        recommendations.append("Database health is excellent. Continue regular maintenance.")
    elif health_score >= 70:
        recommendations.append("Database health is good with minor issues to address.")
    else:
        recommendations.append("Database health needs attention. Review warnings carefully.")
    
    if any("High index-to-data ratio" in w for w in warnings):
        recommendations.append("Consider reviewing and removing redundant or unused indexes.")
    
    if any("Low index-to-data ratio" in w for w in warnings):
        recommendations.append("Analyze slow queries and add indexes on frequently queried columns.")
    
    if any("no data" in w.lower() for w in warnings):
        recommendations.append("Database appears empty. Verify data import and application connectivity.")
    
    return recommendations


def cleanup_engines():
    """Dispose all cached database engines. Call on shutdown."""
    logger.info("Cleaning up database connections")
    for engine in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        cleanup_engines()