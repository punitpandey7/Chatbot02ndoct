# HDFC Mutual Fund FAQ RAG Chatbot (class demo)

Facts-only Q&A for five HDFC schemes. Answers must come from retrieved public pages. **No investment advice.**

| | |
|---|---|
| **Live app** | <https://chatbot02ndoct-tepdujs9hswvhytajhp7ug.streamlit.app/> |
| **Source** | <https://github.com/punitpandey7/Chatbot02ndoct> |
| **Stack** | Python · Streamlit · ChromaDB · `sentence-transformers/all-MiniLM-L6-v2` · Groq |
| **Corpus** | 7 public pages → 239 chunks, ingested 2026-09-29 |

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
| `streamlit run app.py` | Same UI via the **root launcher** — this is the entrypoint Streamlit Community Cloud uses, since the host only looks for `app.py` at the repo root |
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
- `All sources consulted` expander listing every retrieved URL
- No implementation detail anywhere on the page: the collection name, chunk
  count, embedding model and vector store stay out of the UI and live here instead
- Sidebar: the five schemes, what the assistant does and does not do, the two
  source links, and `Clear conversation`
- The three example questions remain available for the whole session, below the
  conversation, so one click starts a new topic at any point

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

Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-d, local). Vector DB:
Chroma persisted on disk under `data/chroma/`. That directory **is committed**
(17 files, ~4.6 MB) on purpose, because the free host used here runs no build
step and so has no opportunity to run ingest — see [Deploy](#deploy-free).

## Deploy (free)

Hosted on **Streamlit Community Cloud** (free tier).

```
https://chatbot02ndoct-tepdujs9hswvhytajhp7ug.streamlit.app/
```

### Why this host

The app peaks at ~635 MB of resident memory: importing `torch` costs ~200 MB,
`sentence_transformers` ~250 MB more, the MiniLM weights ~110 MB, and Chroma
~30 MB. Render's free tier *and* its $7 starter tier both cap at 512 MB, so the
process was OOM-killed on every start. Only Render's $25 Standard tier (2 GB)
would have fit, and that was not worth it for a class demo. Streamlit Community
Cloud gives ~1 GB, which is enough.

This was measured, not inferred — see [Instrumenting it](#instrumenting-it).

### Instrumenting it

Every phase prints a timing line to the server log — `[embed]`, `[retrieve]`,
`[generate]`, `[pipeline]` — and nothing to the UI, because latency and internals
are not the user's business:

```text
[embed] model ready in 34.0s (NETWORK (no local copy))
[retrieve] open 0.01s | embed 0.15s | query 0.01s | total 0.17s
[generate] upstream call 0.61s (openai/gpt-oss-120b)
[pipeline] retrieve 0.17s | generate 0.80s | total 0.97s
```

This is not decoration. The first deployment died silently on every start, and
guessing from outside the runtime cost four deploy cycles on real but secondary
bugs. Adding these timers is what turned "it hangs" into "it is OOM-killed at
512 MB, and here is exactly which import is responsible" — the breakdown quoted
above came straight out of them.

### How the deployment is wired

Community Cloud clones the repo, installs `requirements.txt`, then looks for
`app.py` / `main.py` / `streamlit_app.py` **at the repository root**. The app
lives in `src/app.py`, so the root `app.py` is a launcher that puts the repo
root on `sys.path` and calls `src.app.main()`.

Two consequences of the host having no build step and no shell:

- `data/chroma/` is committed, because nothing would ever run `src.ingest`.
  To change the corpus: run `python -m src.ingest --rebuild` locally and commit
  the updated `data/chroma/` directory.
- `.env` does not exist on the host, so `src/generate.py` reads `st.secrets`
  first and falls back to `.env` for local runs.

### One-time setup

1. New app → connect this GitHub repo, branch `main`.
2. Settings → **Secrets** → add:

   | Key | Value |
   |---|---|
   | `GROQ_API_KEY` | your `gsk_...` key |

   `GROQ_MODEL` is optional; it defaults to `openai/gpt-oss-120b`.

That is the whole configuration. Pushing to `main` redeploys.

### Expected behaviour

- A cold start downloads `torch` and the MiniLM weights from the network, which
  took **34 s** on first boot. Later starts reuse the in-process model.
- Answers once warm: refusals ~1.6 s, grounded answers ~2.2 s.
- Chroma's client is created lazily and the embedding model loads in a
  background thread, so neither blocks the first paint.

### Deploy notes worth knowing

- A free Community Cloud app sleeps when idle. The first request after a sleep
  is slower, and `is_ready()` answers with a short notice rather than starting
  a run the proxy would drop.
- If you push and the old build keeps serving, the redeploy has not happened
  yet — **Reboot** from the Streamlit dashboard forces it from the current
  `main` HEAD.
- `Dockerfile` is kept for running the app in a container locally. It is not
  used by the deployment above.

## Disclaimer

> **Facts-only. No investment advice.**
>
> This assistant answers *scheme facts only* — expense ratios, exit loads, lock-in
> periods, minimum SIP, benchmark, riskometer level. It does **not** recommend or
> compare funds, predict returns, or give tax advice, and it does **not** accept or
> store personal data such as PAN, Aadhaar, account numbers or OTPs.
>
> Every factual answer is grounded in a public source page listed below and carries
> the date that page was ingested. Facts go stale — verify against the official
> HDFC Mutual Fund / AMFI documents before acting on anything.
>
> Not a SEBI-registered investment adviser. Mutual fund investments are subject to
> market risk; read the scheme information document before investing.

## Sources

All seven pages are public and were ingested on **2026-09-29**. The machine-readable
list lives in [`data/sources.csv`](data/sources.csv).

| # | Scheme | Type | URL |
|---|--------|------|-----|
| 1 | HDFC Large Cap Fund (Direct Growth) | scheme page | [groww.in](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 2 | HDFC Equity Fund / Flexi Cap (Direct Growth) | scheme page | [groww.in](https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth) |
| 3 | HDFC ELSS Tax Saver Fund (Direct Growth) | scheme page | [groww.in](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) |
| 4 | HDFC Small Cap Fund (Direct Growth) | scheme page | [groww.in](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth) |
| 5 | HDFC Balanced Advantage Fund (Direct Growth) | scheme page | [groww.in](https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth) |
| 6 | — (process) | help / how-to | [groww.in/help](https://groww.in/help) |
| 7 | — (process) | investor education | [amfiindia.com](https://www.amfiindia.com/mutual-fund) |

Saved page text is in [`data/raw/`](data/raw). All chunks (239) are dumped
human-readably to [`data/chunks.txt`](data/chunks.txt), and every 384-d vector to
[`data/embeddings.txt`](data/embeddings.txt).

## Sample Q&A

These are **real outputs**, produced by running `python -m src.pipeline "<question>"`
against the live Groq model on the ingested corpus — not hand-written. Each was
re-confirmed on the deployed app.

### Factual questions (answered from the corpus)

**1. Expense ratio of HDFC Large Cap Fund Direct Growth?**
> `0.84%`
> Source: [groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) · Last updated from sources: 2026-09-29

**2. Exit load of HDFC Small Cap Fund Direct Growth?**
> `Exit load of 1% if redeemed within 1 year`
> Source: [groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth) · Last updated: 2026-09-29

**3. Minimum SIP for HDFC Flexi Cap / Equity Fund Direct Growth?**
> `The minimum SIP investment is ₹100.`
> Source: [groww.in/mutual-funds/hdfc-equity-fund-direct-growth](https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth) · Last updated: 2026-09-29

**4. Lock-in period for HDFC ELSS Tax Saver?**
> `3 years`
> Source: [groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) · Last updated: 2026-09-29

**5. Riskometer / risk level of HDFC Balanced Advantage Fund?**
> `Moderately High Riskometer`
> Source: [groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth](https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth) · Last updated: 2026-09-29

**6. Benchmark of HDFC Large Cap Fund?**
> `NIFTY 100 Total Return Index`
> Source: [groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) · Last updated: 2026-09-29

### Out-of-corpus (abstains instead of guessing)

**7. How to download capital-gains / account statement?**
> `This fact is not in the loaded sources.`
> Educational link: [amfiindia.com/mutual-fund](https://www.amfiindia.com/mutual-fund)

This is the **correct** behaviour, not a failure. The string `statement` appears
**zero times** across all seven ingested pages, so there is nothing to ground an
answer in. The contract (architecture §7, PRD F7) prefers abstaining over inventing,
so it refuses.

An abstention is presented like a refusal rather than like an answer: an
educational pointer, and **no date**. Printing a source or a date would imply
the answer came from a dated document, which is exactly the claim it cannot make.

### Refusals (guardrails run before retrieval)

**8. Should I buy HDFC Small Cap now?** → *refused: advice*
> `Facts-only. This assistant cannot say whether you should buy, sell, or switch a fund. Read official scheme documents and unbiased investor education instead.`
> Educational link: [amfiindia.com/mutual-fund](https://www.amfiindia.com/mutual-fund) — **no retrieval performed**

**9. Which of these five funds has the best 3-year return?** → *refused: returns*
> `This assistant does not compute or compare returns. Use the official factsheet for past performance figures.`
> Educational link: [amfiindia.com/mutual-fund](https://www.amfiindia.com/mutual-fund) — **no retrieval performed**

**10. My PAN is ABCDE1234F, what's my tax?** → *refused: PII*
> `This assistant does not accept or store personal identifiers (PAN, Aadhaar, account numbers, OTPs, email, or phone). Ask a scheme fact without personal data.`
> Educational link: [amfiindia.com/mutual-fund](https://www.amfiindia.com/mutual-fund) — **no retrieval performed**

Note the refusals carry **no date stamp**. A refusal is not grounded in a dated
corpus fact, so printing one would be misleading.

### Acceptance summary

All ten §13 questions were re-run against the **live deployment**, refusals
included — not just locally.

| Bar (PRD §13) | Local | Live |
|---|---|---|
| Factual items cite a real corpus URL | 6/6 ✅ | 6/6 ✅ |
| Refusal items recommend no product | 3/3 ✅ | 3/3 ✅ |
| No fabricated ratios | ✅ (1 abstention instead) | ✅ |

A transcript-level sweep of the live session also confirmed: no `chunk` wording
on the page, no `Source: none` line, no leaked `SOURCE:` marker, no internal
terms (vector / embedding / Chroma / model name / dimension), and the PAN from
question 10 never echoed back in any reply.

## Known limits

Numbers go stale after the last ingest. MiniLM can miss paraphrases. The LLM must not invent ratios or URLs. See `prd.md` and `architecture.md`.
