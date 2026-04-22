"""Query decomposition: splits a complex research question into sub-questions."""

from __future__ import annotations

import json

from src.utils.logging import get_logger

logger = get_logger(__name__)

_DECOMPOSITION_PROMPT = """\
You are helping retrieve information from a scientific literature database.

Given a complex research question, decompose it into 2-4 specific, self-contained \
sub-questions that together would fully answer the original.

Rules:
- Each sub-question must be answerable independently from a single document passage
- Use specific scientific terminology that would appear in academic papers
- Do not add sub-questions that go beyond what the original question asks
- Prefer fewer, higher-quality sub-questions over many vague ones

Original question: {query}

Respond with only a JSON array of strings and nothing else. No explanation, \
no preamble, no markdown fences. Example:
["sub-question 1", "sub-question 2", "sub-question 3"]"""


def decompose_query(
    query: str,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    max_sub_questions: int = 4,
) -> list[str]:
    """Decompose a complex query into self-contained sub-questions.

    Returns a list of sub-question strings, or [query] on any failure.
    """
    import anthropic

    prompt = _DECOMPOSITION_PROMPT.format(query=query)
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        parsed = json.loads(raw[raw.find("["):raw.rfind("]") + 1])
        sub_questions = [str(q) for q in parsed if str(q).strip()]
        return sub_questions[:max_sub_questions] if sub_questions else [query]
    except Exception as exc:
        logger.warning("Query decomposition failed, using original query: %s", exc)
        return [query]
