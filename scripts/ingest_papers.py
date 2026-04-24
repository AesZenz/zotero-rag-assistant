"""
Bulk ingestion script for the Zotero RAG Assistant.

Walks the PDF library directory, runs each file through the full ingestion
pipeline (parse → chunk → noise-filter → embed → FAISS index), and saves
the resulting index to disk.

Chunks from multiple papers are buffered and embedded together in batches
for efficiency; the model is loaded once and reused across all papers.

Usage:
    PYTHONPATH=. python scripts/ingest_papers.py
    PYTHONPATH=. python scripts/ingest_papers.py --resume
    PYTHONPATH=. python scripts/ingest_papers.py --pdf-dir /path/to/pdfs --output data/my.faiss
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# Must be set before any src imports: src.utils.logging reads LOG_FILE at import
# time, and torch's OpenMP must see OMP_NUM_THREADS before the first encode call.
os.environ["LOG_FILE"] = "logs/ingestion.log"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Import after env setup so Settings() picks up the LOG_FILE override above.
from src.config import settings  # noqa: E402

import numpy as np  # noqa: E402
from tqdm import tqdm  # noqa: E402

from src.ingestion.chunker import chunk_document  # noqa: E402
from src.ingestion.embedder import SentenceTransformerEmbedder  # noqa: E402
from src.ingestion.noise_filter import filter_chunks  # noqa: E402
from src.ingestion.pdf_parser import extract_metadata, extract_text_from_pdf  # noqa: E402
from src.retrieval.vector_store import FAISSVectorStore  # noqa: E402
from src.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = "data/paper_index.faiss"
CHECKPOINT_EVERY = 50   # flush buffer + save index every N papers
EMBEDDING_DIM = 768     # all-mpnet-base-v2 output dimension


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------

@dataclass
class IngestionStats:
    processed: int = 0          # papers successfully parsed and queued
    skipped: int = 0            # papers skipped by --resume
    failed: list[tuple[str, str]] = field(default_factory=list)
    raw_chunks: int = 0         # chunks before noise filter
    kept_chunks: int = 0        # chunks after noise filter
    embed_time: float = 0.0     # cumulative seconds spent in model.encode


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_pdfs(directory: Path) -> list[Path]:
    """Recursively find all PDF files under directory, sorted by name."""
    pdfs = sorted(directory.rglob("*.pdf"))
    logger.info("Found %d PDF files under '%s'", len(pdfs), directory)
    return pdfs


def _already_indexed(store: FAISSVectorStore) -> set[str]:
    """Return the set of source filenames already present in the index."""
    return {
        m.get("source_file", "")
        for m in store._metadata
        if m.get("source_file")
    }


def _flush_buffer(
    buffer: list[dict],
    store: FAISSVectorStore,
    embedder: SentenceTransformerEmbedder,
    batch_size: int,
    stats: IngestionStats,
) -> None:
    """Embed all buffered chunks, add them to the index, then clear the buffer.

    Uses embedder's underlying model directly to honour the caller's batch_size.
    """
    if not buffer:
        return

    texts = [chunk["text"] for chunk in buffer]
    logger.info("Embedding buffer: %d chunks across %d papers…", len(buffer), batch_size)

    model = embedder._load_model()
    t0 = time.perf_counter()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        batch_size=batch_size,
    )
    elapsed = time.perf_counter() - t0
    stats.embed_time += elapsed

    for chunk, vec in zip(buffer, vectors):
        chunk["embedding"] = vec.tolist()

    store.add_chunks(buffer)
    logger.info(
        "Flushed %d chunks in %.1fs → index now has %d vectors",
        len(buffer), elapsed, store.size,
    )
    buffer.clear()


def _checkpoint_save(store: FAISSVectorStore, output_path: Path, papers_done: int) -> None:
    """Save the index to disk as an incremental backup."""
    if store.size == 0:
        return
    store.save(str(output_path))
    logger.info(
        "Checkpoint saved after %d papers (%d vectors total) → '%s'",
        papers_done, store.size, output_path,
    )


def _print_summary(
    stats: IngestionStats,
    store: FAISSVectorStore,
    output_path: Path,
    total_found: int,
) -> None:
    noise_dropped = stats.raw_chunks - stats.kept_chunks
    noise_pct = (noise_dropped / stats.raw_chunks * 100) if stats.raw_chunks else 0.0

    lines = [
        "",
        "=" * 62,
        "  INGESTION COMPLETE",
        "=" * 62,
        f"  PDFs found:            {total_found}",
        f"  Successfully processed: {stats.processed}",
        f"  Skipped (resume):       {stats.skipped}",
        f"  Failed:                 {len(stats.failed)}",
        f"  Raw chunks:             {stats.raw_chunks}",
        f"  After noise filter:     {stats.kept_chunks}  ({noise_pct:.1f}% dropped)",
        f"  Total embedding time:   {stats.embed_time:.1f}s",
        f"  Final index size:       {store.size} vectors",
        f"  Saved to:               {output_path}",
        "=" * 62,
    ]

    if stats.failed:
        lines += ["", "  Failed papers:"]
        for name, reason in stats.failed:
            lines.append(f"    • {name}")
            lines.append(f"      {reason}")
        lines.append("")

    summary = "\n".join(lines)
    print(summary)
    logger.info("Ingestion complete.\n%s", summary)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def ingest(
    pdf_dir: Path,
    output_path: Path,
    batch_size: int,
    resume: bool,
    chunk_size: int,
    overlap: int,
) -> None:
    pdfs = _find_pdfs(pdf_dir)
    if not pdfs:
        print(f"No PDFs found under '{pdf_dir}'. Check --pdf-dir or PDF_LIBRARY_PATH in .env.")
        return

    total = len(pdfs)

    # --- Set up vector store ---
    store = FAISSVectorStore(embedding_dim=EMBEDDING_DIM)
    already_done: set[str] = set()

    if resume and output_path.exists():
        logger.info("--resume: loading existing index from '%s'", output_path)
        store = FAISSVectorStore.load(str(output_path))
        already_done = _already_indexed(store)
        print(f"Resuming: {len(already_done)} papers already indexed, skipping them.\n")

    # --- Load embedding model eagerly so first-paper latency is clean ---
    embedder = SentenceTransformerEmbedder()
    embedder._load_model()

    stats = IngestionStats()
    chunk_buffer: list[dict] = []

    print(f"Ingesting {total} PDFs  →  {output_path}")
    print(f"Chunk size: {chunk_size} tokens, overlap: {overlap}, embed batch: {batch_size}\n")

    pbar = tqdm(pdfs, unit="paper", dynamic_ncols=True)

    for pdf_path in pbar:
        filename = pdf_path.name
        pbar.set_description(f"{filename[:50]:<50}")
        pbar.set_postfix(
            ok=stats.processed,
            fail=len(stats.failed),
            chunks=stats.kept_chunks,
            refresh=False,
        )

        # --- Resume: skip already-indexed papers ---
        if resume and filename in already_done:
            stats.skipped += 1
            continue

        # --- Parse ---
        try:
            text = extract_text_from_pdf(str(pdf_path))
            metadata = extract_metadata(str(pdf_path))
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning("FAILED %s — %s", filename, reason)
            stats.failed.append((filename, reason))
            continue

        # --- Chunk ---
        try:
            chunks = chunk_document(
                text, metadata, chunk_size=chunk_size, overlap=overlap
            )
        except Exception as exc:
            reason = f"Chunking error: {exc}"
            logger.warning("FAILED %s — %s", filename, reason)
            stats.failed.append((filename, reason))
            continue

        stats.raw_chunks += len(chunks)

        # --- Noise filter ---
        chunks = filter_chunks(chunks)
        stats.kept_chunks += len(chunks)

        if not chunks:
            logger.info("Skipping '%s' — all %d chunks were noise", filename, len(chunks))
            stats.processed += 1
            continue

        # --- Enrich with source fields ---
        # source_file: used by --resume to detect already-indexed papers
        # source: used by query_assistant.py for display in results
        display_name = metadata.get("pdf_title") or filename
        for chunk in chunks:
            chunk["source_file"] = filename
            chunk["source"] = display_name

        chunk_buffer.extend(chunks)
        stats.processed += 1

        # --- Checkpoint: flush buffer + save every CHECKPOINT_EVERY papers ---
        if stats.processed % CHECKPOINT_EVERY == 0:
            pbar.write(
                f"  → Checkpoint at {stats.processed} papers "
                f"({stats.kept_chunks} chunks so far) — embedding + saving…"
            )
            _flush_buffer(chunk_buffer, store, embedder, batch_size, stats)
            _checkpoint_save(store, output_path, stats.processed)

    pbar.close()

    # --- Final flush of any remaining buffered chunks ---
    if chunk_buffer:
        print(f"\nFinal embedding pass: {len(chunk_buffer)} remaining chunks…")
        _flush_buffer(chunk_buffer, store, embedder, batch_size, stats)

    # --- Final save ---
    if store.size > 0:
        store.save(str(output_path))
    else:
        logger.warning("Index is empty — nothing to save")

    _print_summary(stats, store, output_path, total)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-ingest a PDF library into a FAISS vector index.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=None,
        help="Directory to search for PDFs. Overrides PDF_LIBRARY_PATH from .env.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help="Output path for the FAISS index file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size passed to model.encode (chunks per forward pass).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip PDFs whose filename is already present in the existing index. "
            "Loads the index at --output, then continues from where it left off."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Resolve PDF directory: CLI flag > .env > error
    pdf_dir_env = settings.pdf_library_path
    if args.pdf_dir:
        pdf_dir = args.pdf_dir
    elif pdf_dir_env:
        pdf_dir = Path(pdf_dir_env)
    else:
        print(
            "Error: PDF directory not specified.\n"
            "  Set PDF_LIBRARY_PATH in .env  or  pass --pdf-dir /path/to/pdfs"
        )
        raise SystemExit(1)

    if not pdf_dir.exists():
        print(f"Error: PDF directory not found: '{pdf_dir}'")
        raise SystemExit(1)

    chunk_size = settings.chunk_size
    overlap = settings.chunk_overlap

    logger.info(
        "Ingestion started — pdf_dir='%s', output='%s', "
        "batch_size=%d, resume=%s, chunk_size=%d, overlap=%d",
        pdf_dir, args.output, args.batch_size, args.resume, chunk_size, overlap,
    )

    ingest(
        pdf_dir=pdf_dir,
        output_path=args.output,
        batch_size=args.batch_size,
        resume=args.resume,
        chunk_size=chunk_size,
        overlap=overlap,
    )


if __name__ == "__main__":
    main()
