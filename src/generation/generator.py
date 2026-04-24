"""
Backend selector for the Zotero RAG Assistant generation layer.

Usage::

    from src.generation.generator import get_generator

    generator = get_generator()   # reads GENERATION_BACKEND from .env

``get_generator()`` returns either a ``ClaudeGenerator`` or an
``OllamaClient``; both expose identical public methods so callers need
no conditional logic after this call.
"""

from __future__ import annotations

from src.config import settings


def get_generator():
    """Instantiate and return the configured generation backend.

    Reads ``GENERATION_BACKEND`` from the environment (default: ``claude``).
    Accepted values:

    - ``claude``  — uses ``ClaudeGenerator`` (Anthropic API)
    - ``ollama``  — uses ``OllamaClient`` (local Ollama server)

    For the ``ollama`` backend, ``health_check()`` is called before
    returning; a ``RuntimeError`` with setup instructions is raised if
    the Ollama server is not reachable.

    Returns:
        A ``ClaudeGenerator`` or ``OllamaClient`` instance.

    Raises:
        RuntimeError: If ``ollama`` backend is selected but the server
            is not running.
        ValueError: If an unrecognised backend name is supplied.
    """
    backend = settings.generation_backend.strip().lower()

    if backend == "claude":
        from src.generation.claude_client import ClaudeGenerator
        return ClaudeGenerator()

    if backend == "ollama":
        from src.generation.ollama_client import OllamaClient
        client = OllamaClient()
        if not client.health_check():
            raise RuntimeError(
                "Ollama is not running or not reachable at http://localhost:11434.\n"
                "\n"
                "To start Ollama:\n"
                "  ollama serve\n"
                "\n"
                "To pull the default model (phi4-mini) if you haven't already:\n"
                "  ollama pull phi4-mini\n"
                "\n"
                "Then re-run your query."
            )
        return client

    raise ValueError(
        f"Unknown GENERATION_BACKEND={backend!r}. "
        "Valid options are: 'claude', 'ollama'."
    )
