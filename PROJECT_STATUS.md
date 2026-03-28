# Project Status

## Update Log
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
- **Test scripts** (`scripts/test_pdf_parser.py`, `test_chunker.py`, `test_embedder.py`, `test_vector_store.py`, `test_claude_generation.py`): Ad-hoc smoke tests for each stage — ingestion confirmed working; vector store test covers full parse→chunk→filter→embed→index→search→save→load round-trip; generation test loads saved index and runs end-to-end query through Claude
- **Query CLI** (`scripts/query_assistant.py`): `python scripts/query_assistant.py "question"` for single-shot; bare invocation for interactive REPL; `--index`, `--top-k`, `--max-tokens`, `--verbose` flags; answers stream token-by-token; per-query and session-total cost printed after each answer
- **PDF library**: 1.3GB, ~600 psychology/neuroscience/AI papers exported from Zotero (with RDF metadata)

## Current State
The ingestion, retrieval, and generation layers are all complete. The full RAG pipeline works end-to-end: parse PDF → chunk (512 tokens, 50 overlap) → noise-filter → embed with `all-mpnet-base-v2` → FAISS index → cosine similarity search → Claude answer with chunk citations. `scripts/query_assistant.py` is a working CLI that can answer questions against the saved index, streaming Claude's response token-by-token and reporting per-query cost. What's still missing: a bulk ingestion script to process the full 600-paper library (currently only the Flynn effect paper is indexed), an evaluation module, and pytest unit tests.

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
- **Missing entry-point scripts**: `scripts/ingest_papers.py` and `scripts/run_evaluation.py` are referenced in `pixi.toml` tasks but don't exist — `pixi run ingest` will fail
- ~~**`scripts/query_assistant.py` missing**~~ — resolved: built with streaming REPL and single-shot modes
- ~~**No vector store implementation**~~ — resolved: `src/retrieval/vector_store.py` built and tested
- **No GitHub repo**: project is local-only, no remote tracking; needs a GitHub repo created and initial push
- **No tests directory**: pytest + pytest-cov configured in pixi.toml but `tests/` doesn't exist; test coverage is 0%
- **Hardcoded batch size**: `32` appears in two separate places in `embedder.py` (lines 105 and 159) — must be kept in sync manually
- **No config management layer**: 17 env vars read ad-hoc; `pydantic-settings` is installed but unused — no validation, no central config object
- **Unused heavy dependencies**: `langchain`, `langchain-community`, `chromadb`, `rich`, `click`, `pandas`, `scikit-learn`, `nltk` all installed but not imported anywhere (`anthropic` is now used)
- **`pdfplumber` installed but unused**: PyMuPDF was chosen but pdfplumber remains as dead weight

## Next Steps (ordered)
1. **Build `scripts/ingest_papers.py`** — walk the full 600-paper PDF library, run parse→chunk→filter→embed pipeline, persist a single FAISS index covering all papers; needs idempotency design (skip already-processed files)
2. **Add Pydantic settings** — centralize all env var reads into one `Settings` class with validation
3. **Implement evaluation** (`src/evaluation/`) — question generation + retrieval/answer quality metrics using the existing `scikit-learn`/`nltk` deps
4. **Write pytest test suite** — unit tests for parser, chunker, embedder, vector store; integration test for full pipeline on known PDF

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
- **Ingestion idempotency**: If `ingest_papers.py` is run twice, will it re-embed all papers or skip already-processed ones? Design not decided.
- **HTML files in library**: Some Zotero exports are `.html` web snapshots, not PDFs — the current parser only handles PDFs; these will be silently skipped or error

## Cost Tracking
- Embedding runs: ~$0 (all local, CPU-only)
- Claude API test calls: <$0.01 (generation layer integrated; costs tracked per query via `cost_usd` field)
- GPU rental: $0
