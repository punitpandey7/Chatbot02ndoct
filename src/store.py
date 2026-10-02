"""Persisted ChromaDB for HDFC FAQ chunks (Phase 3)."""

from __future__ import annotations

from src.config import CHROMA_COLLECTION, CHROMA_DIR, CHROMA_STATUS_TXT, TOP_K


def get_client():
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    client = get_client()
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def collection_count() -> int:
    try:
        return int(get_collection().count())
    except Exception:  # noqa: BLE001
        return 0


def collection_exists_and_populated() -> bool:
    return collection_count() > 0


def reset_collection() -> None:
    client = get_client()
    try:
        client.delete_collection(CHROMA_COLLECTION)
        print(f"[store] deleted collection {CHROMA_COLLECTION}")
    except Exception as exc:  # noqa: BLE001
        print(f"[store] delete skipped: {exc}")


def _sanitize_metadata(meta: dict) -> dict:
    clean = {}
    for key, value in meta.items():
        if value is None:
            clean[key] = "n/a"
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def upsert_chunks(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: list[list[float]],
) -> None:
    col = get_collection()
    safe_meta = [_sanitize_metadata(m) for m in metadatas]
    col.upsert(
        ids=ids,
        documents=documents,
        metadatas=safe_meta,
        embeddings=embeddings,
    )
    print(f"[store] upserted {len(ids)} vectors; collection count={col.count()}")


def query_embedding(embedding: list[float], k: int = TOP_K, where: dict | None = None):
    """Optional helper for Phase 4; unused by ingest."""
    col = get_collection()
    kwargs = {
        "query_embeddings": [embedding],
        "n_results": k,
        "include": ["documents", "metadatas", "distances"],
        # ids are always returned by Chroma
    }
    if where:
        kwargs["where"] = where
    return col.query(**kwargs)


def write_chroma_status() -> None:
    """Human-readable check: is the DB populated and where it lives on disk."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    count = collection_count()
    persist = CHROMA_DIR.resolve()
    lines = [
        f"persistent: yes (chromadb PersistentClient)",
        f"path: {persist}",
        f"collection: {CHROMA_COLLECTION}",
        f"count: {count}",
        f"populated: {count > 0}",
        "",
        "Restarting the app does NOT re-embed. Delete this folder or pass",
        "--rebuild on ingest to wipe vectors.",
        "",
    ]
    if count:
        col = get_collection()
        peek = col.get(limit=min(5, count), include=["metadatas", "documents"])
        ids = peek.get("ids") or []
        metas = peek.get("metadatas") or []
        docs = peek.get("documents") or []
        for i, cid in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            preview = (docs[i] or "").replace("\n", " ")[:120] if i < len(docs) else ""
            lines.extend(
                [
                    f"----- sample {i + 1} -----",
                    f"id: {cid}",
                    f"scheme: {meta.get('scheme_name')}",
                    f"url: {meta.get('source_url')}",
                    f"preview: {preview}",
                    "",
                ]
            )
    CHROMA_STATUS_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"[store] wrote {CHROMA_STATUS_TXT}")


if __name__ == "__main__":
    write_chroma_status()
