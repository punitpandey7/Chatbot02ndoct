"""Stage A orchestration: Load → Chunk → Embed → Store."""

from __future__ import annotations

import argparse
import hashlib

from src.chunk import chunk_all, dump_chunks
from src.config import CHUNKS_TXT, EMBEDDINGS_TXT
from src.load import load_all


def _chunk_id(url: str, chunk_index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"{digest}-{chunk_index}"


def run_load_and_chunk():
    docs = load_all()
    if not docs:
        raise SystemExit("No documents loaded. Check data/sources.csv and network.")
    chunks = chunk_all(docs)
    dump_chunks(chunks, CHUNKS_TXT)
    return docs, chunks


def dump_embeddings_txt(ids, chunks, embeddings) -> None:
    EMBEDDINGS_TXT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"model: sentence-transformers/all-MiniLM-L6-v2",
        f"dim: {len(embeddings[0]) if embeddings else 0}",
        f"count: {len(embeddings)}",
        "",
    ]
    for i, (chunk_id, chunk, vector) in enumerate(zip(ids, chunks, embeddings), start=1):
        preview = chunk.text.replace("\n", " ")[:180]
        values = ", ".join(f"{x:.6f}" for x in vector)
        lines.extend(
            [
                f"----- embedding {i} -----",
                f"id: {chunk_id}",
                f"scheme: {chunk.scheme_name}",
                f"url: {chunk.source_url}",
                f"chunk_index: {chunk.chunk_index}",
                f"text_preview: {preview}",
                f"vector_384: {values}",
                "",
            ]
        )
    EMBEDDINGS_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[embed] wrote {len(embeddings)} vectors -> {EMBEDDINGS_TXT}")


def run_embed_and_store(chunks, rebuild: bool) -> None:
    from src.embed import embed_texts
    from src.store import (
        collection_exists_and_populated,
        reset_collection,
        upsert_chunks,
        write_chroma_status,
    )

    if collection_exists_and_populated() and not rebuild:
        print(
            "[ingest] Chroma already populated; skip embed/store. "
            "Pass --rebuild to wipe and re-index."
        )
        write_chroma_status()
        return
    if rebuild:
        reset_collection()

    texts = [c.text for c in chunks]
    print(f"[ingest] embedding {len(texts)} chunks")
    embeddings = embed_texts(texts)
    ids = [_chunk_id(c.source_url, c.chunk_index) for c in chunks]
    metadatas = [
        {
            "source_url": c.source_url,
            "scheme_name": c.scheme_name,
            "doc_type": c.doc_type,
            "retrieved_or_fetched_date": c.retrieved_or_fetched_date,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    dump_embeddings_txt(ids, chunks, embeddings)
    upsert_chunks(ids, texts, metadatas, embeddings)
    write_chroma_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="HDFC MF FAQ ingest (Stage A)")
    parser.add_argument(
        "--through",
        choices=("chunk", "all"),
        default="all",
        help="Stop after chunk dump, or run full ingest.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete persisted Chroma collection and re-embed.",
    )
    args = parser.parse_args()

    docs, chunks = run_load_and_chunk()
    print(f"[ingest] loaded {len(docs)} docs, {len(chunks)} chunks")
    if args.through == "chunk":
        print("[ingest] stopped after chunk (Phase 2).")
        return
    run_embed_and_store(chunks, rebuild=args.rebuild)
    print("[ingest] Stage A complete.")


if __name__ == "__main__":
    main()
