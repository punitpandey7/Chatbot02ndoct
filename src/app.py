"""Tiny Streamlit UI (Phase 7).

PRD §9 requirements implemented here:
  - Welcome line: HDFC MF FAQ assistant (facts only)
  - Three clickable example questions
  - Persistent note: "Facts-only. No investment advice."
  - Chat input + answer area with one citation link + last-updated stamp
  - Optional collapsible "Sources used" panel (secondary to the one citation)

Hard rule (implementation.md Phase 7): this app NEVER re-ingests on start.
It only opens the persisted Chroma database and calls pipeline.answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run src/app.py` puts only this file's own directory
# (<root>/src) on sys.path, not the project root, so `import src.config`
# raises ModuleNotFoundError under every launcher except `python -m src.app`.
# Prepending the project root makes the app launch identically via
# `python -m src.app`, `streamlit run src/app.py`, and `streamlit run -m src.app`.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

from src.config import CHROMA_COLLECTION, CHROMA_DIR, TOP_K
from src.pipeline import DISCLAIMER, answer
from src.store import collection_count

# PRD §9 example questions.
EXAMPLE_QUESTIONS = [
    "What is the expense ratio of HDFC Large Cap Fund (Direct Growth)?",
    "What is the lock-in for HDFC ELSS Tax Saver?",
    "How can I download a capital-gains statement?",
]

SCHEMES = [
    "HDFC Large Cap Fund",
    "HDFC Equity Fund (Flexi Cap)",
    "HDFC ELSS Tax Saver Fund",
    "HDFC Small Cap Fund",
    "HDFC Balanced Advantage Fund",
]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

.stApp { background: linear-gradient(180deg, #f7f9ff 0%, #eef2ff 55%, #f8fafc 100%); }
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }

/* ---------- hero ---------- */
.hero {
  background: linear-gradient(120deg, #4f46e5 0%, #7c3aed 45%, #db2777 100%);
  border-radius: 22px; padding: 26px 30px; margin-bottom: 14px;
  box-shadow: 0 18px 40px -12px rgba(79, 70, 229, .55);
  color: #fff;
}
.hero h1 { color:#fff !important; font-size: 2.05rem; font-weight:800; margin:0 0 6px 0; letter-spacing:-.02em; }
.hero p  { color:#e9e7ff !important; font-size: 1.02rem; margin:0; font-weight:500; }
.hero .tag {
  display:inline-block; margin-top:12px; padding:5px 13px; border-radius:999px;
  background: rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.32);
  font-size:.78rem; font-weight:600; letter-spacing:.04em;
}

/* ---------- disclaimer ---------- */
.disclaimer {
  background: linear-gradient(90deg, #fff7ed 0%, #fef3c7 100%);
  border: 1.5px solid #fbbf24; border-left: 6px solid #f59e0b;
  border-radius: 14px; padding: 12px 18px; margin-bottom: 16px;
  color: #78350f; font-weight: 700; font-size: .95rem;
  box-shadow: 0 6px 16px -8px rgba(245,158,11,.6);
}
.disclaimer .sub { color:#92400e; font-weight:500; font-size:.82rem; margin-top:3px; }

/* ---------- example cards ---------- */
.ex-heading { font-size:.8rem; font-weight:700; color:#4338ca; text-transform:uppercase;
              letter-spacing:.08em; margin:6px 0 10px 0; }
div[data-testid="stButton"] button[kind="secondary"] {
  background:#ffffff; border:1.5px solid #c7d2fe; border-radius:14px;
  color:#312e81; font-weight:600; font-size:.86rem; line-height:1.35;
  height:auto; padding:14px 16px; width:100%; text-align:left;
  transition: all .18s ease; box-shadow:0 4px 12px -6px rgba(79,70,229,.5);
}
div[data-testid="stButton"] button[kind="secondary"]:hover {
  border-color:#4f46e5; color:#4338ca; transform: translateY(-2px);
  box-shadow:0 12px 24px -10px rgba(79,70,229,.7); background:#f5f3ff;
}

/* ---------- answer card ---------- */
.answer-card {
  background:#ffffff; border-radius:16px; padding:18px 20px; margin:4px 0 6px 0;
  border:1px solid #e2e8f0; border-left:5px solid #10b981;
  box-shadow:0 8px 22px -14px rgba(16,185,129,.7);
}
.answer-card.refusal { border-left-color:#f59e0b; background:#fffbeb; border-color:#fde68a; }
.answer-card.abstain  { border-left-color:#64748b; background:#f8fafc; border-color:#e2e8f0; }
.answer-card .body { font-size:1.02rem; color:#0f172a; line-height:1.62; margin-bottom:12px; }
.answer-card .badge {
  display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; padding:3px 10px; border-radius:999px; margin-bottom:10px;
  background:#d1fae5; color:#065f46; border:1px solid #6ee7b7;
}
.answer-card.refusal .badge { background:#fef3c7; color:#92400e; border-color:#fcd34d; }
.answer-card.abstain  .badge { background:#e2e8f0; color:#334155; border-color:#cbd5e1; }
.answer-card .meta { font-size:.83rem; color:#475569; border-top:1px dashed #cbd5e1; padding-top:10px; }
.answer-card .meta a { color:#047857; font-weight:700; text-decoration:none; word-break:break-all; }
.answer-card .meta a:hover { text-decoration:underline; }
.answer-card .stamp { display:block; margin-top:4px; color:#64748b; }

/* ---------- sidebar ---------- */
div[data-testid="stSidebar"] { background:linear-gradient(180deg,#1e1b4b 0%,#312e81 100%); }
div[data-testid="stSidebar"] * { color:#e0e7ff !important; }
div[data-testid="stSidebar"] h2, div[data-testid="stSidebar"] h3 { color:#fff !important; }
div[data-testid="stSidebar"] hr { border-color:rgba(199,210,254,.35); }
.sidebar-scheme { font-size:.82rem; padding:5px 10px; margin:3px 0; border-radius:8px;
                  background:rgba(255,255,255,.10); color:#c7d2fe !important; }
.sidebar-stat { font-size:.78rem; color:#a5b4fc !important; padding:2px 0; }
.sidebar-link { font-size:.78rem; }
.sidebar-link a { color:#a5f3fc !important; }
</style>
"""


