import asyncio
import os
import json
from datetime import timedelta
from typing import Dict, Any, List
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import structlog
from dataclasses import dataclass

# Define the input/output types
@dataclass
class ResearchParams:
    objective: str
    
@dataclass
class TaskResult:
    task_id: str
    result: Dict[str, str]

logger = structlog.get_logger()

# ----------------- ACTIVITIES -----------------

@activity.defn
async def run_planner_agent(params: ResearchParams) -> Dict[str, Any]:
    from agents.planner_agent import PlannerAgent
    agent = PlannerAgent()
    result = await agent.run(params.objective)
    return result.model_dump()

@activity.defn
async def save_task_graph_activity(run_id: str, graph_dict: Dict[str, Any]):
    from db.memory import insert_task_nodes, insert_run
    await insert_run(run_id, graph_dict.get("objective", "unknown"), "RUNNING", "")
    await insert_task_nodes(run_id, graph_dict.get("tasks", []))

@activity.defn
async def update_task_status_activity(run_id: str, task_id: str, status: str):
    from db.memory import update_task_status
    await update_task_status(run_id, task_id, status)

@activity.defn
async def save_finding_activity(run_id: str, task_id: str, claim: str, source_used: str):
    from db.memory import insert_finding_db, insert_finding_vector
    await insert_finding_db(run_id, task_id, claim, source_used)
    insert_finding_vector(run_id, task_id, claim, {"source_used": source_used})

@activity.defn
async def run_web_agent(global_objective: str, task_description: str) -> Dict[str, str]:
    from agents.research_agent import WebResearchAgent
    agent = WebResearchAgent()
    return await agent.run(global_objective, task_description)

@activity.defn
async def run_academic_agent(global_objective: str, task_description: str) -> Dict[str, str]:
    from agents.academic_agent import AcademicAgent
    agent = AcademicAgent()
    return await agent.run(global_objective, task_description)

@activity.defn
async def run_github_agent(global_objective: str, task_description: str) -> Dict[str, str]:
    from agents.github_agent import GithubAgent
    agent = GithubAgent()
    return await agent.run(global_objective, task_description)

@activity.defn
async def run_code_agent(global_objective: str, task_description: str) -> Dict[str, str]:
    from agents.code_agent import CodeAgent
    agent = CodeAgent()
    return await agent.run(global_objective, task_description)

@activity.defn
async def evaluate_finding_activity(global_objective: str, task_description: str, claim: str, source_used: str) -> Dict[str, Any]:
    from agents.evaluator_agent import EvaluatorAgent
    agent = EvaluatorAgent()
    result = await agent.run(global_objective, task_description, claim, source_used)
    return result.model_dump()

@activity.defn
async def generate_report_activity(global_objective: str, findings: Dict[str, Any]) -> Dict[str, Any]:
    from agents.synthesis_agent import SynthesisAgent
    from agents.consistency_agent import ConsistencyAgent
    
    synthesis_agent = SynthesisAgent()
    consistency_agent = ConsistencyAgent()
    
    max_retries = 3
    for _ in range(max_retries):
        report = await synthesis_agent.run(global_objective, findings)
        consistency = await consistency_agent.run(report)
        if consistency.is_consistent:
            return report.model_dump()
    
    return report.model_dump()

@activity.defn
async def save_report_activity(run_id: str, objective: str, report: Dict[str, Any]):
    from db.memory import insert_run
    
    report_dir = f"reports/{run_id}"
    os.makedirs(report_dir, exist_ok=True)
    report_path = f"{report_dir}/report.json"
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    await insert_run(run_id, objective, "COMPLETED", report_path)


# ----------------- WORKFLOW -----------------

