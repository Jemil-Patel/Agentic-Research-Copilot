import json
import arxiv
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("ArXiv Server")

@mcp.tool()
def search_papers(query: str, max_results: int = 5) -> str:
    """
    Search the ArXiv database for academic papers.
    
    Args:
        query: The search query string (e.g., "author:lecun OR large language models").
        max_results: Maximum number of papers to return (default 5).
        
    Returns:
        A JSON string containing the search results with title, authors, summary, and pdf_url.
    """
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        results = []
        for r in client.results(search):
            results.append({
                "title": r.title,
                "authors": [a.name for a in r.authors],
                "summary": r.summary,
                "pdf_url": r.pdf_url,
                "published": r.published.isoformat() if r.published else None
            })
            
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"ArXiv search failed: {str(e)}"})

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run(transport='stdio')
