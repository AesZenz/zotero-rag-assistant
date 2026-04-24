"""
Ollama HTTP client for the generation layer of the Zotero RAG Assistant.

Mirrors ClaudeGenerator's public interface exactly so query_assistant.py
can swap backends without any conditional logic:

    generate_answer(query, context_chunks, max_tokens) → dict
    stream_answer(query, context_chunks, max_tokens)   → context manager

Calls Ollama's OpenAI-compatible endpoint at http://localhost:11434/v1
using the standard ``requests`` library — no additional dependencies needed.
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

import requests

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

_OLLAMA_BASE = "http://localhost:11434"
_OLLAMA_V1   = f"{_OLLAMA_BASE}/v1"

# Reuse the same prompt templates as the Claude client so answers are
# comparable regardless of which backend is active.
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


# ---------------------------------------------------------------------------
# Streaming helpers — mirror the shape of anthropic.MessageStream so that
# query_assistant.py can use either client with identical code.
# ---------------------------------------------------------------------------

class _Usage:
    """Holds token counts in the same attribute shape as anthropic's Usage."""

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FinalMessage:
    """Returned by _OllamaStream.get_final_message(), mirrors anthropic's Message."""

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.usage = _Usage(input_tokens, output_tokens)


class _OllamaStream:
    """Context manager that wraps a streaming Ollama HTTP response.

    Exposes the same interface as ``anthropic.MessageStream`` so that
    query_assistant.py needs no conditional logic:

        with generator.stream_answer(...) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            final = stream.get_final_message()
        in_tok  = final.usage.input_tokens
        out_tok = final.usage.output_tokens
    """

    def __init__(self, response: requests.Response) -> None:
        self._response = response
        self._input_tokens  = 0
        self._output_tokens = 0

    def __enter__(self) -> "_OllamaStream":
        return self

    def __exit__(self, *args: object) -> None:
        self._response.close()

    @property
    def text_stream(self) -> Iterator[str]:
        """Yield text tokens as they arrive from Ollama."""
        for raw_line in self._response.iter_lines():
            if not raw_line:
                continue

            # SSE format: lines are prefixed with "data: "
            line: str = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
            if line == "[DONE]":
                break

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            # The final usage chunk (with stream_options include_usage=true)
            # has an empty choices list and a populated usage field.
            usage = chunk.get("usage")
            if usage:
                self._input_tokens  = usage.get("prompt_tokens", 0)
                self._output_tokens = usage.get("completion_tokens", 0)

            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                text  = delta.get("content") or ""
                if text:
                    yield text

    def get_final_message(self) -> _FinalMessage:
        """Return usage statistics after the stream has been consumed."""
        return _FinalMessage(self._input_tokens, self._output_tokens)


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------

