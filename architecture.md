# Architecture

**Product:** Mutual Fund FAQ RAG Chatbot (class demo)  
**Source of truth:** `prd.md`  
**Pattern:** Retrieval-Augmented Generation with **two explicit stages** — ingestion and query — not a single LLM call.

---

## 1. Design goals

1. Every factual answer is grounded in retrieved public-page chunks.
2. Ingestion runs **once** (or on explicit rebuild); query path is fast for a live demo.
3. Both RAG stages are **visible in code, files, and README** (inspectable chunks, source list, persisted Chroma).
4. Guardrails sit **in front of** generation: advice, returns comparison, and PII never become “invented” answers.
5. Keep the surface area tiny: one AMC (HDFC), five schemes, facts-only UI.

---

## 2. System context

```text
┌─────────────┐         ┌──────────────────────────────┐         ┌─────────────┐
│  Demo user  │────────▶│  Tiny FAQ UI (local app)     │────────▶│  Groq LLM   │
│  (browser)  │◀────────│  Python query service        │◀────────│  (generate) │
└─────────────┘         │                              │         └─────────────┘
                        │  ┌────────────┐ ┌──────────┐ │
                        │  │ MiniLM     │ │ ChromaDB │ │
                        │  │ 384-d      │ │ on disk  │ │
                        │  └────────────┘ └──────────┘ │
                        └──────────────────────────────┘
                                        ▲
                                        │ ingest once
                        ┌───────────────┴────────────────┐
                        │ Public pages (Groww seed URLs  │
                        │ + official AMC/AMFI/SEBI docs) │
                        └────────────────────────────────┘
```

**Trust boundary:** only **public URLs** enter the corpus and citations. User text is not persisted (especially PII). Groq sees the **question + retrieved chunks**, not a raw scrape of the whole web.

---

## 3. RAG stages (required)

The class architecture is two pipelines that share the **same embedding model** and the **same Chroma collection**.

```text
INGESTION (offline / CLI)
  Load  →  Chunk  →  Embed  →  Store (Chroma persist)

QUERY (online / UI)
  Guard  →  Embed question  →  Retrieve top-k  →  LLM  →  Format answer
```

### 3.1 Stage A — Data ingestion

| Step | What happens | Output |
|------|----------------|--------|
| **Load** | Read a source list of public URLs. Fetch HTML/PDF text (or use already-saved local copies). Extract visible text; strip nav/ads. Record fetch date. | Raw docs + `sources.csv` / `sources.md` |
| **Chunk** | Split each document so scheme name + metric stay together. Attach metadata. Write **all chunks** to a readable `.txt` for inspection. | `chunks.txt` + in-memory chunk list |
| **Embed** | Encode each chunk with `sentence-transformers/all-MiniLM-L6-v2` (local, 384-d). | Vectors aligned 1:1 with chunks |
| **Store** | Upsert into ChromaDB with `persist_directory` on disk. Do **not** re-run this on every app start. | `chroma/` collection |

**Ingest is a separate command** (e.g. `python -m src.ingest`). The UI process only **opens** the persisted DB.

### 3.2 Stage B — Data retrieval + generation

| Step | What happens | Output |
|------|----------------|--------|
| **Guard** | Classify intent: advice / returns-compare / PII vs factual FAQ. | Route: refuse **or** retrieve |
| **Embed** | Same MiniLM model as ingest (must not mix models). | Query vector (384-d) |
| **Retrieve** | Similarity search, top-k chunks + metadata (`source_url`, `scheme_name`, `doc_type`, dates). | Context pack |
| **LLM** | Groq chat completion: answer **only** from context; ≤3 sentences; one citation URL copied from metadata. | Model text |
| **Format** | Attach `Last updated from sources: <date>` (max fetch date among used chunks). | UI payload |

---

## 4. Logical components

```text
src/
  ingest.py          # Stage A orchestration
  load.py            # Fetch / read public pages
  chunk.py           # Split + metadata + dump chunks.txt
  embed.py           # Shared MiniLM wrapper (ingest + query)
  store.py           # Chroma persist / query
  guardrails.py      # Advice, returns, PII
  retrieve.py        # Embed question + top-k
  generate.py        # Groq prompt + parse citation
  app.py             # Tiny UI
data/
  sources.csv        # URL inventory (deliverable)
  raw/               # Optional saved page text
  chunks.txt         # Human-readable chunk dump (deliverable)
  chroma/            # Persisted vector DB (gitignored)
```

