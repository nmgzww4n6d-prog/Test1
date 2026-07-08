"""
Analyse: å tenke som en senior digital markedsfører.

Her ligger de kommersielle vurderingene:
  * søkeintensjon (transaksjonell / informasjon / navigasjon)
  * kommersielt potensial per side
  * en ROI-modell: posisjon → CTR → klikk → leads → kroner

Alle antakelser hentes fra config.yaml slik at de er åpne og justerbare.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .datasources import Keyword, Page, url_to_path


# =============================================================================
# CTR-kurve etter posisjon (bransjegjennomsnitt, forenklet)
# =============================================================================
# Kilde-nøytral tommelfingerkurve. Justér gjerne mot egne GSC-tall over tid.
_CTR_BY_POSITION = {
    1: 0.28, 2: 0.15, 3: 0.11, 4: 0.08, 5: 0.06,
    6: 0.045, 7: 0.035, 8: 0.030, 9: 0.025, 10: 0.022,
}


def ctr_for_position(position: float) -> float:
    """Forventet klikkrate for en gitt snittposisjon."""
    if position <= 0:
        return 0.0
    p = int(round(position))
    if p in _CTR_BY_POSITION:
        return _CTR_BY_POSITION[p]
    if p <= 20:
        return 0.015  # side 1, nedre halvdel
    return 0.005      # side 2+


# =============================================================================
# Søkeintensjon
# =============================================================================
def classify_intent(text: str, config: dict) -> str:
    """Klassifiserer tekst som 'kommersiell', 'informasjon' eller 'navigasjon'."""
    text = text.lower()
    intent_cfg = config.get("intensjon", {})
    clinic = config.get("klinikknavn", "").lower()

    if clinic and clinic.split()[0] in text:
        return "navigasjon"
    for token in intent_cfg.get("kommersielle_signaler", []):
        if token.lower() in text:
            return "kommersiell"
    # Tjenestenavn i søket = kommersiell interesse.
    for service in config.get("prioriterte_tjenester", []):
        if service.lower().split(" (")[0] in text:
            return "kommersiell"
    for token in intent_cfg.get("informasjons_signaler", []):
        if token.lower() in text:
            return "informasjon"
    return "informasjon"


def touches_medical_topic(text: str, config: dict) -> bool:
    text = text.lower()
    return any(t.lower() in text for t in
               config.get("medisinske_temaer_som_krever_godkjenning", []))


def touches_priority(text: str, config: dict) -> bool:
    text = text.lower()
    prio = (config.get("prioriterte_tjenester", [])
            + config.get("prioriterte_byer", []))
    return any(p.lower().split(" (")[0] in text for p in prio)


def page_type(path: str, config: dict) -> str:
    """Grovklassifisering av sidetype ut fra URL-stien."""
    p = path.lower()
    if any(seg in p for seg in ("/blogg", "/artikkel", "/guide", "/rad")):
        return "informasjon"
    if "pris" in p or "kost" in p:
        return "kommersiell"
    if "kontakt" in p or "booking" in p or "time" in p:
        return "konvertering"
    for service in config.get("prioriterte_tjenester", []):
        if service.lower().split(" (")[0].replace(" ", "-") in p or \
           service.lower().split(" (")[0] in p:
            return "tjeneste"
    return "annet"


# =============================================================================
# ROI-modell
# =============================================================================
def value_per_click(intent: str, config: dict) -> float:
    """Forventet kroneverdi av ett ekstra organisk klikk, gitt intensjon."""
    e = config.get("okonomi", {})
    base = (e.get("besok_til_lead_rate", 0.03)
            * e.get("lead_til_pasient_rate", 0.30)
            * e.get("verdi_per_pasient", 45000))
    mult = config.get("intensjon", {}).get("verdi_multiplikator", {})
    factor = {
        "kommersiell": mult.get("kommersiell", 1.0),
        "informasjon": mult.get("informasjon", 0.15),
        "navigasjon": mult.get("navigasjon", 0.40),
    }.get(intent, 0.15)
    return base * factor


def annualize(period_value: float, config: dict) -> float:
    """Skalerer en verdi fra eksportperioden opp til årsbasis."""
    days = config.get("okonomi", {}).get("eksport_periode_dager", 28) or 28
    return period_value / days * 365.0


def estimate_uplift_value(
    impressions: float,
    current_clicks: float,
    current_position: float,
    intent: str,
    config: dict,
    target_position: float = 3.0,
    capture: float = 1.0,
) -> tuple[float, float]:
    """
    Estimerer (årlig merverdi i kr, årlige ekstra klikk) ved å løfte en side/et
    søkeord til `target_position`.

    `capture` < 1.0 brukes for usikre gevinster (f.eks. helt nytt innhold).
    """
    if impressions <= 0:
        return 0.0, 0.0
    potential_clicks = impressions * ctr_for_position(target_position) * capture
    incremental = max(0.0, potential_clicks - current_clicks)
    annual_clicks = annualize(incremental, config)
    return annual_clicks * value_per_click(intent, config), annual_clicks


# =============================================================================
# Action – en prioritert anbefaling med ROI
# =============================================================================
@dataclass
class Action:
    title: str
    rationale: str
    category: str            # kvikk_seo | sokeord | landingsside | innhold | konvertering
    expected_value: float    # årlig merverdi i kr
    effort: int              # 1–5
    confidence: float        # 0–1
    source: str
    needs_medical_review: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def priority(self) -> float:
        """Verdi per innsatsenhet, vektet med confidence. Høyere = viktigere."""
        return round((self.expected_value * self.confidence) / max(1, self.effort), 0)

    @property
    def effort_label(self) -> str:
        return {1: "Svært lav", 2: "Lav", 3: "Middels", 4: "Høy", 5: "Svært høy"}[self.effort]


# =============================================================================
# Kommersielt potensial per side
# =============================================================================
def score_page_potential(page: Page, config: dict) -> float:
    """
    Kommersielt potensial (0–100): hvor mye verdi som står på spill på siden.
    Kombinerer synlighet (visninger), sidetype og posisjonsrom.
    """
    ptype = page_type(page.path, config)
    type_weight = {
        "tjeneste": 1.0, "kommersiell": 1.0, "konvertering": 0.7,
        "informasjon": 0.4, "annet": 0.5,
    }[ptype]
    # Rom til å vokse: sider utenfor topp 3 har mest å hente.
    room = 0.0 if page.position and page.position <= 3 else 1.0
    visibility = min(1.0, page.impressions / 10000.0)
    return round(100 * type_weight * (0.6 * visibility + 0.4 * room), 1)


def rank_pages_by_potential(pages: dict[str, Page], config: dict) -> list[dict]:
    """Rangerer sider etter kommersielt potensial – CEO-vennlig oversikt."""
    rows = []
    for p in pages.values():
        intent = {"tjeneste": "kommersiell", "kommersiell": "kommersiell",
                  "konvertering": "kommersiell"}.get(page_type(p.path, config),
                                                      "informasjon")
        value, clicks = estimate_uplift_value(
            p.impressions, p.clicks, p.position or 15, intent, config)
        rows.append({
            "path": p.path,
            "type": page_type(p.path, config),
            "impressions": p.impressions,
            "position": p.position,
            "potential": score_page_potential(p, config),
            "upside_value": value,
            "upside_clicks": clicks,
        })
    rows.sort(key=lambda r: (r["potential"], r["upside_value"]), reverse=True)
    return rows


# =============================================================================
# Generering av prioriterte actions (ROI-rangert veikart)
# =============================================================================
def build_actions(pages: dict[str, Page], keywords: list[Keyword],
                  config: dict) -> list[Action]:
    """Lager ROI-rangerte anbefalinger fra sider og søkeord."""
    t = config["terskler"]
    lo, hi = t["striking_distance_min_posisjon"], t["striking_distance_max_posisjon"]
    actions: list[Action] = []

    # --- Sidebaserte actions (fra Search Console) ---
    for p in pages.values():
        if p.impressions <= 0:
            continue
        intent = {"tjeneste": "kommersiell", "kommersiell": "kommersiell",
                  "konvertering": "kommersiell"}.get(page_type(p.path, config),
                                                      "informasjon")
        medical = touches_medical_topic(p.path, config)

        # Lav CTR tross synlighet → tittel/meta-optimalisering.
        benchmark = ctr_for_position(p.position or 10)
        if (p.impressions >= t["min_visninger_for_ctr"] and p.position
                and 0 < p.ctr < benchmark):
            uplift_clicks = p.impressions * (benchmark - p.ctr)
            value = annualize(uplift_clicks, config) * value_per_click(intent, config)
            actions.append(Action(
                title=f"Skriv om title/meta på {p.path}",
                rationale=(f"{int(p.impressions)} visninger, men CTR {p.ctr*100:.1f}% "
                           f"mot forventet {benchmark*100:.1f}% på posisjon "
                           f"{p.position:.0f}. Ren klikk-gevinst uten ny rangering."),
                category="kvikk_seo", expected_value=value, effort=2, confidence=0.8,
                source="GSC (sider)", needs_medical_review=medical,
                extra={"path": p.path},
            ))

        # Striking distance → løft til topp 3.
        if p.position and lo <= p.position <= hi:
            value, clicks = estimate_uplift_value(
                p.impressions, p.clicks, p.position, intent, config)
            conf = 0.7 if intent == "kommersiell" else 0.6
            actions.append(Action(
                title=f"Løft {p.path} fra posisjon {p.position:.0f} til topp 3",
                rationale=(f"Snittposisjon {p.position:.1f} med {int(p.impressions)} "
                           f"visninger. ~{clicks:.0f} ekstra klikk/år ved topp 3."),
                category="kvikk_seo" if p.position <= 10 else "innhold",
                expected_value=value, effort=3 if p.position <= 10 else 4,
                confidence=conf, source="GSC (sider)",
                needs_medical_review=medical, extra={"path": p.path},
            ))

        # Høy trafikk, svak konvertering → konverteringsaction.
        if (p.conversions is not None and p.sessions >= 1500
                and p.conversions < p.sessions * 0.01):
            e = config.get("okonomi", {})
            # Verdi: å nå 1% konvertering på eksisterende trafikk.
            extra_leads = annualize(p.sessions * 0.01 - p.conversions, config)
            # Vekt ned informasjonssider: de konverterer sjelden direkte til pasient.
            intent_factor = (value_per_click(intent, config)
                             / value_per_click("kommersiell", config))
            value = extra_leads * e.get("lead_til_pasient_rate", 0.3) \
                * e.get("verdi_per_pasient", 45000) * intent_factor
            actions.append(Action(
                title=f"Øk konvertering på {p.path}",
                rationale=(f"{int(p.sessions)} økter, kun {int(p.conversions)} "
                           f"konverteringer (<1%). Tydeligere CTA og enklere skjema "
                           f"kan løfte til 1%+."),
                category="konvertering", expected_value=value, effort=3,
                confidence=0.55, source="GA4", needs_medical_review=medical,
                extra={"path": p.path},
            ))

    # --- Søkeordbaserte actions (fra GSC-queries + Semrush) ---
    seen_paths = set(pages.keys())
    for k in keywords:
        if k.volume < t["min_sokevolum"]:
            continue
        intent = classify_intent(k.term, config)
        medical = touches_medical_topic(k.term, config)

        if k.position and lo <= k.position <= hi:
            value, clicks = estimate_uplift_value(
                k.volume, k.clicks, k.position, intent, config, capture=0.6)
            actions.append(Action(
                title=f'Optimalisér for "{k.term}" (posisjon {k.position:.0f})',
                rationale=(f"Volum ~{int(k.volume)}, intensjon: {intent}. "
                           f"Ligger like utenfor topp 3 – lav-hengende frukt."),
                category="sokeord", expected_value=value,
                effort=2, confidence=0.7 if intent == "kommersiell" else 0.6,
                source="Søkeord", needs_medical_review=medical,
                extra={"keyword": k.term, "intent": intent, "url": k.url},
            ))
        elif not k.position or k.position > hi:
            # Rangerer dårlig/ikke → nytt innhold (håndteres som brief/landingsside
            # i strategy-modulen; her tar vi bare de kommersielle med tydelig verdi).
            if intent == "kommersiell":
                value, clicks = estimate_uplift_value(
                    k.volume, 0, 25, intent, config, capture=0.4)
                actions.append(Action(
                    title=f'Nytt innhold som rangerer for "{k.term}"',
                    rationale=(f"Kommersielt søk (volum ~{int(k.volume)}) uten sterk "
                               f"rangering i dag. Dedikert side kan fange etterspørselen."),
                    category="innhold", expected_value=value, effort=4,
                    confidence=0.45, source="Søkeord",
                    needs_medical_review=medical,
                    extra={"keyword": k.term, "intent": intent},
                ))

    actions.sort(key=lambda a: a.priority, reverse=True)
    return actions
