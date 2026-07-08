"""
Rapportgenerering – skrevet som en leveranse til CEO i en vekstbedrift.

Prinsipp: forretning først, SEO-detaljer etterpå. Åpne med hvor verdien ligger,
hva den er verdt, og hva vi anbefaler – deretter dokumentasjonen som støtter det.
"""

from __future__ import annotations

from datetime import date

from .analysis import Action, page_type


# =============================================================================
# Formatering
# =============================================================================
def fmt_kr(value: float, currency: str = "NOK") -> str:
    """450000 -> '450 000 kr'  ·  1200000 -> '1,2 mill. kr'."""
    suffix = "kr" if currency.upper() == "NOK" else currency
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".replace(".", ",") + f" mill. {suffix}"
    return f"{int(round(value)):,}".replace(",", " ") + f" {suffix}"


TYPE_LABELS = {
    "tjeneste": "Tjenesteside", "kommersiell": "Kommersiell",
    "konvertering": "Konvertering", "informasjon": "Innhold", "annet": "Annet",
}
CATEGORY_LABELS = {
    "kvikk_seo": "Quick-win SEO", "sokeord": "Søkeord",
    "landingsside": "Ny landingsside", "innhold": "Nytt innhold",
    "konvertering": "Konvertering",
}


# =============================================================================
# Hovedfunksjon
# =============================================================================
def build_report(*, config: dict, files: list, pages: dict, keywords: list,
                 page_potential: list, actions: list, landing_pages: list,
                 internal_links: list, schema: list, faqs: list,
                 briefs: list) -> str:
    currency = config.get("okonomi", {}).get("valuta", "NOK")
    clinic = config.get("klinikknavn", "Klinikken")
    today = date.today().isoformat()

    def kr(v):
        return fmt_kr(v, currency)

    top_actions = actions[:10]
    addressable = sum(a.expected_value for a in top_actions)
    medical_actions = [a for a in actions if a.needs_medical_review]
    quick_wins = [a for a in actions if a.effort <= 2][:5]

    md: list[str] = []
    A = md.append

    # ---------------------------------------------------------------- Header
    A(f"# Vekstnotat: Organisk synlighet & innhold – {clinic}")
    A(f"**Til:** CEO  ·  **Fra:** SEO & Content Agent  ·  **Dato:** {today}")
    A("")
    A("> Dette notatet peker på hvor den organiske trafikken kan skape mest "
      "forretningsverdi det neste kvartalet, hva det er verdt, og hva vi bør "
      "gjøre først. Tall er estimater bygget på åpne forutsetninger (se siste "
      "seksjon) – bruk dem til å prioritere, ikke som budsjett.")
    A("")

    # ------------------------------------------------------- Executive summary
    A("## 1. Executive summary")
    A("")
    A(f"- **Adresserbart årlig potensial (topp 10 tiltak): ~{kr(addressable)}.** "
      f"Retningsgivende merverdi hvis vi gjennomfører de høyest prioriterte "
      f"tiltakene.")
    A(f"- **Vi har «lav-hengende frukt».** {len(quick_wins)} tiltak krever lav "
      f"innsats og kan startes denne uken.")
    A(f"- **{len(landing_pages)} nye landingssider** og "
      f"**{len(faqs)} FAQ-muligheter** er identifisert for å fange udekket "
      f"etterspørsel.")
    A(f"- **Ansvarlig vekst:** {len(medical_actions)} tiltak berører medisinske "
      f"tema og er flagget for faglig godkjenning før publisering.")
    A("")
    if top_actions:
        A("**Mine tre viktigste anbefalinger nå:**")
        for i, a in enumerate(top_actions[:3], 1):
            A(f"{i}. **{a.title}** — est. {kr(a.expected_value)}/år, "
              f"innsats: {a.effort_label.lower()}.")
        A("")
    A(f"**Kommersielle mål dette støtter:** "
      f"{'; '.join(config.get('kommersielle_mal', []))}.")
    A("")

    # ------------------------------------------- Hvor det kommersielle rommet er
    A("## 2. Hvor pengene ligger (sider med størst kommersielt potensial)")
    A("")
    A("| # | Side | Type | Visninger | Posisjon | Potensial | Årlig oppside |")
    A("|--:|------|------|----------:|---------:|----------:|--------------:|")
    for i, r in enumerate(page_potential[:8], 1):
        pos = f"{r['position']:.0f}" if r["position"] else "–"
        A(f"| {i} | {r['path']} | {TYPE_LABELS.get(r['type'], r['type'])} "
          f"| {int(r['impressions'])} | {pos} | {r['potential']:.0f}/100 "
          f"| {kr(r['upside_value'])} |")
    A("")
    A("_«Potensial» vekter sidetype (penge- vs. innholdsside), synlighet og "
      "hvor mye rom det er til å klatre. «Oppside» er ROI-modellens estimat._")
    A("")

    # ----------------------------------------------- Prioritert veikart (ROI)
    A("## 3. Prioritert veikart (rangert etter forventet ROI)")
    A("")
    A("| Prioritet | Tiltak | Kategori | Årlig verdi | Innsats | Sikkerhet | Godkj. |")
    A("|----------:|--------|----------|------------:|:-------:|:---------:|:------:|")
    for a in top_actions:
        flag = "⚠️" if a.needs_medical_review else "–"
        A(f"| {a.priority:,.0f}".replace(",", " ")
          + f" | {a.title} | {CATEGORY_LABELS.get(a.category, a.category)} "
          f"| {kr(a.expected_value)} | {a.effort_label} | {a.confidence:.0%} | {flag} |")
    A("")
    A("### Hva vi gjør allerede denne uken (quick wins)")
    if quick_wins:
        for i, a in enumerate(quick_wins, 1):
            A(f"{i}. **{a.title}** — {a.rationale} _(est. {kr(a.expected_value)}/år)_")
    else:
        A("_Ingen lav-innsats-tiltak funnet i dette datagrunnlaget._")
    A("")

    # ------------------------------------------------------- Innholdshull / LP
    A("## 4. Innholdshull og nye landingssider")
    A("")
    if landing_pages:
        A("| Foreslått side | Målsøkeord | Intensjon | Årlig oppside | Godkj. |")
        A("|----------------|-----------|-----------|--------------:|:------:|")
        for lp in landing_pages[:10]:
            flag = "⚠️" if lp.needs_medical_review else "–"
            A(f"| {lp.title} (`{lp.url}`) | {lp.target_keyword} | {lp.intent} "
              f"| {kr(lp.expected_value)} | {flag} |")
        A("")
        A("_Rasjonale for de tre øverste:_")
        for lp in landing_pages[:3]:
            A(f"- **{lp.title}:** {lp.rationale}")
    else:
        A("_Ingen tydelige innholdshull i dette datagrunnlaget._")
    A("")

    # -------------------------------------------------------- Intern lenkeplan
    A("## 5. Intern lenkeplan")
    A("")
    A("Send autoritet fra trafikksterke innholdssider til kommersielle sider som "
      "ligger like utenfor topp 3.")
    A("")
    if internal_links:
        A("| Fra (kilde) | Til (mål) | Ankertekst |")
        A("|-------------|-----------|------------|")
        for l in internal_links[:12]:
            A(f"| {l.from_path} | {l.to_path} | «{l.anchor}» |")
    else:
        A("_Fant ikke nok side-/posisjonsdata til å foreslå interne lenker ennå._")
    A("")

    # -------------------------------------------------------- Schema markup
    A("## 6. Schema markup-anbefalinger")
    A("")
    A("Strukturerte data styrker E-E-A-T og gir rikere visninger i Google – "
      "spesielt viktig for helseinnhold (YMYL).")
    A("")
    A("| Side | Anbefalt schema | Hvorfor |")
    A("|------|-----------------|---------|")
    for s in schema:
        A(f"| {s.path} | `{'`, `'.join(s.schema_types)}` | {s.rationale} |")
    A("")

    # --------------------------------------------------------------- FAQ
    A("## 7. FAQ-forslag basert på søkeintensjon")
    A("")
    if faqs:
        A("Fra faktiske spørsmålssøk. Kommersielle spørsmål først (nærmest kjøp).")
        A("")
        A("| Spørsmål | Intensjon | Vinkel på svar | Godkj. |")
        A("|----------|-----------|----------------|:------:|")
        for f in faqs[:12]:
            flag = "⚠️" if f.needs_medical_review else "–"
            A(f"| {f.question} | {f.intent} | {f.answer_angle} | {flag} |")
    else:
        A("_Ingen spørsmålssøk funnet i datagrunnlaget._")
    A("")

    # ------------------------------------------------- Innholdsbriefer
    A("## 8. Innholdsbriefer – førsteutkast")
    A("")
    if not briefs:
        A("_Ingen nye sider prioritert høyt nok til å brife i denne kjøringen._")
    for b in briefs:
        A(f"### Brief: {b.title}")
        A("")
        A(f"- **URL:** `{b.url}`")
        A(f"- **Målsøkeord:** {b.target_keyword}  ·  **Intensjon:** {b.intent}")
        A(f"- **Estimert verdi:** {kr(b.expected_value)}/år  ·  "
          f"**Lengde:** {b.word_count}")
        A(f"- **Title tag:** {b.title_tag}")
        A(f"- **H1:** {b.h1}")
        A("- **Disposisjon (H2):**")
        for h in b.outline:
            A(f"  - {h}")
        if b.faqs:
            A("- **FAQ å inkludere:**")
            for q in b.faqs:
                A(f"  - {q}")
        A(f"- **Interne lenker:** {'; '.join(b.internal_links)}")
        A(f"- **Schema:** `{'`, `'.join(b.schema)}`")
        A(f"- **CTA:** {b.cta}")
        A(f"- ⚠️ **Godkjenning:** {b.notes}")
        A("")

    # ------------------------------------------------ Konvertering / UX
    conv = [a for a in actions if a.category == "konvertering"]
    A("## 9. Konvertering / UX-observasjoner")
    A("")
    if conv:
        for a in conv:
            A(f"- **{a.title}** — {a.rationale} _(est. {kr(a.expected_value)}/år)_")
    else:
        A("_Ingen tydelige konverteringsproblemer i GA4-dataene (eller GA4 mangler)._")
    A("")

    # -------------------------------- Medisinsk/menneskelig godkjenning
    A("## 10. Krever medisinsk / menneskelig godkjenning")
    A("")
    med_items = medical_actions + [b for b in briefs] \
        + [l for l in landing_pages if l.needs_medical_review]
    A("Fertilitet er YMYL-innhold. Følgende MÅ kvalitetssikres av fagperson før "
      "publisering – agenten foreslår, men publiserer aldri medisinske påstander:")
    A("")
    for a in medical_actions:
        A(f"- ⚠️ {a.title}")
    for lp in landing_pages:
        if lp.needs_medical_review:
            A(f"- ⚠️ Ny side: {lp.title}")
    if briefs:
        A(f"- ⚠️ Alle {len(briefs)} innholdsbriefer (suksessrater, risiko, "
          f"aldersgrenser krever faglig godkjenning).")
    if not (medical_actions or briefs
            or any(lp.needs_medical_review for lp in landing_pages)):
        A("- _Ingen elementer flagget i denne kjøringen._")
    A("")

    # ---------------------------------- Forutsetninger + datagrunnlag
    e = config.get("okonomi", {})
    recognized = {f["type"] for f in files if f["type"]}
    unknown = [f["name"] for f in files if not f["type"]]
    A("## 11. Forutsetninger og datagrunnlag")
    A("")
    A("**ROI-modellens forutsetninger (juster i `config/config.yaml`):**")
    A(f"- Verdi per pasient: {kr(e.get('verdi_per_pasient', 0))}")
    A(f"- Besøk → lead: {e.get('besok_til_lead_rate', 0):.1%}  ·  "
      f"Lead → pasient: {e.get('lead_til_pasient_rate', 0):.1%}")
    A(f"- Eksportene antas å dekke {e.get('eksport_periode_dager', 28)} dager "
      f"(effekt annualiseres ×{365 / (e.get('eksport_periode_dager', 28) or 28):.1f}).")
    A("- CTR-per-posisjon bygger på en forenklet bransjekurve, ikke egne tall.")
    A("")
    A("**Datagrunnlag:**")
    A(f"- Gjenkjente kilder: {', '.join(sorted(recognized)) if recognized else 'ingen'}.")
    for label, needed in [("Search Console (søkeord)", "gsc_queries"),
                          ("Search Console (sider)", "gsc_pages"),
                          ("GA4 (sider)", "ga4_pages"),
                          ("Semrush (posisjoner)", "semrush")]:
        if needed not in recognized:
            A(f"- Mangler {label} – enkelte analyser ble hoppet over eller svekket.")
    if unknown:
        A(f"- Ignorerte (ukjent format): {', '.join(unknown)}.")
    A("")
    A("**Forbehold:** Estimatene er retningsgivende beslutningsstøtte, ikke "
      "garantert avkastning. Verdier bør ikke summeres ukritisk (overlapp mellom "
      "tiltak). Alt medisinsk innhold skal gjennom faglig godkjenning.")
    A("")

    return "\n".join(md)
