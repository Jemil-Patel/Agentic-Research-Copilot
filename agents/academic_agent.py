import sys
import os
import asyncio
from typing import Dict, Any
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import structlog

from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

class AcademicAgent:
    """
    Connects to the ArXiv MCP Server to fetch academic papers.
    """
    
    def __init__(self):
        server_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers", "arxiv.py")
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path]
        )
        
    def _get_llm(self):
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")
        
    async def _search_papers(self, query: str) -> str:
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search_papers", arguments={"query": query})
                
                if not result.content:
                    return "No results found."
                    
                return "\n".join([c.text for c in result.content if c.type == "text"])

    async def run(self, global_objective: str, task_description: str) -> Dict[str, str]:
        logger.info("academic_agent_start", global_objective=global_objective, task_description=task_description)
        llm = self._get_llm()
        
        try:
            from db.memory import search_similar_findings
            past_findings = search_similar_findings(task_description, limit=3)
            past_findings_str = "\n".join([f"- {f.get('claim', '')}" for f in past_findings]) if past_findings else "None"
            
            query_prompt = f"Global Objective: {global_objective}\nCurrent Task: {task_description}\nExtract a concise arxiv search query to solve the current task."
            query_resp = await llm.ainvoke([HumanMessage(content=query_prompt)])
            search_query = query_resp.content.strip('"\'')
            
            search_results_str = await self._search_papers(search_query)
            
            system_prompt = (
                "You are an academic researcher. Use the provided ArXiv papers and past findings to answer the current task for the global objective. "
                "Cite your sources using the pdf_url provided in the results. "
                "Keep your answer concise and factual."
            )
            human_prompt = f"Global Objective: {global_objective}\nCurrent Task: {task_description}\n\nPast Findings from other agents:\n{past_findings_str}\n\nArXiv Results:\n{search_results_str}"
            
            final_resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            logger.info("academic_agent_success")
            
            return {
                "claim": final_resp.content,
                "source_used": search_query
            }
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            elif "401" in error_str or "invalid_api_key" in error_str or "invalid api key" in error_str:
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            else:
                logger.error("academic_agent_error", error=str(e))
                raise e
