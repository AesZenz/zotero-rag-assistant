# Project Status

## Update Log
- 2026-04-24 — Pydantic Settings config layer; dotenv removed from codebase
  - **`src/config.py`** (new): `Settings(BaseSettings)` covering all 23 env vars from `.env.example` plus `EVAL_QUESTIONS_PATH`; singleton `settings = Settings()` reads `.env` directly via Pydantic's `env_file` — no `load_dotenv()` calls required anywhere
  - Replaced all 24 `os.getenv()` calls across 10 files with `settings.<field>` access; `from dotenv import load_dotenv` / `load_dotenv()` removed from every affected file
  - **`src/utils/logging.py`**: `LOG_LEVEL`, `LOG_FILE` → `settings.log_level`, `settings.log_file`
  - **`src/generation/claude_client.py`**: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`
  - **`src/generation/ollama_client.py`**: `OLLAMA_MODEL`
  - **`src/generation/generator.py`**: `GENERATION_BACKEND`
  - **`src/evaluation/ragas_evaluator.py`**: `ANTHROPIC_API_KEY`
  - **`src/evaluation/question_generator.py`**: `ANTHROPIC_API_KEY`
  - **`scripts/run_evaluation.py`**: `QUERY_DECOMPOSITION`, `QUERY_DECOMPOSITION_MODEL`, `EVAL_QUESTIONS_PATH`, `ANTHROPIC_API_KEY`
  - **`scripts/ingest_papers.py`**: `PDF_LIBRARY_PATH`, `CHUNK_SIZE`, `CHUNK_OVERLAP`; `from src.config import settings` placed after the `os.environ["LOG_FILE"]` override so the ingestion-specific log path is picked up at `Settings()` instantiation time
  - **`scripts/test_claude_generation.py`**: `MAX_TOKENS_PER_RESPONSE`
  - **`scripts/query_assistant.py`**: `MAX_TOKENS_PER_RESPONSE`, `QUERY_DECOMPOSITION`, `QUERY_DECOMPOSITION_MODEL`, `ANTHROPIC_API_KEY` ×2, `GENERATION_BACKEND` ×4
  - **`scripts/test_pdf_parser.py`**, **`test_chunker.py`**, **`test_embedder.py`**, **`test_vector_store.py`**: removed `load_dotenv()`; replaced `os.environ["TEST_PDF_PATH"]` (hard key-lookup that would `KeyError` without `load_dotenv`) with `settings.test_pdf_path`
  - Import ordering constraint documented: in any script that overrides `os.environ` before src imports (e.g. `LOG_FILE` in `ingest_papers.py`, `OMP_NUM_THREADS` in `test_vector_store.py`), `from src.config import settings` must come *after* those overrides because `Settings()` reads `os.environ` at instantiation time
- 2026-04-22 — query decomposition, faithfulness reasoning, eval decomposition support
  - **`src/retrieval/query_decomposer.py`** (new): `decompose_query(query, api_key, model, max_sub_questions)` — calls Claude with a decomposition prompt, parses the JSON array response using safe `find("[")` / `rfind("]")` extraction, falls back to `[query]` on any failure; lazy-imports `anthropic`
  - **`src/evaluation/ragas_evaluator.py`**: updated `_FAITHFULNESS_PROMPT` to request a `"reasoning"` field alongside `"faithfulness"`; fixed JSON parsing to use `find("{")` / `rfind("}")` extraction to handle trailing text; `_score_faithfulness_claude` now returns `dict` with `"faithfulness"` and `"reasoning"` instead of a bare float; call site in `evaluate_answers` unpacks the dict directly so both fields land in results
  - **`scripts/query_assistant.py`**: decomposition wired into both single-shot (`run_query`) and interactive REPL — reads `QUERY_DECOMPOSITION` and `QUERY_DECOMPOSITION_MODEL` from env at startup; deduplicates merged chunks by `chunk_id` keeping highest score; caps merged list at `top_k * 2`; logs sub-questions at INFO level
  - **`src/evaluation/retrieval_metrics.py`**: `evaluate_retrieval` accepts new optional params `decompose`, `api_key`, `decomposition_model`; when decompose=True retrieves `math.ceil(top_k / n_sub)` chunks per sub-question, merges and deduplicates, then runs rank-check logic on the merged set; logs active mode at the start of each run
  - **`scripts/run_evaluation.py`**: reads `QUERY_DECOMPOSITION` / `QUERY_DECOMPOSITION_MODEL` at startup; prints mode label before evaluation begins; passes params to `evaluate_retrieval`; adds `"decomposition_enabled"` boolean to results JSONL
  - **`.env` / `.env.example`**: added `QUERY_DECOMPOSITION=false` and `QUERY_DECOMPOSITION_MODEL=claude-haiku-4-5-20251001` under a new `QUERY DECOMPOSITION` section
  - **`pixi.toml`**: `query-ollama` task env table gains `QUERY_DECOMPOSITION = "true"` for local-model testing
  - **`docs/modules/retrieval.rst`**: added `automodule` entry for `src.retrieval.query_decomposer`
  - **Decomposition experiment result**: enabling decomposition produced *worse* retrieval metrics than the baseline. Root cause is the aggressive per-sub-question budget: `math.ceil(top_k / n_sub)` gives each sub-question only ~2 chunks when top_k=5 and n_sub=3, so the correct chunk has far fewer opportunities to surface than in a flat top-5 search. `QUERY_DECOMPOSITION` has been set back to `false`. See tech debt for the recommended fix before re-enabling.
- 2026-04-14 — evaluation pipeline improvements and data tooling
  - **`src/evaluation/question_generator.py`**: fixed `open(..., "w")` overwrite bug — output now writes to a timestamped file (`eval_questions_<timestamp>.jsonl`) instead of unconditionally overwriting `eval_questions.jsonl`; fixed incorrect `-- --n` CLI example in docstring (pixi forwards `--` literally, correct invocation is `pixi run generate-eval-questions --n 50`)
  - **`scripts/run_evaluation.py`**: fixed `-- --full` CLI example in docstring; `_DEFAULT_QUESTIONS` is no longer hardcoded — now resolves via `EVAL_QUESTIONS_PATH` env var → newest `eval_questions_*.jsonl` → `eval_questions.jsonl` fallback; added `import glob` for the dynamic resolution
  - **`scripts/convert_querylog_to_eval.py`** (new): converts `query_log.jsonl` entries into `eval_questions` format by looking up `source_chunk_text` from the FAISS metadata sidecar; uses top retrieved chunk as source; reports any chunks not found in the index; writes to timestamped `eval_questions_from_querylog_<timestamp>.jsonl`; pixi task: `convert-querylog`
  - **`pixi.toml`**: added `convert-querylog` task
  - **`data/eval/eval_questions_combined_golden.jsonl`**: combined auto-generated eval questions (63) with manually-typed golden questions converted from query log (23) into one 84-entry evaluation dataset (data/ is gitignored, lives locally only)
  - **`.env.example`**: added `EVAL_QUESTIONS_PATH` (commented out) with examples for switching between auto-generated, golden, and combined datasets
  - **`docs/usage.rst`**: fixed `-- --n` and `-- --full` CLI examples
  - **`PROJECT_STATUS.md`**: added tech debt note about `convert_querylog_to_eval.py` format coupling
- 2026-04-11 — set up Sphinx documentation
  - **`pixi.toml`**: added `[feature.docs]` feature with `sphinx`, `sphinx-autodoc-typehints`, `shibuya`; added `docs` environment; wired `docs` task (`sphinx-build -b html docs/ docs/_build/html`)
  - **`docs/conf.py`**: project root on `sys.path` for autodoc imports; extensions: `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, `sphinx_autodoc_typehints`; theme: `shibuya`; Napoleon configured for Google-style docstrings
  - **`docs/index.rst`**: toctree with User Guide (usage) and API Reference (ingestion, retrieval, generation, evaluation, utils) sections
  - **`docs/usage.rst`**: hand-written task reference covering all `pixi run` tasks grouped into Ingestion, Querying, Evaluation, and Development sections; env vars and prerequisites documented per task; `query-ollama` explicitly documents that `ollama serve` must be running as a background process in a separate terminal
  - **`docs/modules/`**: one `.rst` per module group with `automodule` directives and `:members:`, `:undoc-members:`, `:show-inheritance:` options
  - **`.gitignore`**: added `docs/_build/` exclusion
  - **`README.md`**: clarified `ollama serve` background process requirement in query section
  - **`src/ingestion/chunker.py`** and **`src/evaluation/retrieval_metrics.py`**: minor RST formatting fixes in docstrings to resolve Sphinx warnings (missing space in inline literal, indented continuation line)
  - Build confirmed clean: `pixi run -e docs docs` produces `docs/_build/html/index.html` with zero warnings
