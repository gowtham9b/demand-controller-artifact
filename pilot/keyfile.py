"""Load the Cursor API key from ~/workspace/paper-revisions/.env without printing it.

Accepts either `CURSOR_API_KEY=...` or a file containing only the key.
"""

import re
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def cursor_api_key() -> str:
    text = ENV_FILE.read_text().strip()
    m = re.search(r"^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*[\"']?([^\"'\s]+)", text, re.M)
    if m:
        return m.group(1)
    if text and "\n" not in text and "=" not in text:
        return text
    raise RuntimeError(f"No CURSOR_API_KEY found in {ENV_FILE}")
