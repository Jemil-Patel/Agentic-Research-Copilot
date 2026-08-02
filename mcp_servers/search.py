import os
import json
import asyncio
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("Search Server")

@mcp.tool()
def search_web(query: str) -> str:
    """
    Search the web for a given query using the Tavily API.
    
    Args:
        query: The search query string.
    
    Returns:
        A JSON string containing the search results with title, url, and snippet.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or api_key == "your_tavily_api_key_here":
        return json.dumps({"error": "TAVILY_API_KEY is missing or invalid."})

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query, 
            search_depth="basic",
            max_results=3
        )
        
        results = []
        for res in response.get("results", []):
            results.append({
                "title": res.get("title", ""),
                "url": res.get("url", ""),
                "snippet": res.get("content", "")
            })
            
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run(transport='stdio')
