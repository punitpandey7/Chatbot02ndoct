"""Route questions before retrieve/generate. Do not store user text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import EDUCATIONAL_URL

FACTUAL = "factual"
REFUSE_ADVICE = "refuse_advice"
REFUSE_RETURNS = "refuse_returns"
REFUSE_PII = "refuse_pii"

PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.I)
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b")
OTP_RE = re.compile(r"\b(?:otp|one[-\s]?time\s+password)\b", re.I)
ACCOUNT_RE = re.compile(r"\b(?:folio|account)\s*(?:no|number|#)[:\s]*[A-Z0-9]{6,}\b", re.I)

ADVICE_RE = re.compile(
    r"\b(should i|shall i|do i buy|buy or sell|sell now|switch to|invest in|"
    r"recommend|is it a good (time|fund)|portfolio|allocate)\b",
    re.I,
)
RETURNS_RE = re.compile(
    r"\b(best (fund|return)|highest return|cagr|1[-\s]?year return|"
    r"3[-\s]?year return|5[-\s]?year return|compare returns|which (fund )?performed)\b",
    re.I,
)


@dataclass(frozen=True)
class GuardDecision:
    label: str
    message: str
    educational_url: str | None = None


def _pii_hit(question: str) -> bool:
    return bool(
        PAN_RE.search(question)
        or AADHAAR_RE.search(question)
        or EMAIL_RE.search(question)
        or PHONE_RE.search(question)
        or OTP_RE.search(question)
        or ACCOUNT_RE.search(question)
    )


def classify(question: str) -> str:
    text = (question or "").strip()
    if not text:
        return FACTUAL
    if _pii_hit(text):
        return REFUSE_PII
    if ADVICE_RE.search(text):
        return REFUSE_ADVICE
    if RETURNS_RE.search(text):
        return REFUSE_RETURNS
    return FACTUAL


def decide(question: str) -> GuardDecision:
    label = classify(question)
    if label == REFUSE_PII:
        return GuardDecision(
            label=label,
            message=(
                "This assistant does not accept or store personal identifiers "
                "(PAN, Aadhaar, account numbers, OTPs, email, or phone). "
                "Ask a scheme fact without personal data."
            ),
            educational_url=EDUCATIONAL_URL,
        )
    if label == REFUSE_ADVICE:
        return GuardDecision(
            label=label,
            message=(
                "Facts-only. This assistant cannot say whether you should buy, "
                "sell, or switch a fund. Read official scheme documents and "
                "unbiased investor education instead."
            ),
            educational_url=EDUCATIONAL_URL,
        )
    if label == REFUSE_RETURNS:
        return GuardDecision(
            label=label,
            message=(
                "This assistant does not compute or compare returns. "
                "Use the official factsheet for past performance figures."
            ),
            educational_url=EDUCATIONAL_URL,
        )
    return GuardDecision(label=FACTUAL, message="", educational_url=None)


def _self_check() -> None:
    # Refusals are PRD §13 items 8-10; the factual rows are items 1-7 and
    # must stay routable so they actually reach Chroma.
    cases = [
        ("Should I buy HDFC Small Cap now?", REFUSE_ADVICE),
        ("Which of these five funds has the best 3-year return?", REFUSE_RETURNS),
        ("My PAN is ABCDE1234F, what’s my tax?", REFUSE_PII),
        ("What is the lock-in for HDFC ELSS Tax Saver?", FACTUAL),
        (
            "Expense ratio of HDFC Large Cap Fund Direct Growth?",
            FACTUAL,
        ),
        (
            "Exit load of HDFC Small Cap Fund Direct Growth?",
            FACTUAL,
        ),
        (
            "Minimum SIP for HDFC Flexi Cap / Equity Fund Direct Growth?",
            FACTUAL,
        ),
        (
            "Riskometer / risk level of HDFC Balanced Advantage Fund?",
            FACTUAL,
        ),
        ("Benchmark of HDFC Large Cap Fund?", FACTUAL),
        (
            "How to download capital-gains / account statement?",
            FACTUAL,
        ),
    ]
    failed = 0
    for question, expected in cases:
        got = classify(question)
        ok = got == expected
        failed += int(not ok)
        print(f"[{'ok' if ok else 'FAIL'}] {expected} -> {got} | {question}")
    if failed:
        raise SystemExit(f"guardrails self-check failed: {failed} case(s)")
    print("guardrails self-check passed")


if __name__ == "__main__":
    _self_check()
