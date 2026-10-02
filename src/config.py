"""Shared paths and RAG constants (Phase 1)."""

import os
from pathlib import Path

# Chroma phones home (posthog) when a client is created. On a hosted network
# that request can stall for minutes, and because it happens inside
# PersistentClient() the whole page hangs with no output at all. Nothing here
# is needed to answer a question, so opt out before chromadb is ever imported.
# Must run before `import chromadb`, which is why it lives in this module:
# config is imported first by every entry point.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
SOURCES_CSV = DATA_DIR / "sources.csv"
CHUNKS_TXT = DATA_DIR / "chunks.txt"
EMBEDDINGS_TXT = DATA_DIR / "embeddings.txt"
CHROMA_STATUS_TXT = DATA_DIR / "chroma_status.txt"
ENV_FILE = PROJECT_ROOT / ".env"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
CHROMA_COLLECTION = "hdfc_mf_faq"

# Model cache kept INSIDE the project directory rather than the user home.
# On a hosted container the home cache is not carried from build to runtime, so
# every cold start re-downloads ~90 MB and blocks the first question for ~22 s.
# Anchoring it to the project makes the download part of the deployment.
HF_HOME = str(DATA_DIR / ".hf_cache")

# Architecture default; Phase 2 inspects raw pages and may tune.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80

# Fragments shorter than this are section headers / separators left over by the
# recursive split ("Structured page data:"). They contain no fact but embed
# close to any question that names the scheme, so they crowd out real answers.
MIN_CHUNK_CHARS = 120

TOP_K = 4

# Used in Phase 5 refusals (public investor-education page).
# NOTE: the old /investor-corner/knowledge-center path now 404s; this is the
# live AMFI investor-education hub.
EDUCATIONAL_URL = "https://www.amfiindia.com/mutual-fund"

HTTP_TIMEOUT_SEC = 45
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Some Groww/Next.js pages intermittently serve a client-rendered shell with
# almost no text. Below this many characters a fetch counts as "blocked"
# and is retried instead of being written as a near-empty document.
MIN_USABLE_CHARS = 800
FETCH_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0

# --- Generation (Phase 6) -------------------------------------------------
# Key is read from .env only, never hardcoded and never logged.
GROQ_API_KEY_ENV = "GROQ_API_KEY"
GROQ_MODEL_ENV = "GROQ_MODEL"
GROQ_MODEL_DEFAULT = "openai/gpt-oss-120b"
GROQ_TEMPERATURE = 0.0  # factual Q&A: keep it deterministic
# gpt-oss / qwen are "reasoning" models: they spend tokens on a hidden trace
# before the answer. 300 left the answer empty. 1024 leaves room for the trace
# plus a 3-sentence reply.
GROQ_MAX_TOKENS = 1024
GROQ_REASONING_EFFORT = "none"  # suppress the trace when the model supports it

# The Groq SDK defaults to a 600 s timeout and 2 automatic retries. On a
# hosted free tier that means one slow upstream call can hold a request open
# for many minutes: the browser drops the connection long before, and the
# retry quietly pays the wait again. Keep the whole call inside the window a
# proxy will actually serve, and fail loudly instead of retrying.
GROQ_TIMEOUT_SECONDS = 25
GROQ_MAX_RETRIES = 0

# Architecture §7: answer body must be <= 3 sentences.
MAX_ANSWER_SENTENCES = 3

# Architecture §9 / §13: when the corpus does not contain the fact, abstain
# rather than guess. The generator enforces this phrase as a complete answer.
ABSTAIN_PHRASE = "This fact is not in the loaded sources."
