import sys
import os
import json
import asyncio
from typing import Dict, Any, List
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import structlog

from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

class WebResearchAgent:
    """
    A standalone Python class that acts as a web research agent.
    It connects to the local Search MCP Server to fetch data and uses Groq for reasoning.
    """
    
    def __init__(self):
        # We assume the MCP server is available at mcp_servers/search.py
        server_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers", "search.py")
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path]
        )
        
    def _get_llm(self):
        """Helper to get a ChatGroq instance using the current key."""
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")
        
    async def _search_web(self, query: str) -> str:
        """Call the search MCP server to execute a search."""
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Call the 'search_web' tool provided by the MCP server
                result = await session.call_tool("search_web", arguments={"query": query})
                
                # result.content is usually a list of text contents
                if not result.content:
                    return "No results found."
                    
                return "\n".join([c.text for c in result.content if c.type == "text"])

    async def run(self, global_objective: str, task_description: str) -> Dict[str, str]:
        logger.info("agent_start", global_objective=global_objective, task_description=task_description)
        llm = self._get_llm()
        
        try:
            # Query Qdrant for past findings
            from db.memory import search_similar_findings
            past_findings = search_similar_findings(task_description, limit=3)
            past_findings_str = "\n".join([f"- {f.get('claim', '')}" for f in past_findings]) if past_findings else "None"
            
            # Step 1: Formulate search query
            query_prompt = f"Global Objective: {global_objective}\nCurrent Task: {task_description}\nExtract a concise web search query to solve the current task."
            query_resp = await llm.ainvoke([HumanMessage(content=query_prompt)])
            
            # Sometimes models return quotes around the query
            search_query = query_resp.content.strip('"\'')
            logger.info("generated_search_query", query=search_query)
            
            # Step 2: Execute search
            search_results_str = await self._search_web(search_query)
            logger.info("search_completed", result_length=len(search_results_str))
            
            # Step 3: Formulate answer
            system_prompt = (
                "You are an expert researcher. Use the provided search results and past findings to answer the current task for the global objective. "
                "You must cite your sources by including the URL of the source. "
                "Keep your answer concise and factual."
            )
            human_prompt = f"Global Objective: {global_objective}\nCurrent Task: {task_description}\n\nPast Findings from other agents:\n{past_findings_str}\n\nSearch Results:\n{search_results_str}"
            
            final_resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            answer = final_resp.content
            logger.info("agent_success")
            
            return {
                "claim": answer,
                "source_used": search_query
            }
            
        except Exception as e:
            # Check if it's a rate limit exception to rotate key
            error_str = str(e).lower()
            if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                logger.warning("groq_rate_limit_encountered", key_manager="rotating_key")
                get_key_manager().rotate_key(get_groq_api_key())
                # Re-raise to trigger a retry in the workflow
                raise e
            elif "401" in error_str or "invalid_api_key" in error_str or "invalid api key" in error_str:
                logger.warning("groq_invalid_key_encountered", key_manager="rotating_key")
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            else:
                logger.error("agent_error", error=str(e))
                raise e
