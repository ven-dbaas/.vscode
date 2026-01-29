import asyncio
import sys
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 1. Point to your specific Python environment (same as before)
user_base = os.path.expanduser(
    r"~\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages"
)
if user_base not in sys.path:
    sys.path.append(user_base)

async def run_test():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["C:/Venkata-MCP/my_server.py"], # This now contains both tools
        env=os.environ.copy()
    )

    print("Connecting to MCP Server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 1. Test Math
            res_math = await session.call_tool("add_numbers", arguments={"a": 10, "b": 20})
            print(f"Math: {res_math.content[0].text}")

            # 2. Test DB Health
            db_args = {
                "db_type": "mssql", 
                "connection_string": "mssql+pyodbc://your_user:your_pass@localhost/master?driver=ODBC+Driver+17+for+SQL+Server"
            }
            res_health = await session.call_tool("inspect_db_health", arguments=db_args)
            print(f"DB Health: {res_health.content[0].text}")

if __name__ == "__main__":
    asyncio.run(run_test())


