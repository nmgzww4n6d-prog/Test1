# AI Marketing Agent – MVP

Et lokalt proof-of-concept for et AI Marketing Agent-system for en
IVF/fertilitetsklinikk. Første versjon inneholder **én** agent:

> **SEO & Content Opportunity Agent** – leser CSV-eksporter og resonnerer som en
> senior digital markedsfører: finner sidene med størst kommersielt potensial,
> prioriterer tiltak etter forventet **ROI** (posisjon → CTR → klikk → kroner),
> oppdager innholdshull, foreslår nye landingssider, interne lenker, schema
> markup og FAQ, skriver **førsteutkast til innholdsbriefer**, og leverer alt som
> et **CEO-rettet vekstnotat** i Markdown.

Ingen API-integrasjoner er nødvendig for å komme i gang – agenten leser
CSV-filer du eksporterer manuelt og legger i en mappe.

---

## Prosjektstruktur

```
.
├── agents/
│   ├── seo_content_agent.py   # Entrypunkt (orkestrering) – kjør denne
│   └── seo/                    # Fagbibliotek (enkelt å lese og utvide)
│       ├── config.py           #   laster config.yaml + stier
│       ├── datasources.py      #   CSV-lesing + konsoliderte Page/Keyword-modeller
│       ├── analysis.py         #   søkeintensjon, kommersielt potensial, ROI-modell
│       ├── strategy.py         #   landingssider, interne lenker, schema, FAQ, briefer
│       └── report.py           #   bygger CEO-rapporten
├── config/
│   └── config.yaml            # Klinikk, økonomi (ROI), intensjon, terskler
├── data/
│   ├── input/                 # Legg CSV-eksportene dine her
│   └── output/                # (reservert for fremtidige mellomresultater)
├── examples/                  # Eksempel-CSV-er du kan teste med
├── reports/                   # Genererte rapporter havner her
├── .env.example               # Mal for API-nøkler (kopieres til .env)
├── requirements.txt
└── README.md
```

### Hva agenten leverer i rapporten

1. **Executive summary** – forretning først: adresserbart årlig potensial, topp 3 anbefalinger.
2. **Hvor pengene ligger** – sider rangert etter kommersielt potensial.
3. **Prioritert veikart** – tiltak rangert etter forventet ROI + quick wins for denne uken.
4. **Innholdshull og nye landingssider** – med estimert oppside.
5. **Intern lenkeplan** – kilde → mål → ankertekst.
6. **Schema markup** – per side, tilpasset helseinnhold (E-E-A-T / YMYL).
7. **FAQ** – bygget fra faktiske spørsmålssøk, sortert på intensjon.
8. **Innholdsbriefer** – førsteutkast (title tag, H1, disposisjon, FAQ, schema, CTA).
9. **Konvertering / UX-observasjoner**.
10. **Krever medisinsk godkjenning** – alt YMYL-innhold flagges.
11. **Forutsetninger og datagrunnlag** – ROI-antakelsene vises åpent.

### Slik prioriteres tiltak (ROI-modellen)

```
Forventet posisjon → CTR (bransjekurve) → ekstra klikk → leads → pasienter → kr/år
Prioritet = (forventet årlig verdi × sikkerhet) / innsats
```

Verdien per klikk vektes etter **søkeintensjon** (kommersiell > navigasjon >
informasjon). Alle økonomiske antakelser (verdi per pasient, konverteringsrater,
eksportperiode) settes i `config/config.yaml` og vises åpent i rapporten slik at
de kan utfordres. Tallene er **retningsgivende beslutningsstøtte, ikke budsjett**.

---

## Kom i gang

### 1. Installer avhengigheter

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. (Valgfritt) Opprett .env

Trengs **ikke** for MVP-en, men gjør klar for fremtidige API-er:

```bash
cp .env.example .env
# fyll inn nøkler senere – .env committes aldri (se .gitignore)
```

### 3. Tilpass konfigurasjonen

Åpne `config/config.yaml` og sett inn klinikknavn, prioriterte tjenester, byer,
kommersielle mål og medisinske temaer som krever ekstra kvalitetssikring.

---

## Hvordan legge inn CSV-filer

Legg CSV-eksportene i `data/input/`. Agenten kjenner igjen filtypen automatisk
ut fra kolonnene – filnavnet spiller ingen rolle. Følgende kilder støttes i dag:

