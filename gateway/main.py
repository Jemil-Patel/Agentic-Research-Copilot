from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio
import json
from temporalio.client import Client
import structlog
from dotenv import load_dotenv

from workflow.research import ResearchWorkflow, ResearchParams

load_dotenv()

app = FastAPI(title="Agentic Research Copilot Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = structlog.get_logger()

# Global Temporal client
temporal_client: Optional[Client] = None

@app.on_event("startup")
async def startup_event():
    global temporal_client
    # Connect to the local Temporal Server
    temporal_client = await Client.connect("localhost:7233")
    logger.info("gateway_started", connected_to_temporal=True)

class ResearchRequest(BaseModel):
    question: str

class ResearchResponse(BaseModel):
    run_id: str
    status: str

@app.post("/research", response_model=ResearchResponse)
async def start_research(req: ResearchRequest):
    if not temporal_client:
        raise HTTPException(status_code=500, detail="Temporal client not connected.")
    
    # Start the workflow asynchronously
    try:
        handle = await temporal_client.start_workflow(
            ResearchWorkflow.run,
            ResearchParams(objective=req.question),
            id=f"research-run-{asyncio.get_event_loop().time()}", # simplistic unique id
            task_queue="research-task-queue",
        )
        logger.info("gateway_workflow_started", run_id=handle.id, question=req.question)
        
        return ResearchResponse(run_id=handle.id, status="STARTED")
    except Exception as e:
        logger.error("gateway_workflow_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/research/{run_id}")
async def get_research_status(run_id: str):
    if not temporal_client:
        raise HTTPException(status_code=500, detail="Temporal client not connected.")
        
    try:
        handle = temporal_client.get_workflow_handle(run_id)
        # Describe the workflow to get its status
        desc = await handle.describe()
        
        status_name = desc.status.name
        
        # If it's completed, we can get the result
        result = None
        if status_name == "COMPLETED":
            result = await handle.result()
            
        return {
            "run_id": run_id,
            "status": status_name,
            "result": result
        }
    except Exception as e:
        logger.error("gateway_status_fetch_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=404, detail=f"Workflow not found or error: {str(e)}")

@app.get("/research/{run_id}/feed")
async def get_research_feed(run_id: str):
    if not temporal_client:
        raise HTTPException(status_code=500, detail="Temporal client not connected.")
    
    async def event_generator():
        try:
            handle = temporal_client.get_workflow_handle(run_id)
            while True:
                state = await handle.query(ResearchWorkflow.get_live_state)
                yield f"data: {json.dumps(state)}\n\n"
                
                if state.get("status") == "COMPLETED" or state.get("status") == "FAILED":
                    break
                    
                await asyncio.sleep(1)
        except Exception as e:
            logger.error("gateway_feed_error", run_id=run_id, error=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

class ResolveEscalationRequest(BaseModel):
    task_id: str
    resolution: str # "accept" or "retry"

@app.post("/research/{run_id}/approve_plan")
async def approve_plan(run_id: str):
    if not temporal_client:
        raise HTTPException(status_code=500, detail="Temporal client not connected.")
    
    try:
        handle = temporal_client.get_workflow_handle(run_id)
        await handle.signal(ResearchWorkflow.approve_plan, True)
        return {"status": "plan_approved"}
    except Exception as e:
        logger.error("gateway_approve_plan_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/research/{run_id}/resolve_escalation")
async def resolve_escalation(run_id: str, req: ResolveEscalationRequest):
    if not temporal_client:
        raise HTTPException(status_code=500, detail="Temporal client not connected.")
    
    try:
        handle = temporal_client.get_workflow_handle(run_id)
        payload = {"task_id": req.task_id, "resolution": req.resolution}
        await handle.signal(ResearchWorkflow.resolve_escalation, payload)
        return {"status": "escalation_resolved"}
    except Exception as e:
        logger.error("gateway_resolve_escalation_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
