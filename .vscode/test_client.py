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
    # 2. Tell the client how to start your server
    server_params = StdioServerParameters(
        command=sys.executable, # Uses the current Python you're in
        args=["C:/Venkata-MCP/my_server.py"],
        env=os.environ.copy()
    )

    print("Connecting to MCP Server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            
            # 3. Call your 'add_numbers' tool!
            print("Calling tool: add_numbers(a=10, b=20)")
            result = await session.call_tool("add_numbers", arguments={"a": 10, "b": 20})
            
            print(f"\nSERVER RESPONSE: {result.content[0].text}")

if __name__ == "__main__":
    asyncio.run(run_test())