| Kilde | Typiske kolonner | Brukes til |
|---|---|---|
| **Google Search Console – søkeord** | `Query, Clicks, Impressions, CTR, Position` | Søkeordmuligheter |
| **Google Search Console – sider** | `Page, Clicks, Impressions, CTR, Position` | Sider som bør forbedres |
| **GA4 – sider** | `Page path, Sessions, Views, Engagement rate, Conversions` | Konvertering/UX |
| **Semrush – posisjoner** | `Keyword, Position, Search Volume, URL, Traffic` | Søkeord / nytt innhold |

> **Tips:** CTR kan være enten `2.86%` eller `0.0286` – begge tolkes riktig.

**Vil du bare teste?** Kopier eksempelfilene inn:

```bash
cp examples/*.csv data/input/
```

Ikke-gjenkjente filer hoppes trygt over og listes under "Data limitations" i
rapporten.

---

## Hvordan kjøre agenten

```bash
python agents/seo_content_agent.py
```

Agenten:
1. leser alle `.csv` i `data/input/`,
2. finner og prioriterer muligheter,
3. skriver rapporten til `reports/ÅÅÅÅ-MM-DD-seo-content-report.md`.

### Kjøre på schedule (senere)

MVP-en kjøres manuelt. For automatisk kjøring kan du senere bruke f.eks. cron:

```cron
# Hver mandag kl. 07:00
0 7 * * 1  cd /sti/til/prosjekt && .venv/bin/python agents/seo_content_agent.py
```

…eller en GitHub Actions-workflow / Airflow-DAG. Se `TODO(schedule)` i agenten.

---

## Hvordan lese rapporten

Rapporten (`reports/ÅÅÅÅ-MM-DD-seo-content-report.md`) er skrevet som et
**vekstnotat til CEO**: den åpner med hvor verdien ligger og hva den er verdt,
og legger dokumentasjonen (lenkeplan, schema, briefer) etterpå. Seksjonene er
listet under "Hva agenten leverer i rapporten" lenger oppe.

Les den ovenfra og ned:
- **Seksjon 1–3** gir beslutningsgrunnlaget (potensial, ROI-veikart, quick wins).
- **Seksjon 4–8** er de konkrete leveransene å sende til byrå/innholdsteam.
- **Seksjon 10** er en sjekkliste for fagansvarlig før noe medisinsk publiseres.
- **Seksjon 11** viser antakelsene bak tallene – gå hit hvis noe ser for høyt ut.

---

## Videreutvikling

Agenten er bygget for å være enkel å utvide. Tydelige `TODO(...)`-kommentarer
nederst i `agents/seo_content_agent.py` markerer hvor neste steg kobles på:

### Koble på Slack

1. Opprett en **Incoming Webhook** i Slack og lim URL-en inn i `.env` som
   `SLACK_WEBHOOK_URL`.
2. Fjern kommentaren fra `TODO(slack)`-blokken i `main()` (bruker `requests`).
3. Rapporten (eller et sammendrag) postes til kanalen når agenten kjører.

### Koble på API-er (erstatter manuell CSV-eksport)

| Integrasjon | .env-nøkler | Erstatter |
|---|---|---|
| **GA4 Data API** | `GA4_PROPERTY_ID`, `GA4_CREDENTIALS_JSON` | GA4-CSV |
| **Search Console API** | `GSC_SITE_URL`, `GSC_CREDENTIALS_JSON` | GSC-CSV |
| **Semrush API** | `SEMRUSH_API_KEY` | Semrush-CSV |
| **WordPress REST API** | `WORDPRESS_BASE_URL`, `WORDPRESS_USERNAME`, `WORDPRESS_APP_PASSWORD` | Vite hva som allerede er publisert |

Mønsteret er å bytte ut CSV-innlesingen med en API-klient som returnerer en
`pandas.DataFrame` med de samme kolonnene – da fungerer resten av agenten uendret.

### Flere agenter

Neste agenter (f.eks. "Ad Performance Agent" for Google/Meta Ads, eller
"Email Agent" for Brevo) legges som nye filer i `agents/` og deler samme
`config/` og rapportmønster.

---

## Viktige prinsipper

- **Ingen hardkodede API-nøkler.** Alt sensitivt ligger i `.env` (aldri committet).
- **Medisinsk innhold (YMYL) skal alltid kvalitetssikres** av fagperson – agenten
  flagger, men publiserer aldri.
- Dette er en **MVP**: prioriter enkelhet og videreutvikling fremfor perfeksjon.
