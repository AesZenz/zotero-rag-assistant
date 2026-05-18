# zotero-rag-assistant

RAG system for querying ~600 academic PDFs. Learning project — build with understanding, not just generation.

## Environment

- **Task runner**: pixi only. Never suggest `pip install` or bare `python` calls.
- **Run scripts**: always `PYTHONPATH=. python scripts/...` or `pixi run <task>`.
- **Config**: all env vars come from `src/config.py` (`Settings(BaseSettings)`). No `os.getenv()` calls — use `settings.<field>`.
- **dotenv**: Pydantic reads `.env` directly. Never add `load_dotenv()`.
- **Import ordering constraint**: if a script overrides `os.environ` before src imports (e.g. `LOG_FILE`, `OMP_NUM_THREADS`), `from src.config import settings` must come *after* those overrides.
- **Hardware**: Intel iMac 2017, CPU-only. No CUDA. No GPU inference.

## Stack

| Layer | Key files | Notes |
|---|---|---|
| Ingestion | `src/ingestion/` | PyMuPDF → tiktoken chunker (512/50) → noise filter → embedder |
| Embedder | `src/ingestion/embedder.py` | `all-mpnet-base-v2`, 768-dim, batch=32 (two places — keep in sync) |
| Vector store | `src/retrieval/vector_store.py` | FAISS `IndexFlatIP` + JSON sidecar, ~26K vectors |
| Generation | `src/generation/` | `get_generator()` factory; backends: `claude` or `ollama` |
| Config | `src/config.py` | Single `settings` singleton, 23 typed fields |
| Evaluation | `src/evaluation/` | Retrieval metrics + Claude-as-judge faithfulness |
| Scripts | `scripts/` | `query_assistant.py`, `ingest_papers.py`, `run_evaluation.py` |

## Key Constraints & Gotchas

- **OMP_NUM_THREADS=1**: must be set before PyTorch imports on this machine (OpenMP bug, PyTorch 2.2.x). Already handled in scripts — don't remove it.
- **FAISS flat index**: `IndexFlatIP` is correct at ~26K vectors. Do not suggest IVF.
- **Vectors normalised twice**: `faiss.normalize_L2()` called at write and query time. `all-mpnet-base-v2` already outputs unit vectors; this is a safety net — leave it.
- **Query decomposition is OFF** (`QUERY_DECOMPOSITION=false`). It made retrieval *worse* because `math.ceil(top_k / n_sub)` starves each sub-question. Don't re-enable without fixing the budget logic first.
- **Ollama timeout**: `timeout=(10, None)` — 10s connect, no read timeout. Required for slow CPU prefill.
- **REPL duplication**: decomposition+dedup logic is copy-pasted between `run_query()` and the inline REPL loop. Fix both if touching retrieval.
- **ChromaDB installed but unused** — safe to ignore.

## Code Style

- No nested loops or chained `elif` unless strictly necessary.
- Comments explain *why*, not *what*.
- Short, composable functions over monolithic blocks.
- Typing throughout.

## What's Missing (next steps)

1. Pytest suite (`tests/` — generated but not verified)

## Do Not

- Do not add `load_dotenv()` anywhere.
- Do not use `os.getenv()` — always `settings.<field>`.
- Do not suggest IVF index or GPU inference.
- Do not re-enable query decomposition without fixing the per-sub budget.
- Do not read `PROJECT_STATUS.md` unless explicitly asked — it's a changelog, not active context.
