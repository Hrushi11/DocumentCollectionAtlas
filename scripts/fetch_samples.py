"""
Download the official IRS form templates we build fixtures from.

Templates are AcroForm PDFs (see docs/02). They are reproducible, so they are git-ignored;
`scripts/build_fixtures.py` fills them into the committed set under tests/fixtures/.

Run:  ./venv/Scripts/python.exe scripts/fetch_samples.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data" / "templates"

# Correct vintage per fixture need (the year is static text baked into each template):
#   W-2 TY2025  -> correct-year wages for the Rivera 2025 engagement
#   W-2 TY2023  -> the "wrong year" awkward case
#   1040 TY2024 -> last year's completed return (required for a 2025 filing)
#   1040 TY2023 -> the "wrong year" 1040 case
TEMPLATES_TO_FETCH = {
    "fw2--2025.pdf":   "https://www.irs.gov/pub/irs-prior/fw2--2025.pdf",
    "fw2--2023.pdf":   "https://www.irs.gov/pub/irs-prior/fw2--2023.pdf",
    "f1040--2024.pdf": "https://www.irs.gov/pub/irs-prior/f1040--2024.pdf",
    "f1040--2023.pdf": "https://www.irs.gov/pub/irs-prior/f1040--2023.pdf",
}

_UA = "Mozilla/5.0 (fixture-fetch; educational assignment)"


def fetch(name: str, url: str, dest_dir: Path) -> Path:
    dest = dest_dir / name
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {name}")
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"  fetched: {name}  ({len(data):,} bytes)")
    return dest


def main() -> int:
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    print(f"Fetching IRS templates -> {TEMPLATES.relative_to(ROOT)}")
    ok = True
    for name, url in TEMPLATES_TO_FETCH.items():
        try:
            fetch(name, url, TEMPLATES)
        except Exception as exc:  # noqa: BLE001 - report and continue
            ok = False
            print(f"  FAILED {name}: {exc}")
    print("done." if ok else "done with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
