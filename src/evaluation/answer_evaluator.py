"""
Answer quality evaluation for the Zotero RAG Assistant.

Claude-as-judge: scores faithfulness (are all claims grounded in the context?)
and answer relevancy (does the answer address the question?) in a single LLM call.
"""

from __future__ import annotations

import json
from typing import Optional

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


_SCORE_PROMPT = """\
You are evaluating an AI-generated answer on two dimensions.

Context:
{context}

---

Question: {question}

Answer: {answer}

---

Score on two dimensions (0.0–1.0 each):

faithfulness — every claim in the answer is directly supported by the context above
  1.0 — every claim is supported
  0.5 — most claims are supported, but some go beyond what the context states
  0.0 — claims are not present in the context

answer_relevancy — the answer directly addresses the question
  1.0 — the answer fully and directly addresses the question
  0.5 — the answer partially addresses the question
  0.0 — the answer does not address the question

Respond with only a JSON object with exactly three keys: "faithfulness" (float 0.0–1.0), "answer_relevancy" (float 0.0–1.0), and "reasoning" (one sentence). No text before or after the JSON object. Example: {{"faithfulness": 0.85, "answer_relevancy": 0.9, "reasoning": "Most claims are supported and the answer directly addresses the question."}}"""


def _score_answer_claude(
    question: str,
    answer: str,
    contexts: list[str],
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Score faithfulness and answer relevancy in a single Claude call."""
    import anthropic

    context_block = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    prompt = _SCORE_PROMPT.format(
        context=context_block,
        question=question,
        answer=answer,
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        parsed = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return {
            "faithfulness":     float(max(0.0, min(1.0, parsed.get("faithfulness", 0.0)))),
            "answer_relevancy": float(max(0.0, min(1.0, parsed.get("answer_relevancy", 0.0)))),
            "reasoning":        parsed.get("reasoning", ""),
        }
    except Exception as exc:
        logger.warning("Answer scoring failed: %s", exc)
        return {"faithfulness": 0.0, "answer_relevancy": 0.0, "reasoning": ""}


def evaluate_answers(
    eval_questions: list[dict],
    vector_store,
    embedder,
    generator,
    top_k: int = 5,
    api_key: Optional[str] = None,
    judge_model: str = "claude-haiku-4-5-20251001",
) -> list[dict]:
    """Evaluate answer quality for each question using Claude as judge.

    Retrieves top-K chunks, generates an answer, then scores faithfulness
    and answer relevancy in a single Claude call per question.

    Args:
        eval_questions: List of eval question dicts (from ``eval_questions.jsonl``).
        vector_store: Loaded ``FAISSVectorStore``.
        embedder: Loaded ``SentenceTransformerEmbedder``.
        generator: A ``ClaudeGenerator`` or ``OllamaClient`` instance.
        top_k: Number of context chunks to retrieve per question.
        api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        judge_model: Claude model to use as judge.

    Returns:
        List of result dicts with keys: ``question``, ``answer``,
        ``contexts_used``, ``faithfulness``, ``answer_relevancy``, ``reasoning``.
    """
    resolved_key = api_key or settings.anthropic_api_key
    results: list[dict] = []

    for i, q in enumerate(eval_questions, start=1):
        question_text = q["question"]
        logger.info("Evaluating answer %d/%d: %.60s…", i, len(eval_questions), question_text)

        query_embedding = embedder.embed_text(question_text)
        chunks = vector_store.search(query_embedding, top_k=top_k)
        if not chunks:
            logger.warning("No chunks retrieved for: %s", question_text[:80])
            continue

        try:
            gen_result = generator.generate_answer(question_text, chunks, max_tokens=500)
            answer = gen_result["answer"]
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc)
            continue

        contexts = [c.get("text", "") for c in chunks]
        scores = _score_answer_claude(question_text, answer, contexts, resolved_key, judge_model)

        results.append({
            "question":        question_text,
            "answer":          answer,
            "contexts_used":   len(chunks),
            **scores,
        })

    avg_faith = sum(r.get("faithfulness", 0) for r in results) / max(len(results), 1)
    avg_rel   = sum(r.get("answer_relevancy", 0) for r in results) / max(len(results), 1)
    logger.info(
        "Answer eval complete: %d questions, avg faithfulness=%.3f, avg answer_relevancy=%.3f",
        len(results), avg_faith, avg_rel,
    )
    return results
