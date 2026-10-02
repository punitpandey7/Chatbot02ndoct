"""HDFC mutual fund FAQ RAG chatbot (class demo)."""

import sys

# The Windows console defaults to cp1252, which cannot encode characters that
# really appear in scheme pages (rupee sign U+20B9, smart quotes, en-dashes).
# Any CLI that prints retrieved chunk text would crash on print(). Reconfiguring
# the streams once, here, fixes it for every `python -m src.*` entry point.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - exotic stream types
            pass
