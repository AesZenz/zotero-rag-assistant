"""
Zotero RAG Assistant — interactive CLI

Runs the full RAG pipeline:
  embed query → search FAISS index → stream Claude answer → print sources + cost

Usage:
  # Single question from command line:
  python scripts/query_assistant.py "What is working memory?"

  # Interactive mode (REPL):
  python scripts/query_assistant.py

  # Custom index path:
  python scripts/query_assistant.py --index data/my_index.faiss
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from src.ingestion.embedder import SentenceTransformerEmbedder
from src.retrieval.vector_store import FAISSVectorStore
from src.retrieval.query_decomposer import decompose_query
from src.generation.generator import get_generator

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_INDEX = "data/paper_index.faiss"
DEFAULT_TOP_K = 5
DEFAULT_MAX_TOKENS = int(os.getenv("MAX_TOKENS_PER_RESPONSE", "500"))

_DECOMPOSITION_ENABLED = os.getenv("QUERY_DECOMPOSITION", "false").lower() == "true"
_DECOMPOSITION_MODEL = os.getenv("QUERY_DECOMPOSITION_MODEL", "claude-haiku-4-5-20251001")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_PATH = os.path.join(_PROJECT_ROOT, "data", "query_logs", "query_log.jsonl")

# ANSI helpers (disabled automatically when stdout is not a TTY)
_USE_COLOR = sys.stdout.isatty() 
# isatty() checks if standardoutput (stout)
# is connected to a human readable terminal (and not, eg, an output file)
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)
CYAN   = lambda t: _c("36", t)
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)


# ---------------------------------------------------------------------------
# Query logging
# ---------------------------------------------------------------------------

def _log_query(
    query: str,
    model: str,
    chunks: list[dict],
    answer: str,
    latency_seconds: float,
    cost_usd: float | None,
) -> None:
    """Append one JSON line to the query log. Silently skips on write errors."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "model": model,
        "retrieved_chunks": [
            {
                "filename": c.get("source") or c.get("pdf_title") or "Unknown",
                "chunk_index": c.get("chunk_id"),
                "score": c.get("score"),
            }
            for c in chunks
        ],
        "answer": answer,
        "latency_seconds": round(latency_seconds, 3),
        "cost_usd": cost_usd,
    }
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging failure must never interrupt the user


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_query(
    question: str,
    store: FAISSVectorStore,
    embedder: SentenceTransformerEmbedder,
    generator: ClaudeGenerator,
    top_k: int = DEFAULT_TOP_K,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    verbose: bool = False,
) -> None:
    """Execute the full RAG pipeline for a single question and print results."""

    # 1. Embed query and retrieve context
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if _DECOMPOSITION_ENABLED:
        sub_questions = decompose_query(question, api_key, model=_DECOMPOSITION_MODEL)
        logger.info("Query decomposed into %d sub-questions: %s", len(sub_questions), sub_questions)
        seen: dict[str, dict] = {}
        for sq in sub_questions:
            for chunk in store.search(embedder.embed_text(sq), top_k=top_k):
                cid = str(chunk.get("chunk_id", id(chunk)))
                if cid not in seen or chunk.get("score", 0.0) > seen[cid].get("score", 0.0):
                    seen[cid] = chunk
        results = sorted(seen.values(), key=lambda c: c.get("score", 0.0), reverse=True)[: top_k * 2]
    else:
        results = store.search(embedder.embed_text(question), top_k=top_k)

    if not results:
        print(YELLOW("No relevant chunks found in the index."))
        return

    # 3. Print retrieved sources (before the answer so user sees what's used)
    print()
    print(DIM(f"Found {len(results)} relevant chunk(s):"))
    for rank, chunk in enumerate(results, start=1):
        source = chunk.get("source") or chunk.get("pdf_title") or "Unknown"
        score = chunk.get("score", 0.0)
        chunk_id = chunk.get("chunk_id", "?")
        print(DIM(f"  [{rank}] {source} — chunk {chunk_id} (score: {score:.3f})"))
        if verbose:
            preview = chunk["text"][:200].replace("\n", " ")
            print(DIM(f"       \"{preview}…\""))

    # 4. Stream answer
    print()
    print(BOLD("Answer:"))

    total_input_tokens = 0
    total_output_tokens = 0
    answer_parts: list[str] = []
    t0 = time.monotonic()

    try:
        with generator.stream_answer(question, results, max_tokens=max_tokens) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                answer_parts.append(text)
            final = stream.get_final_message()

        total_input_tokens = final.usage.input_tokens
        total_output_tokens = final.usage.output_tokens

    except KeyboardInterrupt:
        print()
        print(YELLOW("(interrupted)"))
        return

    # 5. Cost summary
    latency = time.monotonic() - t0
    cost = generator._calculate_cost(total_input_tokens, total_output_tokens)
    is_local = os.getenv("GENERATION_BACKEND", "claude").strip().lower() == "ollama"
    cost_str = "free (local)" if is_local else f"${cost:.6f}"
    _log_query(question, generator.model, results, "".join(answer_parts), latency, None if is_local else cost)
    print()
    print()
    print(
        DIM(
            f"[{generator.model} · "
            f"{total_input_tokens + total_output_tokens:,} tokens · "
            f"{cost_str}]"
        )
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zotero RAG Assistant — query your document library with Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (omit for interactive mode)",
    )
    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX,
        metavar="PATH",
        help=f"Path to FAISS index file (default: {DEFAULT_INDEX})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        metavar="N",
        help=f"Number of context chunks to retrieve (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        metavar="N",
        help=f"Max tokens in Claude's answer (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print a preview of each retrieved chunk",
    )
    args = parser.parse_args()

    # ---- Load components ----
    if not os.path.exists(args.index):
        print(f"Error: index not found at '{args.index}'", file=sys.stderr)
        print("Run scripts/test_vector_store.py first to build an index.", file=sys.stderr)
        sys.exit(1)

    print(DIM(f"Loading index from '{args.index}'…"))
    store = FAISSVectorStore.load(args.index)
    print(DIM(f"Index ready ({store.size} vectors)"))

    print(DIM("Loading embedding model…"))
    embedder = SentenceTransformerEmbedder()
    print(DIM(f"Embedder ready ({embedder.model_name})"))

    backend = os.getenv("GENERATION_BACKEND", "claude").strip().lower()
    print(DIM(f"Initialising {backend} generator…"))
    generator = get_generator()
    print(DIM(f"Generator ready ({generator.model})"))

    # ---- Single-shot mode ----
    if args.question:
        print()
        print(BOLD(CYAN(f"Q: {args.question}")))
        run_query(
            args.question,
            store,
            embedder,
            generator,
            top_k=args.top_k,
            max_tokens=args.max_tokens,
            verbose=args.verbose,
        )
        return

    # ---- Interactive REPL ----
    # REPL = Read-Eval-Print-Loop
    print()
    print(GREEN("Zotero RAG Assistant — interactive mode"))
    print(DIM('Type a question and press Enter. Type "exit" or Ctrl-D to quit.'))
    print()

    session_cost = 0.0

    while True:
        try:
            raw = input(BOLD(CYAN("Q: ")))
        except (EOFError, KeyboardInterrupt):
            print()
            break

        question = raw.strip()
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break

        # Run query and capture cost for session total
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if _DECOMPOSITION_ENABLED:
            sub_questions = decompose_query(question, api_key, model=_DECOMPOSITION_MODEL)
            logger.info("Query decomposed into %d sub-questions: %s", len(sub_questions), sub_questions)
            seen: dict[str, dict] = {}
            for sq in sub_questions:
                for chunk in store.search(embedder.embed_text(sq), top_k=args.top_k):
                    cid = str(chunk.get("chunk_id", id(chunk)))
                    if cid not in seen or chunk.get("score", 0.0) > seen[cid].get("score", 0.0):
                        seen[cid] = chunk
            results = sorted(seen.values(), key=lambda c: c.get("score", 0.0), reverse=True)[: args.top_k * 2]
        else:
            results = store.search(embedder.embed_text(question), top_k=args.top_k)

        if not results:
            print(YELLOW("No relevant chunks found for this query.\n"))
            continue

        print()
        print(DIM(f"Found {len(results)} relevant chunk(s):"))
        for rank, chunk in enumerate(results, start=1):
            source = chunk.get("source") or chunk.get("pdf_title") or "Unknown"
            score = chunk.get("score", 0.0)
            chunk_id = chunk.get("chunk_id", "?")
            print(DIM(f"  [{rank}] {source} — chunk {chunk_id} (score: {score:.3f})"))
            if args.verbose:
                preview = chunk["text"][:200].replace("\n", " ")
                print(DIM(f"       \"{preview}…\""))

        print()
        print(BOLD("Answer:"))

        try:
            repl_answer_parts: list[str] = []
            t0 = time.monotonic()
            with generator.stream_answer(question, results, max_tokens=args.max_tokens) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                    repl_answer_parts.append(text)
                final = stream.get_final_message()
            repl_latency = time.monotonic() - t0

            in_tok = final.usage.input_tokens
            out_tok = final.usage.output_tokens
            cost = generator._calculate_cost(in_tok, out_tok)
            session_cost += cost

            is_local = os.getenv("GENERATION_BACKEND", "claude").strip().lower() == "ollama"
            _log_query(question, generator.model, results, "".join(repl_answer_parts), repl_latency, None if is_local else cost)
            if is_local:
                cost_line = "free (local)"
            else:
                cost_line = f"${cost:.6f} this query · ${session_cost:.6f} session total"

            print()
            print()
            print(
                DIM(
                    f"[{generator.model} · "
                    f"{in_tok + out_tok:,} tokens · "
                    f"{cost_line}]"
                )
            )

        except KeyboardInterrupt:
            print()
            print(YELLOW("(interrupted — press Ctrl-D or type 'exit' to quit)"))

        print()

    is_local = os.getenv("GENERATION_BACKEND", "claude").strip().lower() == "ollama"
    session_summary = "Session cost: free (local)" if is_local else f"Session cost: ${session_cost:.6f}"
    print(DIM(session_summary))
    print(GREEN("Goodbye!"))


if __name__ == "__main__":
    main()
