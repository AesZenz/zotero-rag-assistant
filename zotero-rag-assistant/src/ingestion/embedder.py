"""
Embedding module for the Zotero RAG Assistant.

Wraps sentence-transformers to produce dense vector embeddings for text chunks.
Uses a singleton model instance so the weights are loaded only once per process.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tqdm import tqdm

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"


class SentenceTransformerEmbedder:
    """Embed text using a sentence-transformers model on CPU.

    The underlying model is loaded lazily on first use and cached for the
    lifetime of the instance.

    Args:
        model_name: HuggingFace model identifier or local path.
            Defaults to ``sentence-transformers/all-mpnet-base-v2``.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> SentenceTransformer:
        """Load (or return cached) the sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model '%s' on CPU…", self.model_name) # %s is {self.model_name}
            t0 = time.perf_counter()
            self._model = SentenceTransformer(self.model_name, device="cpu")
            logger.info(
                "Model loaded in %.2fs (dim=%d)",
                time.perf_counter() - t0,
                self._model.get_sentence_embedding_dimension(),
            )
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """Return the embedding for a single piece of text.

        Args:
            text: The input string to embed.

        Returns:
            A list of floats representing the dense embedding vector.

        Raises:
            ValueError: If *text* is empty.
        """
        if not text or not text.strip():
            raise ValueError("embed_text received an empty string")

        model = self._load_model()
        embedding = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        # mode.encode() returns pytorch tensor by default; we want numpy because
        # this is easier to work with outside of DL libraries
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts efficiently using batched inference.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            A list of embedding vectors in the same order as *texts*.

        Raises:
            ValueError: If *texts* is empty.
        """
        if not texts:
            raise ValueError("embed_batch received an empty list")

        model = self._load_model()
        logger.info("Embedding batch of %d texts…", len(texts))
        t0 = time.perf_counter()

        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )

        elapsed = time.perf_counter() - t0
        logger.info(
            "Batch embedded %d texts in %.2fs (%.1f texts/s)",
            len(texts),
            elapsed,
            len(texts) / elapsed if elapsed > 0 else float("inf"),
        )
        return [emb.tolist() for emb in embeddings]

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of the embedding vectors produced by this model."""
        return self._load_model().get_sentence_embedding_dimension()


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def embed_chunks(
    chunks: list[dict],
    embedder: SentenceTransformerEmbedder | None = None,
) -> list[dict]:
    """Add an ``embedding`` field to each chunk dict.

    Embeds every chunk's ``text`` field and stores the resulting vector under
    the ``embedding`` key.  The original chunk dicts are mutated in place *and*
    returned for convenience.

    Args:
        chunks: Output of :func:`src.ingestion.chunker.chunk_document` or
            :func:`~.chunk_text`.  Each dict must contain a ``text`` key.
        embedder: An existing :class:`SentenceTransformerEmbedder` instance to
            reuse.  If ``None`` a new one is created with the default model.

    Returns:
        The same list of dicts, each enriched with an ``embedding`` field.

    Raises:
        KeyError: If any chunk dict is missing the ``text`` key.
    """
    if not chunks:
        logger.warning("embed_chunks called with an empty chunk list")
        return chunks

    if embedder is None:
        embedder = SentenceTransformerEmbedder()

    texts = [chunk["text"] for chunk in chunks]

    embeddings: list[list[float]] = []
    for i in tqdm(range(0, len(texts), 32), desc="Embedding chunks", unit="batch"):
        batch = texts[i : i + 32]
        embeddings.extend(embedder.embed_batch(batch))

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    logger.info(
        "Added embeddings to %d chunks (dim=%d)",
        len(chunks),
        len(embeddings[0]) if embeddings else 0,
    )
    return chunks