| Component | Responsibility | Does not do |
|-----------|----------------|-------------|
| Loader | Public fetch, source list, fetch timestamps | Cite blogs; store user PII |
| Chunker | Size/overlap, metadata, `chunks.txt` | Embed or call Groq |
| Embedder | One MiniLM instance for docs **and** queries | Different models per stage |
| Vector store | Persist + nearest-neighbor | Generation |
| Guardrails | Block advice / PII / return math before LLM | Replace retrieval for factual FAQs |
| Generator | Grounded Groq call + citation from metadata | Invent URLs or ratios |
| UI | Welcome, 3 examples, disclaimer, answer + link | Auth, analytics |

---

## 5. Data model

### 5.1 Source list (minimum 5 URLs)

Each row:

| Field | Purpose |
|-------|---------|
| `url` | Citation-safe public URL |
| `scheme_name` | One of the five HDFC schemes, or `n/a` for AMC-wide process FAQs |
| `doc_type` | `scheme_page` / `factsheet` / `KIM` / `SID` / `FAQ` / `charges` / `process` |
| `fetched_at` | ISO date used for “Last updated from sources” |

Seed scheme pages (from PRD):

- HDFC Large Cap Fund Direct Growth  
- HDFC Equity Fund Direct Growth (Flexi Cap)  
- HDFC ELSS Tax Saver Direct Growth  
- HDFC Small Cap Fund Direct Growth  
- HDFC Balanced Advantage Fund Direct Growth  

Additional official AMC/AMFI/SEBI pages (statement download, riskometer notes) are ingested the same way and listed in the source file.

### 5.2 Chunk record (Chroma document)

| Field | Location | Notes |
|-------|----------|--------|
| `id` | Chroma id | Stable, e.g. `{url_hash}-{chunk_index}` |
| `text` | document | Chunk body |
| `source_url` | metadata | **Only** allowed citation |
| `scheme_name` | metadata | Or `n/a` |
| `doc_type` | metadata | See PRD |
| `retrieved_or_fetched_date` | metadata | From load step |
| `chunk_index` | metadata | Debug / dump |

Embedding: **384 floats**, MiniLM, cosine (Chroma default for this model family).

### 5.3 Query response (UI)

```text
answer_text          # ≤3 sentences
citation_url         # exactly one, from top used chunk metadata
last_updated         # date string from sources
refusal              # bool (advice / PII / returns)
retrieved_urls[]     # optional collapsible “Sources used” (demo)
```

---

## 6. Query-time control flow

```text
                    user message
                          │
                          ▼
                 ┌────────────────┐
                 │  PII scan      │──yes──▶ refuse: do not store; educational/facts-only
                 └───────┬────────┘
                         │ no
                         ▼
                 ┌────────────────┐
                 │ Advice / buy-  │──yes──▶ refuse + one AMFI/SEBI (or KIM) educational link
                 │ sell / switch  │         (skip retrieve-to-recommend)
                 └───────┬────────┘
                         │ no
                         ▼
                 ┌────────────────┐
                 │ Returns / best │──yes──▶ do not compute; one official factsheet link
                 │ fund / CAGR    │
                 └───────┬────────┘
                         │ no (factual FAQ)
                         ▼
                 embed(question) ──▶ Chroma top-k
                         │
                         ▼
                 Groq: context-only prompt
                         │
                         ▼
                 UI: answer + one URL + last updated
```

**Rationale:** the PRD forbids retrieve-and-invent recommendations. Guardrails are a **routing layer**, not a replacement for RAG on legitimate FAQs.

---

## 7. Generation contract (Groq)

**Inputs:** user question, top-k chunk texts, each chunk’s `source_url` and `fetched_at`.

**System rules (must be in the prompt):**

- Use **only** the provided chunks. If the fact is missing, say so; do not guess ratios or lock-in.
- ≤3 sentences.
- Copy **one** `source_url` from the chunks that actually support the answer. Never invent a URL.
- No investment advice, no “you should buy.”
- Do not compute or rank returns.

**Output shape** (enforce in `generate.py`, not only in prose):

1. Answer body  
2. `Source: <url>`  
3. `Last updated from sources: <YYYY-MM-DD>`

API key: `GROQ_API_KEY` in `.env` only. `.env.example` has an empty placeholder.

---

## 8. Chunking strategy (architecture default)

PRD requires inspecting page text **before** locking numbers. Default **hypothesis** for scheme FAQ pages (short sections, many labeled fields):

