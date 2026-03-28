"""
Claude API client for the generation layer of the Zotero RAG Assistant.

Wraps the Anthropic Python SDK (Software Development Kit) to:
- Build structured prompts from retrieved context chunks
- Call Claude and return the answer with usage/cost metadata
- Support streaming for interactive CLI use
"""

from __future__ import annotations

import os
from typing import Generator, Optional

import anthropic
from dotenv import load_dotenv

from src.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pricing table  (input $/1M tokens, output $/1M tokens)
# Keys are model-ID prefixes; first match wins 
# (= loop breaks on first hit => order important).
# ---------------------------------------------------------------------------
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),   # catches claude-sonnet-4-20250514 etc.
    "claude-haiku-4": (1.0, 5.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-sonnet": (3.0, 15.0),
    "claude-3-haiku": (0.25, 1.25),
}

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a research assistant helping a user find information from their personal document library.

Answer the user's question based ONLY on the provided context chunks. Follow these rules:
1. Use information exclusively from the provided context — do not draw on external knowledge.
2. Cite the source chunks you used by their number in square brackets, e.g. [1], [2].
3. If the context does not contain enough information to answer the question, respond with:
   "I don't have enough information in the provided context to answer this question."
4. Be clear and concise — avoid unnecessary padding.
5. If multiple chunks support the same point, cite all relevant ones."""

_USER_TEMPLATE = """\
Here are the relevant context chunks from your document library:

{context}

---

Question: {query}

Please answer based only on the context above, citing which chunks ([1], [2], etc.) you used."""


class ClaudeGenerator:
    """Generate answers using the Claude API with RAG context.

    Args:
        api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        model: Claude model ID. Falls back to ``CLAUDE_MODEL`` env var, then
            ``claude-sonnet-4-6``.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY in .env or pass it explicitly."
            )

        self.model: str = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self._client = anthropic.Anthropic(api_key=resolved_key)
        logger.info("ClaudeGenerator initialised (model=%s)", self.model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD from token counts.

        Args:
            input_tokens: Number of input (prompt) tokens.
            output_tokens: Number of output (completion) tokens.

        Returns:
            Estimated cost in USD.
        """
        input_rate, output_rate = 3.0, 15.0  # default: Sonnet-level pricing
        for prefix, rates in _PRICING.items():
            if self.model.startswith(prefix):
                input_rate, output_rate = rates
                break

        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    def _build_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks as numbered, source-annotated context.

        Args:
            chunks: List of chunk dicts; each should have a ``text`` field and
                optionally ``source`` / ``pdf_title`` and ``score`` fields.

        Returns:
            Multi-line string ready to embed in the prompt.
        """
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            text = chunk.get("text", "").strip() 
            # strip() = cosmetic cleanup to remove spaces, newlines and tabs from text 
            source = chunk.get("source") or chunk.get("pdf_title") or "Unknown source"
            score = chunk.get("score")
            score_str = f" (relevance: {score:.3f})" if score is not None else ""
            parts.append(f"[{i}] Source: {source}{score_str}\n{text}")
        return "\n\n".join(parts)
        # .join(parts) concatenates all items in parts and separates them by two newlines
    def _build_messages(self, query: str, context_chunks: list[dict]) -> list[dict]:
        context = self._build_context(context_chunks)
        user_content = _USER_TEMPLATE.format(context=context, query=query)
        return [{"role": "user", "content": user_content}]

    # ------------------------------------------------------------------
    # Public API — non-streaming
    # ------------------------------------------------------------------

    def generate_answer(
        self,
        query: str,
        context_chunks: list[dict],
        max_tokens: int = 500,
    ) -> dict:
        """Generate a complete answer from Claude synchronously.

        Builds a prompt from ``query`` and ``context_chunks``, calls the
        Messages API, and returns the answer together with usage metadata.

        Args:
            query: The user's question.
            context_chunks: Retrieved chunks; each dict must have at least a
                ``text`` key. Optional keys ``source``/``pdf_title`` and
                ``score`` are used to annotate the context.
            max_tokens: Maximum number of tokens in Claude's response.

        Returns:
            A dict with the following keys:

            - ``answer`` (str): Claude's text response.
            - ``model`` (str): The model ID used.
            - ``tokens_used`` (int): Total tokens consumed (input + output).
            - ``cost_usd`` (float): Estimated cost in USD.

        Raises:
            anthropic.RateLimitError: When the API rate limit is hit.
            anthropic.BadRequestError: On malformed requests.
            anthropic.APIError: On other API-side failures.
            anthropic.APIConnectionError: On network failures.
        """
        if not context_chunks:
            logger.warning("generate_answer called with empty context_chunks")

        messages = self._build_messages(query, context_chunks)

        logger.debug(
            "Calling Claude (model=%s, max_tokens=%d, chunks=%d)",
            self.model,
            max_tokens,
            len(context_chunks),
        )

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )
        except anthropic.RateLimitError:
            logger.error("Rate-limited by Anthropic API — back off and retry")
            raise
        except anthropic.BadRequestError as exc:
            logger.error("Bad request to Claude API: %s", exc)
            raise
        except anthropic.APIConnectionError as exc:
            logger.error("Network error reaching Claude API: %s", exc)
            raise
        except anthropic.APIError as exc:
            logger.error("Claude API error (status=%s): %s", exc.status_code, exc)
            raise

        answer = next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        logger.info(
            "Answer generated: %d input + %d output tokens, cost=$%.6f",
            input_tokens,
            output_tokens,
            cost,
        )

        return {
            "answer": answer,
            "model": self.model,
            "tokens_used": input_tokens + output_tokens,
            "cost_usd": cost,
        }

    # ------------------------------------------------------------------
    # Public API — streaming
    # ------------------------------------------------------------------

    def stream_answer(
        self,
        query: str,
        context_chunks: list[dict],
        max_tokens: int = 500,
    ):
        """Return a streaming context manager for real-time answer display.

        Intended for interactive CLI use. Wrap with a ``with`` statement and
        iterate over ``stream.text_stream`` to print tokens as they arrive,
        then call ``stream.get_final_message()`` to retrieve usage stats.

        Example::

            with generator.stream_answer(query, chunks) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
            cost = generator._calculate_cost(input_tokens, output_tokens)

        Args:
            query: The user's question.
            context_chunks: Retrieved chunks.
            max_tokens: Maximum tokens in the response.

        Returns:
            An ``anthropic.MessageStream`` context manager.
        """
        messages = self._build_messages(query, context_chunks)
        return self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
