from typing import Dict, Any, List
from pydantic import BaseModel, Field
import structlog
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_groq import ChatGroq
from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

class ComparisonRow(BaseModel):
    feature_or_metric: str = Field(..., description="The name of the feature or metric being compared.")
    details: str = Field(..., description="The comparison details across different options.")

class Report(BaseModel):
    executive_recommendation: str = Field(..., description="A high-level summary and final recommendation.")
    comparison_table: List[ComparisonRow] = Field(..., description="Tabular comparison of the main options or entities researched.")
    citations: Dict[str, str] = Field(..., description="Mapping of claims or entity names to their source URLs.")
    confidence_limitations: str = Field(..., description="Discussion of any gaps in the research, low confidence areas, or limitations.")

class SynthesisAgent:
    def _get_llm(self):
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")

    async def run(self, global_objective: str, findings: Dict[str, Any]) -> Report:
        logger.info("synthesis_start", objective=global_objective)
        llm = self._get_llm()
        
        try:
            findings_str = ""
            for task_id, finding in findings.items():
                claim = finding.get("claim", "")
                source = finding.get("source_used", "Unknown")
                findings_str += f"--- Task {task_id} ---\nClaim: {claim}\nSource: {source}\n\n"
            
            parser = PydanticOutputParser(pydantic_object=Report)
            
            system_prompt = (
                "You are an expert Synthesis Agent. Your job is to read all the raw findings from a multi-agent research run "
                "and produce a final, highly structured report.\n"
                "The report must include an executive recommendation, a comparison table, citations, and confidence/limitations.\n"
                "Make sure your executive recommendation directly answers the global objective using the provided findings.\n\n"
                f"{parser.get_format_instructions()}\n"
                "Ensure your output is only the raw JSON block without markdown formatting."
            )
            
            human_prompt = (
                f"Global Objective: {global_objective}\n\n"
                f"Raw Findings:\n{findings_str}"
            )
            
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            result: Report = parser.invoke(response)
            
            logger.info("synthesis_success")
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
                logger.error("synthesis_error", error=str(e))
                raise e