- 2026-04-06 — built evaluation layer (`src/evaluation/`); **not yet tested**
  - **`src/evaluation/question_generator.py`**: `generate_questions_from_chunks(chunks, n_questions, api_key, model)` — randomly samples chunks from `store._metadata`, calls `claude-haiku-4-5-20251001` once per chunk (max_tokens=200) to generate one self-contained research question, saves to `data/eval/eval_questions.jsonl`; CLI with `--n` and `--index-path` flags; pixi task: `generate-eval-questions`
  - **`src/evaluation/retrieval_metrics.py`**: `evaluate_retrieval(eval_questions, vector_store, embedder, top_k)` — embeds each question, searches FAISS, checks if source chunk (matched by `source_file` + `chunk_id`) appears in top-K; computes Precision@K, Recall@K (hit rate), and MRR; no LLM calls, fully deterministic; returns summary dict + per-question detail rows
  - **`src/evaluation/ragas_evaluator.py`**: `evaluate_answers(eval_questions, vector_store, embedder, generator, top_k)` — retrieves chunks, generates answer via `generator.generate_answer()`, scores with RAGAS if installed, otherwise falls back to Claude-as-judge faithfulness scoring (0–1, `claude-haiku-4-5-20251001`, max_tokens=64); RAGAS path also computes answer_relevancy and context_precision
  - **`scripts/run_evaluation.py`**: orchestrator — loads `eval_questions.jsonl`, runs retrieval evaluation, prints summary table; `--full` flag enables answer quality evaluation (incurs LLM cost); saves timestamped results to `data/eval/eval_results_{timestamp}.jsonl`; pixi task: `evaluate`
  - **`pixi.toml`**: added `generate-eval-questions` task; `evaluate` task already existed (unchanged)
  - **Ollama query logging resolved**: root cause was the Ollama streaming timeout — prior to the `(10, None)` fix, the stream was failing before `_log_query` was ever reached; confirmed working correctly after fix
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
- **Bulk ingestion script** (`scripts/ingest_papers.py`): walks PDF library recursively, full parse→chunk→filter→embed→FAISS pipeline, bulk embedding batches, checkpoint every 50 papers, `--resume` flag; confirmed working against full 600-paper library
- **Centralised config** (`src/config.py`): `Settings(BaseSettings)` with 23 typed, validated env vars; singleton `settings` object is the single import point for all configuration; reads `.env` directly — no `os.getenv` or `load_dotenv` calls remain anywhere in the codebase
- **Sphinx documentation** (`docs/`): `pixi run -e docs docs` builds HTML docs to `docs/_build/html/`; autodoc pulls docstrings from all `src/` modules; `usage.rst` documents every pixi task with env vars and prerequisites; shibuya theme; `[feature.docs]` keeps sphinx deps out of the default environment
- **Query log → eval converter** (`scripts/convert_querylog_to_eval.py`): converts `query_log.jsonl` entries into `eval_questions` format by looking up chunk text from the FAISS metadata sidecar; reports any missing chunks; writes timestamped output; pixi task: `convert-querylog`
- **Evaluation layer** (`src/evaluation/`) — built, **not yet tested**:
  - `question_generator.py`: Claude-powered question generation from sampled index chunks → `data/eval/eval_questions.jsonl`
  - `retrieval_metrics.py`: deterministic Precision@K / Recall@K / MRR computation against labelled questions
  - `ragas_evaluator.py`: answer faithfulness scoring via RAGAS (if installed) or Claude-as-judge fallback
  - `scripts/run_evaluation.py`: orchestrator with `--full` flag for optional answer quality evaluation
