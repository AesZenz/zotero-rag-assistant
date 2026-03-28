"""
FAISS vector store for the Zotero RAG Assistant.

Stores dense embeddings in a FAISS IndexFlatIP index (inner-product / cosine
similarity for L2-normalised vectors) and keeps chunk metadata in a parallel
list.  Persistence is split across two files: a binary FAISS index file and a
JSON sidecar for metadata.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from src.utils.logging import get_logger

logger = get_logger(__name__)


class FAISSVectorStore:
    """In-memory FAISS index with metadata storage and disk persistence.

    Embeddings are expected to be L2-normalised (as produced by
    ``sentence-transformers/all-mpnet-base-v2``), so inner-product search is
    equivalent to cosine similarity and scores fall in [-1, 1].

    Args:
        embedding_dim: Dimensionality of the vectors to store.  Defaults to
            768, matching ``all-mpnet-base-v2``.
    """

    _META_SUFFIX = ".meta.json"

    def __init__(self, embedding_dim: int = 768) -> None:
        self._dim = embedding_dim
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(embedding_dim)
        self._metadata: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    # @property turns the method in a readable attribute (=> store.size()
    # becomes store.size)
    def size(self) -> int:
        """Number of vectors currently stored in the index."""
        return self._index.ntotal

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: list[dict]) -> None:
        """Add embedded chunks to the index.

        Each chunk must contain an ``embedding`` key (list[float]).  All other
        keys are stored as metadata and are returned by :meth:`search`. The
        ``embedding`` field is *not* stored in metadata to save memory.

        Args:
            chunks: List of chunk dicts, each with at least an ``embedding``
                field of length ``embedding_dim``.

        Raises:
            ValueError: If any chunk is missing the ``embedding`` key or the
                embedding has the wrong dimension.
        """
        if not chunks:
            logger.warning("add_chunks called with an empty list — nothing added")
            return

        embeddings: list[list[float]] = []
        metas: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            if "embedding" not in chunk:
                raise ValueError(f"Chunk at index {i} is missing the 'embedding' key")
            emb = chunk["embedding"]
            if len(emb) != self._dim:
                raise ValueError(
                    f"Chunk {i}: expected embedding dim {self._dim}, got {len(emb)}"
                )
            embeddings.append(emb)
            # Store metadata without the raw embedding vector
            metas.append({k: v for k, v in chunk.items() if k != "embedding"})

        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)  # ensure unit norm for cosine similarity
        self._index.add(vectors)
        self._metadata.extend(metas)

        logger.info(
            "Added %d chunks to index (total: %d)", len(chunks), self._index.ntotal
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Find the most similar chunks to a query vector.

        Args:
            query_embedding: Dense query vector of length ``embedding_dim``.
            top_k: Number of results to return.

        Returns:
            A list of at most *top_k* dicts, each containing all metadata
            fields of the matching chunk plus a ``score`` key (cosine
            similarity, float in [-1, 1]; higher is more similar).

        Raises:
            ValueError: If the index is empty or the query has the wrong
                dimension.
        """
        if self._index.ntotal == 0:
            raise ValueError("The index is empty — add chunks before searching")
        if len(query_embedding) != self._dim:
            raise ValueError(
                f"Query embedding dim {len(query_embedding)} != index dim {self._dim}"
            )

        k = min(top_k, self._index.ntotal)
        query = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query)

        scores, indices = self._index.search(query, k)

        results: list[dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # FAISS sentinel for unfilled results
                continue
            result = dict(self._metadata[idx]) 
            # takes full metadata info and adds
            # "score" : cosine sim result
            result["score"] = float(score)
            results.append(result)

        logger.debug("Search returned %d results (top_k=%d)", len(results), top_k)
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist the FAISS index and metadata to disk.

        Writes two files:
        - ``path``                — binary FAISS index
        - ``path.meta.json``      — JSON array of metadata dicts

        Args:
            path: Destination path for the FAISS index file.

        Raises:
            RuntimeError: If the index is empty.
        """
        if self._index.ntotal == 0:
            raise RuntimeError("Cannot save an empty index")

        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = index_path.with_suffix(index_path.suffix + self._META_SUFFIX)

        faiss.write_index(self._index, str(index_path))
        def _default(obj: Any) -> str:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        meta_path.write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2, default=_default),
            encoding="utf-8",
        )

        logger.info(
            "Saved index (%d vectors, dim=%d) to '%s'",
            self._index.ntotal,
            self._dim,
            index_path,
        )

    @classmethod
    def load(cls, path: str) -> "FAISSVectorStore":
        """Load a previously saved index from disk.

        Expects both the FAISS index file at *path* and its ``*.meta.json``
        sidecar to exist.

        Args:
            path: Path to the FAISS index file (the ``.meta.json`` sidecar is
                inferred automatically).

        Returns:
            A fully restored :class:`FAISSVectorStore` instance.

        Raises:
            FileNotFoundError: If either the index or metadata file is missing.
        """
        index_path = Path(path)
        meta_path = index_path.with_suffix(index_path.suffix + cls._META_SUFFIX)

        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index file not found: {index_path}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata sidecar not found: {meta_path}")

        index = faiss.read_index(str(index_path))
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

        store = cls.__new__(cls)
        store._dim = index.d
        store._index = index
        store._metadata = metadata

        logger.info(
            "Loaded index (%d vectors, dim=%d) from '%s'",
            index.ntotal,
            index.d,
            index_path,
        )
        return store
