---
title: HDFC MF FAQ Assistant
emoji: 🏦
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# HDFC Mutual Fund FAQ RAG Chatbot (class demo)

Facts-only Q&A for five HDFC schemes. Answers must come from retrieved public pages. **No investment advice.**

## Scope

- AMC: HDFC Mutual Fund
- Schemes (Direct Growth): Large Cap, Equity (Flexi Cap), ELSS Tax Saver, Small Cap, Balanced Advantage
- Source list: `data/sources.csv`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put your Groq key in `.env` (needed for answers; retrieval works without it). Never commit `.env`.

## Ingest vs app

| Command | When |
|---------|------|
| `python -m src.ingest --through chunk` | Load + chunk only (inspect `data/raw/` and `data/chunks.txt`) |
| `python -m src.ingest` | Full Stage A: load → chunk → embed → Chroma (skip if DB already populated) |
| `python -m src.ingest --rebuild` | Wipe and rebuild the vector store |
| `python -m src.app` | **Web UI** — opens on http://localhost:8501 |
| `python -m src.store` | Print/write `data/chroma_status.txt` (count + persist path) |
| `python -m src.pipeline` | Interactive **chat in the terminal** (Groq). `:q` quit, `:sources on` |
| `python -m src.pipeline "expense ratio of HDFC Large Cap?"` | One-shot answer |
| `python -m src.retrieve` | Interactive **retrieval only** — see raw chunks, no LLM, no key |
| `python -m src.retrieve "ELSS lock-in HDFC"` | One-shot retrieval; writes `data/retrieval_last.txt` |
| `python -m src.guardrails` | Self-check advice / returns / PII routing (all 10 PRD §13 questions) |

### First run order

```bash
python -m src.ingest     # once: fetch, chunk, embed, store
python -m src.app        # every time: UI only, opens persisted Chroma
```

The UI **never** re-ingests. If `data/chroma/` is missing it shows the ingest
command instead of silently rebuilding the index.

## The UI (`src/app.py`)

Streamlit, single page, per PRD §9:

- Welcome hero + **persistent** `Facts-only. No investment advice.` banner
- Three clickable example questions (the PRD's exact three)
- Chat input, conversation history, and a `Clear conversation` button
- Answer cards with a type badge: **grounded answer** (emerald),
  **advice / returns / personal data – refused** (amber),
  **not in corpus** (slate)
- Each answer card shows exactly **one** citation link plus
  `Last updated from sources: <date>`
- Optional `Sources used` expander listing every retrieved URL
- Sidebar: live chunk count, the five schemes, scope limits, AMFI link

## How a question is answered

```text
question → guardrails → refuse (advice / returns / PII)?  → yes: reply + AMFI link
                                                     → no : MiniLM → Chroma top-k
                                                            → Groq, context-only prompt
                                                            → ≤3 sentences + 1 real URL + date
```

Refusals never reach Chroma or the LLM, so they cannot turn into invented answers.

**Output contract is enforced in `generate.py`, not just asked for in the prompt:**

- The model cites by *chunk number*; the number is resolved against the chunks
  actually sent. An out-of-range or missing citation falls back to the top-ranked
  chunk and is flagged, never invented.
- Any URL in the prose that is not in the retrieved set is stripped.
- The answer body is truncated to 3 sentences.
- A blank or answer-less model reply raises an error instead of being reported as
  "not in the corpus", so a failure is never shown as a fact.

**Groq model:** `GROQ_MODEL` in `.env`. `llama-3.3-70b-versatile` now returns
404 on Groq; `openai/gpt-oss-120b` works (also `openai/gpt-oss-20b`,
`qwen/qwen3.8-27b`). `gpt-oss` and `qwen` are *reasoning* models, so
`max_tokens` must leave room for the hidden trace — see `GROQ_MAX_TOKENS`.

Inspect after ingest: `data/raw/`, `data/chunks.txt`, `data/embeddings.txt`.

`GROQ_API_KEY` lives in `.env` (gitignored) and is only read by
`src/generate.py`. Retrieval and guardrails need no key, so
`python -m src.retrieve` still works with an empty `.env`.

Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-d, local). Vector DB: Chroma on disk under `data/chroma/` (gitignored).

## Deploy (free)

Hosted on **Hugging Face Spaces**, Docker SDK, CPU basic (free).

```
https://huggingface.co/spaces/<your-username>/<space-name>
```

**Why Docker and not the Streamlit SDK:** Spaces has no build-command hook.
The Streamlit SDK only runs `streamlit run <file>` and installs
`requirements.txt` — there is no way to rebuild the vector DB, and
`data/chroma/` is gitignored. The Docker SDK gives a real `RUN` step, which
is what `Dockerfile` uses to run Stage A during the image build.

### One-time setup

1. New Space → **Docker** → connect the GitHub repo.
2. Hardware → **CPU basic** (free).
3. Settings → **Variables and secrets** → add:

   | Key | Value |
   |---|---|
   | `GROQ_API_KEY` | *(secret)* your `gsk_...` key |
   | `GROQ_MODEL` | `openai/gpt-oss-120b` |

4. Build. The log ends with `[ingest] Stage A complete.` then
   `[store] ... 239` before the Space starts serving.

Nothing else to configure — `app_port: 7860` and the Dockerfile's
`EXPOSE 7860` already agree, and the app binds `0.0.0.0` in its `CMD`.

### What the build does

```dockerfile
RUN python -m src.ingest   # fetch → chunk → embed → persist Chroma
RUN python -m src.store    # write data/chroma_status.txt
RUN test -f data/chroma/chroma.sqlite3 || exit 1
```

The last line is deliberate: it fails the build loudly rather than shipping an
image whose app can only show an error page.

If the build machine cannot reach `groww.in` or `amfiindia.com`, ingest falls
back to the committed `data/raw/` cache (7 documents) instead of producing an
empty corpus — so the build does not depend on a third-party site being up.

### Expected behaviour

- First build downloads `torch` (~800 MB) and MiniLM, so it takes several
  minutes. Later builds reuse the Docker layer cache.
- A free Space sleeps after ~48 h idle and takes ~10-30 s to wake on the next
  request. The first answer after waking is slower.
- Every rebuild re-runs Stage A, so the corpus date reflects that build.

## Known limits

Numbers go stale after the last ingest. MiniLM can miss paraphrases. The LLM must not invent ratios or URLs. See `prd.md` and `architecture.md`.
