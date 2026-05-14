"""Smoke test the hybrid-search research agent against the dogfooded corpus.

Runs four canned queries that exercise person filtering, time-range
filtering, semantic recall, and aggregation-style questions. For each:

* prints the raw search hits the agent saw on each tool call (so retrieval
  quality can be evaluated independently of synthesis quality),
* prints the planner's final synthesis,
* prints token usage and wall-clock time.

Usage:
    uv run python scripts/research_smoke.py
    uv run python scripts/research_smoke.py --db ~/.openjarvis/dogfood_v1.db
    uv run python scripts/research_smoke.py --model qwen3:8b --max-iterations 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from openjarvis.agents.research_loop import (  # noqa: E402
    DEFAULT_PLANNER_MODEL,
    ResearchAgent,
)
from openjarvis.connectors.embeddings import OllamaEmbedder  # noqa: E402
from openjarvis.connectors.hybrid_search import HybridSearch  # noqa: E402
from openjarvis.connectors.store import KnowledgeStore  # noqa: E402
from openjarvis.engine.ollama import OllamaEngine  # noqa: E402

# Quiet down the noisy connector loggers — we only want our own output.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


CANNED_QUERIES: List[str] = [
    "What emails did I get from Kelly?",
    "Summarize my most recent emails",
    # Real human contact from the dogfood corpus.
    "What do I know about Mintu Manihani?",
    "How many emails do I have from newsletters?",
]


def _hr(char: str = "=", width: int = 78) -> str:
    return char * width


def _print_invocation(idx: int, inv) -> None:
    args = inv.arguments
    print(f"  ── search #{idx} ─────────────────────────────────────────────")
    print(f"    args: query={args.get('query')!r}")
    print(
        f"          person={args.get('person')!r}  "
        f"time_range={args.get('time_range')}  "
        f"sources={args.get('sources')}  "
        f"limit={args.get('limit')}"
    )
    print(f"    → {inv.num_results} hits")
    for j, h in enumerate(inv.raw_hits[:5], start=1):
        sender = h.participants[0] if h.participants else ""
        title = (h.title or "(no title)").replace("\n", " ")
        print(
            f"      {j}. fused={h.score:.4f} bm25={h.bm25_score:.2f} vec={h.vector_score:.3f}"
        )
        print(f"         ts={h.timestamp[:19]}  from={sender}")
        print(f"         {title[:100]}")
        print(f"         {h.content_snippet[:160].replace(chr(10), ' ')}…")
    if inv.num_results > 5:
        print(f"      … {inv.num_results - 5} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=str,
        default="~/.openjarvis/dogfood_v1.db",
        help="KnowledgeStore path (default: ~/.openjarvis/dogfood_v1.db)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_PLANNER_MODEL,
        help=f"Planner model tag (default: {DEFAULT_PLANNER_MODEL})",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max search() calls the planner gets per query (default: 5)",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"KnowledgeStore not found at {db_path}", file=sys.stderr)
        print("Run scripts/v1_gmail_dogfood.py first.", file=sys.stderr)
        return 1

    store = KnowledgeStore(db_path=db_path)
    embedder = OllamaEmbedder()
    if not embedder.is_available():
        print(
            "WARNING: Ollama embedder unavailable — running BM25-only.",
            file=sys.stderr,
        )
        embedder = None

    search = HybridSearch(store, embedder)
    engine = OllamaEngine()
    agent = ResearchAgent(engine, search, model=args.model, max_iterations=args.max_iterations)

    for q_idx, query in enumerate(CANNED_QUERIES, start=1):
        print()
        print(_hr("="))
        print(f"QUERY {q_idx}: {query}")
        print(_hr("="))

        t0 = time.time()
        result = agent.run(query)
        elapsed = time.time() - t0

        print(
            f"iterations={result.iterations}  "
            f"tool_calls={len(result.tool_calls)}  "
            f"wall={elapsed:.1f}s  "
            f"prompt_tokens={result.usage.get('prompt_tokens', 0)}  "
            f"completion_tokens={result.usage.get('completion_tokens', 0)}"
        )
        print()
        print("── retrieval trace " + "─" * 60)
        if not result.tool_calls:
            print("  (no tool calls — planner answered without retrieval)")
        else:
            for j, inv in enumerate(result.tool_calls, start=1):
                _print_invocation(j, inv)
        print()
        print("── final synthesis " + "─" * 60)
        print(result.answer)

    return 0


if __name__ == "__main__":
    sys.exit(main())
