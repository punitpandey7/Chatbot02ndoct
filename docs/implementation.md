# Implementation guide (phase-wise)

Use this file to drive Cursor **one phase at a time**. Each phase lists **goal, files, rules, and done-when**. Do not implement later phases until the current one meets its acceptance checks.

**Architecture:** `architecture.md`  
**Product:** `prd.md`

```text
Phase 1  Scaffold
Phase 2  Load + Chunk          ← Stage A (first half)
Phase 3  Embed + Vector store  ← Stage A (second half)
Phase 4  Retrieve              ← Stage B (no LLM)
Phase 5  Guardrails
Phase 6  Generate (Groq)
Phase 7  Tiny UI
Phase 8  Deliverables (README, sample Q&A, disclaimer)
```

---

## How to prompt Cursor

Copy the **Cursor prompt** block for the next unfinished phase. After it finishes, run the **Verify** commands. Only then start the next phase.

---

## Phase 1 — Scaffold

### Goal

Empty but runnable project layout. No scraping, no embeddings, no Groq.

### Create

| Path | Purpose |
|------|---------|
| `src/__init__.py` | Package |
| `src/config.py` | Paths, collection name, chunk defaults, model name |
| `data/sources.csv` | Five HDFC Groww URLs + optional process pages |
| `requirements.txt` | Runtime deps (install in this phase) |
| `.gitignore` | `.env`, `data/chroma/`, `__pycache__`, venv |
| `.env.example` | `GROQ_API_KEY=` |
| `README.md` | Scope + “ingest vs app” placeholders |

### Do not

- Fetch URLs, chunk, embed, or call Groq.
- Commit secrets.

### Config constants (`src/config.py`)

- `PROJECT_ROOT`, `DATA_DIR`, `RAW_DIR`, `CHROMA_DIR`, `SOURCES_CSV`, `CHUNKS_TXT`
- `EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"`
- `CHROMA_COLLECTION = "hdfc_mf_faq"`
- `CHUNK_SIZE = 500`, `CHUNK_OVERLAP = 80` (architecture default; Phase 2 may tune after inspecting raw text)
- `TOP_K = 4`

### `data/sources.csv` columns

`url,scheme_name,doc_type`

`doc_type` values: `scheme_page`, `factsheet`, `KIM`, `SID`, `FAQ`, `charges`, `process`.

### Verify

- `python -c "from src.config import EMBEDDING_MODEL; print(EMBEDDING_MODEL)"`
- CSV has at least 5 scheme URLs from the PRD.

### Cursor prompt

```text
Implement Phase 1 only from docs/implementation.md (Scaffold).
Follow architecture.md. Do not fetch pages, chunk, embed, or call Groq.
```

---

## Phase 2 — Loading and chunking

### Goal

Stage A first half: **Load → Chunk**. Inspectable raw files + `data/chunks.txt`. No embeddings, no Chroma, no LLM.

### Create / implement

| Path | Responsibility |
|------|----------------|
| `src/load.py` | Read `sources.csv`. Fetch each public URL (browser-like User-Agent). Extract text (HTML: drop script/style/nav; if Groww/Next.js, parse `__NEXT_DATA__` when present). Save `data/raw/<slug>.txt`. Record `fetched_at` (ISO date). If HTTP fails, skip with a clear log (do not crash the whole run). |
| `src/chunk.py` | Split each document: recursive character split, size/overlap from config. Keep scheme name + metrics in the same window. Metadata: `source_url`, `scheme_name`, `doc_type`, `retrieved_or_fetched_date`, `chunk_index`. Dump **all** chunks to `data/chunks.txt` in the architecture dump format. |
| `src/ingest.py` | For this phase only: `load_all()` then `chunk_all()` then dump. CLI: `python -m src.ingest --through chunk` (full ingest comes in Phase 3). |

### Chunking rule (must justify in a short comment at top of `chunk.py`)

Default ~500 chars, ~80 overlap, split on headings/newlines first. After the first successful fetch, if raw text is huge unstructured blobs, increase size; if tidy key-value blocks, keep 500. Do not change the embedding model.

### Do not

- Import sentence-transformers or chromadb in load/chunk.
- Call Groq.

### Verify

- `data/raw/` contains at least one non-empty `.txt` if the network succeeded.
- `data/chunks.txt` has `----- chunk` separators and metadata lines.
- Chunks include `source_url` matching CSV.

### Cursor prompt

```text
Implement Phase 2 only from docs/implementation.md (Loading & Chunking).
Follow architecture.md §3.1 Load/Chunk and §8. Do not embed or write Chroma.
```

---

## Phase 3 — Embed and store (vector DB)

### Goal

Stage A complete: **Embed → Store**. Ingest once; persist Chroma on disk. App start must **not** re-embed.

### Create / implement

| Path | Responsibility |
|------|----------------|
| `src/embed.py` | Shared MiniLM wrapper. Lazy-load `sentence-transformers/all-MiniLM-L6-v2`. `embed_texts(list[str]) -> list[list[float]]` (384-d). Same function used later for queries. |
| `src/store.py` | Chroma `PersistentClient(path=CHROMA_DIR)`. Collection `hdfc_mf_faq`. `upsert_chunks(ids, documents, metadatas, embeddings)`. `collection_exists_and_populated()`. Do not generate answers. |
| `src/ingest.py` | Full pipeline: Load → Chunk → dump `chunks.txt` → Embed → Store. Flags: `--rebuild` (wipe/recreate collection), default skip embed/store if collection already has vectors **unless** `--rebuild`. Print counts. |

