#!/usr/bin/env python3
"""
SEO & Content Opportunity Agent (MVP)
=====================================

Første agent i et AI Marketing Agent-system for en IVF/fertilitetsklinikk.

Hva den gjør i denne versjonen:
  1. Leser CSV-eksporter som ligger i data/input/ (GA4, Search Console, Semrush).
  2. Identifiserer muligheter innen SEO og innhold.
  3. Prioriterer tiltak etter Impact, Effort og Confidence (ICE-score).
  4. Flagger muligheter som berører medisinske temaer for menneskelig godkjenning.
  5. Skriver en strukturert Markdown-rapport til reports/.

Kjør fra terminal:
    python agents/seo_content_agent.py

Dette er en MVP. Ingen API-er er koblet på ennå – se TODO-kommentarene nederst
for hvor fremtidige integrasjoner (GA4, Search Console, Semrush, WordPress,
Slack) skal inn.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Stier – alt regnes relativt til prosjektroten (mappen over /agents).
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "input"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


# =============================================================================
# Datamodell
# =============================================================================
@dataclass
class Opportunity:
    """En enkelt mulighet/tiltak agenten har funnet."""

    category: str          # "side", "sokeord", "nytt_innhold", "teknisk_konvertering"
    title: str
    detail: str
    impact: int            # 1–5 (høyere = større forventet effekt)
    effort: int            # 1–5 (høyere = mer arbeid)
    confidence: float      # 0.0–1.0 (hvor sikre vi er på at dette stemmer)
    source: str            # hvilken datakilde/fil muligheten kommer fra
    needs_medical_review: bool = False

    @property
    def ease(self) -> int:
        """Effort snudd om til "hvor lett" (1–5), for ICE-scoren."""
        return 6 - self.effort

    @property
    def score(self) -> float:
        """
        ICE-score = Impact × Ease × Confidence.
        Rekkevidde ~0–25. Brukes til å sortere muligheter.
        """
        return round(self.impact * self.ease * self.confidence, 1)


# =============================================================================
# Konfig og hjelpefunksjoner
# =============================================================================
def load_config() -> dict:
    """Leser config.yaml. Feiler tydelig hvis filen mangler."""
    if not CONFIG_PATH.exists():
        sys.exit(f"FEIL: Fant ikke konfigurasjonsfil: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_columns(df: pd.DataFrame) -> dict:
    """
    Lager en oppslagstabell {kolonnenavn_i_små_bokstaver: faktisk_kolonnenavn}
    slik at vi kan lese CSV-er uansett om Google skriver "Query" eller "query".
    """
    return {str(c).strip().lower(): c for c in df.columns}


def parse_rate(value) -> float:
    """
    Gjør om en CTR/rate-verdi til desimaltall.
    Håndterer "2.86%" -> 0.0286, "0.62" -> 0.62, tomme verdier -> 0.0.
    """
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
    # Tall > 1 tolkes som prosent (f.eks. 62 -> 0.62)
    return value / 100.0 if value > 1 else float(value)


def to_number(value) -> float:
    """Trygg konvertering til tall (tåler mellomrom og komma)."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def impact_from_volume(volume: float) -> int:
    """Grov skalering av forventet effekt basert på volum/visninger."""
    if volume >= 4000:
        return 5
    if volume >= 2000:
        return 4
    if volume >= 1000:
        return 3
    if volume >= 300:
        return 2
    return 1


# =============================================================================
# CSV-innlesing og typegjenkjenning
# =============================================================================
def detect_source_type(cols: dict) -> str | None:
    """
    Gjetter datatype ut fra hvilke kolonner som finnes.
    Returnerer en av: gsc_queries, gsc_pages, ga4_pages, semrush – ellers None.
    """
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


