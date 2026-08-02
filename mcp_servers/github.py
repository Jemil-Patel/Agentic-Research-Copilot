import os
import json
import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("GitHub Server")

@mcp.tool()
def search_repos(query: str, max_results: int = 5) -> str:
    """
    Search GitHub repositories.
    
    Args:
        query: The search query string (e.g., "language:python machine learning").
        max_results: Maximum number of repos to return (default 5).
        
    Returns:
        A JSON string containing the search results with full_name, description, stars, and html_url.
    """
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token and token != "your_github_token_here":
        headers["Authorization"] = f"token {token}"
        
    try:
        url = f"https://api.github.com/search/repositories?q={query}&per_page={max_results}"
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("items", []):
            results.append({
                "full_name": item.get("full_name"),
                "description": item.get("description"),
                "stars": item.get("stargazers_count"),
                "html_url": item.get("html_url"),
                "language": item.get("language")
            })
            
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"GitHub search failed: {str(e)}"})

@mcp.tool()
def get_readme(repo_name: str) -> str:
    """
    Fetch the README content of a specific GitHub repository.
    
    Args:
        repo_name: The full repository name (e.g., "owner/repo").
        
    Returns:
        A JSON string containing the README text.
    """
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if token and token != "your_github_token_here":
        headers["Authorization"] = f"token {token}"
        
    try:
        url = f"https://api.github.com/repos/{repo_name}/readme"
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        
        return json.dumps({"repo": repo_name, "readme": response.text})
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch README for {repo_name}: {str(e)}"})

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run(transport='stdio')
