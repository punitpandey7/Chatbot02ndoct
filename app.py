"""Repository-root entrypoint.

Hosted platforms that run `streamlit run <entrypoint>` look for a script at
the root of the repository. The application itself lives in `src/app.py`
alongside the rest of the pipeline; this file is only a launcher, so that the
module layout stays the same locally and in the terminal.

Why the import dance rather than `from src.app import main`: this file may be
executed as a bare script, in which case the repository root is not
automatically importable. Putting it on `sys.path` explicitly is what makes
`import src` work regardless of how it was launched.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app import main  # noqa: E402

if __name__ == "__main__":
    main()