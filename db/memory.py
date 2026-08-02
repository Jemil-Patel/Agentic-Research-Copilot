import os
import json
import asyncpg
import structlog
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger()

# ----------------- QDRANT -----------------
qdrant_client = QdrantClient(path=os.getenv("QDRANT_PATH", "./qdrant_data"))
COLLECTION_NAME = "findings"

# Initialize local embedding model
# We use a fast, small model for embeddings on the CPU
model = SentenceTransformer('all-MiniLM-L6-v2')

def init_qdrant():
    collections = qdrant_client.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("qdrant_collection_created", collection=COLLECTION_NAME)

def insert_finding_vector(run_id: str, task_id: str, claim: str, payload: Dict[str, Any]):
    """Embeds the claim and stores it in Qdrant."""
    vector = model.encode(claim).tolist()
    point_id = hash(f"{run_id}_{task_id}") & ((1<<63)-1) # fast uint64
    
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={"run_id": run_id, "task_id": task_id, "claim": claim, **payload}
            )
        ]
    )
    logger.info("finding_vector_inserted", run_id=run_id, task_id=task_id)

def search_similar_findings(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Search for similar findings based on a query."""
    vector = model.encode(query).tolist()
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit
    )
    return [hit.payload for hit in results.points if hit.score > 0.6]

# ----------------- SUPABASE (POSTGRES) -----------------
async def get_db_connection():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url or db_url == "your_supabase_connection_string_here":
        raise ValueError("Invalid SUPABASE_DB_URL. Please update .env")
    
    # Handle the fact that some connection strings use 'postgres://' instead of 'postgresql://'
    # asyncpg requires 'postgresql://' or it accepts it directly if parsed.
    return await asyncpg.connect(db_url)

async def init_postgres():
    conn = await get_db_connection()
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS task_graph (
                run_id TEXT,
                task_id TEXT,
                task_type TEXT,
                description TEXT,
                dependencies JSONB,
                status TEXT,
                PRIMARY KEY (run_id, task_id)
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS findings (
                run_id TEXT,
                task_id TEXT,
                claim TEXT,
                source_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (run_id, task_id)
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                objective TEXT,
                status TEXT,
                report_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("postgres_tables_initialized")
    finally:
        await conn.close()

async def insert_task_nodes(run_id: str, tasks: List[Dict[str, Any]]):
    conn = await get_db_connection()
    try:
        records = []
        for t in tasks:
            records.append((
                run_id, 
                t["id"], 
                t["task_type"], 
                t["description"], 
                json.dumps(t.get("dependencies", [])), 
                "PENDING"
            ))
            
        await conn.executemany('''
            INSERT INTO task_graph (run_id, task_id, task_type, description, dependencies, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (run_id, task_id) DO NOTHING
        ''', records)
    finally:
        await conn.close()

async def update_task_status(run_id: str, task_id: str, status: str):
    conn = await get_db_connection()
    try:
        await conn.execute('''
            UPDATE task_graph SET status = $1 WHERE run_id = $2 AND task_id = $3
        ''', status, run_id, task_id)
    finally:
        await conn.close()

async def insert_finding_db(run_id: str, task_id: str, claim: str, source_used: str):
    conn = await get_db_connection()
    try:
        await conn.execute('''
            INSERT INTO findings (run_id, task_id, claim, source_used)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (run_id, task_id) DO UPDATE SET claim = $3, source_used = $4
        ''', run_id, task_id, claim, source_used)
    finally:
        await conn.close()

async def insert_run(run_id: str, objective: str, status: str, report_path: str = ""):
    conn = await get_db_connection()
    try:
        await conn.execute('''
            INSERT INTO runs (run_id, objective, status, report_path)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (run_id) DO UPDATE SET status = $3, report_path = $4
        ''', run_id, objective, status, report_path)
    finally:
        await conn.close()

# Combined initialization
async def init_db():
    init_qdrant()
    await init_postgres()
