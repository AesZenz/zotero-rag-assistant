# Project Status

## Update Log
- 2026-04-02 — added local LLM backend (Ollama) alongside Claude API; added query logging; multiple bug fixes (details below)
  - **`src/generation/ollama_client.py`**: `OllamaClient` class with interface identical to `ClaudeGenerator` — same `generate_answer()`, `stream_answer()`, `_calculate_cost()` signatures; uses Ollama's OpenAI-compatible HTTP endpoint (`http://localhost:11434/v1`) via `requests`; `_OllamaStream` context manager mirrors `anthropic.MessageStream` shape so `query_assistant.py` needs no backend-conditional logic; `health_check()` hits `/api/tags` and returns bool; `cost_usd` always 0.0; reads `OLLAMA_MODEL` from env (default: `phi4-mini`); both models confirmed downloaded: `llama3.2:3b` (2.0GB) and `phi4-mini:latest` (2.5GB)
  - **`src/generation/generator.py`**: `get_generator()` factory reads `GENERATION_BACKEND` env var (`claude` or `ollama`, default: `claude`); runs `health_check()` for Ollama and raises `RuntimeError` with setup instructions if server not reachable
  - **`scripts/query_assistant.py`**: replaced direct `ClaudeGenerator()` instantiation with `get_generator()`; cost display shows `"free (local)"` for Ollama backend in both single-shot and REPL modes; added query logging (see below)
  - **`pixi.toml`**: added `query-ollama = { cmd = "PYTHONPATH=. python scripts/query_assistant.py", env = { GENERATION_BACKEND = "ollama" } }` task using pixi's explicit env table syntax
  - **`.env` / `.env.example`**: added `GENERATION_BACKEND=claude` and `OLLAMA_MODEL=llama3.2:3b`
  - **Query logging**: every completed query appends a JSON line to `data/query_logs/query_log.jsonl` — fields: `timestamp` (UTC ISO), `query`, `model`, `retrieved_chunks` (list of `{filename, chunk_index, score}`), `answer`, `latency_seconds`, `cost_usd` (null for Ollama); directory created automatically on first write; log path anchored to absolute `_PROJECT_ROOT` (derived from `__file__`) to avoid CWD sensitivity; `data/query_logs/` covered by existing `data/` entry in `.gitignore`
  - **Ollama timeout fix**: initial timeout of 120s → 600s still timed out on first token (CPU prefill is slow); changed to `timeout=(10, None)` — 10s connect timeout, no read timeout — so CPU inference never times out mid-generation
  - **Log path bug fix**: relative `"data/query_logs/..."` was silently failing under pixi's CWD; fixed to absolute path via `_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`
  - **Ollama query logging unresolved**: Claude logging confirmed working (1 entry in log); Ollama logging still produces no entry — root cause not yet identified; `except OSError: pass` in `_log_query` may be too narrow (a `TypeError` or `UnicodeEncodeError` from `json.dumps` would escape it and crash the REPL silently); proposed fix (`except Exception` + `default=str` in `json.dumps`) not yet applied due to interrupted session
