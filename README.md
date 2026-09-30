# Agentic Research Copilot

A distributed multi-agent research assistant that decomposes complex technical objectives into dynamic Directed Acyclic Graphs (DAGs), executes specialized research agents in parallel using the Model Context Protocol (MCP), and verifies findings through an LLM-as-a-judge evaluation pipeline backed by Qdrant vector memory.

Orchestrated with **Temporal** for event-sourced execution durability, resilient activity retries, and Human-in-the-Loop (HITL) checkpoints, with real-time state streaming to a **React** dashboard via **Server-Sent Events (SSE)**.

---

## Key Features

- **Dynamic Runtime DAG Decomposition**: A `PlannerAgent` decomposes arbitrary research queries into dependency-aware task graphs at runtime (rather than relying on static, pre-compiled graphs).
- **Durable Temporal Orchestration**: Manages long-running workflows with fault tolerance, activity-level retry policies, and zero-resource pauses for human checkpoints.
- **Human-in-the-Loop (HITL) Checkpoints**:
  1. *Plan Approval*: Review and approve the decomposed task graph before execution begins.
  2. *Conflict Arbitration*: Intervene when the automated judge flags conflicting assertions across parallel sources.
- **Standardized Tooling via Model Context Protocol (MCP)**: Communicates with tool servers over stdio subprocesses for Tavily web search and ArXiv academic retrieval.
- **LLM-as-a-Judge Fact Verification**: Evaluates source grounding (1–5) and queries local **Qdrant** vector memory (`all-MiniLM-L6-v2`) to detect cross-agent factual contradictions.
- **Resilient API Key Rotation**: Thread-safe round-robin `GroqKeyManager` that catches HTTP 429 rate limits and rotates keys without crashing active workflow activities.
- **Real-Time Reactive GUI**: React 19 + Vite dashboard that connects directly to the gateway via Server-Sent Events (SSE) to render live task progress, status badges, and synthesized comparison tables.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  React 19 Dashboard (Vite)                   │
│          Live DAG Feed, HITL Approvals, Synthesis Report      │
└───────────────┬──────────────────────────────▲───────────────┘
                │ REST (POST)                  │ SSE (/feed)
┌───────────────▼──────────────────────────────┴───────────────┐
│                     FastAPI Gateway                          │
│        Protocol Translation (HTTP/JSON <-> Temporal gRPC)     │
└───────────────┬──────────────────────────────────────────────┘
                │ Temporal Client (port 7233)
┌───────────────▼──────────────────────────────────────────────┐
│                 Temporal Workflow Engine                     │
│               Durable State & Signal Routing                 │
└───────────────┬──────────────────────────────────────────────┘
                │ Task Queue: "research-task-queue"
┌───────────────▼──────────────────────────────────────────────┐
│                     Temporal Workers                         │
│                                                              │
│  • PlannerAgent         • WebResearchAgent (Tavily MCP)      │
│  • SynthesisAgent       • AcademicAgent (ArXiv MCP)          │
│  • EvaluatorAgent (LLM-as-a-judge + Qdrant Vector Memory)    │
└──────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Agentic-Research-Copilot/
├── agents/                  # Specialized LLM agents
│   ├── planner_agent.py     # Decomposes queries into dynamic DAGs
│   ├── research_agent.py    # Web research agent (Tavily MCP client)
│   ├── academic_agent.py    # Academic paper agent (ArXiv MCP client)
│   ├── evaluator_agent.py   # LLM-as-a-judge (grounding & conflict check)
│   └── synthesis_agent.py   # Compiles structured report & comparison matrix
├── mcp_servers/             # FastMCP stdio tool servers
│   ├── search.py            # Tavily web search server
│   └── arxiv.py             # ArXiv paper retrieval server
├── workflow/                # Temporal orchestration
│   ├── research.py          # ResearchWorkflow & activity definitions
│   └── worker.py            # Temporal worker runtime
├── gateway/                 # FastAPI service
│   └── main.py              # REST endpoints & SSE streaming gateway
├── db/                      # Persistence
│   └── memory.py            # Qdrant embedded vector client (MiniLM-L6-v2)
├── frontend/                # React 19 + Vite dashboard
│   ├── src/                 # App.jsx, index.css, main.jsx
│   └── package.json
├── utils/                   # Key management
│   └── key_manager.py       # Thread-safe Groq API key rotator
├── interview-prep/          # Technical deep-dives & endpoint references
├── .env.example             # Template for API keys & config
└── pyproject.toml           # Python dependencies
```

---

## Prerequisites

1. **Python 3.11+**
2. **Node.js 18+** & **npm**
3. **Temporal CLI** (for local workflow orchestration)
   - macOS: `brew install temporal`
   - Linux: `curl -sSf https://temporal.download/cli.sh | sh`
