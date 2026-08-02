import sys
import os
import json
import asyncio
from typing import Dict, Any
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import structlog

from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

class CodeAgent:
    """
    Connects to the Code Execution MCP Server to run Python code.
    """
    
    def __init__(self):
        server_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers", "code_execution.py")
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path]
        )
        
    def _get_llm(self):
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")
        
    async def _execute_python(self, code: str) -> str:
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("execute_python", arguments={"code": code})
                
                if not result.content:
                    return "No output."
                    
                return "\n".join([c.text for c in result.content if c.type == "text"])

    async def run(self, global_objective: str, task_description: str) -> Dict[str, str]:
        logger.info("code_agent_start", global_objective=global_objective, task_description=task_description)
        llm = self._get_llm()
        
        try:
            from db.memory import search_similar_findings
            past_findings = search_similar_findings(task_description, limit=3)
            past_findings_str = "\n".join([f"- {f.get('claim', '')}" for f in past_findings]) if past_findings else "None"
            
            # Step 1: Write code
            system_prompt = (
                "You are an expert Python developer. Write a python script to solve the current task for the global objective. "
                "You have access to the past findings of other agents. Use them as hardcoded variables or reference data in your script if needed. "
                "Output ONLY the python code inside a ```python``` block, nothing else."
            )
            human_prompt = f"Global Objective: {global_objective}\nCurrent Task: {task_description}\n\nPast Findings from other agents:\n{past_findings_str}"
            
            code_resp = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            # Extract code from markdown block
            code_text = code_resp.content
            if "```python" in code_text:
                code = code_text.split("```python")[1].split("```")[0].strip()
            elif "```" in code_text:
                code = code_text.split("```")[1].strip()
            else:
                code = code_text.strip()
                
            # Step 2: Execute code
            execution_result = await self._execute_python(code)
            
            logger.info("code_agent_success")
            
            return {
                "claim": f"Code Execution Results:\n{execution_result}",
                "source_used": code
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
                logger.error("code_agent_error", error=str(e))
                raise e
