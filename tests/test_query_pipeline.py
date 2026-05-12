"""Tests for query decomposition retrieval budget (option 1: full top_k per sub-question)."""

from unittest.mock import MagicMock, patch


def _make_chunk(chunk_id: int, score: float) -> dict:
    return {"chunk_id": chunk_id, "score": score, "text": "text", "source": "paper.pdf"}


def _make_store(search_results: list[list[dict]]) -> MagicMock:
    store = MagicMock()
    store.search.side_effect = search_results
    return store


def _make_embedder() -> MagicMock:
    embedder = MagicMock()
    embedder.embed_text.return_value = [0.1] * 768
    return embedder


def _run_decomposed(store, embedder, top_k: int, sub_questions: list[str]) -> list[dict]:
    """Inline the decomposition+dedup logic from query_assistant to test it in isolation."""
    seen: dict[str, dict] = {}
    for sq in sub_questions:
        for chunk in store.search(embedder.embed_text(sq), top_k=top_k):
            cid = str(chunk.get("chunk_id", id(chunk)))
            if cid not in seen or chunk.get("score", 0.0) > seen[cid].get("score", 0.0):
                seen[cid] = chunk
    return sorted(seen.values(), key=lambda c: c.get("score", 0.0), reverse=True)


def test_all_unique_chunks_returned_no_truncation():
    """3 sub-questions × top_k=5 → 15 unique chunks, not truncated to 5 or 10."""
    store = _make_store([
        [_make_chunk(i, 0.9 - i * 0.05) for i in range(5)],
        [_make_chunk(i, 0.9 - i * 0.05) for i in range(5, 10)],
        [_make_chunk(i, 0.9 - i * 0.05) for i in range(10, 15)],
    ])
    results = _run_decomposed(store, _make_embedder(), top_k=5, sub_questions=["q1", "q2", "q3"])
    assert len(results) == 15


def test_dedup_keeps_max_score():
    """Same chunk_id returned by two sub-questions — keep the higher score."""
    store = _make_store([
        [_make_chunk(1, 0.5)],
        [_make_chunk(1, 0.9)],
    ])
    results = _run_decomposed(store, _make_embedder(), top_k=1, sub_questions=["q1", "q2"])
    assert len(results) == 1
    assert results[0]["score"] == 0.9


def test_results_sorted_descending_by_score():
    store = _make_store([
        [_make_chunk(0, 0.3), _make_chunk(1, 0.8)],
        [_make_chunk(2, 0.5), _make_chunk(3, 0.95)],
    ])
    results = _run_decomposed(store, _make_embedder(), top_k=2, sub_questions=["q1", "q2"])
    scores = [c["score"] for c in results]
    assert scores == sorted(scores, reverse=True)


def test_store_called_once_per_sub_question():
    store = _make_store([
        [_make_chunk(0, 0.9)],
        [_make_chunk(1, 0.8)],
        [_make_chunk(2, 0.7)],
    ])
    _run_decomposed(store, _make_embedder(), top_k=1, sub_questions=["q1", "q2", "q3"])
    assert store.search.call_count == 3
