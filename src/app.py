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
import threading
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

from src.config import CHROMA_DIR, TOP_K
from src.embed import get_model, is_ready
from src.generate import GenerationError
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

# Turned instead of answering when the host cannot finish the lookup in time.
NOT_READY_NOTICE = (
    "Still getting ready. On a cold start this host needs about a minute "
    "before the first answer can be looked up — please ask again in a moment."
)
GENERIC_ERROR = (
    "Something went wrong while preparing that answer. "
    "Please try again in a moment."
)

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
        # Refusals and abstentions have no document to cite, so they point at
        # investor education instead and carry no date. Only a real grounded
        # answer gets a "Source:" line.
        label = "Source" if not (refusal or abstained) else "Educational link"
        citation = f"{label}: <a href='{url}' target='_blank'>{url}</a>"

    stamp = ""
    if result.get("last_updated") and not abstained:
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
            # No counts, no "chunks", no retrieval jargon: this panel exists so
            # a reader can see which pages were consulted, and nothing about
            # how the lookup was done internally.
            with st.expander("All sources consulted"):
                for u in unique:
                    st.markdown(f"- <a href='{u}' target='_blank'>{u}</a>", unsafe_allow_html=True)
                st.caption(
                    "The card above cites exactly one of these."
                    if not abstained
                    else "None of these contained the fact, so no source is cited."
                )


def render_sidebar() -> None:
    """User-facing sidebar only.

    Deliberately hides implementation detail (collection name, chunk count,
    embedding model, vector DB). Those belong in the README for an evaluator,
    not on the product surface shown to an end user.
    """
    with st.sidebar:
        st.markdown("## 🏦 HDFC Mutual Fund")
        st.markdown(
            "<div class='sidebar-scheme'>Facts-only FAQ assistant</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        st.markdown("### 📈 Schemes covered")
        for name in SCHEMES:
            st.markdown(f"<div class='sidebar-scheme'>{name}</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### ⚖️ What this assistant does")
        st.markdown(
            "<div class='sidebar-stat'>Answers scheme facts — fees, exit load, lock-in, "
            "SIP, benchmark, riskometer — using only the sources linked below. "
            "It will not recommend a fund, compare returns, or accept personal data."
            "</div>",
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


_warm_error = None


def _warm() -> None:
    """Preload MiniLM so the first question does not pay the load cost.

    The failure is recorded rather than discarded. On a small host the load can
    fail outright (commonly a memory limit), and an earlier version swallowed
    that error, which made the resulting hang impossible to diagnose from the
    deploy logs.
    """
    global _warm_error
    try:
        get_model()
    except Exception as exc:  # noqa: BLE001 — never break the page render
        _warm_error = f"{type(exc).__name__}: {exc}"
        print(f"[app] warm-up FAILED -> {_warm_error}", flush=True)
        import traceback

        traceback.print_exc()
    else:
        print("[app] warm-up complete", flush=True)


_warm_thread = None
_warm_started = False


def start_warmup() -> None:
    """Kick off the ~20 s MiniLM load on a daemon thread, once per process.

    Loading it inline would block the first script run for the full duration,
    which is long enough for a hosting proxy to drop the connection. On a
    background thread the page paints immediately and the model is usually
    ready before the first question is typed. `embed.get_model()` is
    lock-guarded, so a question arriving mid-load waits for this one rather
    than starting a second copy.

    `_warm_started` is a separate flag from the thread's liveness: the thread
    finishes as soon as the model is cached, and Streamlit reruns the script
    on every interaction, so an liveness check alone would spawn a fresh
    no-op thread on each rerun.
    """
    global _warm_thread, _warm_started
    if not _warm_started:
        _warm_started = True
        _warm_thread = threading.Thread(target=_warm, daemon=True)
        _warm_thread.start()


def _queue_question(question: str) -> None:
    """Hold a clicked example until the script body picks it up."""
    st.session_state.pending = question


def handle(question: str) -> None:
    """Record the turn and compute its result. Drawing is left to the loop.

    handle() deliberately renders nothing itself. The transcript loop in main()
    already draws every message, including this one, so drawing here as well
    placed the answer after the elements that follow it in the script.
    """
    st.session_state.messages.append({"role": "user", "content": question})
    if not is_ready():
        # Asking anyway would start a run that cannot finish: the first
        # load is dominated by an import that takes longer than a hosting
        # proxy will wait, and the browser would drop the connection and
        # lose the question. Say so, and let them ask again.
        st.session_state.messages.append(
            {"role": "assistant", "notice": NOT_READY_NOTICE}
        )
        return
    try:
        with st.spinner("Searching the corpus and writing a grounded answer..."):
            result = answer(question, k=TOP_K)
    except GenerationError as exc:
        st.session_state.messages.append({"role": "assistant", "notice": str(exc)})
        return
    except Exception as exc:  # noqa: BLE001
        # Without this the chat message simply never completes and the
        # widget sits on a spinner that can no longer do anything.
        print(f"[app] question failed: {type(exc).__name__}: {exc}", flush=True)
        st.session_state.messages.append(
            {"role": "assistant", "notice": GENERIC_ERROR}
        )
        return
    st.session_state.messages.append({"role": "assistant", "result": result})


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
    start_warmup()

    st.markdown(
        "<div class='hero'>"
        "<h1>🏦 HDFC Mutual Fund FAQ Assistant</h1>"
        "<p>Ask about HDFC scheme facts &mdash; expense ratios, exit loads, lock-in, SIP, benchmark, riskometer.</p>"
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

    # Ask first, render second. A question has to be recorded before the
    # transcript loop runs: if the loop went first, the new turn would be drawn
    # after everything below it and the examples would drift into the middle of
    # the history instead of staying under it.
    typed = st.chat_input("Ask a factual question about an HDFC Mutual Fund…")
    question = typed or st.session_state.pop("pending", None)
    if question:
        handle(question)

    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar="🧑"):
                st.markdown(message["content"])
        elif "result" in message:
            with st.chat_message("assistant", avatar="🏦"):
                render_answer_card(message["result"])
        else:
            # A turn that ended in a notice rather than an answer. Kept in the
            # transcript so the question asked is not silently dropped.
            with st.chat_message("assistant", avatar="🏦"):
                st.info(message["notice"])

    # Always visible, below the conversation, so one click starts a new topic at
    # any point in the session. They used to render only while the transcript
    # was empty, and because that check ran before handle() recorded anything,
    # the row appeared next to the first answer and then vanished on the next
    # interaction, which read as the layout glitching.
    st.markdown(
        "<div class='ex-heading'>💡 Try one of these</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for i, (col, example) in enumerate(zip(cols, EXAMPLE_QUESTIONS)):
        # on_click, not an inline `if button(...)`: a callback runs before the
        # script body, so `pending` is already set by the time the pop above
        # happens. Streamlit reruns only once per click, so setting pending
        # after that pop would leave the question queued and never answered.
        col.button(
            example,
            key=f"example_{i}",
            use_container_width=True,
            on_click=_queue_question,
            args=(example,),
        )


if __name__ == "__main__":
    main()