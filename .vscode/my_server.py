import sys
import os

# 1. Define the base path where pip installed your packages
user_base = os.path.expanduser(
    r"~\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages"
)

# 2. Add the main site-packages and the hidden win32 folders to sys.path
paths_to_add = [
    user_base,
    os.path.join(user_base, "win32"),
    os.path.join(user_base, "win32", "lib"),
    os.path.join(user_base, "Pythonwin")
]

for p in paths_to_add:
    if p not in sys.path:
        sys.path.append(p)

# 3. CRITICAL: Tell Windows where to find the pywin32 DLLs
# This fixes the 'ModuleNotFoundError: No module named pywintypes'
os.add_dll_directory(os.path.join(user_base, "pywin32_system32"))

# NOW try the import
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyLocalServer")

# ---TOOL Section 1: Math ---
@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Adds two numbers together."""
    return a + b

# ---TOOL Section 2: File System ---
@mcp.tool()
def search_code(directory: str, query: str) -> str:
    """Searches for a specific string in all text files within a directory."""
    results = []
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(('.py', '.txt', '.json', '.md')):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        if query in f.read():
                            results.append(path)
        return "\n".join(results) if results else "No matches found."
    except Exception as e:
        return f"Error: {str(e)}"

# --- TOOL Section 3: File Content ---
@mcp.tool()
def read_file(file_path: str) -> str:
    """Reads the full text content of a file so the AI can analyze it."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

if __name__ == "__main__":
    mcp.run()
