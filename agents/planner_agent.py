import structlog
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq

from utils.key_manager import get_groq_api_key, get_key_manager

logger = structlog.get_logger()

# Define the Pydantic schema for the Task Graph
class TaskNode(BaseModel):
    id: str = Field(description="A unique identifier for the task (e.g., 'task_1')")
    task_type: Literal["web", "academic", "github", "code"] = Field(
        description="The type of agent needed to solve this task"
    )
    description: str = Field(description="A clear description of what this task must accomplish")
    dependencies: List[str] = Field(
        description="A list of task IDs that must complete before this task can start. Empty list if none.",
        default_factory=list
    )

class TaskGraph(BaseModel):
    tasks: List[TaskNode] = Field(description="List of tasks forming a Directed Acyclic Graph (DAG)")

class PlannerAgent:
    """
    Takes an objective and decomposes it into a structured Task Graph.
    """
    
    def _get_llm(self):
        api_key = get_groq_api_key()
        # Use structured output capable model
        return ChatGroq(api_key=api_key, model="llama-3.1-8b-instant")
        
    async def run(self, objective: str) -> TaskGraph:
        logger.info("planner_agent_start", objective=objective)
        llm = self._get_llm()
        
        # Enforce structured output
        structured_llm = llm.with_structured_output(TaskGraph)
        
        system_prompt = (
            "You are a master research planner. Break down the user's objective into a series of highly specific sub-tasks. "
            "Available task types:\n"
            "- 'web': General web search.\n"
            "- 'academic': Search for academic papers on ArXiv.\n"
            "- 'github': Search for open-source repositories and their code.\n"
            "- 'code': Execute Python code to analyze data or verify behavior.\n\n"
            "Identify dependencies correctly. A task that needs information from another task should list it as a dependency. "
            "Make sure the task IDs are unique and dependency IDs match the task IDs exactly."
        )
        
        try:
            result: TaskGraph = await structured_llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=objective)
            ])
            logger.info("planner_agent_success", num_tasks=len(result.tasks))
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
                logger.error("planner_agent_error", error=str(e))
                raise e