class OllamaClient:
    """Generate answers using a local Ollama model with RAG context.

    Mirrors ``ClaudeGenerator``'s public interface exactly:
    - ``generate_answer(query, context_chunks, max_tokens)`` → dict
    - ``stream_answer(query, context_chunks, max_tokens)``   → context manager
    - ``_calculate_cost(input_tokens, output_tokens)``       → float (always 0.0)
    - ``model``                                              → str attribute

    Args:
        model: Ollama model tag. Falls back to ``OLLAMA_MODEL`` env var,
            then ``phi4-mini``.
        base_url: Ollama server base URL (default: http://localhost:11434).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model: str = model or settings.ollama_model
        self._base = (base_url or _OLLAMA_BASE).rstrip("/")
        self._v1   = f"{self._base}/v1"
        logger.info("OllamaClient initialised (model=%s, base=%s)", self.model, self._base)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Always returns 0.0 — local inference is free."""
        return 0.0

    def _build_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks as numbered, source-annotated context."""
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            text   = chunk.get("text", "").strip()
            source = chunk.get("source") or chunk.get("pdf_title") or "Unknown source"
            score  = chunk.get("score")
            score_str = f" (relevance: {score:.3f})" if score is not None else ""
            parts.append(f"[{i}] Source: {source}{score_str}\n{text}")
        return "\n\n".join(parts)

    def _build_messages(self, query: str, context_chunks: list[dict]) -> list[dict]:
        context = self._build_context(context_chunks)
        user_content = _USER_TEMPLATE.format(context=context, query=query)
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Return True if Ollama is reachable, False otherwise.

        Hits ``GET /api/tags`` — the lightest endpoint available.
        Used by ``get_generator()`` to give a clear error before any
        query attempt if the user forgot to start Ollama.
        """
        try:
            resp = requests.get(f"{self._base}/api/tags", timeout=3)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False
        except requests.Timeout:
            return False

    # ------------------------------------------------------------------
    # Public API — non-streaming
    # ------------------------------------------------------------------

    def generate_answer(
        self,
        query: str,
        context_chunks: list[dict],
        max_tokens: int = 500,
    ) -> dict:
        """Generate a complete answer from Ollama synchronously.

        Args:
            query: The user's question.
            context_chunks: Retrieved chunks; each dict must have at least a
                ``text`` key. Optional keys ``source``/``pdf_title`` and
                ``score`` are used to annotate the context.
            max_tokens: Maximum number of tokens in the model's response.

        Returns:
            A dict with the following keys:

            - ``answer`` (str): The model's text response.
            - ``model`` (str): The model tag used.
            - ``tokens_used`` (int): Total tokens consumed (input + output),
              or 0 if Ollama did not report usage.
            - ``cost_usd`` (float): Always 0.0 for local inference.

        Raises:
            RuntimeError: If Ollama returns a non-200 status or a network
                error occurs.
        """
        if not context_chunks:
            logger.warning("generate_answer called with empty context_chunks")

        messages = self._build_messages(query, context_chunks)

        logger.debug(
            "Calling Ollama (model=%s, max_tokens=%d, chunks=%d)",
            self.model, max_tokens, len(context_chunks),
        )

        payload = {
            "model":      self.model,
            "messages":   messages,
            "max_tokens": max_tokens,
            "stream":     False,
        }

        try:
            resp = requests.post(
                f"{self._v1}/chat/completions",
                json=payload,
                timeout=(10, None),  # 10 s to connect; no read timeout (CPU inference is slow)
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base}. "
                "Make sure Ollama is running: ollama serve"
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base} (connection timed out). "
                "Make sure Ollama is running: ollama serve"
            ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        usage  = data.get("usage", {})
        input_tokens  = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        logger.info(
            "Answer generated: %d input + %d output tokens (local, free)",
            input_tokens, output_tokens,
        )

        return {
            "answer":      answer,
            "model":       self.model,
            "tokens_used": input_tokens + output_tokens,
            "cost_usd":    0.0,
        }

    # ------------------------------------------------------------------
    # Public API — streaming
    # ------------------------------------------------------------------

    def stream_answer(
        self,
        query: str,
        context_chunks: list[dict],
        max_tokens: int = 500,
    ) -> _OllamaStream:
        """Return a streaming context manager for real-time answer display.

        Mirrors the interface of ``anthropic.MessageStream`` so that
        query_assistant.py uses identical code regardless of backend::

            with generator.stream_answer(query, chunks) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                final = stream.get_final_message()
            input_tokens  = final.usage.input_tokens
            output_tokens = final.usage.output_tokens

        Args:
            query: The user's question.
            context_chunks: Retrieved chunks.
            max_tokens: Maximum tokens in the response.

        Returns:
            An ``_OllamaStream`` context manager.

        Raises:
            RuntimeError: If the streaming request cannot be initiated.
        """
        messages = self._build_messages(query, context_chunks)

        payload = {
            "model":          self.model,
            "messages":       messages,
            "max_tokens":     max_tokens,
            "stream":         True,
            "stream_options": {"include_usage": True},
        }

        try:
            resp = requests.post(
                f"{self._v1}/chat/completions",
                json=payload,
                stream=True,
                timeout=(10, None),  # 10 s to connect; no read timeout (CPU inference is slow)
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base}. "
                "Make sure Ollama is running: ollama serve"
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base} (connection timed out). "
                "Make sure Ollama is running: ollama serve"
            ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        return _OllamaStream(resp)