def load_input_files() -> list[dict]:
    """
    Leser alle CSV-filer i data/input og merker dem med gjenkjent type.
    Returnerer en liste av {name, type, df}.
    """
    files = []
    for path in sorted(INPUT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001 – MVP: vi logger og hopper over
            print(f"  ! Klarte ikke å lese {path.name}: {exc}")
            continue
        cols = normalize_columns(df)
        source_type = detect_source_type(cols)
        files.append({"name": path.name, "type": source_type, "df": df, "cols": cols})
        label = source_type or "ukjent"
        print(f"  ✓ {path.name}  ({label}, {len(df)} rader)")
    return files


# =============================================================================
# Muligheter: en analysefunksjon per datakilde
# =============================================================================
def touches_medical_topic(text: str, config: dict) -> bool:
    """Sjekker om en tekst berører et medisinsk tema som krever godkjenning."""
    text = text.lower()
    topics = config.get("medisinske_temaer_som_krever_godkjenning", [])
    return any(topic.lower() in text for topic in topics)


def touches_priority(text: str, config: dict) -> bool:
    """Sjekker om teksten treffer en prioritert tjeneste eller by."""
    text = text.lower()
    priorities = (
        config.get("prioriterte_tjenester", [])
        + config.get("prioriterte_byer", [])
    )
    return any(p.lower() in text for p in priorities)


def analyze_gsc_pages(item: dict, config: dict) -> list[Opportunity]:
    """Sider som bør forbedres (lav CTR, eller 'striking distance'-posisjon)."""
    df, cols, src = item["df"], item["cols"], item["name"]
    t = config["terskler"]
    opps: list[Opportunity] = []

    for _, row in df.iterrows():
        page = str(row[cols["page"]])
        impressions = to_number(row[cols["impressions"]])
        ctr = parse_rate(row[cols["ctr"]]) if "ctr" in cols else 0.0
        position = to_number(row[cols["position"]]) if "position" in cols else 0.0

        # Mange visninger, men lav klikkrate -> tittel/meta-optimalisering.
        if impressions >= t["min_visninger_for_ctr"] and 0 < ctr < t["lav_ctr_terskel"]:
            opps.append(Opportunity(
                category="side",
                title=f"Forbedre tittel/meta på {page}",
                detail=(
                    f"{int(impressions)} visninger men bare "
                    f"{ctr * 100:.1f}% CTR. Optimalisér title/meta description "
                    f"for flere klikk."
                ),
                impact=impact_from_volume(impressions),
                effort=2,
                confidence=0.8,
                source=src,
                needs_medical_review=touches_medical_topic(page, config),
            ))

        # Ligger like utenfor topp-plasseringene -> løft innhold/interne lenker.
        if t["striking_distance_min_posisjon"] <= position <= t["striking_distance_max_posisjon"]:
            impact = impact_from_volume(impressions)
            if touches_priority(page, config):
                impact = min(5, impact + 1)
            opps.append(Opportunity(
                category="side",
                title=f"Løft {page} fra posisjon {position:.0f}",
                detail=(
                    f"Ligger på snittposisjon {position:.1f} med "
                    f"{int(impressions)} visninger. Oppdater innhold og interne "
                    f"lenker for å nå topp 3."
                ),
                impact=impact,
                effort=3,
                confidence=0.7,
                source=src,
                needs_medical_review=touches_medical_topic(page, config),
            ))
    return opps


def analyze_keywords(item: dict, config: dict) -> list[Opportunity]:
    """Søkeordmuligheter fra GSC-queries eller Semrush-posisjoner."""
    df, cols, src = item["df"], item["cols"], item["name"]
    t = config["terskler"]
    opps: list[Opportunity] = []

    is_semrush = item["type"] == "semrush"
    kw_col = cols.get("keyword") or cols.get("query")
    if not kw_col:
        return opps

    for _, row in df.iterrows():
        keyword = str(row[kw_col])
        position = to_number(row[cols["position"]]) if "position" in cols else 0.0
        if is_semrush and "search volume" in cols:
            volume = to_number(row[cols["search volume"]])
        elif "impressions" in cols:
            volume = to_number(row[cols["impressions"]])
        else:
            volume = 0.0

        if volume < t["min_sokevolum"]:
            continue

        medical = touches_medical_topic(keyword, config)

        # Striking distance -> optimalisér eksisterende innhold for søkeordet.
        if t["striking_distance_min_posisjon"] <= position <= t["striking_distance_max_posisjon"]:
            impact = impact_from_volume(volume)
            if touches_priority(keyword, config):
                impact = min(5, impact + 1)
            opps.append(Opportunity(
                category="sokeord",
                title=f'Optimalisér for "{keyword}" (posisjon {position:.0f})',
                detail=(
                    f"Volum ~{int(volume)}, ligger på posisjon {position:.1f}. "
                    f"Lav-hengende frukt: styrk relevant side for dette søkeordet."
                ),
                impact=impact,
                effort=2,
                confidence=0.75,
                source=src,
                needs_medical_review=medical,
            ))

        # Rangerer dårlig (>20) tross volum -> vurdér nytt/utvidet innhold.
        elif position > t["striking_distance_max_posisjon"]:
            opps.append(Opportunity(
                category="nytt_innhold",
                title=f'Nytt/utvidet innhold for "{keyword}"',
                detail=(
                    f"Volum ~{int(volume)} men svak rangering "
                    f"(posisjon {position:.0f}). Vurdér dedikert side eller artikkel."
                ),
                impact=impact_from_volume(volume),
                effort=4,
                confidence=0.6,
                source=src,
                needs_medical_review=medical,
            ))
    return opps


def analyze_ga4(item: dict, config: dict) -> list[Opportunity]:
    """Konverterings- og UX-observasjoner fra GA4-sidedata."""
    df, cols, src = item["df"], item["cols"], item["name"]
    t = config["terskler"]
    opps: list[Opportunity] = []

    page_col = cols.get("page path") or cols.get("page")
    if not page_col:
        return opps

    for _, row in df.iterrows():
        page = str(row[page_col])
        sessions = to_number(row[cols["sessions"]]) if "sessions" in cols else 0.0
        engagement = parse_rate(row[cols["engagement rate"]]) if "engagement rate" in cols else None
        conversions = to_number(row[cols["conversions"]]) if "conversions" in cols else None

        # Høy trafikk + lav engasjementsrate -> UX-problem.
        if engagement is not None and sessions >= 1000 and engagement < t["lav_engasjementsrate"]:
            opps.append(Opportunity(
                category="teknisk_konvertering",
                title=f"Lav engasjementsrate på {page}",
                detail=(
                    f"{int(sessions)} økter men bare {engagement * 100:.0f}% "
                    f"engasjement. Sjekk lastetid, relevans og innholdsstruktur."
                ),
                impact=impact_from_volume(sessions),
                effort=3,
                confidence=0.65,
                source=src,
                needs_medical_review=touches_medical_topic(page, config),
            ))

        # Mye trafikk, få konverteringer -> konverteringsmulighet.
        if conversions is not None and sessions >= 1500 and conversions < sessions * 0.01:
            impact = impact_from_volume(sessions)
            if touches_priority(page, config):
                impact = min(5, impact + 1)
            opps.append(Opportunity(
                category="teknisk_konvertering",
                title=f"Svak konvertering på {page}",
                detail=(
                    f"{int(sessions)} økter, kun {int(conversions)} konverteringer "
                    f"(<1%). Vurdér tydeligere CTA og enklere kontaktskjema."
                ),
                impact=impact,
                effort=3,
                confidence=0.6,
                source=src,
                needs_medical_review=touches_medical_topic(page, config),
            ))
    return opps


def analyze_content_gaps(files: list[dict], config: dict) -> list[Opportunity]:
    """
    Innholdsgap fra konfig: prioriterte tjenester/byer vi ikke ser dekket i
    dataen. Lavere confidence siden dette er utledet, ikke observert direkte.
    """
    # Samle all tekst vi har sett (søkeord + sider) til én stor streng.
    seen = []
    for item in files:
        cols = item["cols"]
        for key in ("keyword", "query", "page", "page path", "url"):
            if key in cols:
                seen.extend(item["df"][cols[key]].astype(str).str.lower().tolist())
    corpus = " ".join(seen)

    opps: list[Opportunity] = []
    services = config.get("prioriterte_tjenester", [])
    cities = config.get("prioriterte_byer", [])

    # Tjenester som ikke nevnes i det hele tatt.
    for service in services:
        if service.lower() not in corpus:
            opps.append(Opportunity(
                category="nytt_innhold",
                title=f"Manglende innhold for tjeneste: {service}",
                detail=(
                    f"'{service}' er en prioritert tjeneste, men vises ikke i "
                    f"dataene. Vurdér en dedikert tjenesteside."
                ),
                impact=4,
                effort=4,
                confidence=0.5,
                source="config (utledet)",
                needs_medical_review=touches_medical_topic(service, config),
            ))

    # Lokale landingssider: tjeneste × by som ikke er dekket.
    for service in services[:3]:  # begrens til de tre viktigste for MVP-støy
        for city in cities:
            combo = f"{service} {city}".lower()
            if service.lower() in corpus and city.lower() not in corpus:
                opps.append(Opportunity(
                    category="nytt_innhold",
                    title=f"Lokal landingsside: {service} i {city}",
                    detail=(
                        f"Vi rangerer for '{service}', men '{city}' er ikke synlig. "
                        f"En lokal landingsside kan fange lokal etterspørsel."
                    ),
                    impact=3,
                    effort=3,
                    confidence=0.45,
                    source="config (utledet)",
                    needs_medical_review=touches_medical_topic(combo, config),
                ))
    return opps


# =============================================================================
# Orkestrering av analysen
# =============================================================================
def run_analysis(files: list[dict], config: dict) -> list[Opportunity]:
    """Kjører riktig analysefunksjon per fil og samler alle muligheter."""
    opps: list[Opportunity] = []
    for item in files:
        if item["type"] == "gsc_pages":
            opps += analyze_gsc_pages(item, config)
        elif item["type"] in ("gsc_queries", "semrush"):
            opps += analyze_keywords(item, config)
        elif item["type"] == "ga4_pages":
            opps += analyze_ga4(item, config)
    opps += analyze_content_gaps(files, config)

    # Sortér etter ICE-score, høyest først.
    opps.sort(key=lambda o: o.score, reverse=True)
    return opps


# =============================================================================
# Rapportgenerering (Markdown)
# =============================================================================
CATEGORY_LABELS = {
    "side": "Sider som bør forbedres",
    "sokeord": "Søkeordmuligheter",
    "nytt_innhold": "Nye artikler/sider",
    "teknisk_konvertering": "Teknisk / konvertering",
}


def _table(opps: list[Opportunity]) -> str:
    """Bygger en Markdown-tabell for en liste muligheter."""
    if not opps:
        return "_Ingen funn i denne kategorien._\n"
    lines = [
        "| Prioritet | Tiltak | Impact | Effort | Confidence | Kilde | Krever godkjenning |",
        "|---:|---|:---:|:---:|:---:|---|:---:|",
    ]
    for o in opps:
        flag = "⚠️ Ja" if o.needs_medical_review else "Nei"
        lines.append(
            f"| {o.score} | {o.title}<br><sub>{o.detail}</sub> "
            f"| {o.impact} | {o.effort} | {o.confidence:.2f} | {o.source} | {flag} |"
        )
    return "\n".join(lines) + "\n"


def build_report(opps: list[Opportunity], files: list[dict], config: dict) -> str:
    """Setter sammen hele Markdown-rapporten med den påkrevde strukturen."""
    today = date.today().isoformat()
    clinic = config.get("klinikknavn", "Klinikk")
    goals = config.get("kommersielle_mal", [])

    top5 = opps[:5]
    by_cat = {cat: [o for o in opps if o.category == cat] for cat in CATEGORY_LABELS}
    medical = [o for o in opps if o.needs_medical_review]

    recognized = [f for f in files if f["type"]]
    unknown = [f for f in files if not f["type"]]
    seen_types = {f["type"] for f in recognized}

    md: list[str] = []
    md.append(f"# SEO & Content Opportunity Report – {clinic}")
    md.append(f"_Generert: {today} · Agent: seo_content_agent (MVP)_\n")

    # --- Executive summary ---
    md.append("## Executive summary\n")
    md.append(
        f"Agenten analyserte **{len(recognized)}** gjenkjente datafil(er) og fant "
        f"**{len(opps)}** muligheter. Av disse er **{len(medical)}** flagget for "
        f"medisinsk/menneskelig godkjenning.\n"
    )
    if goals:
        md.append("**Kommersielle mål vi jobber mot:**")
        md += [f"- {g}" for g in goals]
        md.append("")
    if top5:
        md.append(
            f"Den høyest prioriterte muligheten er: **{top5[0].title}** "
            f"(score {top5[0].score}).\n"
        )

    # --- Top 5 opportunities ---
    md.append("## Top 5 opportunities\n")
    md.append(_table(top5))

    # --- SEO observations ---
    md.append("## SEO observations\n")
    md.append("### " + CATEGORY_LABELS["side"] + "\n")
    md.append(_table(by_cat["side"]))
    md.append("### " + CATEGORY_LABELS["sokeord"] + "\n")
    md.append(_table(by_cat["sokeord"]))

    # --- Content gaps ---
    md.append("## Content gaps\n")
    md.append(_table(by_cat["nytt_innhold"]))

    # --- Conversion / UX observations ---
    md.append("## Conversion / UX observations\n")
    md.append(_table(by_cat["teknisk_konvertering"]))

    # --- Recommended actions this week ---
    md.append("## Recommended actions this week\n")
    quick_wins = [
        o for o in opps
        if o.effort <= 2 and not o.needs_medical_review
    ][:5]
    if quick_wins:
        for i, o in enumerate(quick_wins, 1):
            md.append(f"{i}. **{o.title}** — {o.detail} _(score {o.score})_")
    else:
        md.append("_Ingen lav-terskel quick wins uten godkjenningsbehov denne uken._")
    md.append("")

    # --- Items requiring human/medical approval ---
    md.append("## Items requiring human/medical approval\n")
    if medical:
        md.append(
            "Følgende berører medisinske/YMYL-temaer og MÅ kvalitetssikres av "
            "fagperson før publisering:\n"
        )
        for o in medical:
            md.append(f"- ⚠️ **{o.title}** — {o.detail}")
    else:
        md.append("_Ingen av mulighetene ble flagget for medisinsk godkjenning._")
    md.append("")

    # --- Data limitations ---
    md.append("## Data limitations\n")
    md.append(
        "- Denne MVP-en leser kun manuelt eksporterte CSV-filer – ingen live "
        "API-data. Tallene er kun så ferske som eksportene."
    )
    md.append(
        "- Prioritering (Impact/Effort/Confidence) er regelbasert og heuristisk, "
        "ikke maskinlært. Bruk den som beslutningsstøtte, ikke fasit."
    )
    md.append(
        f"- Gjenkjente datakilder: "
        f"{', '.join(sorted(seen_types)) if seen_types else 'ingen'}."
    )
    for missing_label, needed in [
        ("Search Console (sider)", "gsc_pages"),
        ("Search Console (søkeord)", "gsc_queries"),
        ("GA4 (sider)", "ga4_pages"),
        ("Semrush (posisjoner)", "semrush"),
    ]:
        if needed not in seen_types:
            md.append(f"- Mangler {missing_label} – enkelte analyser ble hoppet over.")
    if unknown:
        md.append(
            "- Ikke-gjenkjente filer (ble ignorert): "
            + ", ".join(f["name"] for f in unknown) + "."
        )
    md.append("")

    return "\n".join(md)


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    # Last miljøvariabler (API-nøkler brukes ikke ennå, men lastes for fremtiden).
    load_dotenv(PROJECT_ROOT / ".env")

    # Sørg for at mappene finnes.
    for d in (INPUT_DIR, OUTPUT_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    config = load_config()
    print(f"Klinikk: {config.get('klinikknavn')}")
    print(f"Leser CSV-filer fra: {INPUT_DIR}")

    files = load_input_files()
    if not files:
        print(
            "\nIngen CSV-filer funnet i data/input/.\n"
            "Legg inn eksporter (eller kopier fra examples/) og kjør på nytt."
        )
        return

    opps = run_analysis(files, config)
    print(f"\nFant {len(opps)} muligheter.")

    report = build_report(opps, files, config)
    report_path = REPORTS_DIR / f"{date.today().isoformat()}-seo-content-report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Rapport skrevet til: {report_path}")

    # TODO(slack): Post rapporten til Slack via innkommende webhook.
    #   import requests
    #   webhook = os.getenv("SLACK_WEBHOOK_URL")
    #   if webhook:
    #       requests.post(webhook, json={"text": report[:3500]})  # Slack-grense


# =============================================================================
# TODO – fremtidige integrasjoner (erstatter manuell CSV-innlesing steg for steg)
# =============================================================================
# TODO(ga4):       Hent sidedata direkte via GA4 Data API i stedet for CSV.
#                  Bruk GA4_PROPERTY_ID + GA4_CREDENTIALS_JSON fra .env.
# TODO(gsc):       Hent søkeord/side-data via Search Console API.
#                  Bruk GSC_SITE_URL + GSC_CREDENTIALS_JSON fra .env.
# TODO(semrush):   Hent posisjoner/volum via Semrush API (SEMRUSH_API_KEY).
# TODO(wordpress): Hent publiserte sider/innlegg via WordPress REST API for å
#                  vite hva som allerede finnes (WORDPRESS_BASE_URL m.fl.).
# TODO(slack):     Post rapporten automatisk til en Slack-kanal (SLACK_WEBHOOK_URL).
# TODO(schedule):  Kjør agenten på schedule (cron / GitHub Actions / Airflow).

if __name__ == "__main__":
    main()
