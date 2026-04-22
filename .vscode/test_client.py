import asyncio
import sys
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Ensure site-packages are in path
user_base = os.path.expanduser(
    r"~\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages"
)
if user_base not in sys.path:
    sys.path.append(user_base)

async def run_test():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["C:/sredba-MCP/my_server.py"],
        env=os.environ.copy()
    )

    print("--- Connecting to MCP Server ---")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # --- 1. SQL SERVER TEST ---
            print("\nTesting SQL Server...")
            mssql_args = {
                "db_type": "mssql", 
                "connection_string": "mssql+pyodbc://sa:YourPassword@localhost/master?driver=ODBC+Driver+17+for+SQL+Server"
            }
            res_ms = await session.call_tool("inspect_db_health", arguments=mssql_args)
            print(f"Result: {res_ms.content[0].text}")

            # --- 2. MYSQL (RDS) TEST ---
            print("\nTesting MySQL (RDS)...")
            # Note: Update 'C:/certs/global-bundle.pem' to your actual local path
            mysql_args = {
                "db_type": "mysql", 
                "connection_string": (
                    "mysql+mysqlconnector://zbxrdsadmin:YourPassword@"
                    "prodzabbix-restore.c22febpuflcu.us-east-1.rds.amazonaws.com:3306/zbxmysql001"
                    "?ssl_ca=C:/certs/global-bundle.pem&ssl_verify_cert=true"
                )
            }
            res_my = await session.call_tool("inspect_db_health", arguments=mysql_args)
            print(f"Result: {res_my.content[0].text}")

            # --- 3. POSTGRESQL TEST ---
            print("\nTesting PostgreSQL...")
            pg_args = {
                "db_type": "postgresql", 
                "connection_string": "postgresql+psycopg2://postgres:YourPassword@localhost:5432/postgres"
            }
            res_pg = await session.call_tool("inspect_db_health", arguments=pg_args)
            print(f"Result: {res_pg.content[0].text}")

if __name__ == "__main__":
    asyncio.run(run_test())