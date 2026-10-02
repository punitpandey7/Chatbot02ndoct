"""Grounded Groq generation (Phase 6).

Architecture §7 contract, enforced here in code rather than left to prose:

  1. Answer body            — at most MAX_ANSWER_SENTENCES sentences
  2. `Source: <url>`        — exactly one URL, copied from a retrieved
                               chunk's metadata. Never invented, never a
                               URL the model made up.
  3. `Last updated from sources: <date>`

The model is asked to cite by *chunk number*. That number is then resolved
against the chunks we actually sent, so a hallucinated index or a
hallucinated URL cannot reach the user: an out-of-range citation falls back
to the top-ranked chunk and is flagged, and any URL in the prose that is not
in the retrieved set is stripped.
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.config import (
    ABSTAIN_PHRASE,
    ENV_FILE,
    GROQ_API_KEY_ENV,
    GROQ_MAX_RETRIES,
    GROQ_MAX_TOKENS,
    GROQ_MODEL_DEFAULT,
    GROQ_MODEL_ENV,
    GROQ_REASONING_EFFORT,
    GROQ_TEMPERATURE,
    GROQ_TIMEOUT_SECONDS,
    MAX_ANSWER_SENTENCES,
    PROJECT_ROOT,
)

SYSTEM_PROMPT = """You are a mutual fund FAQ assistant for a classroom demo.

Hard rules:
- Answer ONLY from the numbered CONTEXT chunks below. They are the only truth.
- If the chunks do not contain the requested fact, reply exactly:
  {abstain}
  Do not fill the gap from memory, and do not guess a number.
- Copy figures (expense ratio, exit load, lock-in, minimum SIP, benchmark,
  riskometer) verbatim from the chunks. Never round, recompute, or convert.
- At most {max_sentences} sentences. No preamble, no restating the question.
- Never give investment advice. Never say what the user should buy, sell,
  switch, or hold. Never rank funds or compare returns.
- Never write a URL. Only finish with `SOURCE: <chunk number>`.

Output format, exactly two parts:
ANSWER: <your answer text>
SOURCE: <the number of the chunk that supports the answer>
"""

URL_RE = re.compile(r"https?://\S+")
SOURCE_RE = re.compile(r"SOURCE\s*[:\-]?\s*\[?(\d+)\]?", re.IGNORECASE)


class GenerationError(RuntimeError):
    """Raised for config/API problems; the caller must not fake an answer."""


def load_api_key() -> str:
    """Read GROQ_API_KEY from .env (or the environment). Never logs the value."""
    if ENV_FILE.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(ENV_FILE, override=False)
        except Exception:  # noqa: BLE001 — fall back to the OS environment
            pass
    key = (os.getenv(GROQ_API_KEY_ENV) or "").strip()
    if not key:
        raise GenerationError(
            f"{GROQ_API_KEY_ENV} is not set. Add it to {PROJECT_ROOT / '.env'} "
            f"(never commit that file). Retrieval still works without it: "
            f"python -m src.retrieve"
        )
    return key


def model_name() -> str:
    if ENV_FILE.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(ENV_FILE, override=False)
        except Exception:  # noqa: BLE001
            pass
    return (os.getenv(GROQ_MODEL_ENV) or "").strip() or GROQ_MODEL_DEFAULT


def build_context(hits: list[dict[str, Any]]) -> str:
    """Number the retrieved chunks so the citation can be resolved to real metadata."""
    blocks = []
    for i, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or {}
        blocks.append(
            "\n".join(
                [
                    f"[{i}] scheme={meta.get('scheme_name', 'n/a')} "
                    f"doc_type={meta.get('doc_type', 'n/a')} "
                    f"fetched={meta.get('retrieved_or_fetched_date', 'n/a')}",
                    f"url={meta.get('source_url', 'n/a')}",
                    (hit.get("text") or "").strip(),
                ]
            )
        )
    return "\n\n".join(blocks)


def trim_sentences(text: str, limit: int = MAX_ANSWER_SENTENCES) -> str:
    """Keep at most `limit` sentences (architecture §7 is a hard output rule)."""
    text = (text or "").strip()
    if not text:
        return ""
    # Split after ., ! or ? only when followed by whitespace and a capital/
    # digit, so "1.5%" and "e.g." do not create false sentence breaks.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])", text)
    if len(parts) <= limit:
        return text
    kept = " ".join(parts[:limit]).strip()
    return re.sub(r"\s+", " ", kept)


def _parse(raw: str) -> tuple[str, int | None]:
    """Split the model's reply into answer text and the cited chunk number."""
    text = (raw or "").strip()
    source_index: int | None = None
    match = None
    for match in SOURCE_RE.finditer(text):
        pass  # keep the last one
    if match:
        try:
            source_index = int(match.group(1))
        except ValueError:
            source_index = None
    answer = SOURCE_RE.sub("", text).strip()
    answer = re.sub(r"^ANSWER\s*[:\-]\s*", "", answer, flags=re.IGNORECASE).strip()
    return answer, source_index


