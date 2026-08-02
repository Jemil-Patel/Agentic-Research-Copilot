import json
import subprocess
import tempfile
import os
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("Code Execution Server")

@mcp.tool()
def execute_python(code: str) -> str:
    """
    Execute a python script in a sandboxed, temporary directory and return its stdout/stderr.
    The process is restricted to a 30-second timeout.
    
    Args:
        code: The Python code to execute.
        
    Returns:
        A JSON string containing the stdout, stderr, and return code.
    """
    # Create a temporary directory that acts as our scratch space
    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = os.path.join(temp_dir, "script.py")
        
        with open(script_path, "w") as f:
            f.write(code)
            
        try:
            # Run the subprocess.
            # In a production environment, we would use setrlimit or a container.
            # Here we restrict via timeout and isolated working directory.
            process = subprocess.run(
                ["python", script_path],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30.0
            )
            
            return json.dumps({
                "stdout": process.stdout,
                "stderr": process.stderr,
                "return_code": process.returncode
            })
        except subprocess.TimeoutExpired as e:
            return json.dumps({
                "error": "Execution timed out after 30 seconds.",
                "stdout": e.stdout.decode('utf-8') if e.stdout else "",
                "stderr": e.stderr.decode('utf-8') if e.stderr else ""
            })
        except Exception as e:
            return json.dumps({"error": f"Execution failed: {str(e)}"})

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run(transport='stdio')
