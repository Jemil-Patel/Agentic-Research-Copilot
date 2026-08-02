from typing import Dict, Any
from pydantic import BaseModel, Field
import structlog
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_groq import ChatGroq
from utils.key_manager import get_groq_api_key, get_key_manager
from agents.synthesis_agent import Report

logger = structlog.get_logger()

class ConsistencyResult(BaseModel):
    is_consistent: bool = Field(..., description="True if the executive recommendation matches the comparison table data.")
    reason: str = Field(..., description="Explanation of why it is or is not consistent.")

class ConsistencyAgent:
    def _get_llm(self):
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")

    async def run(self, report: Report) -> ConsistencyResult:
        logger.info("consistency_check_start")
        llm = self._get_llm()
        
        try:
            parser = PydanticOutputParser(pydantic_object=ConsistencyResult)
            
            system_prompt = (
                "You are an expert Consistency Checker. Your job is to verify that a generated report is internally consistent. "
                "Specifically, check if the 'executive_recommendation' logically matches the data presented in the 'comparison_table'. "
                "If it does, return is_consistent=True. If the recommendation contradicts the table, return is_consistent=False.\n\n"
                f"{parser.get_format_instructions()}\n"
                "Ensure your output is only the raw JSON block without markdown formatting."
            )
            
            human_prompt = (
                f"Executive Recommendation:\n{report.executive_recommendation}\n\n"
                f"Comparison Table:\n{report.comparison_table}"
            )
            
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            result: ConsistencyResult = parser.invoke(response)
            
            logger.info("consistency_check_success", is_consistent=result.is_consistent)
            return result
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            elif "401" in error_str or "invalid_api_key" in error_str or "invalid api key" in error_str:
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            else:
                logger.error("consistency_check_error", error=str(e))
                raise e
