"""Prompt template loading helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt_template(name: str) -> str:
    path = _PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()
