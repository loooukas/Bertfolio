#!/usr/bin/env python3
"""CLI wrapper for OpenAI-powered Motley Fool transcript link discovery."""

from finbert_site.openai_motley_search import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
