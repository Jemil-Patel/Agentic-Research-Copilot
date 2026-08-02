import asyncio
import structlog
from temporalio.client import Client
from temporalio.worker import Worker
from dotenv import load_dotenv

from workflow.research import (
    ResearchWorkflow,
    run_planner_agent,
    save_task_graph_activity,
    update_task_status_activity,
    save_finding_activity,
    run_web_agent,
    run_academic_agent,
    run_github_agent,
    run_code_agent,
    evaluate_finding_activity,
    generate_report_activity,
    save_report_activity
)
from db.memory import init_db

load_dotenv()

logger = structlog.get_logger()

async def main():
    # Initialize DB (Postgres tables + Qdrant collection)
    await init_db()

    # Connect to local Temporal server
    client = await Client.connect("localhost:7233")
    
    # Run a worker
    worker = Worker(
        client,
        task_queue="research-task-queue",
        workflows=[ResearchWorkflow],
        activities=[
            run_planner_agent,
            save_task_graph_activity,
            update_task_status_activity,
            save_finding_activity,
            run_web_agent,
            run_academic_agent,
            run_github_agent,
            run_code_agent,
            evaluate_finding_activity,
            generate_report_activity,
            save_report_activity
        ],
    )
    
    logger.info("worker_started", task_queue="research-task-queue")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
