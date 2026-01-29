import json
import sqlalchemy as sa
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

mcp = FastMCP("DB-Health-Expert")

@mcp.tool()
def get_advanced_health(db_type: str, conn_str: str):
    """
    Performs deep inspection of DB health, IO hotspots, and index efficiency.
    """
    engine = sa.create_engine(conn_str)
    report = {"databases": [], "hot_tables": [], "index_stats": [], "health_prediction": {}}

    with engine.connect() as conn:
        # --- SQL SERVER SPECIFIC (Deep DMV Inspection) ---
        if db_type == 'mssql':
            # 1. List User Databases & Sizes
            db_query = "SELECT name, database_id FROM sys.databases WHERE database_id > 4"
            report['databases'] = [dict(row) for row in conn.execute(text(db_query))]

            # 2. IO Hotspots (Virtual File Stats)
            io_query = """
            SELECT DB_NAME(database_id) AS DB, file_id, io_stall_read_ms, io_stall_write_ms,
            num_of_reads, num_of_writes FROM sys.dm_io_virtual_file_stats(NULL, NULL)
            ORDER BY io_stall_read_ms DESC;
            """
            report['hot_tables'] = [dict(row) for row in conn.execute(text(io_query))]

            # 3. Missing Indexes (Prediction)
            index_query = """
            SELECT TOP 5 mig.index_handle, mid.statement AS table_name, 
            (migs.user_seeks + migs.user_scans) * migs.avg_user_impact as potential_gain
            FROM sys.dm_db_missing_index_groups mig
            JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_handle
            JOIN sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
            ORDER BY potential_gain DESC;
            """
            report['index_stats'] = [dict(row) for row in conn.execute(text(index_query))]

        # --- POSTGRESQL SPECIFIC (Cache & Bloat) ---
        elif db_type == 'postgresql':
            # 1. Cache Hit Ratio (Goal > 99%)
            cache_query = """
            SELECT sum(heap_blks_read) as read, sum(heap_blks_hit) as hit,
            (sum(heap_blks_hit) - sum(heap_blks_read)) / sum(heap_blks_hit + 1) * 100 as ratio
            FROM pg_statio_user_tables;
            """
            cache_data = conn.execute(text(cache_query)).fetchone()
            report['cache_ratio'] = float(cache_data[2]) if cache_data else 0

    # --- Health Prediction Logic ---
    score = 100
    warnings = []
    
    if db_type == 'mssql' and len(report['index_stats']) > 0:
        score -= 15
        warnings.append("High impact missing indexes detected. Performance is degraded.")
    
    if db_type == 'postgresql' and report.get('cache_ratio', 100) < 95:
        score -= 20
        warnings.append("Cache hit ratio below 95%. Increase shared_buffers or optimize queries.")

    report['health_prediction'] = {
        "score": max(score, 0),
        "status": "Optimal" if score > 85 else "Action Required",
        "recommendations": warnings
    }

    return json.dumps(report, indent=2)

if __name__ == "__main__":
    mcp.run()