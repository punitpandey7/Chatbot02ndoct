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
against the live Groq model on the ingested corpus — not hand-written.

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
> Source: none — nothing in the corpus supports this.

This is the **correct** behaviour, not a failure. The string `statement` appears
**zero times** across all seven ingested pages, so there is nothing to ground an
answer in. The contract (architecture §7, PRD F7) prefers abstaining over inventing,
so it refuses. Fixing it properly means adding a source that actually documents
statement downloads — e.g. a Groww help-centre article on account statements — then
re-running ingest.

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

| Bar (PRD §13) | Result |
|---|---|
| Factual items cite a real corpus URL | 6/6 ✅ |
| Refusal items recommend no product | 3/3 ✅ |
| No fabricated ratios | ✅ (1 abstention instead) |

## Known limits

Numbers go stale after the last ingest. MiniLM can miss paraphrases. The LLM must not invent ratios or URLs. See `prd.md` and `architecture.md`.
