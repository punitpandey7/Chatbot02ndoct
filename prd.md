# Product Requirements Document (PRD)

**Product:** Mutual Fund FAQ RAG Chatbot  
**Audience:** Class demo / milestone prototype  
**AMC scope:** HDFC Mutual Fund  
**Status:** Draft for implementation  
**Last updated:** 2026-09-28

---

## 1. Summary

Build a small **facts-only FAQ assistant** that answers questions about selected HDFC mutual fund schemes using **Retrieval-Augmented Generation (RAG)**. Answers must come from official public pages, include **one source link**, and never give investment advice.

This is a **working class demo**, not a production support product. The architecture must still show a complete RAG loop: **ingestion** (load → chunk → embed → store) and **query** (question → embed → retrieve → LLM → answer).

---

## 2. Problem

Retail users and support/content teams repeatedly ask the same factual questions (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, how to download statements). Those facts live on public scheme pages, but people want a fast Q&A interface.

Without retrieval, an LLM may invent numbers or give advice. This product must **ground every answer in retrieved source text**.

---

## 3. Goals (class demo)

1. Demonstrate a full RAG pipeline with persisted vectors (ingest once, query many times).
2. Answer factual scheme questions in **≤3 sentences**, with **one citation URL**.
3. Refuse advice / portfolio / “should I buy” questions politely.
4. Show a tiny UI: welcome line, 3 example questions, facts-only disclaimer.
5. Ship the milestone deliverables listed in section 12.

**Non-goals:** returns comparison, personalized portfolios, login, PII handling, multi-AMC search, live NAV tickers, agentic tool-calling beyond retrieve + generate.

---

## 4. Users

| User | Need |
|------|------|
| Retail user comparing schemes | Fast facts (fees, lock-in, SIP min, riskometer) with a source |
| Support / content (demo persona) | Same repetitive FAQs without inventing numbers |
| Instructor / classmates | Inspect chunks, sources, and RAG stages |

---

## 5. Scope

### 5.1 In scope — one AMC, five schemes

| Category | Scheme (Direct Growth) | Seed URL (Groww public page) |
|----------|------------------------|------------------------------|
| Large Cap | HDFC Large Cap Fund | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| Flexi Cap | HDFC Equity Fund (Flexi Cap) | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| ELSS | HDFC ELSS Tax Saver Fund | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| Small Cap | HDFC Small Cap Fund | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth |
| Hybrid | HDFC Balanced Advantage Fund | https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth |

**Corpus rule:** Prefer **official public** AMC / SEBI / AMFI pages (factsheets, KIM/SID, scheme FAQs, fee/charges, riskometer/benchmark notes, statement/tax-doc guides). Groww URLs above are the starting scheme list; ingestion should pull **public page content** and record the **canonical source URL** used for citations.

**Query types in scope**

- Expense ratio  
- Exit load  
- Minimum SIP / lump-sum  
- ELSS lock-in  
- Riskometer / risk level  
- Benchmark  
- How to download statements / capital-gains documents (process facts only)

### 5.2 Out of scope

- “Should I buy/sell/switch?” or any portfolio recommendation  
- Computing or ranking returns, CAGR, “best fund”  
- Storing PAN, Aadhaar, account numbers, OTPs, email, phone  
- Third-party blogs as citation sources  
- Screenshots of any app back-end as sources  
- Multi-user auth, analytics, production hosting SLAs  

---

## 6. Product behavior

### 6.1 Happy path

1. User opens the UI and sees welcome copy, **3 example questions**, and: **“Facts-only. No investment advice.”**
2. User asks a factual question.
3. System embeds the question with the same model used at ingest.
4. System retrieves top chunks from ChromaDB.
5. LLM answers **only from retrieved context**.
6. UI shows:
   - Answer (≤3 sentences)
   - **One** source link
   - Line: `Last updated from sources: <date>`

### 6.2 Refusal path (advice / opinion)

If the question is opinionated or about buying/selling/allocating:

- Do **not** retrieve-and-invent a recommendation.
- Reply with a short, polite **facts-only** refusal.
- Include **one relevant educational link** (e.g. AMFI/SEBI investor education, or scheme KIM/SID), not a “buy this fund” page.

### 6.3 Performance / returns questions

Do **not** compute or compare returns. Point the user to the **official factsheet** (or equivalent official page) via a single link.

### 6.4 PII

If the user pastes PAN, Aadhaar, account numbers, OTPs, email, or phone:

- Do not store them.
- Tell the user the assistant does not accept personal identifiers.
- Continue only with the non-PII part of the question if possible.

---

## 7. RAG architecture (required stages)

The class demo must make both stages visible in code and README (not a single “magic” LLM call).

```
Ingestion:  Load → Chunk → Embed → Store in Vector DB
Query:      Question → Embed → Retrieve top-k chunks → LLM → Answer
```

### 7.1 Ingestion

| Step | Requirement |
|------|-------------|
| Load | Fetch/save public page text for the 5 schemes + supporting official FAQ/process pages. Keep a source list (CSV or MD) of the URLs used (minimum 5). |
| Chunk | Agent inspects the data **before** coding a chunker: propose strategy, chunk size, overlap, and per-chunk metadata. Persist **all chunks to a readable `.txt`** for inspection. |
| Embed | `sentence-transformers/all-MiniLM-L6-v2` only. Local, no API key. **384-dim**. Same model for documents and queries. |
| Store | **ChromaDB**, persisted to disk. Ingestion runs **once** (or on explicit rebuild), not on every app start. |

