"""
Retrieval evaluation metrics for the Zotero RAG Assistant.

For each question in the evaluation set, embeds the question, searches the
FAISS index, and checks whether the source chunk appears in the top-K results.

Computed metrics (all averaged over questions):
- Precision@K  = 1/K  if the source chunk is found in top-K, else 0
- Recall@K     = 1.0  if the source chunk is found in top-K, else 0
  (equivalent to Hit Rate@K for a single relevant document per question)
- MRR          = 1/rank if found, else 0  (Mean Reciprocal Rank)

No LLM calls — fully deterministic.
"""

from __future__ import annotations

from src.utils.logging import get_logger

logger = get_logger(__name__)


def evaluate_retrieval(
    eval_questions: list[dict],
    vector_store,
    embedder,
    top_k: int = 5,
) -> dict:
    """Evaluate retrieval quality against labelled evaluation questions.

    Args:
        eval_questions: List of dicts produced by ``generate_questions_from_chunks``.
            Each dict must have keys ``question``, ``source_filename``,
            ``chunk_index``.
        vector_store: A loaded ``FAISSVectorStore`` instance.
        embedder: A loaded ``SentenceTransformerEmbedder`` instance.
        top_k: Number of results to retrieve per question.

    Returns:
        Dict with keys:

        - ``precision_at_k`` (float): Mean precision@K.
        - ``recall_at_k`` (float): Mean recall@K (= hit rate@K).
        - ``mrr`` (float): Mean reciprocal rank.
        - ``top_k`` (int): K value used.
        - ``n_questions`` (int): Total questions evaluated.
        - ``n_found`` (int): Questions where the source chunk was in top-K.
        - ``per_question`` (list[dict]): Per-question detail rows.
    """
    per_question: list[dict] = []

    for q in eval_questions:
        question_text  = q["question"]
        source_filename = q["source_filename"]
        chunk_index     = q["chunk_index"]

        query_embedding = embedder.embed_text(question_text)
        results = vector_store.search(query_embedding, top_k=top_k)

        found_rank: int | None = None
        for rank, result in enumerate(results, start=1):
            # Match on source_file (filename); fall back to pdf_title/source
            result_filename = (
                result.get("source_file")
                or result.get("pdf_title")
                or result.get("source")
                or ""
            )
            if result_filename == source_filename and result.get("chunk_id") == chunk_index:
                found_rank = rank
                break

        found            = found_rank is not None
        precision_at_k   = (1 / top_k) if found else 0.0
        recall_at_k      = 1.0          if found else 0.0
        reciprocal_rank  = (1 / found_rank) if found else 0.0

        per_question.append({
            "question":        question_text,
            "source_filename": source_filename,
            "chunk_index":     chunk_index,
            "found":           found,
            "rank":            found_rank,
            "precision_at_k":  precision_at_k,
            "recall_at_k":     recall_at_k,
            "reciprocal_rank": reciprocal_rank,
        })

        logger.debug(
            "Q: %.60s… | found=%s rank=%s",
            question_text, found, found_rank,
        )

    n = len(per_question)
    if n == 0:
        return {
            "precision_at_k": 0.0,
            "recall_at_k":    0.0,
            "mrr":            0.0,
            "top_k":          top_k,
            "n_questions":    0,
            "n_found":        0,
            "per_question":   [],
        }

    precision_at_k = sum(r["precision_at_k"]  for r in per_question) / n
    recall_at_k    = sum(r["recall_at_k"]      for r in per_question) / n
    mrr            = sum(r["reciprocal_rank"]  for r in per_question) / n
    n_found        = sum(1 for r in per_question if r["found"])

    logger.info(
        "Retrieval eval complete: P@%d=%.3f  R@%d=%.3f  MRR=%.3f  (%d/%d found)",
        top_k, precision_at_k,
        top_k, recall_at_k,
        mrr, n_found, n,
    )

    return {
        "precision_at_k": precision_at_k,
        "recall_at_k":    recall_at_k,
        "mrr":            mrr,
        "top_k":          top_k,
        "n_questions":    n,
        "n_found":        n_found,
        "per_question":   per_question,
    }
