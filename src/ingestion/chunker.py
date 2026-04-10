"""
Text chunking module for the Zotero RAG Assistant.

Splits extracted PDF text into overlapping token-based chunks suitable for
embedding and retrieval. Uses tiktoken (cl100k_base) for accurate token counts.
"""

import tiktoken

from src.utils.logging import get_logger

logger = get_logger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[dict]:
    """Split text into overlapping token-based chunks.

    Encodes the full text into tokens, then slides a window of ``chunk_size``
    tokens across it with a stride of ``chunk_size - overlap``.  Each window is
    decoded back to a string and its character offsets in the original text are
    computed from the prefix token sequence.

    Args:
        text: The raw text to chunk.
        chunk_size: Maximum number of tokens per chunk.
        overlap: Number of tokens shared between consecutive chunks.

    Returns:
        A list of dicts, each with keys:
            - ``chunk_id``   (int)  – zero-based index of the chunk.
            - ``text``       (str)  – decoded text of the chunk.
            - ``start_char`` (int)  – inclusive start character offset.
            - ``end_char``   (int)  – exclusive end character offset.
            - ``token_count`` (int) – number of tokens in this chunk.

    Raises:
        ValueError: If ``chunk_size`` <= 0 or ``overlap`` >= ``chunk_size``.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    if not text or not text.strip():
        logger.warning("chunk_text received empty or whitespace-only text")
        return []

    tokens = _ENCODING.encode(text)
    total_tokens = len(tokens)
    logger.debug("Encoded text: %d tokens", total_tokens)

    if total_tokens == 0:
        return []

    stride = chunk_size - overlap
    chunks: list[dict] = []
    chunk_id = 0
    start = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        window = tokens[start:end]

        chunk_text_str = _ENCODING.decode(window)

        # Character offsets: decode the prefix to find start_char
        start_char = len(_ENCODING.decode(tokens[:start]))
        end_char = start_char + len(chunk_text_str)

        chunks.append(
            {
                "chunk_id": chunk_id,
                "text": chunk_text_str,
                "start_char": start_char,
                "end_char": end_char,
                "token_count": len(window),
            }
        )
        logger.debug(
            "Chunk %d: tokens [%d, %d), chars [%d, %d)",
            chunk_id,
            start,
            end,
            start_char,
            end_char,
        )

        chunk_id += 1

        if end == total_tokens:
            break
        start += stride

    logger.info("Created %d chunks from %d tokens", len(chunks), total_tokens)
    return chunks


def chunk_document(
    text: str,
    metadata: dict,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[dict]:
    """Chunk document text and enrich each chunk with document metadata.

    Calls :func:`chunk_text` then merges a subset of ``metadata`` fields into
    every chunk dict so downstream components have full provenance information
    without needing to look up the source document separately.

    Args:
        text: The raw extracted text of the document.
        metadata: Document-level metadata dict.  The following keys are
            propagated to each chunk if present:
            ``pdf_title``, ``author``, ``page_count``, ``creation_date``.
        chunk_size: Maximum tokens per chunk (forwarded to :func:`chunk_text`).
        overlap: Token overlap between consecutive chunks (forwarded to
            :func:`chunk_text`).

    Returns:
        A list of enriched chunk dicts.  Each dict contains all keys produced
        by :func:`chunk_text` plus ``pdf_title``, ``author``, ``page_count``,
        and ``creation_date`` drawn from *metadata*.

    Raises:
        ValueError: Propagated from :func:`chunk_text` for invalid parameters.
    """
    METADATA_KEYS = ("pdf_title", "author", "page_count", "creation_date")

    doc_meta = {key: metadata.get(key) for key in METADATA_KEYS}
    logger.info(
        "Chunking document '%s' by %s",
        doc_meta.get("pdf_title", "<unknown>"),
        doc_meta.get("author", "<unknown>"),
    )

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    for chunk in chunks:
        chunk.update(doc_meta)

    return chunks