- 2026-03-31 — ran bulk ingestion over full 600-paper library; confirmed index built successfully; ran first end-to-end query against the full index: clinical question about efficacy of mindfulness interventions for ADHD executive function symptoms — system returned relevant chunks and a coherent cited answer; full RAG pipeline confirmed working at scale
- 2026-03-29 — built bulk ingestion script (`scripts/ingest_papers.py`): walks PDF library recursively, runs full parse→chunk→filter→embed→FAISS pipeline, buffers chunks across papers and embeds in bulk batches, checkpoints every 50 papers, `--resume` flag skips already-indexed files by filename, end-of-run summary (processed/failed/chunk counts/embed time/index size); added `ingest-library` pixi task; **not yet tested against full library** — also: repo documentation pass (README rewrite, model name fixes, PYTHONPATH fix, pushed to GitHub)
- 2026-03-29 — repo documentation pass: rewrote `README.md` to reflect actual project state (component status table, known limitations, accurate setup/query commands); fixed incorrect model ID (`claude-sonnet-4-20250514` → `claude-sonnet-4-6`) in `README.md` and `.env.example`; added `PYTHONPATH=.` to direct `python` invocations in README (needed outside of `pixi run`); committed and pushed to GitHub; confirmed end-to-end pipeline works up to generation layer (retrieval returns correct chunks); generation currently blocked by insufficient Anthropic API credits
- 2026-03-27 — built generation layer (`src/generation/claude_client.py`): `ClaudeGenerator` class wrapping the Anthropic SDK with non-streaming `generate_answer()` and streaming `stream_answer()` methods; structured RAG prompt (system + numbered context chunks + citation instruction + "I don't have enough information" fallback); model-prefix pricing table for cost calculation; typed error handling for rate limits, bad requests, and network failures; added `scripts/test_claude_generation.py` (load index → embed → retrieve → generate → print) and `scripts/query_assistant.py` (full CLI with single-shot and interactive REPL modes, streaming display, per-query and session cost tracking)
- 2026-03-24 — fixed metadata key mismatch (`extract_metadata()` now returns `"pdf_title"` instead of `"title"`); fixed pixi.toml deprecation warnings (`[project]` → `[workspace]`, `depends_on` → `depends-on`); diagnosed and fixed PyTorch segfault on osx-64 Intel Mac (`OMP_NUM_THREADS=1` env var in test script — PyTorch 2.2.2 OpenMP threading bug); built noise filter (`src/ingestion/noise_filter.py`) with chunk-level signal detection for reference lists, author affiliations, funding acknowledgments, and journal headers — confirmed working on Flynn effect paper (23/51 chunks correctly identified as noise, all verified as legitimate drops)
- 2026-03-23 — fixed datetime JSON serialization in `FAISSVectorStore.save()` (added `default` serializer converting `datetime` to isoformat); suppressed HuggingFace tokenizer parallelism warning in `scripts/test_vector_store.py` via `TOKENIZERS_PARALLELISM=false`
- 2026-03-21 — built FAISS vector store (`src/retrieval/vector_store.py`), end-to-end test script, added `test-vector-store` pixi task; audited `pixi.toml` and `pixi.lock` for dependency conflicts
- 2026-03-20 — resolved dependency hell; all three ingestion test scripts confirmed working
- 2026-03-20 — noted PDF parser noise issue; deferred parser filtering until after basic pipeline is working
- 2026-03-13 — built ingestion pipeline (PDF parsing, chunking, embeddings)

## What's Built
- **PDF parser** (`src/ingestion/pdf_parser.py`): PyMuPDF-based text extraction with whitespace normalization, metadata parsing (title, author, date, page count), encrypted/scanned PDF detection
- **Text chunker** (`src/ingestion/chunker.py`): Token-accurate sliding window chunking using tiktoken (cl100k_base), with character offset tracking for source attribution and metadata propagation per chunk
- **Noise filter** (`src/ingestion/noise_filter.py`): Post-chunking, pre-embedding filter using chunk-level signal density heuristics — removes reference lists (DOI/vol/year counts), author affiliations (email + institution keywords), funding acknowledgments (keyword density), and journal headers (publisher keywords at chunk start); figure captions intentionally kept; confirmed ~45% drop rate on meta-analysis paper (all drops verified as legitimate noise)
- **Embedder** (`src/ingestion/embedder.py`): `sentence-transformers/all-mpnet-base-v2` wrapper with lazy model loading, CPU-only batch inference (batch size 32), tqdm progress tracking
- **Logging infrastructure** (`src/utils/logging.py`): Dual console/file output, environment-driven config, named loggers per module
- **FAISS vector store** (`src/retrieval/vector_store.py`): `FAISSVectorStore` class — `IndexFlatIP` with L2 normalisation for cosine similarity, `add_chunks()` / `search()` / `save()` / `load()` API, metadata stored in JSON sidecar alongside binary FAISS index file
- **Claude generation layer** (`src/generation/claude_client.py`): `ClaudeGenerator` class — reads `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` from env; `generate_answer(query, context_chunks, max_tokens) → dict` (non-streaming, returns `answer/model/tokens_used/cost_usd`); `stream_answer(query, context_chunks, max_tokens)` returns an `anthropic.MessageStream` context manager for real-time token display; model-prefix pricing table (Opus 4/$5/$25, Sonnet 4/$3/$15, Haiku 4/$1/$5); RAG system prompt instructs Claude to use only provided context, cite chunks by number, and say "I don't have enough information" when context is insufficient; typed error handling for `RateLimitError`, `BadRequestError`, `APIConnectionError`, `APIError`
- **Ollama generation layer** (`src/generation/ollama_client.py`): `OllamaClient` class — mirrors `ClaudeGenerator` interface exactly; calls Ollama's OpenAI-compatible HTTP API via `requests` (no new dependencies); `_OllamaStream` context manager reproduces `anthropic.MessageStream` shape (`text_stream`, `get_final_message()`, `final.usage.input_tokens/output_tokens`); streaming uses `timeout=(10, None)` to handle slow CPU prefill; `health_check()` for startup validation; `cost_usd` always 0.0
- **Generation backend selector** (`src/generation/generator.py`): `get_generator()` reads `GENERATION_BACKEND` env var and returns the appropriate client; validates Ollama availability via `health_check()` before returning
- **Test scripts** (`scripts/test_pdf_parser.py`, `test_chunker.py`, `test_embedder.py`, `test_vector_store.py`, `test_claude_generation.py`): Ad-hoc smoke tests for each stage — ingestion confirmed working; vector store test covers full parse→chunk→filter→embed→index→search→save→load round-trip; generation test loads saved index and runs end-to-end query through Claude
- **Query CLI** (`scripts/query_assistant.py`): `python scripts/query_assistant.py "question"` for single-shot; bare invocation for interactive REPL; `--index`, `--top-k`, `--max-tokens`, `--verbose` flags; answers stream token-by-token; per-query and session-total cost printed after each answer
- **PDF library**: 1.3GB, ~600 psychology/neuroscience/AI papers exported from Zotero (with RDF metadata)

