# Zotero RAG Assistant

A retrieval-augmented generation (RAG) system for querying a personal Zotero research library (~600 papers, psychology / neuroscience / AI) using local embeddings and the Claude API. Built as a learning project to understand RAG architecture from the ground up — each component was implemented independently before any orchestration layer was introduced.

---

## What It Does

Ask a question in natural language → the system retrieves the most relevant passages from your PDF library → Claude answers using only that context, with numbered citations back to the source chunks.

```
$ python scripts/query_assistant.py "What does the literature say about working memory and fluid intelligence?"

[streaming answer with chunk citations]
Cost: $0.012 | Tokens: 410
```

---

## Architecture

```
PDF library
    │
    ▼
pdf_parser.py       PyMuPDF text + metadata extraction
    │
    ▼
chunker.py          512-token sliding window (50-token overlap), tiktoken cl100k_base
    │
    ▼
noise_filter.py     Drops reference lists, affiliations, funding blocks (~45% of chunks)
    │
    ▼
embedder.py         all-mpnet-base-v2 (768-dim), CPU-only, batch inference
    │
    ▼
vector_store.py     FAISS IndexFlatIP, L2-normalised cosine similarity
    │
    ▼
claude_client.py    RAG prompt → Claude API → streamed answer + cost tracking
```

All layers are independently testable. The pipeline was built one component at a time, with each stage confirmed working before moving to the next.

---

## Key Design Decisions

**Token-based chunking over character-based** — tiktoken gives token-accurate splits that respect LLM context limits. Chunk size (512) and overlap (50) are environment-configurable, not hardcoded.

**Noise filtering as a separate module** — reference lists, author affiliations, and funding acknowledgments degrade retrieval quality without contributing semantic signal. Filtering post-chunking but pre-embedding keeps the parser and chunker concerns clean. Confirmed ~45% chunk drop rate on a test paper, with all drops verified as legitimate noise.

**`all-mpnet-base-v2` over MiniLM variants** — higher quality embeddings at the cost of slightly slower inference; acceptable tradeoff for a CPU-only setup querying a static library.

**FAISS `IndexFlatIP` over IVF clustering** — exact cosine similarity is fast enough at ~30K vectors (600 papers × ~50 chunks). IVF approximate search would add complexity with no meaningful latency benefit at this scale.

**Local embeddings only** — zero embedding cost. The only API spend is at query time (Claude generation), which is tracked per-query and per-session.

**`all-mpnet-base-v2` already produces unit-norm vectors** — `faiss.normalize_L2()` is called at both write and query time anyway as a safety net, since cosine similarity via inner product requires unit vectors.

---

## What's Built

| Component | File | Status |
|---|---|---|
| PDF parser | `src/ingestion/pdf_parser.py` | ✅ complete |
| Text chunker | `src/ingestion/chunker.py` | ✅ complete |
| Noise filter | `src/ingestion/noise_filter.py` | ✅ complete |
| Embedder | `src/ingestion/embedder.py` | ✅ complete |
| FAISS vector store | `src/retrieval/vector_store.py` | ✅ complete |
| Claude generation layer | `src/generation/claude_client.py` | ✅ complete |
| Query CLI | `scripts/query_assistant.py` | ✅ complete |
| Bulk ingestion script | `scripts/ingest_papers.py` | 🔲 next |
| Evaluation module | `src/evaluation/` | 🔲 planned |
| Pytest test suite | `tests/` | 🔲 planned |

---

## Setup

### Prerequisites
- [pixi](https://prefix.dev/) for environment management
- Anthropic API key
- A directory of PDFs (Zotero export or otherwise)

### Install
```bash
cp .env.example .env
# edit .env with your API key and PDF path
pixi install
```

### Ingest a single paper (current)
```bash
OMP_NUM_THREADS=1 PYTHONPATH=. python scripts/test_vector_store.py
```
> Note: `OMP_NUM_THREADS=1` is required on Intel Mac to prevent a PyTorch 2.2.x OpenMP threading bug.

### Query
```bash
# Single question
PYTHONPATH=. python scripts/query_assistant.py "your question here"

# Interactive REPL
PYTHONPATH=. python scripts/query_assistant.py

# Options
PYTHONPATH=. python scripts/query_assistant.py --top-k 8 --max-tokens 600 --verbose "your question"
```

---

## Configuration

```bash
# .env
ANTHROPIC_API_KEY=your-key-here
CLAUDE_MODEL=claude-sonnet-4-6
PDF_LIBRARY_PATH=/path/to/zotero/folder
CHUNK_SIZE=512
CHUNK_OVERLAP=50
TOP_K_CHUNKS=5
MAX_TOKENS_PER_RESPONSE=500
USE_LOCAL_EMBEDDINGS=true
```

---

## Cost

| Operation | Cost |
|---|---|
| Embedding (full library) | ~$0 — local CPU only |
| Query (Claude Sonnet) | ~$0.01–0.02 per question |
| GPU | $0 — not required for inference |

---

## Planned: Phase 2

- **Bulk ingestion** (`scripts/ingest_papers.py`) — idempotent pipeline over the full 600-paper library
- **Evaluation layer** — retrieval precision/recall + answer faithfulness metrics (RAGAS)
- **Pydantic settings** — centralize 17 env vars into a validated `Settings` class
- **Reranking** — cross-encoder reranking post-retrieval for higher precision
- **Zotero RDF metadata** — enrich chunk metadata with Zotero tags, collections, and notes
- **Fine-tuning** — domain-adapted Llama model via cloud GPU rental

---

## Known Limitations

- `pixi run ingest` currently fails — `scripts/ingest_papers.py` not yet built
- Only one paper indexed so far (Flynn effect meta-analysis used for testing)
- HTML web snapshots in Zotero exports are silently skipped (PDF parser only)
- No pytest suite yet — testing is currently ad-hoc smoke scripts per component