### Do not

- Implement retrieve/UI/Groq (query API on store can be a thin `query(embedding, k)` helper if it keeps Phase 4 smaller; optional).
- Re-download/re-embed on every `ingest` without `--rebuild`.

### Verify

- `python -m src.ingest` (first time) creates `data/chroma/`.
- Second run without `--rebuild` prints skip message and does not re-embed.
- Embedding length is 384.

### Cursor prompt

```text
Implement Phase 3 only from docs/implementation.md (Embed & Store vector DB).
Use sentence-transformers/all-MiniLM-L6-v2 and Chroma persist_directory.
Wire src/ingest.py Load → Chunk → Embed → Store. No Groq, no UI.
```

---

## Phase 4 — Retrieve

### Goal

Stage B retrieval only: question → same MiniLM → top-k chunks from disk Chroma.

### Create

| Path | Responsibility |
|------|----------------|
| `src/retrieve.py` | `retrieve(question: str, k: int = TOP_K)` → list of `{text, metadata, distance}`. Optional metadata filter if the question names a scheme. |
| CLI smoke | `python -m src.retrieve "ELSS lock-in HDFC"` prints texts + URLs. |

### Do not

- Call Groq or build Streamlit.

### Verify

- Query about ELSS lock-in or expense ratio returns chunks whose `scheme_name` / text look relevant.
- Fails clearly if Chroma is empty.

### Cursor prompt

```text
Implement Phase 4 only from docs/implementation.md (Retrieve).
Reuse src/embed.py and src/store.py. No LLM.
```

---

## Phase 5 — Guardrails

### Goal

Route **before** retrieve/generate: PII, advice, returns comparison.

### Create

| Path | Responsibility |
|------|----------------|
| `src/guardrails.py` | `classify(question) -> factual | refuse_advice | refuse_returns | refuse_pii`. Do not store the user string. PII: PAN-like, Aadhaar-like, OTP, email, phone, account numbers. Advice: buy/sell/switch/should I. Returns: best fund, CAGR, compare returns. |
| `src/config.py` | `EDUCATIONAL_URL` (AMFI or SEBI public investor-ed page). |

### Do not

- Call Groq.

### Verify

- Unit-style assertions or a tiny `if __name__` demo for the 3 PRD refusal questions.

### Cursor prompt

```text
Implement Phase 5 only from docs/implementation.md (Guardrails).
Follow architecture.md §6 query-time control flow. No LLM.
```

---

## Phase 6 — Generate (Groq)

### Goal

Context-only answers: ≤3 sentences, one citation from **chunk metadata**, last-updated date.

### Create

| Path | Responsibility |
|------|----------------|
| `src/generate.py` | Load `GROQ_API_KEY` from `.env`. Prompt: use only chunks; never invent URLs or ratios; no advice. Return `{answer, citation_url, last_updated, refusal}`. |
| `src/pipeline.py` | `answer(question)`: guardrails → (refuse) or retrieve → generate. |

### Do not

- Build the full UI (a CLI `python -m src.pipeline "question"` is enough).

### Verify

- Factual question cites a real `source_url` from metadata.
- Advice question never recommends a fund.

### Cursor prompt

```text
Implement Phase 6 only from docs/implementation.md (Generate with Groq).
Ground answers in retrieved chunks. Never invent citation URLs.
```

---

## Phase 7 — Tiny UI

### Goal

PRD §9: welcome, 3 examples, facts-only disclaimer, citation + last updated.

### Create

| Path | Responsibility |
|------|----------------|
| `src/app.py` | Streamlit (preferred) or Gradio. Calls `pipeline.answer`. Optional expander for retrieved URLs. |

### Do not

- Re-run ingest on startup. Only open persisted Chroma.

### Verify

- App starts with existing `data/chroma/`.
- Disclaimer visible: `Facts-only. No investment advice.`

### Cursor prompt

```text
Implement Phase 7 only from docs/implementation.md (Tiny UI).
Do not re-ingest on app start. Follow PRD UI requirements.
```

---

## Phase 8 — Deliverables

### Goal

Milestone wrap-up.

### Create / update

- README: setup, AMC + schemes, ingest vs query, chunking rationale, `k`, models, known limits, stale data.
- `sample_qa.md`: 5–10 Q&A with links (PRD §13).
- Disclaimer snippet file or README section used in UI.
- Confirm `data/sources.csv` matches ingested URLs.

### Cursor prompt

```text
Implement Phase 8 only from docs/implementation.md (Deliverables).
Do not change RAG behavior unless README is wrong.
```

---

## Dependency list (install in Phase 1)

```text
python-dotenv
requests
beautifulsoup4
lxml
sentence-transformers
chromadb
streamlit
groq
```

`streamlit` and `groq` may be unused until Phases 6–7; installing them in Phase 1 keeps one venv.

---

## Done when (whole project)

Classmate can: start UI without re-ingest; get a short cited answer; get a refusal on “should I invest?”; open `data/chunks.txt` and `data/sources.csv`.
