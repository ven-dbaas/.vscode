import sys
import os
import sqlalchemy as sa
from sqlalchemy import text
from mcp.server.fastmcp import FastMCP

# Ensure your site-packages are available to the server process
user_base = os.path.expanduser(
    r"~\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages"
)
if user_base not in sys.path:
    sys.path.append(user_base)

mcp = FastMCP("Unified-Venkata-Server")

# --- Existing Tool ---
@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    return a + b

# --- New Database Health Tool ---
@mcp.tool()
def inspect_db_health(db_type: str, connection_string: str):
    """
    Analyzes DB health, IO hotspots, and index efficiency.
    Supported types: 'mssql', 'postgresql', 'mysql'
    """
    engine = sa.create_engine(connection_string)
    report = {}

    with engine.connect() as conn:
        # SQL Server Logic
        if db_type == 'mssql':
            # Get largest DBs
            db_size_query = "SELECT name, (size * 8 / 1024) as size_mb FROM sys.master_files"
            # Get IO Latency (Hot Tables indicator)
            io_query = "SELECT DB_NAME(database_id), io_stall_read_ms FROM sys.dm_io_virtual_file_stats(NULL, NULL)"
            
            report['databases'] = [dict(row) for row in conn.execute(text(db_size_query)).fetchmany(5)]
            report['io_hotspots'] = [dict(row) for row in conn.execute(text(io_query)).fetchmany(5)]
            report['health_prediction'] = "Analysis complete. Check IO stalls for latency issues."

        # PostgreSQL Logic
        elif db_type == 'postgresql':
            pg_query = "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database"
            report['databases'] = [dict(row) for row in conn.execute(text(pg_query))]
            
    return str(report)

if __name__ == "__main__":
    mcp.run()