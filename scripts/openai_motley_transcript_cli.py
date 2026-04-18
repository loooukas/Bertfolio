#!/usr/bin/env python3
"""CLI wrapper for OpenAI-powered Motley Fool transcript link discovery."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finbert_site.openai_motley_search import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