def init_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("pending", None)


def render_answer_card(result: dict) -> None:
    """One citation + last-updated stamp, or a refusal / abstention card."""
    refusal = bool(result.get("refusal"))
    abstained = bool(result.get("abstained"))
    cls = "answer-card refusal" if refusal else ("answer-card abstain" if abstained else "answer-card")

    if refusal:
        badge = {"refuse_advice": "advice - refused", "refuse_returns": "returns - refused",
                 "refuse_pii": "personal data - refused"}.get(result.get("refusal_kind", ""), "refused")
    elif abstained:
        badge = "not in corpus"
    else:
        badge = "grounded answer"

    body = (result.get("answer_text") or "").replace("\n", "<br>")

    citation = ""
    url = result.get("citation_url")
    if url:
        label = "Educational link" if refusal else "Source"
        citation = f"{label}: <a href='{url}' target='_blank'>{url}</a>"
    elif not refusal:
        citation = "<span style='color:#64748b'>Source: none &mdash; nothing in the loaded sources supports this.</span>"

    stamp = ""
    if result.get("last_updated"):
        stamp = f"Last updated from sources: {result['last_updated']}"

    st.markdown(
        f"<div class='{cls}'><span class='badge'>{badge}</span>"
        f"<div class='body'>{body}</div>"
        f"<div class='meta'>{citation}"
        + (f"<span class='stamp'>{stamp}</span>" if stamp else "")
        + "</div></div>",
        unsafe_allow_html=True,
    )

    if not refusal:
        urls = [u for u in (result.get("retrieved_urls") or []) if u]
        if urls:
            unique = list(dict.fromkeys(urls))
            with st.expander(f"Sources used ({len(unique)} chunk(s) in context)"):
                for u in unique:
                    st.markdown(f"- <a href='{u}' target='_blank'>{u}</a>", unsafe_allow_html=True)
                st.caption(
                    "These chunks were given to the model as context. "
                    "The card above cites exactly one of them."
                )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🏦 HDFC Mutual Fund")
        st.markdown(
            "<div class='sidebar-scheme'>Facts-only FAQ assistant</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        count = collection_count()
        st.markdown("### 📚 Corpus")
        st.markdown(
            f"<div class='sidebar-stat'>Collection: <b>{CHROMA_COLLECTION}</b></div>"
            f"<div class='sidebar-stat'>Chunks indexed: <b>{count}</b></div>"
            f"<div class='sidebar-stat'>Embedding: MiniLM 384-d (local)</div>"
            f"<div class='sidebar-stat'>Vector DB: Chroma (on disk)</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("### 📈 Schemes covered")
        for name in SCHEMES:
            st.markdown(f"<div class='sidebar-scheme'>{name}</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### ⚖️ Scope")
        st.markdown(
            "<div class='sidebar-stat'>Answers come only from ingested public pages. "
            "Advice, return comparisons and personal data are refused.</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            "<div class='sidebar-link'>"
            f"<a href='https://groww.in/mutual-funds' target='_blank'>groww.in/mutual-funds</a><br>"
            f"<a href='https://www.amfiindia.com/mutual-fund' target='_blank'>AMFI investor education</a>"
            "</div>",
            unsafe_allow_html=True,
        )

        if st.button("🔄 Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def handle(question: str) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🏦"):
        with st.spinner("Searching the corpus and writing a grounded answer..."):
            result = answer(question, k=TOP_K)
        st.session_state.messages.append({"role": "assistant", "result": result})
        render_answer_card(result)


def main() -> None:
    st.set_page_config(
        page_title="HDFC MF FAQ Assistant",
        page_icon="🏦",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    render_sidebar()

    st.markdown(
        "<div class='hero'>"
        "<h1>🏦 HDFC Mutual Fund FAQ Assistant</h1>"
        "<p>Ask about HDFC scheme facts &mdash; expense ratios, exit loads, lock-in, SIP, benchmark, riskometer.</p>"
        "<span class='tag'>RAG &middot; MiniLM embeddings &middot; ChromaDB &middot; Groq</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='disclaimer'>⚠️ Facts-only. No investment advice."
        "<div class='sub'>This assistant does not recommend funds, compare returns, "
        "or accept personal data such as PAN, Aadhaar or account numbers.</div></div>",
        unsafe_allow_html=True,
    )

    # Never ingest on start: open the persisted DB and tell the user if it is empty.
    if collection_count() == 0:
        st.error(
            "No vector database found. Run ingest once in a terminal:\n\n"
            "```bash\npython -m src.ingest\n```\n\n"
            f"Then relaunch this page. Expected location: `{CHROMA_DIR}`"
        )
        st.stop()

    if not st.session_state.messages:
        st.markdown(
            "<div class='ex-heading'>💡 Try one of these</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(3)
        for i, (col, question) in enumerate(zip(cols, EXAMPLE_QUESTIONS)):
            if col.button(question, key=f"example_{i}", use_container_width=True):
                st.session_state.pending = question

    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar="🧑"):
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant", avatar="🏦"):
                render_answer_card(message["result"])

    typed = st.chat_input("Ask a factual question about an HDFC Mutual Fund…")
    question = typed or st.session_state.pop("pending", None)
    if question:
        handle(question)


if __name__ == "__main__":
    main()