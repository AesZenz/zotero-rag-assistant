"""
Answer quality evaluation for the Zotero RAG Assistant.

Attempts to use the RAGAS library if available; falls back silently to a
Claude-as-judge implementation that scores faithfulness (0–1) by asking
Claude whether every claim in the answer is supported by the provided context.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv

from src.utils.logging import get_logger

load_dotenv()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional RAGAS import
# ---------------------------------------------------------------------------

try:
    from ragas import evaluate as _ragas_evaluate
    from ragas.metrics import answer_relevancy, context_precision, faithfulness as _ragas_faithfulness
    _RAGAS_AVAILABLE = True
    logger.info("RAGAS library available — using RAGAS metrics")
except ImportError:
    _RAGAS_AVAILABLE = False
    logger.info("RAGAS not installed — using Claude-as-judge faithfulness fallback")


# ---------------------------------------------------------------------------
# Claude-as-judge fallback
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """\
You are evaluating whether an AI-generated answer is faithful to the provided context.

Context:
{context}

---

Question: {question}

Answer: {answer}

---

Score the faithfulness of the answer on a scale from 0.0 to 1.0:
  1.0 — every claim in the answer is directly supported by the context above
  0.5 — most claims are supported, but some go beyond what the context states
  0.0 — the answer makes claims that are not present in the context

Respond with only a JSON object containing exactly two keys: "faithfulness" (a float 0.0–1.0) and "reasoning" (a one-sentence explanation of your score). No text before or after the JSON object. Example: {{"faithfulness": 0.85, "reasoning": "Most claims are directly supported by the context, but the effect size mentioned in the answer does not appear in the provided chunks."}}"""


def _score_faithfulness_claude(
    question: str,
    answer: str,
    contexts: list[str],
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Ask Claude to rate answer faithfulness. Returns dict with 'faithfulness' and 'reasoning'."""
    import anthropic # lazy import inside function; only gets imported if the function is actually called 

    context_block = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    prompt = _FAITHFULNESS_PROMPT.format(
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
        logger.warning("Faithfulness raw response: %r", raw)
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        parsed = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return {
            "faithfulness": float(max(0.0, min(1.0, parsed.get("faithfulness", 0.0)))),
            "reasoning": parsed.get("reasoning", ""),
        }
    except Exception as exc:
        logger.warning("Faithfulness scoring failed: %s", exc)
        return {"faithfulness": 0.0, "reasoning": ""}


# ---------------------------------------------------------------------------
# RAGAS path (only called when RAGAS is available)
# ---------------------------------------------------------------------------

def _score_with_ragas(question: str, answer: str, contexts: list[str]) -> dict:
    """Score a single QA pair with RAGAS faithfulness, relevancy, and context precision."""
    try:
        from datasets import Dataset

        dataset = Dataset.from_dict({
            "question": [question],
            "answer":   [answer],
            "contexts": [contexts],
        })
        scores = _ragas_evaluate(
            dataset,
            metrics=[_ragas_faithfulness, answer_relevancy, context_precision],
        )
        return {
            "faithfulness":       float(scores["faithfulness"]),
            "answer_relevancy":   float(scores["answer_relevancy"]),
            "context_precision":  float(scores["context_precision"]),
        }
    except Exception as exc:
        logger.warning("RAGAS scoring failed, returning zeros: %s", exc)
        return {"faithfulness": 0.0, "answer_relevancy": 0.0, "context_precision": 0.0}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_answers(
    eval_questions: list[dict],
    vector_store,
    embedder,
    generator,
    top_k: int = 5,
    api_key: Optional[str] = None,
    judge_model: str = "claude-haiku-4-5-20251001",
) -> list[dict]:
    """Evaluate answer quality for each question in the evaluation set.

    For each question, retrieves top-K chunks, generates an answer via
    ``generator.generate_answer()``, then scores it. If RAGAS is available,
    uses faithfulness + answer_relevancy + context_precision. Otherwise falls
    back to Claude-as-judge faithfulness scoring.

    Args:
        eval_questions: List of eval question dicts (from ``eval_questions.jsonl``).
        vector_store: Loaded ``FAISSVectorStore``.
        embedder: Loaded ``SentenceTransformerEmbedder``.
        generator: A ``ClaudeGenerator`` or ``OllamaClient`` instance.
        top_k: Number of context chunks to retrieve per question.
        api_key: Anthropic API key (required for Claude-as-judge fallback).
            Falls back to ``ANTHROPIC_API_KEY`` env var if not passed.
        judge_model: Claude model to use as judge in fallback mode.

    Returns:
        List of result dicts with keys ``question``, ``answer``,
        ``contexts_used``, ``faithfulness``, and (when RAGAS is available)
        ``answer_relevancy``, ``context_precision``.
    """
    resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    results: list[dict] = []

    for i, q in enumerate(eval_questions, start=1):
        question_text = q["question"]
        logger.info("Evaluating answer %d/%d: %.60s…", i, len(eval_questions), question_text)

        # Retrieve context
        query_embedding = embedder.embed_text(question_text)
        chunks = vector_store.search(query_embedding, top_k=top_k)
        if not chunks:
            logger.warning("No chunks retrieved for: %s", question_text[:80])
            continue

        # Generate answer
        try:
            gen_result = generator.generate_answer(question_text, chunks, max_tokens=500)
            answer = gen_result["answer"]
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc)
            continue

        contexts = [c.get("text", "") for c in chunks]

        if _RAGAS_AVAILABLE:
            scores = _score_with_ragas(question_text, answer, contexts)
        else:
            scores = _score_faithfulness_claude(
                question_text, answer, contexts, resolved_key, judge_model
            )

        results.append({
            "question":      question_text,
            "answer":        answer,
            "contexts_used": len(chunks),
            **scores,
        })

    avg_faith = sum(r.get("faithfulness", 0) for r in results) / max(len(results), 1)
    logger.info(
        "Answer eval complete: %d questions, avg faithfulness=%.3f",
        len(results), avg_faith,
    )
    return results
