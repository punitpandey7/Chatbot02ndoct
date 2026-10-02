# Data artifacts (class demo)

| Path | What it is | When it appears |
|------|------------|-----------------|
| `sources.csv` | URL inventory | Already in the repo |
| `raw/*.txt` | Extracted page text | After `python -m src.ingest` |
| `chunks.txt` | Every chunk + metadata | After ingest (or `--through chunk`) |
| `embeddings.txt` | Chunk id + 384-d MiniLM vector | After full ingest |
| `chroma_status.txt` | Count / persist path / sample ids | After ingest or `python -m src.store` |
| `retrieval_last.txt` | Last one-shot retrieval test hits | After `python -m src.retrieve "..."` |
| `chroma/` | Persistent ChromaDB files | After full ingest (**gitignored**, stays on disk) |

Chunking and embeddings are **not** in git by magic — they are created when ingest runs. If this folder only has `sources.csv`, ingest has not been run yet on this machine.

## Source URLs (verified reachable)

| URL | Status |
|-----|--------|
| 5 × `groww.in/mutual-funds/hdfc-*` | 200, rich `__NEXT_DATA__` |
| `groww.in/help` | 200, but **intermittently** serves a JS-only shell (~218 chars) |
| `amfiindia.com/mutual-fund` | 200 |

Two originals were replaced because they no longer work: the AMFI
`/investor-corner/knowledge-center` path 404s, and `hdfcfund.com` returns 403 to
non-browser clients. `src/config.py::EDUCATIONAL_URL` now points at the live AMFI
page, since guardrails hand that link to the user on every refusal.

`load.py` retries a thin/blocked fetch and reuses the previous good
`raw/*.txt` rather than overwriting it, so one flaky response cannot shrink the
corpus.