| Parameter | Default | Why |
|-----------|---------|-----|
| Method | Recursive character split on headings / blank lines, then size cap | Keeps “Expense ratio: …” with the scheme name in the same window |
| `chunk_size` | ~500 characters (~100–120 tokens) | MiniLM works better on small passages; fees/lock-in are local |
| `overlap` | ~80 characters | Avoid splitting “HDFC Large Cap” from the number on the next line |
| Metadata | `source_url`, `scheme_name`, `doc_type`, `retrieved_or_fetched_date`, `chunk_index` | Citation + stale-data stamp |

**Pre-code gate:** after the first fetch, open a sample of raw text. If pages are huge unstructured blobs, increase size; if they are tidy key-value blocks, keep ~500. Record the final choice in README.

**Always:** dump every chunk to `data/chunks.txt` in a readable form, e.g.

```text
----- chunk 12 -----
scheme: HDFC ELSS Tax Saver Fund
url: https://...
doc_type: scheme_page
fetched: 2026-09-28
text:
...
```

---

## 9. Retrieval defaults (demo)

| Parameter | Default | Notes |
|-----------|---------|--------|
| `k` | 4 | Enough for one scheme fact + a process snippet; small context for Groq |
| Distance | cosine | Matches MiniLM embeddings |
| Filter | optional `scheme_name` if the question names a scheme | Reduces mix-ups across five HDFC funds |

If retrieval scores are uniformly poor, the generator must **abstain** (“not in the corpus”) rather than guess.

---

## 10. Persistence and runtime

```text
First time / rebuild:
  python -m src.ingest     → writes data/chroma + data/chunks.txt + updates sources

Every demo start:
  python -m src.app        → load MiniLM + open Chroma persist_directory
                             NO full re-embed
```

| Artifact | Git |
|----------|-----|
| `data/sources.csv` | Commit (no secrets) |
| `data/chunks.txt` | Commit or attach as deliverable |
| `data/chroma/` | **Gitignore** (binary; rebuild via ingest) |
| `.env` | **Gitignore** |
| `.env.example` | Commit |

---

## 11. UI architecture (tiny)

Single page:

- Welcome: HDFC MF FAQ assistant (facts only)  
- Disclaimer always visible: **Facts-only. No investment advice.**  
- Three example questions (click fills the input)  
- Input + Send  
- Answer card: text, one citation link, last-updated line  
- Optional expander: retrieved URLs (still one primary citation in the card)

**Suggested stack for class:** Streamlit or Gradio (one file `app.py`). No login.

---

## 12. Security and compliance (demo-scale)

| Topic | Architecture rule |
|-------|-------------------|
| Sources | Public HTTP(S) pages only; no app back-end screenshots; no blogs as citations |
| Secrets | Groq key only in `.env` |
| PII | Regex/heuristic scan; never write user messages to disk or Chroma |
| Advice | Hard refuse path; educational link from a **fixed** AMFI/SEBI URL in config, not a hallucinated “best fund” |
| Returns | No calculator; factsheet URL from corpus metadata if present, else configured official factsheet page |

---

## 13. Failure modes

| Failure | User-visible behavior |
|---------|------------------------|
| Empty Chroma / ingest not run | UI error: run ingest first |
| Groq down / missing key | Clear config error; do not fake an answer |
| No relevant chunks | “This fact is not in the loaded sources” + no invented number |
| Fetch blocked at ingest | Leave URL in source list as failed; do not cite empty docs |

---

## 14. Mapping to PRD

| PRD | Architecture |
|-----|----------------|
| F1–F4 grounded short answers | Retrieve → Groq contract → UI format |
| F5–F7 refusals | `guardrails.py` before retrieve/generate |
| F8 persist Chroma | Stage A once; Stage B open-only |
| F9 `chunks.txt` | Chunker dump |
| F10–F11 UI + source list | `app.py` + `data/sources.csv` |
| MiniLM / Chroma / Groq | Fixed in embedder, store, generator |

---

## 15. What this architecture is not

- Not a multi-agent tool loop (PRD non-goal).  
- Not live NAV or returns analytics.  
- Not production RAG (no eval harness, no reranker required for the demo).  
- A **reranker** or hybrid BM25 can be added later; it is **out of the class MVP**.

---

## 16. Implementation sequence (for the next coding phase)

1. Freeze `data/sources.csv` (5 seed URLs + any official extras).  
2. Load one page, inspect text, confirm chunk size/overlap.  
3. Implement Stage A end-to-end → `chunks.txt` + Chroma persist.  
4. Implement Stage B CLI (one question in, formatted answer out).  
5. Add guardrails.  
6. Wrap with tiny UI.  
7. Fill sample Q&A file from the PRD acceptance list.
