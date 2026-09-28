"""FastAPI wrapper for the Zotero RAG Assistant."""

from __future__ import annotations

import os
import subprocess
import sys

# Must precede any PyTorch / sentence-transformers imports (OpenMP bug, PyTorch 2.2.x).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from src.config import settings
from src.generation.generator import get_generator
from src.ingestion.embedder import SentenceTransformerEmbedder
from src.retrieval.vector_store import FAISSVectorStore


# ---------------------------------------------------------------------------
# Lifespan — load all heavy resources exactly once at startup
# ---------------------------------------------------------------------------

def _index_path() -> str:
    return str(Path(settings.data_dir) / "paper_index.faiss")


def _child_log() -> Any:
    """Open the capture file for a spawned script's stdout/stderr.

    The scripts configure their own log files, but that only starts once they
    import successfully. Anything earlier — a bad interpreter path, an import
    error, a traceback on startup — would vanish if the stream went to DEVNULL,
    leaving a failed run indistinguishable from a successful one.
    """
    path = Path("logs/api_subprocess.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    return open(path, "a", encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = FAISSVectorStore.load(_index_path())
    app.state.embedder = SentenceTransformerEmbedder(settings.embedding_model)
    app.state.generator = get_generator()
    yield


app = FastAPI(title="Zotero RAG Assistant", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest():
    # Fire-and-forget: embed run can take minutes on CPU; caller gets a response immediately.
    env = {**os.environ, "PYTHONPATH": "."}
    # The parent's handle is closed straight after Popen; the child keeps its own.
    with _child_log() as log:
        subprocess.Popen(
            [sys.executable, "scripts/ingest_papers.py", "--resume"],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return {"status": "started"}


@app.post("/sync")
async def sync():
    # Runs sync_zotero.py, which copies new PDFs then internally POSTs to /ingest.
    env = {**os.environ, "PYTHONPATH": "."}
    with _child_log() as log:
        subprocess.Popen(
            [sys.executable, "scripts/sync_zotero.py"],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return {"status": "started"}


@app.post("/reload")
async def reload(request: Request):
    # Re-read the on-disk index into memory. Called after a background ingest so
    # newly embedded papers become queryable without restarting the server.
    store = FAISSVectorStore.load(_index_path())
    request.app.state.store = store
    return {"status": "reloaded", "vectors": store.size}


@app.post("/query")
async def query(body: QueryRequest, request: Request):
    store: FAISSVectorStore = request.app.state.store
    embedder: SentenceTransformerEmbedder = request.app.state.embedder
    generator = request.app.state.generator

    def _run() -> dict[str, Any]:
        embedding = embedder.embed_text(body.query)
        chunks = store.search(embedding, top_k=body.top_k)
        return generator.generate_answer(
            body.query,
            chunks,
            max_tokens=settings.max_tokens_per_response,
        )

    result = await asyncio.get_event_loop().run_in_executor(None, _run)
    return {
        "answer": result["answer"],
        "cost_usd": result["cost_usd"],
        "model": result["model"],
    }
