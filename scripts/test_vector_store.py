"""
End-to-end test: parse → chunk → embed → FAISS index → search → save → load → search.

Reads the test PDF path from TEST_PDF_PATH in .env (or the environment).
"""

import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

from src.config import settings
from src.ingestion.pdf_parser import extract_text_from_pdf, extract_metadata
from src.ingestion.chunker import chunk_document
from src.ingestion.noise_filter import filter_chunks
from src.ingestion.embedder import SentenceTransformerEmbedder, embed_chunks
from src.retrieval.vector_store import FAISSVectorStore

PDF_PATH = settings.test_pdf_path
INDEX_PATH = "data/test_index.faiss"
QUERY = "How does working memory relate to intelligence?"
TOP_K = 5

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

print("=== Step 1: Parse PDF ===")
text = extract_text_from_pdf(PDF_PATH)
metadata = extract_metadata(PDF_PATH)
print(f"Extracted {len(text):,} characters")
print(f"Title : {metadata.get('pdf_title', '<unknown>')}")
print(f"Author: {metadata.get('author', '<unknown>')}")

print("\n=== Step 2: Chunk ===")
chunks = chunk_document(text, metadata)
print(f"Chunks (raw): {len(chunks)}")

print("\n=== Step 2b: Filter noise ===")
chunks = filter_chunks(chunks)
print(f"Chunks (filtered): {len(chunks)}")

print("\n=== Step 3: Embed ===")
embedder = SentenceTransformerEmbedder()
print(f"Embedding dim: {embedder.embedding_dim}")
chunks = embed_chunks(chunks, embedder=embedder)
print(f"Embedded {len(chunks)} chunks")

print("\n=== Step 4: Build FAISS index ===")
store = FAISSVectorStore(embedding_dim=embedder.embedding_dim)
store.add_chunks(chunks)
print(f"Index size: {store.size} vectors")

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def run_search(store: FAISSVectorStore, label: str) -> None:
    print(f"\n=== {label} ===")
    print(f"Query: \"{QUERY}\"")
    query_embedding = embedder.embed_text(QUERY)
    results = store.search(query_embedding, top_k=TOP_K)
    for rank, result in enumerate(results, start=1):
        score = result["score"]
        preview = result["text"][:100].replace("\n", " ")
        print(f"\n  [{rank}] score={score:.4f}")
        print(f"       chunk_id={result.get('chunk_id')}  tokens={result.get('token_count')}")
        print(f"       \"{preview}…\"")


run_search(store, "Search (original index)")

# ---------------------------------------------------------------------------
# Save & reload
# ---------------------------------------------------------------------------

print(f"\n=== Step 5: Save index to '{INDEX_PATH}' ===")
os.makedirs("data", exist_ok=True)
store.save(INDEX_PATH)
print(f"Saved. Files on disk:")
print(f"  {INDEX_PATH}")
print(f"  {INDEX_PATH}.meta.json")

print(f"\n=== Step 6: Load index from '{INDEX_PATH}' ===")
loaded_store = FAISSVectorStore.load(INDEX_PATH)
print(f"Loaded index size: {loaded_store.size} vectors")

run_search(loaded_store, "Search (reloaded index)")

print("\nDone.")
