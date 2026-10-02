"""Split loaded pages into inspectable chunks (Phase 2).

Strategy (architecture §8): scheme FAQ pages mix short labeled fields
(expense ratio, exit load, SIP, lock-in) with marketing chrome.
Recursive split on blank lines / headings first, then cap at ~500
characters with ~80 overlap so a scheme name and its metric usually
stay in the same window. MiniLM prefers small passages; do not change
the embedding model if retrieval is weak — tune size/overlap instead.

Pre-code gate result (after the first real fetch): the Groww pages are
tidy key-value blocks, so ~500/80 was kept. Two recorded adjustments:
  1. `load.py` flattens __NEXT_DATA__ to short labels, so a chunk holds
     real facts instead of property paths.
  2. Fragments under `MIN_CHUNK_CHARS` are dropped. They are section
     headers ("Structured page data:") with no fact, but they embed close
     to any question naming the scheme and displaced the real answer.
Measured median chunk length stayed ~550 after both changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_TXT, MIN_CHUNK_CHARS
from src.load import LoadedDocument

SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass
class Chunk:
    text: str
    source_url: str
    scheme_name: str
    doc_type: str
    retrieved_or_fetched_date: str
    chunk_index: int


def _split_once(text: str, separator: str) -> list[str]:
    if not separator:
        return list(text)
    return [part for part in text.split(separator) if part.strip()]


def recursive_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = [text]
    for sep in SEPARATORS:
        next_pieces: list[str] = []
        for piece in pieces:
            if len(piece) <= chunk_size:
                next_pieces.append(piece)
            else:
                parts = _split_once(piece, sep)
                if len(parts) == 1 and sep != " ":
                    next_pieces.append(piece)
                else:
                    rebuilt: list[str] = []
                    buf = ""
                    join = sep if sep != " " else " "
                    for part in parts:
                        candidate = part if not buf else buf + join + part
                        if len(candidate) <= chunk_size:
                            buf = candidate
                        else:
                            if buf:
                                rebuilt.append(buf)
                            buf = part
                    if buf:
                        rebuilt.append(buf)
                    next_pieces.extend(rebuilt)
        pieces = next_pieces
        if all(len(p) <= chunk_size for p in pieces):
            break

    hard: list[str] = []
    for piece in pieces:
        if len(piece) <= chunk_size:
            hard.append(piece)
        else:
            start = 0
            while start < len(piece):
                hard.append(piece[start : start + chunk_size])
                start += max(chunk_size - overlap, 1)

    if overlap <= 0 or len(hard) == 1:
        return [p.strip() for p in hard if p.strip()]

    with_overlap: list[str] = []
    for i, piece in enumerate(hard):
        if i == 0:
            with_overlap.append(piece)
            continue
        prev_tail = hard[i - 1][-overlap:]
        merged = (prev_tail + " " + piece).strip()
        if len(merged) > chunk_size + overlap:
            merged = merged[: chunk_size + overlap]
        with_overlap.append(merged)
    return [p.strip() for p in with_overlap if p.strip()]


def chunk_document(doc: LoadedDocument) -> list[Chunk]:
    prefix = ""
    if doc.scheme_name and doc.scheme_name.lower() != "n/a":
        prefix = f"{doc.scheme_name}\n"
    body = prefix + doc.text
    parts = recursive_split(body, CHUNK_SIZE, CHUNK_OVERLAP)
    chunks: list[Chunk] = []
    for i, part in enumerate(parts):
        if len(part) < MIN_CHUNK_CHARS:
            # Section header / separator fragment left by the split. It holds no
            # fact yet embeds near any question naming the scheme, which pushes
            # the real answer out of the top-k. Keep the original index so the
            # {url_hash}-{chunk_index} ids stay aligned with the split.
            continue
        chunks.append(
            Chunk(
                text=part,
                source_url=doc.url,
                scheme_name=doc.scheme_name,
                doc_type=doc.doc_type,
                retrieved_or_fetched_date=doc.fetched_at,
                chunk_index=i,
            )
        )
    return chunks


def chunk_all(docs: list[LoadedDocument]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_document(doc))
    return chunks


def dump_chunks(chunks: list[Chunk], path=CHUNKS_TXT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            "\n".join(
                [
                    f"----- chunk {i} -----",
                    f"scheme: {chunk.scheme_name}",
                    f"url: {chunk.source_url}",
                    f"doc_type: {chunk.doc_type}",
                    f"fetched: {chunk.retrieved_or_fetched_date}",
                    f"chunk_index: {chunk.chunk_index}",
                    "text:",
                    chunk.text,
                    "",
                ]
            )
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    print(f"[chunk] wrote {len(chunks)} chunks -> {path}")
