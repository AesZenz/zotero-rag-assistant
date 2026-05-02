from pathlib import Path
from unittest.mock import MagicMock, patch

import faiss
import numpy as np
import pytest

DIM = 768


class _DeterministicEmbedder:
    """Deterministic mock embedder — avoids loading the real model."""

    def __init__(self):
        self._rng = np.random.default_rng(seed=7)

    def embed_batch(self, texts):
        vecs = self._rng.random((len(texts), DIM)).astype(np.float32)
        faiss.normalize_L2(vecs)
        return [v.tolist() for v in vecs]


@pytest.mark.integration
def test_full_pipeline_round_trip(sample_pdf_path):
    from src.ingestion.chunker import chunk_document
    from src.ingestion.embedder import embed_chunks
    from src.ingestion.noise_filter import filter_chunks
    from src.ingestion.pdf_parser import extract_metadata, extract_text_from_pdf
    from src.retrieval.vector_store import FAISSVectorStore

    # 1. Parse
    text = extract_text_from_pdf(str(sample_pdf_path))
    metadata = extract_metadata(str(sample_pdf_path))
    assert text, "extracted text should be non-empty"

    # 2. Chunk
    chunks = chunk_document(text, metadata, chunk_size=64, overlap=8)
    assert len(chunks) > 0

    # 3. Add source field (pipeline step that would normally happen during ingestion)
    source_filename = Path(sample_pdf_path).name
    for chunk in chunks:
        chunk["source"] = source_filename

    # 4. Noise filter
    chunks = filter_chunks(chunks)
    assert len(chunks) > 0

    # 5. Embed with mock (no real model load)
    embedder = _DeterministicEmbedder()
    with patch("sentence_transformers.SentenceTransformer"):
        embed_chunks(chunks, embedder)

    assert all("embedding" in c for c in chunks)

    # 6. Store
    store = FAISSVectorStore(embedding_dim=DIM)
    store.add_chunks(chunks)
    assert store.size == len(chunks)

    # 7. Search with first chunk's embedding → should retrieve that chunk
    query_vec = chunks[0]["embedding"]
    results = store.search(query_vec, top_k=1)

    assert len(results) == 1
    assert results[0]["source"] == source_filename
