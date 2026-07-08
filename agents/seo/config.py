"""Lasting av konfigurasjon og felles stier."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Prosjektroten = to nivåer opp fra denne filen (agents/seo/config.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "input"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config() -> dict:
    """Leser config.yaml. Feiler tydelig hvis filen mangler."""
    if not CONFIG_PATH.exists():
        sys.exit(f"FEIL: Fant ikke konfigurasjonsfil: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