- **PDF library**: 1.3GB, ~600 psychology/neuroscience/AI papers exported from Zotero (with RDF metadata)

## Current State
All core pipeline components are complete and confirmed working at scale. The full RAG pipeline runs end-to-end: parse PDF → chunk (512 tokens, 50 overlap) → noise-filter → embed with `all-mpnet-base-v2` → FAISS index → cosine similarity search → generation (Claude or local Ollama) with chunk citations. Two local Ollama models are available (`llama3.2:3b`, `phi4-mini`). Query logging writes to `data/query_logs/query_log.jsonl`. Sphinx documentation is set up and builds cleanly. The evaluation pipeline has been improved: question generation now writes timestamped files, the query log can be converted to eval format via `convert-querylog`, and a combined 84-question golden dataset (`eval_questions_combined_golden.jsonl`) has been created. The eval questions path is now configurable via `EVAL_QUESTIONS_PATH`. All environment variables are now managed through a single `Settings(BaseSettings)` class in `src/config.py` — no `os.getenv` calls remain in the codebase. The evaluation layer has been tested end-to-end; the one untested path is the RAGAS branch of `ragas_evaluator.py` (requires the `ragas` package, which is not installed — the Claude-as-judge fallback is what runs and has been confirmed working). What's still missing: pytest unit tests.

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
- **Query decomposition budget too aggressive**: the current `math.ceil(top_k / n_sub)` allocation gives each sub-question only ~2 chunks at the default top_k=5 with 3 sub-questions, which performed *worse* than a flat top-5 search in evaluation. Before re-enabling decomposition for complex queries, either (a) relax the budget to a fixed per-sub allocation (e.g. always retrieve `top_k` per sub-question and deduplicate), or (b) increase the baseline top_k so the total candidate pool matches: 3 sub-questions × 5 chunks = 15 candidates, so compare against `top_k=15` without decomposition to isolate the decomposition benefit from the retrieval budget change. `QUERY_DECOMPOSITION` is currently `false`.
- **Query decomposition retrieval duplicated in REPL**: the decomposition + deduplication block in `scripts/query_assistant.py` is copy-pasted between `run_query()` (single-shot) and the inline REPL loop. The correct fix is to have the REPL call `run_query()` instead of reimplementing retrieval inline, but that requires refactoring the REPL's cost-tracking and streaming logic. Until then, any change to the retrieval block must be applied in both places.
- **`convert_querylog_to_eval.py` format coupling**: the conversion script assumes `query_log.jsonl` uses `filename`/`chunk_index` keys in `retrieved_chunks`, and that these match the FAISS metadata's `source`/`chunk_id` fields. If either the query log format or the metadata schema changes, the script will silently produce wrong output (missing chunks). If either format is ever updated, update the script and re-validate with a test run.
- ~~**PDF parser noise**~~ — resolved: `src/ingestion/noise_filter.py` built and confirmed working; pipeline is now parse→chunk→filter→embed
- ~~**Metadata key mismatch bug**~~ — resolved: `extract_metadata()` now returns `"pdf_title"`
- **RAGAS evaluation path untested** — `ragas_evaluator.py` has two code paths: RAGAS (if the `ragas` package is installed) and Claude-as-judge fallback. Only the fallback has been tested; the RAGAS path has never run
- ~~**`scripts/query_assistant.py` missing**~~ — resolved: built with streaming REPL and single-shot modes
- ~~**No vector store implementation**~~ — resolved: `src/retrieval/vector_store.py` built and tested
- ~~**No GitHub repo**~~ — resolved: pushed to https://github.com/AesZenz/zotero-rag-assistant
- **No tests directory**: pytest + pytest-cov configured in pixi.toml but `tests/` doesn't exist; test coverage is 0%
- **Hardcoded batch size**: `32` appears in two separate places in `embedder.py` (lines 105 and 159) — must be kept in sync manually
- ~~**No config management layer**~~ — resolved: `src/config.py` centralises all env vars into a `Settings(BaseSettings)` class; no `os.getenv` calls remain
- **Unused heavy dependencies**: `langchain`, `langchain-community`, `chromadb`, `rich`, `click`, `pandas`, `scikit-learn`, `nltk` all installed but not imported anywhere (`anthropic` is now used)
- **`pdfplumber` installed but unused**: PyMuPDF was chosen but pdfplumber remains as dead weight

## Next Steps (ordered)
1. **Write pytest test suite** — unit tests for parser, chunker, embedder, vector store; integration test for full pipeline on known PDF
2. **Install and test RAGAS** — add `ragas` to `pixi.toml` pypi-dependencies, run `pixi run evaluate --full`, verify the RAGAS metrics path in `ragas_evaluator.py` produces valid scores

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
