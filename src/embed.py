"""Shared MiniLM embeddings for ingest and query (Phase 3)."""

from __future__ import annotations

from src.config import EMBEDDING_DIM, EMBEDDING_MODEL

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(f"[embed] loading {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 8,
        normalize_embeddings=True,
    )
    rows = vectors.tolist()
    if rows and len(rows[0]) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Expected {EMBEDDING_DIM}-d embeddings, got {len(rows[0])}"
        )
    return rows
