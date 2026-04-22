"""
Zotero RAG Assistant — evaluation orchestrator

Loads eval_questions.jsonl, runs retrieval metrics (always), and optionally
runs answer quality evaluation (--full flag, incurs LLM cost).

Usage:
  # Retrieval metrics only (free — no LLM calls):
  pixi run evaluate

  # Full evaluation including answer quality (uses Claude/Ollama):
  pixi run evaluate --full

  # Custom question set (or set EVAL_QUESTIONS_PATH in .env):
  pixi run evaluate --questions data/eval/eval_questions_combined_golden.jsonl --top-k 10
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

_PROJECT_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DECOMPOSE          = os.getenv("QUERY_DECOMPOSITION", "false").lower() == "true"
_DECOMPOSITION_MODEL = os.getenv("QUERY_DECOMPOSITION_MODEL", "claude-haiku-4-5-20251001")

_EVAL_DIR      = os.path.join(_PROJECT_ROOT, "data", "eval")
_DEFAULT_INDEX = os.path.join(_PROJECT_ROOT, "data", "paper_index.faiss")
_DEFAULT_TOP_K = 5


def _latest_eval_questions() -> str:
    """Return the path set by EVAL_QUESTIONS_PATH, or the newest eval_questions_*.jsonl,
    falling back to eval_questions.jsonl if no timestamped file exists."""
    env_path = os.getenv("EVAL_QUESTIONS_PATH")
    if env_path:
        return env_path
    timestamped = sorted(glob.glob(os.path.join(_EVAL_DIR, "eval_questions_*.jsonl")))
    if timestamped:
        return timestamped[-1]
    return os.path.join(_EVAL_DIR, "eval_questions.jsonl")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_eval_questions(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"Error: eval questions file not found at '{path}'", file=sys.stderr)
        print("Generate one first with:  pixi run generate-eval-questions", file=sys.stderr)
        sys.exit(1)
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def _print_retrieval_summary(metrics: dict) -> None:
    k = metrics["top_k"]
    n = metrics["n_questions"]
    print()
    print("=" * 52)
    print("  Retrieval Evaluation Results")
    print("=" * 52)
    print(f"  Questions evaluated  : {n}")
    print(f"  Found in top-{k:<2}      : {metrics['n_found']}  ({metrics['recall_at_k']:.1%})")
    print(f"  Precision@{k}          : {metrics['precision_at_k']:.4f}")
    print(f"  Recall@{k} (hit rate) : {metrics['recall_at_k']:.4f}")
    print(f"  MRR                  : {metrics['mrr']:.4f}")
    print("=" * 52)
    print()


def _print_answer_summary(results: list[dict]) -> None:
    if not results:
        return
    n = len(results)
    avg_faith = sum(r.get("faithfulness", 0.0) for r in results) / n
    print()
    print("=" * 52)
    print("  Answer Quality Results")
    print("=" * 52)
    print(f"  Questions evaluated  : {n}")
    print(f"  Avg faithfulness     : {avg_faith:.4f}")
    if "answer_relevancy" in results[0]:
        avg_rel = sum(r.get("answer_relevancy",  0.0) for r in results) / n
        avg_cp  = sum(r.get("context_precision", 0.0) for r in results) / n
        print(f"  Avg answer relevancy : {avg_rel:.4f}")
        print(f"  Avg context precision: {avg_cp:.4f}")
    print("=" * 52)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zotero RAG Assistant — evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--questions", default=_latest_eval_questions(), metavar="PATH",
        help="Eval questions JSONL path (default: EVAL_QUESTIONS_PATH env var, "
             "then newest eval_questions_*.jsonl, then eval_questions.jsonl)",
    )
    parser.add_argument(
        "--index", default=_DEFAULT_INDEX, metavar="PATH",
        help="Path to FAISS index file (default: data/paper_index.faiss)",
    )
    parser.add_argument(
        "--top-k", type=int, default=_DEFAULT_TOP_K, metavar="N",
        help=f"Chunks to retrieve per question (default: {_DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Also run answer quality evaluation (incurs LLM API cost)",
    )
    args = parser.parse_args()

    decomp_label = f"ON (model={_DECOMPOSITION_MODEL})" if _DECOMPOSE else "OFF"
    print(f"Query decomposition: {decomp_label}")

    # ---- Load eval questions ----
    print(f"Loading eval questions from '{args.questions}'…")
    questions = _load_eval_questions(args.questions)
    print(f"  {len(questions)} questions loaded")

    # ---- Load FAISS index ----
    from src.retrieval.vector_store import FAISSVectorStore
    print(f"Loading index from '{args.index}'…")
    store = FAISSVectorStore.load(args.index)
    print(f"  {store.size:,} vectors")

    # ---- Load embedder ----
    from src.ingestion.embedder import SentenceTransformerEmbedder
    print("Loading embedding model…")
    embedder = SentenceTransformerEmbedder()
    print(f"  {embedder.model_name}")

    # ---- Retrieval evaluation ----
    from src.evaluation.retrieval_metrics import evaluate_retrieval
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    print(f"Running retrieval evaluation (top_k={args.top_k})…")
    retrieval_metrics = evaluate_retrieval(
        questions, store, embedder, top_k=args.top_k,
        decompose=_DECOMPOSE, api_key=api_key, decomposition_model=_DECOMPOSITION_MODEL,
    )
    _print_retrieval_summary(retrieval_metrics)

    # ---- Answer quality evaluation (optional) ----
    answer_results: list[dict] = []
    if args.full:
        from src.generation.generator import get_generator
        from src.evaluation.ragas_evaluator import evaluate_answers
        print("Initialising generator for answer evaluation…")
        generator = get_generator()
        print(f"  Generator: {generator.model}")
        print("Running answer quality evaluation…")
        answer_results = evaluate_answers(
            questions, store, embedder, generator, top_k=args.top_k
        )
        _print_answer_summary(answer_results)

    # ---- Save results ----
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir  = os.path.join(_PROJECT_ROOT, "data", "eval")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"eval_results_{timestamp}.jsonl")

    output: dict = {
        "timestamp":             timestamp,
        "n_questions":           len(questions),
        "top_k":                 args.top_k,
        "decomposition_enabled": _DECOMPOSE,
        "retrieval":             {k: v for k, v in retrieval_metrics.items() if k != "per_question"},
        "retrieval_per_question": retrieval_metrics.get("per_question", []),
    }
    if answer_results:
        output["answer_quality"] = answer_results

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")

    print(f"Results saved to '{out_path}'")


if __name__ == "__main__":
    main()