## Current State
All core pipeline components are complete and confirmed working at scale. The full RAG pipeline runs end-to-end: parse PDF → chunk (512 tokens, 50 overlap) → noise-filter → embed with `all-mpnet-base-v2` → FAISS index → cosine similarity search → Claude answer with chunk citations. The full 600-paper library has been ingested and the system has been validated with a real clinical query (mindfulness interventions for ADHD executive function). `scripts/query_assistant.py` streams Claude's response token-by-token and reports per-query cost. What's still missing: an evaluation module and pytest unit tests.

## Dependency Resolutions
- **`sentence-transformers = ">=2.3.0,<2.4.0"`** — 2.2.x was broken because it imports `cached_download` from `huggingface_hub`, which was removed in newer versions of that library (installed: 0.36.2). 2.3.x dropped that import. Upper bound `<2.4.0` chosen for stability.
- **`numpy = ">=1.24.0,<2.0.0"`** — upper bound added to prevent NumPy 2.x incompatibilities with sentence-transformers and related ML deps.
- **`torch = ">=2.1.0"`** — kept as-is; no conflicts found.

## Architecture Decisions Made
- **Embedding model: `all-mpnet-base-v2`** — chosen over MiniLM variants for higher quality; comment in `.env.example` mentions matryoshka embeddings as a future placeholder
- **Token-based chunking over character-based** — uses tiktoken `cl100k_base` encoding for consistency with LLM context limits; chunk_size=512, overlap=50 (set in `.env`, passed through pipeline)
- **Local embeddings only** — `USE_LOCAL_EMBEDDINGS=true` in config; no OpenAI embeddings to control cost
- **CPU-only execution** — `device="cpu"` hardcoded in embedder; design choice for broad compatibility, not a hardware limitation
- **PyMuPDF (`fitz`) for PDF parsing** — chosen over `pypdf`/`pdfplumber` (both also in dependencies); PyMuPDF handles more edge cases
- **Chunk-level metadata** — document metadata (author, title, creation_date) propagated to every chunk dict for retrieval context
- **Vector store: FAISS `IndexFlatIP`** — exact cosine similarity via inner product on L2-normalised vectors; chose flat index over IVF because ~30K vectors (600 papers × ~50 chunks) is small enough for exact search with negligible latency; ChromaDB installed but unused and safe to remove
- **Vectors normalised at write and query time** — `faiss.normalize_L2()` called on both incoming chunk vectors and query vectors as a safety net, since `all-mpnet-base-v2` already produces unit-norm outputs
- **Cost guardrails baked into config** — `MAX_TOKENS_PER_RESPONSE=500`, `MAX_COST_PER_QUERY_USD=0.05` defined; not enforced yet since generation layer is missing

