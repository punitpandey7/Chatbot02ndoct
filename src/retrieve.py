"""Stage B retrieval: embed question with MiniLM, top-k from disk Chroma."""

from __future__ import annotations

import argparse
from typing import Any

from src.config import DATA_DIR, TOP_K
from src.embed import embed_texts
from src.guardrails import FACTUAL, classify, decide
from src.store import collection_exists_and_populated, query_embedding

SCHEME_HINTS = (
    ("elss", "HDFC ELSS Tax Saver Fund"),
    ("tax saver", "HDFC ELSS Tax Saver Fund"),
    ("large cap", "HDFC Large Cap Fund"),
    ("small cap", "HDFC Small Cap Fund"),
    ("balanced advantage", "HDFC Balanced Advantage Fund"),
    ("flexi", "HDFC Equity Fund"),
    ("equity fund", "HDFC Equity Fund"),
)

RETRIEVAL_DUMP = DATA_DIR / "retrieval_last.txt"


def scheme_filter(question: str) -> dict[str, str] | None:
    q = question.lower()
    hits = []
    for hint, name in SCHEME_HINTS:
        if hint in q:
            hits.append(name)
    unique = list(dict.fromkeys(hits))
    if len(unique) == 1:
        return {"scheme_name": unique[0]}
    return None


def retrieve(question: str, k: int = TOP_K) -> list[dict[str, Any]]:
    import time

    t_all = time.perf_counter()

    t0 = time.perf_counter()
    if not collection_exists_and_populated():
        raise SystemExit(
            "Chroma is empty. Run: python -m src.ingest   "
            "(vectors persist under data/chroma/)."
        )
    t_open = time.perf_counter() - t0

    t0 = time.perf_counter()
    vectors = embed_texts([question])
    t_embed = time.perf_counter() - t0

    where = scheme_filter(question)
    t0 = time.perf_counter()
    raw = query_embedding(vectors[0], k=k, where=where)
    t_query = time.perf_counter() - t0

    # Timing only. On a slow host the split between these is the only way to
    # tell a slow vector store from a slow model or a slow first read.
    print(
        f"[retrieve] open {t_open:.2f}s | embed {t_embed:.2f}s | "
        f"query {t_query:.2f}s | total {time.perf_counter() - t_all:.2f}s",
        flush=True,
    )
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]
    ids = (raw.get("ids") or [[]])[0]
    hits: list[dict[str, Any]] = []
    for i, text in enumerate(docs):
        hits.append(
            {
                "id": ids[i] if i < len(ids) else "",
                "text": text or "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return hits


def format_hits(question: str, hits: list[dict[str, Any]], where: dict | None) -> str:
    lines = [
        f"question: {question}",
        f"filter: {where or 'none'}",
        f"hits: {len(hits)}",
        "",
    ]
    for i, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or {}
        lines.extend(
            [
                f"----- hit {i} -----",
                f"id: {hit.get('id')}",
                f"distance: {hit.get('distance')}",
                f"scheme: {meta.get('scheme_name')}",
                f"url: {meta.get('source_url')}",
                f"doc_type: {meta.get('doc_type')}",
                f"fetched: {meta.get('retrieved_or_fetched_date')}",
                "text:",
                hit.get("text") or "",
                "",
            ]
        )
    return "\n".join(lines)


def dump_hits(question: str, hits: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    text = format_hits(question, hits, scheme_filter(question))
    RETRIEVAL_DUMP.write_text(text, encoding="utf-8")
    print(text)
    print(f"[retrieve] wrote {RETRIEVAL_DUMP}")


def format_hit_compact(i: int, hit: dict[str, Any], width: int = 220) -> str:
    meta = hit.get("metadata") or {}
    body = (hit.get("text") or "").replace("\n", " ").strip()
    if len(body) > width:
        body = body[:width] + "..."
    return "\n".join(
        [
            f"  {i}. d={hit.get('distance'):.4f}  [{meta.get('scheme_name')}]",
            f"     {body}",
            f"     {meta.get('source_url')}",
        ]
    )


def run_interactive(k: int) -> None:
    """Type questions, see the chunks Chroma returns. No LLM, no key used."""
    if not collection_exists_and_populated():
        raise SystemExit(
            "Chroma is empty. Run: python -m src.ingest   "
            "(vectors persist under data/chroma/)."
        )
    print(f"[retrieve] interactive mode, top_k={k}. Type :q or Ctrl+C to exit.")
    print("[retrieve] first question loads the MiniLM model (a few seconds)...\n")
    while True:
        try:
            question = input("ask> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[retrieve] bye")
            return
        if not question:
            continue
        if question.lower() in {":q", ":quit", ":exit", "quit", "exit"}:
            print("[retrieve] bye")
            return

        # Guardrails run before retrieval (architecture §6); show the route
        # without calling any LLM.
        label = classify(question)
        if label != FACTUAL:
            decision = decide(question)
            print(f"\nroute: {label} -> refused before retrieval")
            print(f"  {decision.message}")
            print(f"  {decision.educational_url}\n")
            continue

        hits = retrieve(question, k=k)
        where = scheme_filter(question)
        print(f"\nquestion: {question}")
        print(f"filter: {where or 'none'}   hits: {len(hits)}")
        for i, hit in enumerate(hits, start=1):
            print(format_hit_compact(i, hit))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Chroma retrieval (no LLM). No question = interactive."
    )
    parser.add_argument("question", nargs="*", help="Question to retrieve for")
    parser.add_argument("-k", type=int, default=TOP_K)
    args = parser.parse_args()
    question = " ".join(args.question).strip()
    if not question:
        run_interactive(args.k)
        return
    hits = retrieve(question, k=args.k)
    dump_hits(question, hits)


if __name__ == "__main__":
    main()
