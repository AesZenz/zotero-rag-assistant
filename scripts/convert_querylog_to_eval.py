"""
Convert query_log.jsonl entries into eval_questions format.

For each query log entry, uses the top retrieved chunk (retrieved_chunks[0])
as the "source" and looks up its text from the FAISS metadata sidecar.
Entries whose source chunk cannot be found in the index are reported and skipped.

Output: data/eval/eval_questions_from_querylog_<timestamp>.jsonl

Usage:
  pixi run convert-querylog
  pixi run convert-querylog --log-path data/query_logs/query_log.jsonl
  pixi run convert-querylog --index-path data/paper_index.faiss
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_LOG   = os.path.join(_PROJECT_ROOT, "data", "query_logs", "query_log.jsonl")
_DEFAULT_INDEX = os.path.join(_PROJECT_ROOT, "data", "paper_index.faiss")
_EVAL_DIR      = os.path.join(_PROJECT_ROOT, "data", "eval")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log-path",   default=_DEFAULT_LOG,   metavar="PATH", help="Path to query_log.jsonl")
    parser.add_argument("--index-path", default=_DEFAULT_INDEX, metavar="PATH", help="Path to FAISS index file")
    args = parser.parse_args()

    meta_path = args.index_path + ".meta.json"

    # ---- Load FAISS metadata sidecar ----
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"FAISS metadata sidecar not found: {meta_path}")

    print(f"Loading FAISS metadata from '{meta_path}'…")
    with open(meta_path, encoding="utf-8") as f:
        metadata = json.load(f)

    # Build lookup: (source, chunk_id) -> chunk_text
    lookup: dict[tuple[str, int], str] = {}
    for chunk in metadata:
        source   = chunk.get("source") or chunk.get("pdf_title") or ""
        chunk_id = chunk.get("chunk_id")
        text     = chunk.get("text", "")
        if source and chunk_id is not None:
            lookup[(source, chunk_id)] = text

    print(f"  {len(lookup):,} chunks indexed")

    # ---- Load query log ----
    if not os.path.exists(args.log_path):
        raise FileNotFoundError(f"Query log not found: {args.log_path}")

    print(f"Loading query log from '{args.log_path}'…")
    entries = []
    with open(args.log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    print(f"  {len(entries)} queries loaded")

    # ---- Convert ----
    converted = []
    missing   = []

    for entry in entries:
        query            = entry.get("query", "").strip()
        retrieved_chunks = entry.get("retrieved_chunks", [])

        if not retrieved_chunks:
            print(f"  [SKIP] No retrieved chunks for query: {query[:80]!r}")
            continue

        top_chunk    = retrieved_chunks[0]
        filename     = top_chunk.get("filename", "")
        chunk_index  = top_chunk.get("chunk_index")

        chunk_text = lookup.get((filename, chunk_index))

        if chunk_text is None:
            missing.append({"query": query, "filename": filename, "chunk_index": chunk_index})
            print(f"  [MISSING] '{filename}' chunk {chunk_index} not in index — skipping")
            continue

        converted.append({
            "question":         query,
            "source_chunk_text": chunk_text,
            "source_filename":   filename,
            "chunk_index":       chunk_index,
        })

    # ---- Report ----
    print()
    print(f"Converted : {len(converted)}/{len(entries)} entries")
    if missing:
        print(f"Missing   : {len(missing)} entries (chunks not found in index):")
        for m in missing:
            print(f"  - '{m['filename']}' chunk {m['chunk_index']}")
            print(f"    Query: {m['query'][:80]!r}")

    # ---- Write output ----
    timestamp   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = os.path.join(_EVAL_DIR, f"eval_questions_from_querylog_{timestamp}.jsonl")
    os.makedirs(_EVAL_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in converted:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print()
    print(f"Written to '{output_path}'")


if __name__ == "__main__":
    main()
