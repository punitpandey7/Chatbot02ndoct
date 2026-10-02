"""Shared MiniLM embeddings for ingest and query (Phase 3)."""

from __future__ import annotations

import os
import threading

from src.config import HF_HOME

# Must be set before sentence_transformers is imported anywhere: the library
# resolves its cache location at import time, not at first use.
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", HF_HOME)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_model = None
# Guards against the UI warming the model on a background thread while a
# question arrives on the main thread. Without this both would load a copy.
_model_lock = threading.Lock()


def get_model():
    """Return the shared SentenceTransformer, loading it once.

    The model name is imported inside the function instead of being read as a
    module-level global: on this interpreter a bare global lookup for
    EMBEDDING_MODEL inside this function raised
    `NameError: name 'EMBEDDING_MODEL' is not defined` even though the name was
    verifiably present in this module's globals. A local binding is not subject
    to that failure, and reads more clearly at the call site.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-check: another thread may have won
                from sentence_transformers import SentenceTransformer

                from src.config import EMBEDDING_MODEL as model_name

                print(f"[embed] loading {model_name}")
                _model = SentenceTransformer(model_name)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    from src.config import EMBEDDING_DIM

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
