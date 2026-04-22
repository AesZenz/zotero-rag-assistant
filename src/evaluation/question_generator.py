"""
Evaluation question generator for the Zotero RAG Assistant.

Samples chunks from the FAISS index and uses Claude to generate one
self-contained research question per chunk that the chunk directly answers.
Output is written to data/eval/eval_questions_<timestamp>.jsonl.

CLI usage (via pixi run generate-eval-questions):
  pixi run generate-eval-questions
  pixi run generate-eval-questions --n 50
  pixi run generate-eval-questions --n 50 --index-path data/paper_index.faiss
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_EVAL_DIR      = os.path.join(_PROJECT_ROOT, "data", "eval")
_DEFAULT_INDEX = os.path.join(_PROJECT_ROOT, "data", "paper_index.faiss")


def _timestamped_output_path() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(_EVAL_DIR, f"eval_questions_{timestamp}.jsonl")

_QUESTION_PROMPT = """\
You are creating evaluation questions for a retrieval-augmented generation (RAG) system.

Read the following text excerpt from a research paper and write exactly one specific, \
self-contained research question that this excerpt directly and fully answers. \
The question must be specific enough that this exact passage would be needed to answer it. \
Do not ask vague or general questions.

Return only the question text — no preamble, no explanation, no numbering.

Text excerpt:
{text}"""


def generate_questions_from_chunks(
    chunks: list[dict],
    n_questions: int,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    output_path: Optional[str] = None,
) -> list[dict]:
    """Generate one evaluation question per sampled chunk using Claude.

    Randomly samples ``n_questions`` chunks from the provided list, calls the
    Claude API once per chunk (non-streaming, max_tokens=200) to generate a
    self-contained research question, and writes the results to
    ``output_path`` as JSONL.

    Args:
        chunks: All chunk dicts (e.g. ``store._metadata`` from FAISSVectorStore).
        n_questions: Number of questions to generate.
        api_key: Anthropic API key.
        model: Claude model ID to use for generation.
        output_path: Destination JSONL path. Defaults to a timestamped file
            ``<project_root>/data/eval/eval_questions_<timestamp>.jsonl``.

    Returns:
        List of dicts with keys:
        - ``question`` (str): The generated question.
        - ``source_chunk_text`` (str): The chunk text the question was based on.
        - ``source_filename`` (str): The source PDF filename (``source_file`` field).
        - ``chunk_index`` (int): The ``chunk_id`` of the source chunk.
    """
    if not output_path:
        output_path = _timestamped_output_path()

    n_questions = min(n_questions, len(chunks))
    sampled = random.sample(chunks, n_questions)
    client = anthropic.Anthropic(api_key=api_key)
    results: list[dict] = []

    for i, chunk in enumerate(sampled, start=1):
        text = chunk.get("text", "").strip()
        # source_file is the actual filename; fall back to pdf_title / source
        source_filename = (
            chunk.get("source_file")
            or chunk.get("pdf_title")
            or chunk.get("source")
            or "Unknown"
        )
        chunk_index = chunk.get("chunk_id")

        logger.info(
            "Generating question %d/%d  (chunk_id=%s  source=%s)",
            i, n_questions, chunk_index, source_filename,
        )

        try:
            response = client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": _QUESTION_PROMPT.format(text=text)}],
            )
            question = response.content[0].text.strip()
        except anthropic.APIError as exc:
            logger.error("Claude API error on chunk_id=%s: %s", chunk_index, exc)
            continue

        results.append({
            "question":          question,
            "source_chunk_text": text,
            "source_filename":   source_filename,
            "chunk_index":       chunk_index,
        })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info("Saved %d questions to '%s'", len(results), output_path)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate evaluation questions from FAISS index chunks",
    )
    parser.add_argument(
        "--n", type=int, default=20,
        help="Number of questions to generate (default: 20)",
    )
    parser.add_argument(
        "--index-path", default=_DEFAULT_INDEX, metavar="PATH",
        help=f"Path to FAISS index file (default: {_DEFAULT_INDEX})",
    )
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
        help="Claude model to use (default: claude-haiku-4-5-20251001)",
    )
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    from src.retrieval.vector_store import FAISSVectorStore

    print(f"Loading index from '{args.index_path}'…")
    store = FAISSVectorStore.load(args.index_path)
    print(f"  {store.size:,} vectors in index")

    output_path = _timestamped_output_path()
    questions = generate_questions_from_chunks(
        chunks=store._metadata,
        n_questions=args.n,
        api_key=api_key,
        model=args.model,
        output_path=output_path,
    )
    print(f"Generated {len(questions)} questions → {output_path}")
