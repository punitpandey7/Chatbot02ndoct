"""Load public pages listed in data/sources.csv (Phase 2)."""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.config import (
    FETCH_RETRIES,
    HTTP_TIMEOUT_SEC,
    HTTP_USER_AGENT,
    MIN_USABLE_CHARS,
    RAW_DIR,
    RETRY_BACKOFF_SEC,
    SOURCES_CSV,
)

FACT_KEY_HINTS = (
    "expense",
    "exitload",
    "exit_load",
    "sip",
    "lockin",
    "lock_in",
    "riskometer",
    "benchmark",
    "nav",
    "aum",
    "min",
    "charge",
    "tax",
    "statement",
    "category",
    "scheme",
    "fund",
    "ratio",
)

# Leaves too vague to index on their own; the parent key is prepended instead.
GENERIC_LEAVES = {
    "years",
    "months",
    "days",
    "value",
    "values",
    "amount",
    "name",
    "type",
    "code",
    "date",
    "text",
    "url",
    "id",
    "title",
    "detail",
    "details",
    "status",
    "flag",
    "is",
}


@dataclass
class LoadedDocument:
    url: str
    scheme_name: str
    doc_type: str
    fetched_at: str
    text: str
    raw_path: Path


def slug_for(url: str, scheme_name: str) -> str:
    if scheme_name and scheme_name.lower() != "n/a":
        base = scheme_name
    else:
        path = urlparse(url).path.strip("/") or "page"
        base = path.replace("/", "-")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return slug[:80] or "source"


def read_sources(path: Path = SOURCES_CSV) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _label_for(prefix: str) -> str:
    """Turn a flattened Next.js path into a short, readable label.

    The raw payload nests every fact under long dotted paths, e.g.
    ``props.pageProps.mfServerSideData.lock_in.years``. Inside a 500-char
    chunk that boilerplate outnumbers the actual fact, so MiniLM sees mostly
    property names. Keep the leaf, and borrow the parent only when the leaf
    is too generic to stand alone ("years" -> "lock_in years").
    """
    parts = [p for p in prefix.split(".") if p]
    if not parts:
        return "field"
    leaf = parts[-1]
    leaf_clean = leaf.lower().replace("-", "").replace("_", "")
    if len(parts) > 1 and leaf_clean in GENERIC_LEAVES:
        parent = re.sub(r"\[\d+\]$", "", parts[-2])
        if parent:
            return f"{parent} {leaf}"
    return leaf


def _flatten_json(obj, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_s = str(key)
            next_prefix = f"{prefix}.{key_s}" if prefix else key_s
            lines.extend(_flatten_json(value, next_prefix))
    elif isinstance(obj, list):
        if len(obj) > 40:
            return lines
        for i, value in enumerate(obj):
            lines.extend(_flatten_json(value, f"{prefix}[{i}]"))
    elif obj is None or isinstance(obj, bool):
        return lines
    else:
        text = str(obj).strip()
        if not text or text in {"None", "{}", "[]"}:
            return lines
        if len(text) > 2000:
            text = text[:2000] + "…"
        leaf = prefix.split(".")[-1].lower().replace("-", "").replace("_", "")
        if any(h in leaf or h in prefix.lower() for h in FACT_KEY_HINTS) or len(text) < 400:
            lines.append(f"{_label_for(prefix)}: {text}")
    return lines


def extract_next_data(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return ""
    try:
        payload = json.loads(tag.string)
    except json.JSONDecodeError:
        return ""
    lines = _flatten_json(payload)
    # Keep fact-like lines first, then a short unique tail.
    useful = []
    seen: set[str] = set()
    for line in lines:
        low = line.lower()
        if any(h in low for h in FACT_KEY_HINTS):
            if line not in seen:
                seen.add(line)
                useful.append(line)
    if len(useful) < 20:
        for line in lines:
            if line not in seen:
                seen.add(line)
                useful.append(line)
            if len(useful) >= 80:
                break
    return "\n".join(useful[:250])


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_page_text(html: str, scheme_name: str) -> str:
    parts = []
    if scheme_name and scheme_name.lower() != "n/a":
        parts.append(f"Scheme: {scheme_name}")
    next_data = extract_next_data(html)
    visible = extract_visible_text(html)
    if next_data:
        parts.append("Structured page data:")
        parts.append(next_data)
    if visible:
        parts.append("Visible page text:")
        # Cap noisy chrome; facts usually appear early on Groww SSR.
        parts.append(visible[:12000])
    return "\n\n".join(parts).strip()


def fetch_url(url: str) -> str:
    headers = {
        "User-Agent": HTTP_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SEC)
    response.raise_for_status()
    return response.text


def fetch_with_retry(url: str, attempts: int = FETCH_RETRIES) -> str:
    """GET with linear backoff; raises the last error if every attempt fails."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch_url(url)
        except Exception as exc:  # noqa: BLE001 — transient network/403/5xx
            last = exc
            if attempt < attempts:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise last if last else RuntimeError("no attempt made")


def read_cached_raw(raw_path: Path) -> str | None:
    """Reuse a previously saved good extract so a flaky refetch cannot shrink the corpus."""
    if not raw_path.exists():
        return None
    cached = raw_path.read_text(encoding="utf-8").strip()
    return cached if len(cached) >= MIN_USABLE_CHARS else None


def load_all() -> list[LoadedDocument]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = date.today().isoformat()
    docs: list[LoadedDocument] = []
    for row in read_sources():
        url = (row.get("url") or "").strip()
        scheme_name = (row.get("scheme_name") or "n/a").strip() or "n/a"
        doc_type = (row.get("doc_type") or "scheme_page").strip()
        if not url:
            continue
        slug = slug_for(url, scheme_name)
        raw_path = RAW_DIR / f"{slug}.txt"

        try:
            html = fetch_with_retry(url)
            text = extract_page_text(html, scheme_name)
            thin = len(text) < MIN_USABLE_CHARS
        except Exception as exc:  # noqa: BLE001 — hard failure: never lose a cached doc
            # A build on a clean machine (CI, Render) may be unable to reach the
            # source at all. The committed data/raw/ cache is the fallback.
            cached = read_cached_raw(raw_path)
            if cached is None:
                print(f"[load] skip {url}: {exc}")
                continue
            print(
                f"[load] fetch failed for {url} ({exc}); "
                f"reusing cached {raw_path.name} ({len(cached)} chars)"
            )
            text = cached
        else:
            if thin:
                # Blocked / JS-only shell. Never overwrite a good file with this.
                cached = read_cached_raw(raw_path)
                if cached is not None:
                    print(
                        f"[load] thin fetch ({len(text)} chars) for {url}; "
                        f"reusing cached {raw_path.name} ({len(cached)} chars)"
                    )
                    text = cached
                else:
                    print(
                        f"[load] skip {url}: thin extract ({len(text)} chars "
                        f"< {MIN_USABLE_CHARS}) after {FETCH_RETRIES} attempts"
                    )
                    continue
            else:
                raw_path.write_text(text, encoding="utf-8")
                print(f"[load] ok {url} -> {raw_path.name} ({len(text)} chars)")

        docs.append(
            LoadedDocument(
                url=url,
                scheme_name=scheme_name,
                doc_type=doc_type,
                fetched_at=fetched_at,
                text=text,
                raw_path=raw_path,
            )
        )
    return docs