## Known Issues / Tech Debt
- ~~**PDF parser noise**~~ — resolved: `src/ingestion/noise_filter.py` built and confirmed working; pipeline is now parse→chunk→filter→embed
- ~~**Metadata key mismatch bug**~~ — resolved: `extract_metadata()` now returns `"pdf_title"`
- **`scripts/ingest_papers.py` complete and tested** — run against full 600-paper library; index confirmed working (first query returned correct results); `scripts/run_evaluation.py` still missing (`pixi run evaluate` will fail)
- **Ollama query logging unresolved** — Claude logging confirmed working; Ollama logging silently produces no log entry; root cause unknown (likely `except OSError: pass` being too narrow — any non-OSError exception from `json.dumps` escapes the handler); fix: broaden to `except Exception` and add `default=str` to `json.dumps`
- ~~**`scripts/query_assistant.py` missing**~~ — resolved: built with streaming REPL and single-shot modes
- ~~**No vector store implementation**~~ — resolved: `src/retrieval/vector_store.py` built and tested
- **No GitHub repo**: project is local-only, no remote tracking; needs a GitHub repo created and initial push
- **No tests directory**: pytest + pytest-cov configured in pixi.toml but `tests/` doesn't exist; test coverage is 0%
- **Hardcoded batch size**: `32` appears in two separate places in `embedder.py` (lines 105 and 159) — must be kept in sync manually
- **No config management layer**: 17 env vars read ad-hoc; `pydantic-settings` is installed but unused — no validation, no central config object
- **Unused heavy dependencies**: `langchain`, `langchain-community`, `chromadb`, `rich`, `click`, `pandas`, `scikit-learn`, `nltk` all installed but not imported anywhere (`anthropic` is now used)
- **`pdfplumber` installed but unused**: PyMuPDF was chosen but pdfplumber remains as dead weight

## Next Steps (ordered)
1. **Add Pydantic settings** — centralize all env var reads into one `Settings` class with validation
2. **Implement evaluation** (`src/evaluation/`) — question generation + retrieval/answer quality metrics using the existing `scikit-learn`/`nltk` deps
3. **Write pytest test suite** — unit tests for parser, chunker, embedder, vector store; integration test for full pipeline on known PDF

## Concepts Learned So Far
- **RAG pipeline**: All four stages built and working end-to-end — ingest (parse→chunk→filter→embed), index (FAISS), retrieve (cosine similarity search), generate (Claude with context + citation prompt)
- **Chunking strategy**: Understand why token-based > character-based; understand the overlap tradeoff (too small = lost context at boundaries, too large = redundant retrieval); 512/50 is a reasonable starting point
- **Embeddings**: Understand dense vector representations, batch inference, the tradeoff between model size and quality (MiniLM vs mpnet); aware of matryoshka embeddings as an advanced option but haven't implemented
- **Tiktoken**: Understand `cl100k_base` encoding is OpenAI's tokenizer for GPT-3.5/4 — using it here for consistency even though the generation model is Claude
- **FAISS**: Implemented — `IndexFlatIP` for exact cosine similarity on normalised vectors; understand flat vs IVF tradeoff and why flat is appropriate at ~30K vectors; understand the two-file persistence pattern (binary index + JSON metadata sidecar)
- **PyMuPDF vs alternatives**: Chose it over pypdf/pdfplumber for robustness on academic PDFs; have seen it handle encrypted and scanned PDF edge cases

## Open Questions
- ~~**FAISS index type**~~ — resolved: `IndexFlatIP` chosen; ~30K vectors is small enough for exact search
- **Query embedding vs chunk embedding**: Should the query be embedded with the same model used for chunks? (Yes, it must be — but not explicitly documented anywhere)
- **Reranking**: `USE_RERANKING=false` in config — is this worth enabling? Cross-encoder reranking would improve quality but adds latency and complexity; unclear if the dataset size justifies it
- **Zotero RDF metadata**: The library has a `Psy:Neuroscience:AI.rdf` file with rich Zotero metadata (tags, collections, notes) — should this be used to enrich chunk metadata, or just rely on PDF-extracted metadata?
- **cl100k_base for Claude**: Using OpenAI's tokenizer for chunking, but the generation model is Claude (different tokenizer) — does this create a mismatch for context window calculations?
- ~~**`all-mpnet-base-v2` embedding dim**~~ — resolved: 768, confirmed, `IndexFlatIP(768)` built and tested
- ~~**Ingestion idempotency (crash recovery)**~~ — resolved via `--resume` flag.
- **Ingestion idempotency (naive re-run)**: running without `--resume` silently duplicates all vectors in the index. No guard implemented.
- **HTML files in library**: Some Zotero exports are `.html` web snapshots, not PDFs — the current parser only handles PDFs; these will be silently skipped or error

## Cost Tracking
- Embedding runs: ~$0 (all local, CPU-only)
- Claude API test calls: <$0.01 (generation layer integrated; costs tracked per query via `cost_usd` field)
- GPU rental: $0
