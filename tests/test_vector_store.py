import copy

import numpy as np
import pytest

from src.retrieval.vector_store import FAISSVectorStore


def _make_chunks_with_embeddings(sample_chunks, sample_vectors):
    chunks = []
    for i, chunk in enumerate(sample_chunks):
        c = dict(chunk)
        c["embedding"] = sample_vectors[i].tolist()
        chunks.append(c)
    return chunks


def test_add_and_search_returns_correct_chunk(sample_chunks, sample_vectors):
    store = FAISSVectorStore(embedding_dim=768)
    chunks = _make_chunks_with_embeddings(sample_chunks, sample_vectors)
    store.add_chunks(chunks)

    query = sample_vectors[0].tolist()
    results = store.search(query, top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == sample_chunks[0]["chunk_id"]


def test_search_respects_top_k(sample_chunks, sample_vectors):
    store = FAISSVectorStore(embedding_dim=768)
    chunks = _make_chunks_with_embeddings(sample_chunks, sample_vectors)
    store.add_chunks(chunks)

    for k in (1, 2, 3):
        results = store.search(sample_vectors[0].tolist(), top_k=k)
        assert len(results) == k


def test_search_scores_are_descending(sample_chunks, sample_vectors):
    store = FAISSVectorStore(embedding_dim=768)
    chunks = _make_chunks_with_embeddings(sample_chunks, sample_vectors)
    store.add_chunks(chunks)

    results = store.search(sample_vectors[0].tolist(), top_k=4)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_save_load_round_trip(sample_chunks, sample_vectors, tmp_index_dir):
    store = FAISSVectorStore(embedding_dim=768)
    chunks = _make_chunks_with_embeddings(sample_chunks, sample_vectors)
    store.add_chunks(chunks)

    index_path = str(tmp_index_dir)
    store.save(index_path)

    loaded = FAISSVectorStore.load(index_path)
    results = loaded.search(sample_vectors[1].tolist(), top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == sample_chunks[1]["chunk_id"]


def test_dimension_mismatch_raises(sample_chunks):
    store = FAISSVectorStore(embedding_dim=768)
    bad_chunk = dict(sample_chunks[0])
    bad_chunk["embedding"] = [0.1] * 5

    with pytest.raises(ValueError, match="dim"):
        store.add_chunks([bad_chunk])


def test_search_on_empty_index_raises():
    store = FAISSVectorStore(embedding_dim=768)
    query = [0.0] * 768
    with pytest.raises(ValueError, match="empty"):
        store.search(query)


def test_save_empty_index_raises(tmp_index_dir):
    store = FAISSVectorStore(embedding_dim=768)
    with pytest.raises(RuntimeError):
        store.save(str(tmp_index_dir))


def test_load_missing_file_raises(tmp_index_dir):
    with pytest.raises(FileNotFoundError):
        FAISSVectorStore.load(str(tmp_index_dir / "nonexistent"))


def test_embedding_not_stored_in_metadata(sample_chunks, sample_vectors):
    store = FAISSVectorStore(embedding_dim=768)
    chunks = _make_chunks_with_embeddings(sample_chunks, sample_vectors)
    store.add_chunks(chunks)

    results = store.search(sample_vectors[0].tolist(), top_k=1)
    assert "embedding" not in results[0]
