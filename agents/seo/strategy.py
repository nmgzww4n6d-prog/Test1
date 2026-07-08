"""
Strategiske leveranser – det en senior markedsfører faktisk gir fra seg:

  * forslag til nye landingssider
  * intern lenkeplan
  * schema markup-anbefalinger
  * FAQ basert på søkeintensjon
  * førsteutkast til innholdsbriefer

Alt bygger på de konsoliderte Page/Keyword-modellene og ROI-modellen i analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .analysis import (
    classify_intent,
    estimate_uplift_value,
    page_type,
    touches_medical_topic,
    value_per_click,
    annualize,
)
from .datasources import Keyword, Page, url_to_path


def _slugify(text: str) -> str:
    text = text.lower().strip()
    replacements = {"æ": "ae", "ø": "oe", "å": "aa", " ": "-"}
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")


# =============================================================================
# 1. Forslag til nye landingssider
# =============================================================================
@dataclass
class LandingPage:
    title: str
    url: str
    target_keyword: str
    intent: str
    expected_value: float
    rationale: str
    needs_medical_review: bool = False


def suggest_landing_pages(pages: dict[str, Page], keywords: list[Keyword],
                          config: dict) -> list[LandingPage]:
    """
    To kilder til nye landingssider:
      a) prioriterte tjeneste × by-kombinasjoner som ikke er dekket
      b) kommersielle søkeord med volum men uten sterk egen side
    """
    domain = config.get("domene", "").rstrip("/")
    corpus = " ".join(list(pages.keys())
                      + [k.term.lower() for k in keywords]).lower()
    suggestions: list[LandingPage] = []

    # a) Lokale landingssider: tjeneste × by.
    services = config.get("prioriterte_tjenester", [])
    cities = config.get("prioriterte_byer", [])
    for service in services[:4]:
        svc = service.split(" (")[0]
        for city in cities:
            if svc.lower() in corpus and city.lower() not in corpus:
                kw = f"{svc.lower()} {city.lower()}"
                # Ingen volumdata på kombinasjonen → konservativt estimat.
                value, _ = estimate_uplift_value(
                    500, 0, 25, "kommersiell", config, capture=0.4)
                suggestions.append(LandingPage(
                    title=f"{service} i {city}",
                    url=f"{domain}/{_slugify(svc)}-{_slugify(city)}",
                    target_keyword=kw, intent="kommersiell",
                    expected_value=value,
                    rationale=(f"Vi er synlige for '{svc}', men ikke i {city}. "
                               f"Lokal landingsside fanger lokal etterspørsel og "
                               f"styrker lokal SEO."),
                    needs_medical_review=touches_medical_topic(kw, config),
                ))

    # b) Kommersielle søkeord uten sterk rangering.
    t = config["terskler"]
    for k in keywords:
        if k.volume < t["min_sokevolum"]:
            continue
        intent = classify_intent(k.term, config)
        if intent != "kommersiell":
            continue
        if k.position and k.position <= t["striking_distance_max_posisjon"]:
            continue  # allerede rimelig synlig – håndteres som optimalisering
        value, _ = estimate_uplift_value(
            k.volume, 0, 25, intent, config, capture=0.4)
        suggestions.append(LandingPage(
            title=k.term.capitalize(),
            url=f"{domain}/{_slugify(k.term)}",
            target_keyword=k.term, intent=intent, expected_value=value,
            rationale=(f"Kommersielt søk (volum ~{int(k.volume)}) uten dedikert, "
                       f"velrangert side. Egen landingsside kan eie søket."),
            needs_medical_review=touches_medical_topic(k.term, config),
        ))

    # Dedup på URL og sortér etter verdi.
    unique = {s.url: s for s in suggestions}
    return sorted(unique.values(), key=lambda s: s.expected_value, reverse=True)


# =============================================================================
# 2. Intern lenkeplan
# =============================================================================
@dataclass
class InternalLink:
    from_path: str
    to_path: str
    anchor: str
    rationale: str


def suggest_internal_links(pages: dict[str, Page], keywords: list[Keyword],
                           config: dict) -> list[InternalLink]:
    """
    Send autoritet fra trafikksterke informasjonssider til pengesider som ligger
    like utenfor topp 3. Klassisk grep for å løfte kommersielle sider.
    """
    t = config["terskler"]
    lo, hi = t["striking_distance_min_posisjon"], t["striking_distance_max_posisjon"]

    # Kilder: informasjonssider med mest trafikk.
    sources = sorted(
        [p for p in pages.values() if page_type(p.path, config) == "informasjon"],
        key=lambda p: (p.sessions or p.clicks), reverse=True)

    # Mål: kommersielle/tjeneste-sider i striking distance.
    targets = [p for p in pages.values()
               if page_type(p.path, config) in ("tjeneste", "kommersiell")
               and p.position and lo <= p.position <= hi]

    def anchor_for(path: str) -> str:
        slug = path.rstrip("/").split("/")[-1].replace("-", " ")
        return slug or path

    links: list[InternalLink] = []
    for target in sorted(targets, key=lambda p: p.impressions, reverse=True):
        # Velg opptil 2 relevante kildesider (del et ord med målet, ellers topp-trafikk).
        target_tokens = set(target.path.replace("-", " ").replace("/", " ").split())
        chosen = [s for s in sources
                  if target_tokens & set(s.path.replace("-", " ").replace("/", " ").split())
                  and s.path != target.path][:2]
        if not chosen:
            chosen = [s for s in sources if s.path != target.path][:2]
        for s in chosen:
            links.append(InternalLink(
                from_path=s.path, to_path=target.path,
                anchor=anchor_for(target.path),
                rationale=(f"'{s.path}' har trafikk; en kontekstuell lenke med anker "
                           f"«{anchor_for(target.path)}» styrker målsiden som ligger "
                           f"på posisjon {target.position:.0f}."),
            ))
    return links


# =============================================================================
# 3. Schema markup-anbefalinger
# =============================================================================
@dataclass
class SchemaSuggestion:
    path: str
    schema_types: list
    rationale: str


_SCHEMA_BY_TYPE = {
    "tjeneste": (["MedicalProcedure", "MedicalWebPage", "FAQPage", "BreadcrumbList"],
                 "Tjenesteside: beskriv prosedyren strukturert og legg ved FAQ."),
    "kommersiell": (["Service", "Offer", "FAQPage", "BreadcrumbList"],
                    "Kommersiell side: marker tjeneste/pris og vanlige spørsmål."),
    "konvertering": (["MedicalClinic", "LocalBusiness", "BreadcrumbList"],
                     "Kontakt/booking: marker klinikk, adresse og åpningstider."),
    "informasjon": (["MedicalWebPage", "Article", "FAQPage", "BreadcrumbList"],
                    "Fagartikkel: marker som medisinsk innhold med forfatter/kilde (E-E-A-T)."),
    "annet": (["WebPage", "BreadcrumbList"], "Generell side."),
}


def suggest_schema(pages: dict[str, Page], config: dict,
                   top_n: int = 8) -> list[SchemaSuggestion]:
    """Foreslår schema markup for de mest synlige sidene."""
    ranked = sorted(pages.values(), key=lambda p: p.impressions, reverse=True)[:top_n]
    out = []
    for p in ranked:
        types, why = _SCHEMA_BY_TYPE[page_type(p.path, config)]
        out.append(SchemaSuggestion(path=p.path, schema_types=types, rationale=why))
    # Alltid anbefal organisasjons-schema på forsiden/globalt.
    out.append(SchemaSuggestion(
        path="/ (globalt)",
        schema_types=["MedicalOrganization", "MedicalClinic", "WebSite"],
        rationale="Global E-E-A-T: definer klinikken som medisinsk organisasjon."))
    return out


# =============================================================================
# 4. FAQ basert på søkeintensjon
# =============================================================================
@dataclass
class FAQItem:
    question: str
    topic: str
    intent: str
    answer_angle: str
    needs_medical_review: bool


_QUESTION_MARKERS = ("hva", "hvordan", "hvorfor", "hvor", "når", "kan",
                     "hvem", "er det", "koster", "pris")


def suggest_faqs(keywords: list[Keyword], config: dict) -> list[FAQItem]:
    """Bygger FAQ-forslag fra spørsmåls- og prislignende søk."""
    faqs: list[FAQItem] = []
    seen = set()
    for k in keywords:
        term = k.term.lower().strip()
        is_question = any(term.startswith(m) or f" {m} " in f" {term} "
                          for m in _QUESTION_MARKERS)
        if not is_question or term in seen:
            continue
        seen.add(term)
        intent = classify_intent(term, config)
        medical = touches_medical_topic(term, config)
        # Gjør søket om til et naturlig spørsmål.
        question = k.term.strip()
        if not question.endswith("?"):
            question = question[0].upper() + question[1:] + "?"
        angle = ("Kort, konkret svar + lenke til relevant tjenesteside og CTA."
                 if intent == "kommersiell"
                 else "Forklarende svar som bygger tillit og leder videre i trakten.")
        if medical:
            angle = "MÅ skrives/godkjennes av fagperson. " + angle
        faqs.append(FAQItem(question=question, topic=term, intent=intent,
                            answer_angle=angle, needs_medical_review=medical))
    # Kommersielle spørsmål først.
    faqs.sort(key=lambda f: 0 if f.intent == "kommersiell" else 1)
    return faqs


# =============================================================================
# 5. Innholdsbriefer (førsteutkast)
# =============================================================================
@dataclass
class ContentBrief:
    title: str
    url: str
    target_keyword: str
    intent: str
    expected_value: float
    word_count: str
    title_tag: str
    h1: str
    outline: list          # liste av H2-er
    faqs: list             # spørsmål (str)
    internal_links: list   # anchor/målsti-hint (str)
    schema: list
    cta: str
    needs_medical_review: bool
    notes: str


def _related_questions(keyword: str, faqs: list[FAQItem], limit: int = 4) -> list:
    base = keyword.lower().split()[0]
    hits = [f.question for f in faqs if base in f.question.lower()]
    return hits[:limit] if hits else [f.question for f in faqs[:limit]]


def build_content_briefs(landing_pages: list[LandingPage], faqs: list[FAQItem],
                         config: dict, top_n: int = 3) -> list[ContentBrief]:
    """Skriver førsteutkast til briefer for de mest verdifulle nye sidene."""
    clinic = config.get("klinikknavn", "Klinikken")
    briefs: list[ContentBrief] = []
    for lp in landing_pages[:top_n]:
        kw = lp.target_keyword
        commercial = lp.intent == "kommersiell"
        outline = [
            f"Hva er {kw}? (kort, klar definisjon)",
            f"Hvem passer {kw} for?",
            "Slik foregår behandlingen – steg for steg",
            "Hva koster det? (prisintervall + hva som inngår)",
            f"Hvorfor velge {clinic}? (E-E-A-T: fagfolk, resultater, trygghet)",
            "Neste steg: book en uforpliktende konsultasjon",
        ]
        if not commercial:
            outline = [
                f"Hva er {kw}?",
                "Vanlige spørsmål og misforståelser",
                "Hva sier forskningen / hva er normalt",
                f"Når bør du kontakte en klinikk som {clinic}?",
                "Neste steg",
            ]
        briefs.append(ContentBrief(
            title=lp.title,
            url=lp.url,
            target_keyword=kw,
            intent=lp.intent,
            expected_value=lp.expected_value,
            word_count="900–1400 ord" if commercial else "1200–1800 ord",
            title_tag=f"{lp.title} | {clinic}"[:60],
            h1=lp.title,
            outline=outline,
            faqs=_related_questions(kw, faqs),
            internal_links=[
                f"Lenke fra relevant fagartikkel med anker «{kw}»",
                "Lenke til /kontakt eller booking (CTA)",
            ],
            schema=(["MedicalWebPage", "Service", "FAQPage", "BreadcrumbList"]
                    if commercial else
                    ["MedicalWebPage", "Article", "FAQPage"]),
            cta=("Book konsultasjon" if commercial else "Last ned guide / book konsultasjon"),
            needs_medical_review=lp.needs_medical_review or True,  # helseinnhold: alltid
            notes=("Medisinske påstander (suksessrater, risiko, aldersgrenser) må "
                   "faktasjekkes og godkjennes av fagansvarlig før publisering."),
        ))
    return briefs