def _strip_foreign_urls(text: str, allowed: set[str]) -> str:
    """Remove any URL the model wrote that is not in the retrieved chunk set."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;)")
        if url in allowed:
            return url
        return ""

    return re.sub(r"https?://\S+", _replace, text)


def _is_unsupported_argument(exc: BaseException) -> bool:
    """True only when the failure was about the argument we added.

    Timeouts, rate limits and transport errors must not be retried: each
    retry costs another full wait, and the caller is already on a hosted
    request with a short budget.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return False
    text = f"{type(exc).__name__} {exc}".lower()
    markers = ("reasoning_effort", "unsupported", "unrecognized", "unexpected", "invalid")
    return any(m in text for m in markers)


def _create_completion(client, prompt: str, user_payload: str):
    """Call Groq, asking reasoning models to skip their hidden trace.

    Some Groq models reject the `reasoning_effort` argument; retry once
    without it rather than failing the whole run.
    """
    kwargs = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": GROQ_TEMPERATURE,
        "max_tokens": GROQ_MAX_TOKENS,
    }
    import time

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            reasoning_effort=GROQ_REASONING_EFFORT, **kwargs
        )
    except GenerationError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Retry without the argument ONLY when the model rejected that
        # argument. Retrying a timeout or a rate limit would pay the full
        # wait a second time, which is what turns one slow reply into a
        # request the browser has already given up on.
        if not _is_unsupported_argument(exc):
            raise
        response = client.chat.completions.create(**kwargs)

    # Timing only. The upstream call is the one step that can be slow purely
    # because of the network, so it is worth separating from everything else.
    print(
        f"[generate] upstream call {time.perf_counter() - t0:.2f}s "
        f"({model_name()})",
        flush=True,
    )
    return response


def _message_text(response) -> str:
    """Pull the visible answer out of the completion, ignoring reasoning trace."""
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, KeyError):
        return ""
    text = getattr(message, "content", None)
    if text:
        return str(text)
    if isinstance(message, dict):
        content = message.get("content")
        if content:
            return str(content)
    return ""


def answer_from_chunks(
    question: str, hits: list[dict[str, Any]]
) -> dict[str, Any]:
    """Call Groq with the retrieved context and enforce the output contract."""
    if not hits:
        return {
            "answer_text": ABSTAIN_PHRASE,
            "citation_url": None,
            "last_updated": None,
            "refusal": False,
            "retrieved_urls": [],
            "abstained": True,
            "citation_fallback": False,
        }

    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover
        raise GenerationError("groq is not installed. pip install -r requirements.txt") from exc

    try:
        client = Groq(
            api_key=load_api_key(),
            timeout=GROQ_TIMEOUT_SECONDS,
            max_retries=GROQ_MAX_RETRIES,
        )
    except GenerationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(f"Could not create Groq client: {exc}") from exc

    prompt = SYSTEM_PROMPT.format(
        abstain=ABSTAIN_PHRASE, max_sentences=MAX_ANSWER_SENTENCES
    )
    user_payload = (
        f"CONTEXT:\n{build_context(hits)}\n\n"
        f"QUESTION: {question}\n\n"
        "Now reply with exactly:\nANSWER: ...\nSOURCE: <number>"
    )

    try:
        response = _create_completion(client, prompt, user_payload)
    except GenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — never fake an answer on API failure
        raise GenerationError(f"Groq request failed: {exc}") from exc

    raw = _message_text(response)
    if not raw.strip():
        # A blank reply must never be rendered as "not in the corpus": that
        # would be an invented answer. Report the real problem instead.
        raise GenerationError(
            f"{model_name()} returned an empty reply. Reasoning models can "
            f"exhaust max_tokens ({GROQ_MAX_TOKENS}) before answering — raise "
            f"GROQ_MAX_TOKENS or set GROQ_MODEL to a non-reasoning model."
        )

    answer, source_index = _parse(raw)
    if not answer.strip():
        # Only a citation line came back. Reporting "not in the corpus" here
        # would be a fabricated fact, so surface the contract break instead.
        raise GenerationError(
            f"{model_name()} returned a citation but no answer text. "
            f"Re-ask, or try a different GROQ_MODEL."
        )

    citation_fallback = False
    if source_index is not None and 1 <= source_index <= len(hits):
        cited = hits[source_index - 1]
    else:
        # The model gave no usable index. Fall back to the top-ranked chunk
        # rather than inventing a citation, and tell the caller it happened.
        cited = hits[0]
        citation_fallback = True

    cited_meta = cited.get("metadata") or {}
    citation_url = cited_meta.get("source_url")
    last_updated = cited_meta.get("retrieved_or_fetched_date")

    answer = trim_sentences(answer)
    allowed = {
        (h.get("metadata") or {}).get("source_url") for h in hits
    } - {None}
    answer = _strip_foreign_urls(answer, allowed)
    answer = re.sub(r"\s+", " ", answer).strip()

    abstained = ABSTAIN_PHRASE.lower() in answer.lower()
    if abstained:
        citation_url = None
        last_updated = None

    return {
        "answer_text": answer or ABSTAIN_PHRASE,
        "citation_url": citation_url,
        "last_updated": last_updated,
        "refusal": False,
        "retrieved_urls": [
            (h.get("metadata") or {}).get("source_url") for h in hits
        ],
        "abstained": abstained,
        "citation_fallback": citation_fallback,
        "model": model_name(),
    }