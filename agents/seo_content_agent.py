#!/usr/bin/env python3
"""
SEO & Content Opportunity Agent
===============================

Første agent i et AI Marketing Agent-system for en IVF/fertilitetsklinikk.

Agenten leser CSV-eksporter (GA4, Search Console, Semrush) fra data/input og
tenker som en senior digital markedsfører:

  1. Slår sammen kildene til ett bilde per side og per søkeord.
  2. Finner sidene med størst kommersielt potensial.
  3. Prioriterer tiltak etter forventet ROI (posisjon → CTR → klikk → kroner).
  4. Oppdager innholdshull og foreslår nye landingssider.
  5. Foreslår interne lenker, schema markup og FAQ basert på søkeintensjon.
  6. Skriver førsteutkast til innholdsbriefer.
  7. Flagger medisinsk (YMYL) innhold for faglig godkjenning.
  8. Leverer alt som en CEO-rettet Markdown-rapport i reports/.

Kjør fra terminal:
    python agents/seo_content_agent.py

Selve fagkunnskapen ligger i pakken agents/seo/ (config, datasources, analysis,
strategy, report). Denne filen er kun orkestrering.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Gjør pakken agents/seo/ importerbar uansett hvor skriptet kjøres fra.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo.analysis import build_actions, rank_pages_by_potential
from seo.config import INPUT_DIR, OUTPUT_DIR, PROJECT_ROOT, REPORTS_DIR, load_config
from seo.datasources import build_keywords, build_pages, load_input_files
from seo.report import build_report
from seo.strategy import (
    build_content_briefs,
    suggest_faqs,
    suggest_internal_links,
    suggest_landing_pages,
    suggest_schema,
)


def main() -> None:
    # API-nøkler lastes for fremtidige integrasjoner (brukes ikke ennå).
    load_dotenv(PROJECT_ROOT / ".env")

    for d in (INPUT_DIR, OUTPUT_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    config = load_config()
    print(f"Klinikk: {config.get('klinikknavn')}")
    print(f"Leser CSV-filer fra: {INPUT_DIR}")

    files = load_input_files()
    if not files:
        print("\nIngen CSV-filer funnet i data/input/.\n"
              "Legg inn eksporter (eller kopier fra examples/) og kjør på nytt.")
        return

    # --- Konsolider datagrunnlaget ---
    pages = build_pages(files)
    keywords = build_keywords(files)
    print(f"\nKonsolidert: {len(pages)} sider, {len(keywords)} søkeord.")

    # --- Analyse (senior markedsfører-logikken) ---
    page_potential = rank_pages_by_potential(pages, config)
    actions = build_actions(pages, keywords, config)

    # --- Strategiske leveranser ---
    landing_pages = suggest_landing_pages(pages, keywords, config)
    internal_links = suggest_internal_links(pages, keywords, config)
    schema = suggest_schema(pages, config)
    faqs = suggest_faqs(keywords, config)
    briefs = build_content_briefs(landing_pages, faqs, config)

    print(f"Fant {len(actions)} prioriterte tiltak, "
          f"{len(landing_pages)} landingssideforslag, {len(faqs)} FAQ-er.")

    # --- Rapport ---
    report = build_report(
        config=config, files=files, pages=pages, keywords=keywords,
        page_potential=page_potential, actions=actions,
        landing_pages=landing_pages, internal_links=internal_links,
        schema=schema, faqs=faqs, briefs=briefs,
    )
    report_path = REPORTS_DIR / f"{date.today().isoformat()}-seo-content-report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Rapport skrevet til: {report_path}")

    # TODO(slack): Post rapporten (eller et sammendrag) til Slack via webhook.
    #   import requests
    #   webhook = os.getenv("SLACK_WEBHOOK_URL")
    #   if webhook:
    #       requests.post(webhook, json={"text": report[:3500]})


# =============================================================================
# TODO – fremtidige integrasjoner (erstatter manuell CSV-innlesing steg for steg)
# =============================================================================
# TODO(ga4):       Hent sidedata via GA4 Data API (GA4_PROPERTY_ID, credentials).
# TODO(gsc):       Hent søkeord/side-data via Search Console API.
# TODO(semrush):   Hent posisjoner/volum via Semrush API (SEMRUSH_API_KEY).
# TODO(wordpress): Hent publiserte sider via WordPress REST API (vite hva som finnes).
# TODO(slack):     Post rapporten automatisk til en Slack-kanal (SLACK_WEBHOOK_URL).
# TODO(schedule):  Kjør agenten på schedule (cron / GitHub Actions / Airflow).

if __name__ == "__main__":
    main()
