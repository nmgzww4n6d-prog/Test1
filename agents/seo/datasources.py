"""
Innlesing av CSV-eksporter og bygging av konsoliderte datamodeller.

En senior markedsfører ser ikke på én rapport av gangen – hun slår sammen
Search Console, GA4 og Semrush til ett bilde per side og per søkeord. Det er
det denne modulen gjør: bygger `Page`- og `Keyword`-objekter på tvers av kilder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import INPUT_DIR


# =============================================================================
# Parsing-hjelpere
# =============================================================================
def normalize_columns(df: pd.DataFrame) -> dict:
    """{kolonne_i_små_bokstaver: faktisk_kolonnenavn} – tåler ulik skrivemåte."""
    return {str(c).strip().lower(): c for c in df.columns}


def parse_rate(value) -> float:
    """'2.86%' -> 0.0286, '0.62' -> 0.62, 62 -> 0.62, tomt -> 0.0."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if value.endswith("%"):
            try:
                return float(value[:-1]) / 100.0
            except ValueError:
                return 0.0
        try:
            value = float(value)
        except ValueError:
            return 0.0
    return value / 100.0 if value > 1 else float(value)


def to_number(value) -> float:
    """Trygg tallkonvertering (tåler mellomrom og komma)."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def url_to_path(url: str) -> str:
    """Normaliserer full URL til sti, slik at GSC og GA4 kan matches.

    'https://klinikk.no/ivf/' -> '/ivf'   ·   '/ivf' -> '/ivf'
    """
    url = str(url).strip()
    if url.startswith("http"):
        # fjern skjema + domene
        parts = url.split("/", 3)
        url = "/" + parts[3] if len(parts) > 3 else "/"
    if not url.startswith("/"):
        url = "/" + url
    if len(url) > 1:
        url = url.rstrip("/")
    return url


# =============================================================================
# Datamodeller
# =============================================================================
@dataclass
class Page:
    """Én side, konsolidert på tvers av Search Console og GA4."""

    path: str
    url: str = ""
    impressions: float = 0.0
    clicks: float = 0.0
    ctr: float = 0.0
    position: float = 0.0
    sessions: float = 0.0
    engagement_rate: float | None = None
    conversions: float | None = None


@dataclass
class Keyword:
    """Ett søkeord, konsolidert på tvers av Search Console og Semrush."""

    term: str
    volume: float = 0.0
    position: float = 0.0
    clicks: float = 0.0
    impressions: float = 0.0
    url: str = ""
    sources: set = field(default_factory=set)


# =============================================================================
# CSV-innlesing + typegjenkjenning
# =============================================================================
def detect_source_type(cols: dict) -> str | None:
    """Gjetter datatype ut fra kolonnene."""
    if "query" in cols and "impressions" in cols:
        return "gsc_queries"
    if "page" in cols and "impressions" in cols:
        return "gsc_pages"
    if "page path" in cols and ("engagement rate" in cols or "sessions" in cols):
        return "ga4_pages"
    if "keyword" in cols and "url" in cols and (
        "search volume" in cols or "position" in cols
    ):
        return "semrush"
    return None


def load_input_files(verbose: bool = True) -> list[dict]:
    """Leser alle CSV-er i data/input og merker dem med gjenkjent type."""
    files = []
    for path in sorted(INPUT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            if verbose:
                print(f"  ! Klarte ikke å lese {path.name}: {exc}")
            continue
        cols = normalize_columns(df)
        source_type = detect_source_type(cols)
        files.append({"name": path.name, "type": source_type, "df": df, "cols": cols})
        if verbose:
            print(f"  ✓ {path.name}  ({source_type or 'ukjent'}, {len(df)} rader)")
    return files


# =============================================================================
# Konsolidering
# =============================================================================
def build_pages(files: list[dict]) -> dict[str, Page]:
    """Slår sammen GSC-sider og GA4-sider til én Page per sti."""
    pages: dict[str, Page] = {}

    def get(path: str) -> Page:
        return pages.setdefault(path, Page(path=path))

    for item in files:
        cols = item["cols"]
        df = item["df"]

        if item["type"] == "gsc_pages":
            for _, row in df.iterrows():
                url = str(row[cols["page"]])
                p = get(url_to_path(url))
                p.url = url
                p.impressions = to_number(row[cols["impressions"]])
                p.clicks = to_number(row[cols["clicks"]]) if "clicks" in cols else 0.0
                p.ctr = parse_rate(row[cols["ctr"]]) if "ctr" in cols else 0.0
                p.position = to_number(row[cols["position"]]) if "position" in cols else 0.0

        elif item["type"] == "ga4_pages":
            page_col = cols.get("page path") or cols.get("page")
            for _, row in df.iterrows():
                p = get(url_to_path(str(row[page_col])))
                p.sessions = to_number(row[cols["sessions"]]) if "sessions" in cols else 0.0
                if "engagement rate" in cols:
                    p.engagement_rate = parse_rate(row[cols["engagement rate"]])
                if "conversions" in cols:
                    p.conversions = to_number(row[cols["conversions"]])
    return pages


def build_keywords(files: list[dict]) -> list[Keyword]:
    """Slår sammen GSC-queries og Semrush-posisjoner til unike søkeord."""
    kws: dict[str, Keyword] = {}

    def get(term: str) -> Keyword:
        key = term.strip().lower()
        return kws.setdefault(key, Keyword(term=term.strip()))

    for item in files:
        cols = item["cols"]
        df = item["df"]

        if item["type"] == "gsc_queries":
            for _, row in df.iterrows():
                k = get(str(row[cols["query"]]))
                k.impressions = to_number(row[cols["impressions"]])
                k.clicks = to_number(row[cols["clicks"]]) if "clicks" in cols else 0.0
                if "position" in cols:
                    k.position = to_number(row[cols["position"]])
                k.sources.add("gsc")

        elif item["type"] == "semrush":
            for _, row in df.iterrows():
                k = get(str(row[cols["keyword"]]))
                if "search volume" in cols:
                    k.volume = to_number(row[cols["search volume"]])
                if "position" in cols:
                    # Semrush-posisjon er ofte mer presis enn GSC-snitt.
                    k.position = to_number(row[cols["position"]]) or k.position
                if "url" in cols:
                    k.url = str(row[cols["url"]])
                k.sources.add("semrush")

    # Fall tilbake til visninger som volum-proxy der Semrush-volum mangler.
    for k in kws.values():
        if k.volume == 0.0 and k.impressions > 0:
            k.volume = k.impressions
    return list(kws.values())
