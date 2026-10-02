"""Query-time orchestration: Guard → Retrieve → Generate (Phase 6).

Architecture §6: guardrails run BEFORE retrieval, so advice / returns / PII
never reach Chroma and never become an invented answer. This module is the
only place the three stages are wired together.

CLI:
    python -m src.pipeline                 # interactive: type questions
    python -m src.pipeline "question"      # one-shot
    python -m src.pipeline -k 6 "question"
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from src.config import EDUCATIONAL_URL, TOP_K
from src.guardrails import FACTUAL, decide
from src.retrieve import retrieve

DISCLAIMER = "Facts-only. No investment advice."

_client = None


def answer(question: str, k: int = TOP_K) -> dict[str, Any]:
    """Full query path. Returns the architecture §5.3 response shape."""
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")

    decision = decide(question)
    if decision.label != FACTUAL:
        return {
            "answer_text": decision.message,
            "citation_url": decision.educational_url or EDUCATIONAL_URL,
            "last_updated": None,
            "refusal": True,
            "refusal_kind": decision.label,
            "retrieved_urls": [],
        }

    import time

    t_all = time.perf_counter()
    hits = retrieve(question, k=k)
    t_retrieve = time.perf_counter() - t_all

    from src.generate import answer_from_chunks

    t0 = time.perf_counter()
    result = answer_from_chunks(question, hits)
    t_generate = time.perf_counter() - t0

    # Timing only, printed to the server log. On a hosted container this is
    # the only place the split is visible, and it decides whether a slow
    # request is the vector store, the model, or the upstream API call.
    print(
        f"[pipeline] retrieve {t_retrieve:.2f}s | generate {t_generate:.2f}s | "
        f"total {time.perf_counter() - t_all:.2f}s",
        flush=True,
    )

    result["refusal_kind"] = None
    return result


def _ensure_store() -> None:
    """Fail fast with the documented message if ingest has never been run."""
    from src.store import collection_exists_and_populated

    if not collection_exists_and_populated():
        raise SystemExit(
            "Chroma is empty. Run: python -m src.ingest   "
            "(vectors persist under data/chroma/)."
        )


def format_result(question: str, result: dict[str, Any], show_sources: bool) -> str:
    lines = [f"Q: {question}", ""]
    lines.append(result.get("answer_text") or "")

    if result.get("refusal"):
        lines.append("")
        lines.append(f"Refused ({result.get('refusal_kind')}) — no retrieval performed.")
        if result.get("citation_url"):
            lines.append(f"Source: {result['citation_url']}")
    else:
        lines.append("")
        if result.get("citation_url"):
            lines.append(f"Source: {result['citation_url']}")
        else:
            lines.append("Source: none (nothing in the corpus supports this)")
        if result.get("last_updated"):
            lines.append(f"Last updated from sources: {result['last_updated']}")
        if result.get("citation_fallback") and not result.get("abstained"):
            lines.append("(note: model gave no valid citation; used top-ranked chunk)")

    urls = [u for u in (result.get("retrieved_urls") or []) if u]
    if show_sources and urls:
        lines.append("")
        lines.append("Sources used (context only):")
        for url in dict.fromkeys(urls):
            lines.append(f"  - {url}")

    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def run_interactive(k: int) -> None:
    """Type a question, get a grounded answer. Ctrl+C or :q to exit."""
    _ensure_store()
    print("HDFC Mutual Fund FAQ assistant — facts only, no advice.")
    print(DISCLAIMER)
    print(f"top_k={k}. Commands: :q quit, :sources on|off. Ctrl+C also quits.\n")

    show_sources = False
    while True:
        try:
            raw = input("ask> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return
        if not raw:
            continue
        low = raw.lower()
        if low in {":q", ":quit", ":exit", "quit", "exit"}:
            print("bye")
            return
        if low == ":sources on":
            show_sources = True
            print("[sources on]\n")
            continue
        if low == ":sources off":
            show_sources = False
            print("[sources off]\n")
            continue
        if low == ":sources":
            print(f"[sources {'on' if show_sources else 'off'}]\n")
            continue

        try:
            result = answer(raw, k=k)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — show the error, never fake a result
            print(f"\nerror: {exc}\n")
            continue
        print()
        print(format_result(raw, result, show_sources))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="HDFC MF FAQ assistant (Groq, no UI)")
    parser.add_argument("question", nargs="*", help="Question; omit for interactive mode")
    parser.add_argument("-k", type=int, default=TOP_K)
    args = parser.parse_args()

    _ensure_store()
    question = " ".join(args.question).strip()
    if not question:
        run_interactive(args.k)
        return

    try:
        result = answer(question, k=args.k)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(format_result(question, result, show_sources=True))


if __name__ == "__main__":
    main()