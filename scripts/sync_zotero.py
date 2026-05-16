"""Sync new PDFs from local Zotero storage into the RAG export folder, then trigger ingestion.

Usage:
  PYTHONPATH=. python scripts/sync_zotero.py
  pixi run sync-zotero
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

import requests

from src.config import settings

# Collection to sync — can be made configurable later
_COLLECTION = "Psy/Neuroscience/AI"

_SQL = """
SELECT ia.itemID, ia_item.key, ia.path
FROM collections c
JOIN collectionItems ci ON c.collectionID = ci.collectionID
JOIN items i ON ci.itemID = i.itemID
JOIN itemAttachments ia ON i.itemID = ia.parentItemID
JOIN items ia_item ON ia.itemID = ia_item.itemID
WHERE ia.contentType = 'application/pdf'
AND ia.path LIKE 'storage:%'
AND c.collectionID IN (
    SELECT collectionID FROM collections
    WHERE collectionName = ?
    OR parentCollectionID IN (
        SELECT collectionID FROM collections
        WHERE collectionName = ?
    )
)
"""


def main() -> None:
    if not settings.pdf_library_path:
        print("Error: PDF_LIBRARY_PATH is not set in .env", file=sys.stderr)
        sys.exit(1)

    db_path = os.path.expanduser("~/Zotero/zotero.sqlite")
    zotero_storage = Path(os.path.expanduser("~/Zotero/storage"))
    export_root = Path(settings.pdf_library_path)

    # Open read-only so we never accidentally write to Zotero's database.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(_SQL, (_COLLECTION, _COLLECTION)).fetchall()
    finally:
        conn.close()

    print(f"Found {len(rows)} PDF attachment(s) in '{_COLLECTION}'.")

    new_count = 0
    copied = 0

    for item_id, key, path_col in rows:
        filename = path_col.removeprefix("storage:")
        dest = export_root / str(item_id) / filename
        if dest.exists():
            continue

        new_count += 1
        src = zotero_storage / key / filename

        if not src.exists():
            print(f"  WARN: source not found — {src}")
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"  Copied: {filename} → {dest.parent}/")
        copied += 1

    ingest_triggered = False
    if copied > 0:
        try:
            requests.post("http://localhost:8000/ingest", timeout=5)
            ingest_triggered = True
        except requests.RequestException as exc:
            print(f"WARN: /ingest POST failed: {exc}", file=sys.stderr)

    print(
        f"\nNew PDFs found: {new_count}  |  Copied: {copied}  |  "
        f"Ingest triggered: {ingest_triggered}"
    )


if __name__ == "__main__":
    main()