**Chunk metadata (minimum):** `source_url`, `scheme_name` (or `n/a` for AMC-wide FAQs), `doc_type` (factsheet / KIM / FAQ / charges / process), `retrieved_or_fetched_date`.

### 7.2 Retrieval + generation

| Step | Requirement |
|------|-------------|
| Embed question | Same MiniLM model as ingest |
| Retrieve | Top-k similar chunks from Chroma (k chosen for demo; document in README) |
| Generate | **Groq** LLM; API key in `.env`, never committed |
| Grounding | Prompt must instruct: use only provided chunks; if missing, say you don’t have that fact; always emit one citation URL from chunk metadata |
| Format | ≤3 sentences + citation + last-updated line |

---

## 8. Tech constraints (must follow)

| Area | Choice |
|------|--------|
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-d, local) |
| Vector DB | ChromaDB on disk |
| LLM | Groq (`GROQ_API_KEY` in `.env`) |
| Chunk dump | Human-readable `.txt` of all chunks |
| Secrets | `.env` gitignored; never commit keys |

Stack around this (Python app, Streamlit/Gradio/FastAPI, etc.) is implementer choice as long as the demo UI matches section 9.

---

## 9. UI requirements (tiny)

- Welcome line stating HDFC MF FAQ assistant (facts only).
- **Three** clickable or copyable example questions, e.g.:
  1. What is the expense ratio of HDFC Large Cap Fund (Direct Growth)?
  2. What is the lock-in for HDFC ELSS Tax Saver?
  3. How can I download a capital-gains statement?
- Persistent note: **Facts-only. No investment advice.**
- Chat input + answer area with citation link and last-updated stamp.
- Optional (nice for class): show retrieved source titles/URLs in a collapsible “Sources used” panel — still **one** primary citation in the answer body.

---

## 10. Functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | Answer in-scope factual queries from retrieved corpus | P0 |
| F2 | Every answer includes exactly one primary source URL | P0 |
| F3 | Answers ≤3 sentences | P0 |
| F4 | Include `Last updated from sources: <date>` | P0 |
| F5 | Refuse advice/portfolio questions with educational link | P0 |
| F6 | Do not compute/compare returns; link factsheet | P0 |
| F7 | Do not accept/store PII | P0 |
| F8 | Persist Chroma collection; skip re-ingest on restart | P0 |
| F9 | Dump chunks to inspectable `.txt` | P0 |
| F10 | Example questions + disclaimer on UI | P0 |
| F11 | Source list file (CSV or MD) of URLs used | P0 |

---

## 11. Non-functional requirements

| ID | Requirement |
|----|-------------|
| N1 | Prototype quality: works for a live or recorded ≤3 min demo |
| N2 | Deterministic enough for class: same question should cite a real page in the corpus |
| N3 | Latency: interactive on a laptop (ingest may be slow once; queries should feel demo-ready) |
| N4 | Transparency: README explains chunking rationale, k, model names, and known stale-data risk |
| N5 | Public sources only for citations |

---

## 12. Deliverables (milestone)

1. **Working prototype** (app URL or notebook) **or** ≤3-minute demo video if hosting is not possible.
2. **Source list** (CSV or MD) of the URLs used (at least the 5 scheme pages; more official pages encouraged).
3. **README:** setup, AMC + schemes in scope, how to ingest vs query, known limits.
4. **Sample Q&A file:** 5–10 queries with assistant answers + links.
5. **Disclaimer snippet** used in the UI (facts-only, no advice).
6. **Chunk dump** `.txt` (class RAG requirement).
7. **`.env.example`** with `GROQ_API_KEY=` and no real secrets.

---

## 13. Sample evaluation questions (acceptance)

Use these (or close variants) in the sample Q&A file:

1. Expense ratio of HDFC Large Cap Fund Direct Growth?  
2. Exit load of HDFC Small Cap Fund Direct Growth?  
3. Minimum SIP for HDFC Flexi Cap / Equity Fund Direct Growth?  
4. Lock-in period for HDFC ELSS Tax Saver?  
5. Riskometer / risk level of HDFC Balanced Advantage Fund?  
6. Benchmark of HDFC Large Cap Fund?  
7. How to download capital-gains / account statement?  
8. Should I buy HDFC Small Cap now? *(must refuse)*  
9. Which of these five funds has the best 3-year return? *(must not compute; point to factsheet)*  
10. My PAN is ABCDE1234F, what’s my tax? *(must refuse PII / tax advice; no storage)*

**Pass bar for demo:** Factual items cite a real corpus URL; refusal items do not recommend products; no fabricated ratios.

---

## 14. Risks and known limits (document in README)

- Groww/AMC pages can change; numbers may go stale after last ingest.  
- Scraped HTML may be noisy; chunking must preserve scheme name + metric together.  
- MiniLM is small; retrieval can miss if the user uses very different wording.  
- Groq may still over-generate; the prompt and “answer only from context” rule are mandatory.  
- Citation must be a **public** URL from metadata, not a hallucinated link.

---

## 15. Success criteria (class demo)

The demo is successful if a classmate can:

1. Start the app without re-running a long ingest (Chroma on disk).  
2. Ask one fee/lock-in question and see a short answer + one link.  
3. Ask “should I invest?” and see a refusal + educational link.  
4. Open the chunk `.txt` and source list and see how retrieval is grounded.

---

## 16. Open decisions (implementer)

- Exact official AMC/AMFI URLs beyond the five Groww seed links (record whatever is actually ingested).  
- Chunk size / overlap (must be justified from inspecting the pages).  
- Top-k and Groq model name (e.g. a small/fast Groq chat model).  
- UI framework (keep it tiny).
