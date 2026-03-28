# Zotero RAG Assistant

RAG system for querying scientific papers using Claude API and local embeddings.

## Quick Start

### 1. Setup
```bash
# Copy environment template
cp .env.example .env

# Edit with your API key and PDF path
nano .env
```

### 2. Install
```bash
pixi install
pixi run setup
```

### 3. Ingest Papers (~5-10 min for 600 papers)
```bash
pixi run ingest
```

### 4. Query
```bash
pixi run query
```

## Project Structure
```
zotero-rag-assistant/
├── pixi.toml          # Dependencies
├── .env               # Your secrets (gitignored)
├── data/              # PDFs, embeddings
├── src/               # Core code
│   ├── ingestion/     # PDF → embeddings
│   ├── retrieval/     # Vector search
│   ├── generation/    # Claude API
│   └── evaluation/    # Testing
├── scripts/           # CLI tools
└── notebooks/         # Jupyter analysis
```

## Cost Estimates
- **Embedding:** FREE (local CPU, ~10 min)
- **Query:** ~$0.01-0.02 per question (Claude Sonnet 4.5)

## Configuration (.env)
```bash
ANTHROPIC_API_KEY=your-key-here
CLAUDE_MODEL=claude-sonnet-4-20250514
PDF_LIBRARY_PATH=/path/to/zotero/folder
CHUNK_SIZE=512
TOP_K_CHUNKS=5
```

## How It Works
1. Extract text from PDFs
2. Split into chunks with overlap
3. Generate embeddings (sentence-transformers)
4. Store in FAISS vector database
5. At query time: embed question → find similar chunks → send to Claude

## Security
- `.gitignore` excludes `.env`, PDFs, and all sensitive data
- Never commit your API key
- PDFs stay local only

## Development
```bash
pixi run format    # Black formatting
pixi run lint      # Ruff linting
pixi run test      # Pytest
pixi run notebook  # Jupyter Lab
```

## Troubleshooting
**Slow embedding:** Normal on CPU (5-10 min), only runs once
**API errors:** Check key validity and credits
**Memory issues:** Reduce batch size in embedder.py

## Next Steps (Phase 2)
- Compare embedding models
- Add reranking
- Fine-tune Llama
- Build web UI
