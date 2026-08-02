from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
import structlog
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_groq import ChatGroq
from db.memory import search_similar_findings
from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

class EvaluationResult(BaseModel):
    groundedness_score: int = Field(..., ge=1, le=5, description="Score 1-5 on how well the claim is supported by the source text.")
    completeness_score: int = Field(..., ge=1, le=5, description="Score 1-5 on how completely the claim answers the task description.")
    conflict: bool = Field(..., description="True if the claim directly contradicts past findings.")
    conflict_reason: str = Field(..., description="Explanation of the conflict, or empty string if none.")
    recommendation: Literal["accept", "retry", "escalate"] = Field(..., description="Recommendation for next steps based on scores and conflicts.")

class EvaluatorAgent:
    """
    EvaluatorAgent acts as an LLM-as-a-judge to evaluate findings.
    """
    def _get_llm(self):
        # We can use a larger model like 70b if available, or just the 8b one for now.
        # But we must stick to the working model: llama-3.1-8b-instant
        api_key = get_groq_api_key()
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")

    async def run(self, global_objective: str, task_description: str, claim: str, source_used: str) -> EvaluationResult:
        logger.info("evaluator_start", task_description=task_description)
        llm = self._get_llm()
        
        try:
            # Query Qdrant for past findings to check for conflicts
            past_findings = search_similar_findings(task_description, limit=5)
            past_findings_str = "\n".join([f"- {f.get('claim', '')}" for f in past_findings]) if past_findings else "None"
            
            parser = PydanticOutputParser(pydantic_object=EvaluationResult)
            
            system_prompt = (
                "You are an expert Evaluator. Your job is to judge a generated 'claim' (finding) based on the 'source text' used to generate it.\n"
                "You must score Groundedness (1-5) and Completeness (1-5).\n"
                "You must check for logical conflicts against past findings from other agents.\n"
                "Rules for recommendation:\n"
                "- If scores are high (4 or 5) and no conflict: return 'accept'.\n"
                "- If scores are low (1 to 3) or the claim does not properly answer the task: return 'retry'.\n"
                "- If there is a direct factual conflict with past findings: return 'escalate'.\n\n"
                f"{parser.get_format_instructions()}\n"
                "Ensure your output is only the raw JSON block without markdown formatting."
            )
            
            human_prompt = (
                f"Global Objective: {global_objective}\n"
                f"Task Description: {task_description}\n\n"
                f"Generated Claim (Finding):\n{claim}\n\n"
                f"Source Text Used:\n{source_used}\n\n"
                f"Past Findings (for conflict checking):\n{past_findings_str}"
            )
            
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])
            
            result: EvaluationResult = parser.invoke(response)
            
            logger.info("evaluator_success", recommendation=result.recommendation, groundedness=result.groundedness_score)
            return result
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                logger.warning("groq_rate_limit_encountered", key_manager="rotating_key")
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            elif "401" in error_str or "invalid_api_key" in error_str or "invalid api key" in error_str:
                logger.warning("groq_invalid_key_encountered", key_manager="rotating_key")
                get_key_manager().rotate_key(get_groq_api_key())
                raise e
            else:
                logger.error("evaluator_error", error=str(e))
                raise e
