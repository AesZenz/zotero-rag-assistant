"""
End-to-end test of the full RAG generation pipeline.

Steps:
  1. Load the saved FAISS index from data/test_index.faiss
  2. Embed the query using the local sentence-transformer model
  3. Retrieve top-5 chunks from the index
  4. Send query + context to Claude and receive an answer
  5. Print query, retrieved chunks with scores, Claude's answer, token usage, and cost
"""

import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from src.ingestion.embedder import SentenceTransformerEmbedder
from src.retrieval.vector_store import FAISSVectorStore
from src.generation.claude_client import ClaudeGenerator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INDEX_PATH = "data/test_index.faiss"
QUERY = "How does working memory relate to intelligence?"
TOP_K = 5
MAX_TOKENS = int(os.getenv("MAX_TOKENS_PER_RESPONSE", "500"))

# ---------------------------------------------------------------------------
# Step 1: Load index
# ---------------------------------------------------------------------------

print("=" * 60)
print("Step 1: Loading FAISS index")
print("=" * 60)
store = FAISSVectorStore.load(INDEX_PATH)
print(f"  Loaded {store.size} vectors from '{INDEX_PATH}'")

# ---------------------------------------------------------------------------
# Step 2: Embed query
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("Step 2: Embedding query")
print("=" * 60)
embedder = SentenceTransformerEmbedder()
print(f"  Model : {embedder.model_name}")
print(f"  Dim   : {embedder.embedding_dim}")
query_embedding = embedder.embed_text(QUERY)
print(f"  Query : \"{QUERY}\"")

# ---------------------------------------------------------------------------
# Step 3: Retrieve top-k chunks
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print(f"Step 3: Retrieving top-{TOP_K} chunks")
print("=" * 60)
results = store.search(query_embedding, top_k=TOP_K)

for rank, chunk in enumerate(results, start=1):
    score = chunk["score"]
    preview = chunk["text"][:120].replace("\n", " ")
    source = chunk.get("source") or chunk.get("pdf_title") or "Unknown"
    print(f"\n  [{rank}] score={score:.4f}")
    print(f"       source : {source}")
    print(f"       chunk  : {chunk.get('chunk_id')} | tokens: {chunk.get('token_count')}")
    print(f"       text   : \"{preview}…\"")

# ---------------------------------------------------------------------------
# Step 4: Generate answer with Claude
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("Step 4: Generating answer with Claude")
print("=" * 60)
generator = ClaudeGenerator()
print(f"  Model : {generator.model}")
print(f"  Max tokens : {MAX_TOKENS}")
print()

result = generator.generate_answer(QUERY, results, max_tokens=MAX_TOKENS)

# ---------------------------------------------------------------------------
# Step 5: Display results
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("Answer")
print("=" * 60)
print(result["answer"])

print("\n" + "=" * 60)
print("Usage Summary")
print("=" * 60)
print(f"  Model       : {result['model']}")
print(f"  Tokens used : {result['tokens_used']:,}")
print(f"  Cost        : ${result['cost_usd']:.6f}")
print()