@workflow.defn
class ResearchWorkflow:
    def __init__(self):
        self._plan_approved = False
        self._escalation_resolutions: Dict[str, str] = {}
        self._state = {
            "status": "PLANNING",
            "tasks": {},
            "task_details": {},
            "findings": {},
            "report": None
        }

    @workflow.signal
    def approve_plan(self, approved: bool) -> None:
        self._plan_approved = approved

    @workflow.signal
    def resolve_escalation(self, payload: Dict[str, str]) -> None:
        task_id = payload.get("task_id")
        resolution = payload.get("resolution")
        if task_id and resolution:
            self._escalation_resolutions[task_id] = resolution

    @workflow.query
    def get_live_state(self) -> Dict[str, Any]:
        return self._state

    @workflow.run
    async def run(self, params: ResearchParams) -> Dict[str, Any]:
        workflow.logger.info(f"workflow_started for objective: {params.objective}")
        run_id = workflow.info().run_id
        self._state["status"] = "PLANNING"
        
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=5,
        )
        activity_args = {
            "start_to_close_timeout": timedelta(minutes=5),
            "retry_policy": retry_policy,
        }

        # 1. Run Planner
        task_graph = await workflow.execute_activity(
            run_planner_agent, params, **activity_args
        )
        
        for t in task_graph.get("tasks", []):
            self._state["tasks"][t["id"]] = "PENDING"
            self._state["task_details"][t["id"]] = t.get("description", "")
        
        # 2. Save Graph to DB
        await workflow.execute_activity(
            save_task_graph_activity, args=[run_id, {"objective": params.objective, "tasks": task_graph.get("tasks", [])}], start_to_close_timeout=timedelta(seconds=10)
        )

        # 3. Human-in-the-Loop: Pause for plan approval
        self._state["status"] = "WAITING_FOR_APPROVAL"
        workflow.logger.info("waiting_for_plan_approval")
        await workflow.wait_condition(lambda: self._plan_approved)
        workflow.logger.info("plan_approved")
        self._state["status"] = "EXECUTING_DAG"

        # 4. Fan-out execution (DAG)
        futures: Dict[str, asyncio.Task] = {}
        findings: Dict[str, Any] = {}

        for task in task_graph.get("tasks", []):
            task_id = task["id"]
            
            async def execute_task(t: Dict[str, Any]) -> TaskResult:
                t_id = t["id"]
                t_type = t["task_type"]
                desc = t["description"]
                deps = t.get("dependencies", [])
                
                # Wait for dependencies
                for dep in deps:
                    if dep in futures:
                        await futures[dep]
                
                self._state["tasks"][t_id] = "RUNNING"
                
                # Update status
                await workflow.execute_activity(
                    update_task_status_activity, args=[run_id, t_id, "RUNNING"], start_to_close_timeout=timedelta(seconds=10)
                )
                
                max_retries = 3
                final_status = "COMPLETED"
                result = None

                for attempt in range(max_retries):
                    if t_type == "web":
                        result = await workflow.execute_activity(run_web_agent, args=[params.objective, desc], **activity_args)
                    elif t_type == "academic":
                        result = await workflow.execute_activity(run_academic_agent, args=[params.objective, desc], **activity_args)
                    elif t_type == "github":
                        result = await workflow.execute_activity(run_github_agent, args=[params.objective, desc], **activity_args)
                    elif t_type == "code":
                        result = await workflow.execute_activity(run_code_agent, args=[params.objective, desc], **activity_args)
                    else:
                        result = await workflow.execute_activity(run_web_agent, args=[params.objective, desc], **activity_args)
                    
                    # Run evaluation
                    eval_result = await workflow.execute_activity(
                        evaluate_finding_activity,
                        args=[params.objective, desc, result["claim"], result.get("source_used", "")],
                        **activity_args
                    )
                    
                    recommendation = eval_result["recommendation"]
                    has_conflict = eval_result["conflict"]

                    if recommendation == "accept":
                        if has_conflict:
                            final_status = "CONTESTED"
                        break
                    
                    elif recommendation == "retry":
                        if attempt == max_retries - 1:
                            if has_conflict:
                                final_status = "CONTESTED"
                            break
                        continue
                    
                    elif recommendation == "escalate":
                        self._state["tasks"][t_id] = "ESCALATED"
                        await workflow.execute_activity(
                            update_task_status_activity, args=[run_id, t_id, "ESCALATED"], start_to_close_timeout=timedelta(seconds=10)
                        )
                        workflow.logger.info(f"escalating_task waiting for human resolution: {t_id}")
                        await workflow.wait_condition(lambda: t_id in self._escalation_resolutions)
                        
                        resolution = self._escalation_resolutions[t_id]
                        if resolution == "accept":
                            if has_conflict:
                                final_status = "CONTESTED"
                            break
                        elif resolution == "retry":
                            if attempt == max_retries - 1:
                                if has_conflict:
                                    final_status = "CONTESTED"
                                break
                            continue
                    
                # Save finding
                if result:
                    self._state["findings"][t_id] = result["claim"]
                    await workflow.execute_activity(
                        save_finding_activity, 
                        args=[run_id, t_id, result["claim"], result.get("source_used", "")],
                        start_to_close_timeout=timedelta(seconds=10)
                    )
                
                self._state["tasks"][t_id] = final_status
                # Update status
                await workflow.execute_activity(
                    update_task_status_activity, args=[run_id, t_id, final_status], start_to_close_timeout=timedelta(seconds=10)
                )
                
                return TaskResult(task_id=t_id, result=result or {})

            # Schedule task execution asynchronously
            futures[task_id] = asyncio.create_task(execute_task(task))
            
        # Wait for all tasks to complete
        task_results = await asyncio.gather(*futures.values())
        
        for r in task_results:
            findings[r.task_id] = r.result
            
        self._state["status"] = "SYNTHESIZING"
            
        # 5. Generate and Save Report
        report = await workflow.execute_activity(
            generate_report_activity,
            args=[params.objective, findings],
            **activity_args
        )
        
        await workflow.execute_activity(
            save_report_activity,
            args=[run_id, params.objective, report],
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        self._state["status"] = "COMPLETED"
        self._state["report"] = report
            
        workflow.logger.info("workflow_completed")
        return {
            "objective": params.objective,
            "findings": findings,
            "report": report
        }
