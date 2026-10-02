"""Shared MiniLM embeddings for ingest and query (Phase 3)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from src.config import EMBEDDING_MODEL, HF_HOME

# Must be set before sentence_transformers is imported anywhere: the library
# resolves its cache location at import time, not at first use.
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", HF_HOME)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# Bound the network fallback. The hub client otherwise retries against a
# default timeout of ten seconds per attempt, so on a throttled host a single
# load can sit there for many minutes with nothing to show for it.
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

_model = None
# Guards against the UI warming the model on a background thread while a
# question arrives on the main thread. Without this both would load a copy.
_model_lock = threading.Lock()


def _model_is_cached() -> bool:
    """True when the weights are already on disk, so no download is needed."""
    root = Path(HF_HOME)
    if not root.is_dir():
        return False
    # A real snapshot carries a weights file of a plausible size; matching on
    # the glob alone would also match an interrupted or partial download.
    for weights in root.glob("models--*/snapshots/*/model.safetensors"):
        try:
            if weights.stat().st_size > 1_000_000:
                return True
        except OSError:
            continue
    return False


def _build_model():
    """Construct the SentenceTransformer, trimmed for a small container.

    When the weights are already on disk they are loaded strictly from the
    cache. Left to its own devices the hub client revalidates against the
    network on every load, and on a throttled free-tier container those calls
    stall for minutes. The `local_files_only` flag turns that into a plain
    disk read.

    torch defaults to one intra-op thread per core. On a 512 MB instance that
    costs memory, and on a throttled CPU it slows the load down through thread
    contention rather than speeding it up. One thread suits this workload: it
    embeds one short query string.
    """
    from sentence_transformers import SentenceTransformer

    try:
        import torch

        torch.set_num_threads(1)
    except Exception as exc:  # noqa: BLE001 — a tuning knob, never fatal
        print(f"[embed] could not pin torch to 1 thread: {exc}")

    cached = _model_is_cached()
    if cached:
        return SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    print(
        f"[embed] WARNING: no local copy under {HF_HOME}; loading "
        f"{EMBEDDING_MODEL} from the network. On a rate-limited host this "
        "can take many minutes.",
        flush=True,
    )
    return SentenceTransformer(EMBEDDING_MODEL)


def is_ready() -> bool:
    """True once the model is in memory and a query can be embedded.

    Callers use this to avoid starting work that cannot finish in time: the
    first load on a fresh container is dominated by importing
    sentence_transformers, which is far slower than reading the weights
    themselves, and a hosting proxy will drop the connection on a request
    that runs too long.
    """
    return _model is not None


def get_model():
    """Return the shared SentenceTransformer, loading it once.

    The name and the constructor are imported inside the helpers rather than
    read as module-level globals from inside a function: on this interpreter a
    bare global lookup for EMBEDDING_MODEL inside a function raised
    `NameError: name 'EMBEDDING_MODEL' is not defined` even though the name was
    verifiably present in this module's globals.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-check: another thread may have won
                cached = _model_is_cached()
                mode = "local cache" if cached else "NETWORK (no local copy)"
                print(f"[embed] loading {EMBEDDING_MODEL} from {mode}", flush=True)
                started = time.time()
                _model = _build_model()
                print(
                    f"[embed] model ready in {time.time() - started:.1f}s "
                    f"({mode})",
                    flush=True,
                )
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