4. **API Keys**:
   - [Groq API Key](https://console.groq.com/) (free tier available; comma-separated multiple keys supported for auto-rotation)
   - [Tavily API Key](https://app.tavily.com/) (free tier available for web search)

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Jemil-Patel/Agentic-Research-Copilot.git
cd Agentic-Research-Copilot
```

### 2. Configure Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Set Up Environment Variables
Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```
Edit `.env`:
```env
GROQ_API_KEYS=gsk_your_groq_key_1,gsk_your_groq_key_2
TAVILY_API_KEY=tvly-your_tavily_key
QDRANT_PATH=./qdrant_data
```

### 4. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

---

## Running the Application

To run the complete system, start the following 4 processes in separate terminal windows:

### Terminal 1: Start Temporal Server
```bash
temporal server start-dev
```
*Temporal Web UI will be available at [http://localhost:8233](http://localhost:8233).*

### Terminal 2: Start the Temporal Worker
```bash
source venv/bin/activate
python -m workflow.worker
```
*Initializes local Qdrant collection and registers agents/activities on `research-task-queue`.*

### Terminal 3: Start the FastAPI Gateway
```bash
source venv/bin/activate
uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```
*FastAPI server runs at [http://localhost:8000](http://localhost:8000). Interactive Swagger docs at [http://localhost:8000/docs](http://localhost:8000/docs).*

### Terminal 4: Start the React Frontend
```bash
cd frontend
npm run dev
```
*React dashboard runs at [http://localhost:5173](http://localhost:5173).*

---

## Usage Walkthrough

1. Open **[http://localhost:5173](http://localhost:5173)** in your browser.
2. Enter a research topic (e.g. *"Compare the architecture, context window, and inference efficiency of LLaMA-3 vs. Mistral Large"*).
3. **Plan Review Checkpoint**: The Planner Agent will break down the objective into parallel sub-tasks. Inspect the task DAG on the dashboard and click **"Approve Plan"**.
4. **Execution & Fact Verification**: The system executes parallel searches via ArXiv and Tavily. The Evaluator Agent checks each claim against source text and past findings in Qdrant.
5. **Conflict Checkpoint (if triggered)**: If conflicting claims are detected across sources, the task status becomes `ESCALATED`. The UI prompts you to **"Force Retry"** or **"Accept Anyway"**.
6. **Executive Report**: Once all tasks complete, the dashboard renders an executive summary, side-by-side comparison table, and cited sources.

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/research` | Starts a new `ResearchWorkflow` execution on Temporal. |
| `GET` | `/research/{run_id}/feed` | Server-Sent Events (SSE) streaming live DAG updates & report. |
| `POST` | `/research/{run_id}/approve_plan` | Human-in-the-Loop signal to approve DAG and begin execution. |
| `POST` | `/research/{run_id}/resolve_escalation` | Human-in-the-Loop signal to arbitrate a flagged factual conflict. |
| `GET` | `/research/{run_id}` | Direct polling endpoint to retrieve workflow status and final result. |

*For complete payload schemas and example JSON objects, see [interview-prep/06_endpoints.md](interview-prep/06_endpoints.md).*

---

## License

This project is licensed under the MIT License.
