import os
import time
from dotenv import load_dotenv
from src.ingestion.pdf_parser import extract_text_from_pdf, extract_metadata
from src.ingestion.chunker import chunk_document
from src.ingestion.embedder import embed_chunks, SentenceTransformerEmbedder

load_dotenv()
PDF_PATH = os.environ["TEST_PDF_PATH"]

# --- Extract ---
text = extract_text_from_pdf(PDF_PATH)
metadata = extract_metadata(PDF_PATH)

# --- Chunk ---
chunks = chunk_document(text, metadata)
print(f"Chunks to embed : {len(chunks)}")

# --- Embed ---
embedder = SentenceTransformerEmbedder()
print(f"Embedding dim   : {embedder.embedding_dim}")

t0 = time.perf_counter()
embed_chunks(chunks, embedder=embedder)
elapsed = time.perf_counter() - t0

# --- Report ---
first_emb = chunks[0]["embedding"]
print(f"\n=== Embedding results ===")
print(f"Chunks embedded : {len(chunks)}")
print(f"Embedding dim   : {len(first_emb)}")
print(f"Time taken      : {elapsed:.2f}s")
print(f"\nFirst chunk – first 10 values:")
print([round(v, 6) for v in first_emb[:10]])
