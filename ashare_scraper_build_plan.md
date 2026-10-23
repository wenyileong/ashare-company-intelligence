# A-Share Company Intelligence Scraper
## Consolidated Build Plan and Data Pipeline

**Current implemented release:** v2.0.6 (patch from the first live runs of the v2.0.4 engine; end state; section 18, with fixes from the live runs; section 18.14)  
**Next planned release:** v2.1 (desktop language toggle, extraction speed, polish; `docs/plan_v2.1.md`, with the approved glossary `docs/glossary_zh_CN.md`). See section 18.14
**Status:** v2.0.6 (23 October 2026): listing dates read board by board, extraction with progress and resume (migration 0005), finer catalogue splits and short-window splits; 224 tests pass on Linux Python 3.12 (two skips), 215 on Python 3.13 (nine skips), 221 against PostgreSQL 16 (five skips) and 222 on Windows CPython 3.12 under Wine (four skips); live confirmation pending (`CHANGELOG.md`). v2.0.5 (22 October 2026) prepares the public release: the user agent names the repository, the request rate has a ceiling of 2 per second, and the repository has a disclaimer, CONTRIBUTING.md and SECURITY.md; 192 tests pass on Linux Python 3.12 (two skips) and 184 on Python 3.13 (eight skips). v2.0.4 implemented and verified offline: 184 tests pass on Linux Python 3.12 (two skips), 181 against PostgreSQL 16 (five skips, three of them the SQLite-only migration fixtures), 182 on Windows CPython 3.12 under Wine (four skips) and 176 on Python 3.13 (eight skips). Confirmed live by the author so far: the company list (5,574 companies), CNINFO's 3,000-result limit, resume by day, the quote list, and a live self-test passing all 20 checks. The finer catalogue splits of v2.0.4 still need a live run (`CHANGELOG.md`, "Still to confirm live"). The installer is unsigned because no certificate was available.

> **Correction to the v0.7 status line.** v0.7 was recorded as "consolidated and verified", but its session factory returned a `sessionmaker` rather than a session, so every database operation failed. Its tests covered only pure helper functions. The defects and fixes are listed under v0.7.1 below.

---

## 1. Project objective

Build a source-agnostic, research-grade company intelligence system for China A-share listed companies.

The system is designed to move from the security master through primary disclosure documents and structured financial, market, ownership and corporate information while preserving enough provenance to make every material observation auditable.

The intended universe is:

- SSE Main Board
- SSE STAR Market
- SZSE Main Board
- SZSE ChiNext

The system is not intended to be a conventional webpage scraper. It is a provenance-preserving data acquisition and normalisation pipeline.

---

## 2. Current architecture

```text
                     ┌──────────────────────┐
                     │   A-share Universe   │
                     │  CNINFO + exchange   │
                     │      validation      │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │    Disclosures       │
                     │ CNINFO announcements │
                     │ PDFs / documents     │
                     └──────────┬───────────┘
                                │
               ┌────────────────┼────────────────┐
               │                │                │
               ▼                ▼                ▼
        ┌────────────┐   ┌────────────┐   ┌────────────┐
        │ Financials │   │ Market Data│   │ Ownership  │
        │ XBRL/PDF   │   │ OHLCV etc. │   │ & Capital  │
        └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                     ┌──────────────────────┐
                     │ Validation /         │
                     │ Reconciliation       │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │ Research Dataset /   │
                     │ Company Intelligence │
                     └──────────────────────┘
```

---

## 3. Implemented releases

### v0.1 — Initial architecture

Established:

- SQLite persistence
- HTTP client
- source adapters
- provenance concept
- CLI structure
- basic company/security models

### v0.2 — Master-universe layer

Added:

- CSV universe import
- exchange inference
- board inference
- universe validation
- SSE/SZSE/CNINFO adapters
- tests

### v0.3 — Automatic A-share universe

CNINFO machine-readable stock mappings became the primary acquisition mechanism.

Supported:

- SSE Main
- STAR
- SZSE Main
- ChiNext
- ordinary A-share filtering
- company/security records
- `orgId` preservation
- source-last-seen tracking

SSE/SZSE remain exchange-level validation/reference sources.

### v0.4 — CNINFO disclosure layer

Added:

- announcement catalogue
- company-specific disclosure queries
- annual/interim/quarterly report classification
- announcement IDs
- announcement dates
- Chinese titles and types
- original document URLs
- optional document downloads
- SHA-256 document hashing
- raw-response preservation
- idempotent disclosure storage

### v0.5 — Financial facts

Added:

- canonical financial-fact model
- XBRL/iXBRL extraction path
- PDF-text fallback
- reporting-period inference
- FY/Q1/H1/Q3 handling
- unit normalisation
- statement classification
- source document/page provenance
- XBRL-tag preservation
- extraction method
- confidence
- balance-sheet validation

Core metrics include:

- revenue
- cost of revenue
- operating profit
- profit before tax
- net profit
- parent-attributable profit
- assets
- liabilities
- equity
- cash
- receivables
- inventory
- operating cash flow
- investing cash flow
- financing cash flow
- R&D expenditure
- employees

### v0.6 — Market data

Added:

- daily OHLCV
- previous close
- price changes
- percentage changes
- turnover
- turnover rate where available
- adjusted/unadjusted series
- market-cap snapshots
- shares/float shares
- P/E and P/B fields
- raw provider payload hashing
- market-data provenance
- public-feed adapter
- CSV import path for licensed datasets

Market data is explicitly labelled by provider. Public third-party data is not represented as official exchange data.

### v0.7 — Ownership and capital structure

Added:

- ownership observations
- shareholder ranking
- shares held
- ownership percentage
- tradable shares
- pledged shares
- restricted shares
- controlling-shareholder flag
- actual-controller flag
- relationship information
- capital-structure observations
- total shares
- tradable shares
- restricted shares
- A/B/H share categories
- treasury shares
- observation dates
- source document/page
- extraction method
- confidence

The ownership model is time-series based rather than a static largest-shareholder field.

### v0.7.1 — Corrections

These corrections were required before any v0.7 layer could run:

- session factory returned a `sessionmaker`, so all reads and writes failed;
- the CNINFO disclosure adapter was constructed without a user agent;
- financial extraction filtered on report kinds that the classifier never produces;
- reporting-period inference let body text override the title, and the annual fallback used the wrong year;
- XBRL extraction ignored contexts, `scale` and `sign`;
- the PDF heuristic matched labels inside longer labels and captured years and note references;
- the employee count was scaled by the currency unit;
- balance-sheet validation mixed facts across documents;
- ownership quantities in 万股/亿股 were not scaled, missing flags were recorded as False, and 股东大会 notices were treated as ownership disclosures;
- configuration paths were frozen at import time;
- schema migration added for new columns (`init-db` upgrades v0.7 databases in place).

Ownership and capital observations also gained a `validation_status` and a `validate-ownership` pass. Financial facts gained `source_label` and `source_context` provenance.

### v0.8 — Corporate actions and distributions

Implemented as specified in section 9:

- a `corporate_actions` table with the full core model, plus `base_share_count`, `shares_affected`, `total_cash_amount`, `listing_date`, `fiscal_period`, `tax_basis` and `validation_status`;
- title classification into fifteen action types and a seven-state lifecycle;
- a document-text parser for standard PRC disclosure phrasing, including date tables;
- `TITLE_ONLY` observations for events whose quantities are not machine-readable;
- a CSV import for authorised vendor data;
- capital reconciliation (`capital_reconciliations`), with deduplication across disclosures, buyback/treasury handling, conversion-period dating and per-window status;
- CNINFO corporate-action category codes, pending live verification.

### v0.9 — Regulatory and legal events; desktop application

Implemented as specified in section 10:

- a `regulatory_events` table with every field in the specification (event type, authority, event date, company, affected security, status, source document, primary-source URL, document hash, legal/regulatory classification), plus authority name, document and case numbers, the company's role, amount in dispute, fines (total and on the company), confiscation, violation categories, cited provisions and per-party sanctions;
- thirteen event types under thirteen legal classifications, separating the instrument from the procedural stage;
- a parser for penalty and disciplinary decisions (sanctions by party, cited statutory provisions with Chinese-numeral conversion, violation categories), litigation and arbitration (court or arbitral body, case number, amount, role), audit opinions, listing status and suspensions;
- three sources: regulator documents supplied by the user (file or URL; no crawling or endpoint guessing), CNINFO company announcements, and authorised CSV data;
- a point-in-time `regulatory-status` profile whose derived states cite the events they rest on.

Also in v0.9:

- a Tkinter desktop interface (`AShareScraper.exe`) and a console executable (`ashare-cli.exe`), sharing one PyInstaller build, with a Windows build script and a GitHub Actions workflow; every GUI run is logged with its equivalent CLI command;
- CSV export of any table (`export`);
- a fixed UTC+8 conversion replacing `zoneinfo`, which would otherwise have failed on Windows without `tzdata`;
- removal of the unused `pandas` and `pydantic` requirements.

### v1.0 — Integrated company intelligence

Implemented as specified in section 11, together with the items carried forward from v0.8 and v0.9:

- **Research interface:** company profiles; point-in-time historical financial series (as originally reported or latest, with vintages and restatement marks); ownership and capital-structure history; corporate-action and regulatory timeline; market-history statistics; disclosure search; full-text search of downloaded documents; source-document inspection with hash verification; cross-company comparison; CSV, SQLite and optional Parquet export; reproducible, logged, read-only research queries; versioned dataset releases with hashed manifests; a self-contained HTML company report.
- **Validation (section 7):** all five stages integrated in `validate-all`. Stage 3 cross-document checks (restatement/discrepancy, interim vs annual, ownership vs capital, distribution terms) and stage 4 cross-source checks (prices, capital) write `validation_flags`. Stage 5 confidence classes are applied in every view.
- **Carried forward:** XBRL comparatives (enabling restatement detection); event linking with recorded basis; tradable-share reconciliation.
- **Desktop application:** redesigned sidebar interface in workflow order, with explanatory notes, field hints and input checks; Windows encoding fix for Chinese output on redirected streams.

### v1.1 — Industry classification and management (section 12, first part)

- **Industry:** `industry_classifications` as point-in-time observations under any scheme. Imports validate CSRC 2012 codes (sections and division ranges) and SW 2021 level-1 names. Peer groups, industry statistics with percentile ranks and confidence filtering, and counts per industry are available.
- **Management:** `management_events` (appointments, elections, resignations with deferred effectiveness, dismissals, deaths, inability to perform) from announcements; `management_observations` from annual-report officer tables or CSV (roles, gender, age, tenure, holdings, pay). Rosters can be reconstructed for any date.
- **Governance variables and screening checks:** board size, independence ratio, female directors, CEO duality, key-role departures and pay, checked against the CSRC independent-director rules (2023).
- **Integration:** six new validation flags, profile and report sections, and the Industry and Management desktop pages.

### v1.2 — Segments and group structure (section 12, second part)

- **Segments:** `segment_observations` hold revenue, share, prior-year revenue, growth, cost and gross margin by industry, product, region, sales model and reportable segment. They are parsed from the revenue-composition and segment-margin tables or imported from CSV. On top of these sit overseas share, HHI and effective segments, segment history, and point-in-time views by publication date.
- **Group structure:** `subsidiary_observations` hold relationship, direct and indirect stakes, principal and registered place, jurisdiction class (including offshore centres), business nature, acquisition method, consolidation, registered capital, and summary financials of major subsidiaries. On top of these sit a structure summary and changes in the consolidation scope.
- **Validation:** `SEGMENT_SUM_MISMATCH`, `SUBSIDIARY_PCT_INVALID` and `CONSOLIDATED_WITH_MINORITY_STAKE`.
- **Interface:** a "Segments & group" collection page, and the Analyse area split into Company, Business & group, and Board & industry.

### v1.3 — R&D, human capital and ESG (section 12, final part)

- **R&D and human capital:** `human_capital_observations` hold R&D staff and investment, expensed and capitalised R&D, intensity and capitalisation share, employees (parent, subsidiaries, total, retirees borne), composition by function, education, and patents (narrative and STAR table). Derived ratios and a history view sit on top.
- **ESG:**
  - `esg_observations` hold key pollutant-discharge-unit status, pollutant and greenhouse-gas emissions and reductions, environmental investment, donations, rural revitalisation, and sustainability-report publication; `esg_ratings` hold imported third-party ratings.
  - The regulatory layer recognises environmental, tax, market-regulation and safety regulators.
  - An ESG profile per fiscal year combines E and S data with the governance and regulatory layers, without a composite score.
- **Validation:** `RD_RATIO_INCONSISTENT`, `RD_COMPONENTS_MISMATCH`, `WORKFORCE_COMPOSITION_MISMATCH` and `EDUCATION_SUM_MISMATCH`.
- **Distribution:** the Windows build is delivered as the desktop application plus an optional command-line add-on.

### v1.4 to v2.0 — The end-state roadmap

These releases implement section 18 (verification, review, security master, research datasets, ownership and control, whole-market operations, distribution and documentation, and native visualisation). Each subsection of section 18 ends with a "Status (delivered in …)" note recording what was built, how it was accepted and which bugs the build found.

---

## 4. Current database layers

The consolidated v0.7 database contains the following conceptual layers.

### Entity/master data

- `companies`
- `securities`
- `sources`

### Raw evidence

- `raw_records`

Raw source responses should remain immutable and content-addressed where practical.

### Disclosure layer

- `disclosures`

Each disclosure should retain:

- company
- security
- announcement ID
- announcement date
- title
- announcement type
- original URL
- local document path where downloaded
- SHA-256
- retrieval timestamp
- source

### Financial layer

- `financial_facts`

Each fact should retain:

- company/security
- reporting period
- period type
- statement type
- metric
- value
- unit
- currency
- consolidation scope
- source document
- source page where known
- XBRL tag where available
- extraction method
- confidence
- retrieval timestamp

### Market layer

- `market_bars`
- `market_snapshots`

Market observations should distinguish:

- trading date
- OHLCV
- adjusted/unadjusted status
- provider
- retrieval time
- source/raw payload

### Ownership layer

- `ownership_observations`
- `capital_structure_observations`

Ownership observations should be tied to an observation/reporting date rather than treated as timeless company attributes.

### Corporate-action layer (v0.8)

- `corporate_actions` (observations)
- `capital_reconciliations` (derived results; may be regenerated, never used to overwrite observations)

### Regulatory layer (v0.9)

- `regulatory_events`

---

## 5. Source hierarchy

### Tier 1 — Primary / official

- SSE
- SZSE
- CNINFO
- CSRC
- CSDC where authorised access is available

These should be preferred for legally or economically material facts.

### Tier 2 — Commercial structured databases

- Wind
- CSMAR

Use through authorised access/API/data services rather than webpage scraping.

### Tier 3 — Alternative commercial databases

- Choice
- iFinD

Useful for cross-checking and enrichment where properly licensed.

### General rule

A commercial source can improve completeness and convenience, but should not silently replace the primary disclosure source where a primary source exists.

---

## 6. Provenance standard

Every material observation should be traceable through:

```text
Company
  ↓
Security
  ↓
Observation
  ↓
Source
  ↓
Source document / API response
  ↓
Page / table / XBRL tag where applicable
  ↓
Raw value
  ↓
Normalised value
  ↓
Extraction method
  ↓
Validation status
```

The minimum desirable provenance record is:

```text
source
source_url
retrieved_at
document_id
document_hash
publication_date
reporting_period
raw_value
normalised_value
unit
currency
source_page
source_xbrl_tag
extraction_method
confidence
validation_status
```

No extracted number should be considered fully research-grade merely because it has been stored successfully.

---

## 7. Validation pipeline

Validation should operate in stages.

### Stage 1 — Schema validation

Check:

- valid security code
- valid exchange
- valid board
- valid dates
- numeric fields
- required source metadata

### Stage 2 — Internal accounting validation

Examples:

```text
Assets = Liabilities + Equity
```

and where appropriate:

```text
Beginning cash
+ operating cash flow
+ investing cash flow
+ financing cash flow
+ FX effects
= ending cash
```

### Stage 3 — Cross-document validation

Compare:

- annual report against subsequent comparative figures
- interim report against annual report
- restated figures against earlier published figures
- ownership disclosures against later capital changes

### Stage 4 — Cross-source validation

Where authorised sources are available, compare:

- financial facts
- share capital
- market data
- ownership
- corporate actions

Discrepancies should be flagged, not automatically overwritten.

### Stage 5 — Confidence classification

Suggested categories:

```text
HIGH
MEDIUM
LOW
UNVALIDATED
```

Native XBRL facts generally receive higher confidence than heuristic PDF extraction.

---

## 8. Acquisition rules

The system should:

1. Acquire from the most authoritative available source.
2. Preserve the original response/document.
3. Hash immutable raw material.
4. Normalise into canonical tables.
5. Record extraction provenance.
6. Validate before exposing the observation as research-ready.
7. Never silently overwrite conflicting observations.
8. Never bypass authentication, CAPTCHA, access controls or rate limits.
9. Respect licensing restrictions for commercial datasets.

---

## 9. v0.8 — Corporate actions and distributions (implemented)

Implemented in v0.8. The specification is retained below for reference. Outstanding items carried forward to later releases are tradable-share reconciliation (restricted-share unlocks) and live verification of the CNINFO category codes.

### Coverage

- cash dividends
- profit distributions
- bonus shares
- capitalisation issues
- rights issues
- private placements
- public offerings
- share issuances
- share buybacks
- share cancellations
- stock splits
- share consolidations
- convertible-bond conversions
- warrant/share conversion events
- other events altering issued or tradable capital

### Core model

A corporate-action observation should contain:

```text
company
security
action_id
action_type
announcement_date
record_date
ex_date
payment_date
effective_date
old_share_count
new_share_count
ratio
cash_amount
subscription_price
issue_price
currency
status
source_document
source_page
announcement_id
raw_value
normalised_value
extraction_method
confidence
```

### Reconciliation

v0.8 should reconcile:

```text
Capital structure at t0
        +
Corporate actions between t0 and t1
        =
Capital structure at t1
```

This is particularly important for:

- bonus issues
- rights issues
- placements
- buybacks
- cancellations
- splits/consolidations
- convertible-bond conversions

---

## 10. v0.9 — Regulatory and legal events (implemented)

Implemented in v0.9. The specification is retained below for reference. Carried forward: linking events across announcements (investigation → prior notice → decision; filing → judgment → appeal), and live verification of the CNINFO risk-warning category codes.

Capture:

- CSRC enforcement
- exchange disciplinary actions
- regulatory enquiries
- warnings
- penalties
- audit qualifications
- litigation
- material arbitration
- accounting irregularities
- disclosure violations
- delisting risk events
- trading suspensions

Each event should have:

- event type
- authority
- event date
- company
- affected security
- status
- source document
- primary-source URL
- document hash
- legal/regulatory classification

---

## 11. v1.0 — Integrated company intelligence (implemented)

Implemented in v1.0; see section 3. The target architecture below is now in place, except for the Management and ESG/R&D branches beyond R&D expenditure and employees, which belong to section 12.

The target v1.0 architecture is:

```text
                    COMPANY
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    Securities     Ownership       Management
        │              │              │
        ├──────────────┼──────────────┤
        │              │              │
    Financials      Market Data   Corporate Actions
        │              │              │
        ├──────────────┼──────────────┤
        │              │              │
    Disclosures     Regulatory      ESG/R&D
        │              │              │
        └──────────────┼──────────────┘
                       │
                 VALIDATION
                       │
                 PROVENANCE
                       │
              RESEARCH DATASET
```

The eventual research interface should support:

- company profiles
- historical financial series
- ownership history
- capital-structure history
- corporate-action timeline
- market-history queries
- disclosure search
- source-document inspection
- cross-company comparisons
- CSV/Parquet/SQLite export
- reproducible research queries

---

## 12. Longer-term enrichment (v1.1 onwards)

Done in v1.1: industry classification; management (directors, supervisors, executives, tenure, appointments/resignations, remuneration). Done in v1.3: R&D and human capital (R&D expenditure, intensity and capitalisation, patents, employees, technical staff, education), and ESG (environmental disclosures, emissions, governance and social indicators, sustainability reports, third-party ratings). Section 12 is complete apart from geographic workforce information, which A-share reports rarely disclose in a structured form. The roadmap to the end state (v2.0) is set out in section 18.

Done in v1.2: subsidiaries (names, ownership percentages, jurisdiction, registered capital, business scope, consolidation status) and geographic and segment information (revenue by geography and segment, overseas exposure). 

After v1.0, candidate layers include:

### Management

- directors
- supervisors
- senior executives
- tenure
- appointments/resignations
- remuneration

### Subsidiaries

- subsidiary names
- ownership percentages
- jurisdiction
- registered capital
- business scope
- consolidation status

### R&D and human capital

- R&D expenditure
- R&D intensity
- patents where available
- employees
- technical staff
- geographic workforce information

### Geographic and segment information

- revenue by geography
- revenue by business segment
- assets by segment
- overseas exposure

### ESG

- environmental disclosures
- emissions
- governance indicators
- social indicators
- sustainability reports

---

## 13. CLI workflow

### Initialise

```bash
python -m ashare.cli init-db
```

### Universe

```bash
python -m ashare.cli update-universe
python -m ashare.cli validate-universe
python -m ashare.cli universe-stats
```

### Disclosures

```bash
python -m ashare.cli catalogue-disclosures \
  --since 2026-01-01 \
  --until 2026-10-08 \
  --kind reports
```

### Financials

```bash
python -m ashare.cli extract-financials --security-code 600519
python -m ashare.cli show-financials 600519 --metric revenue
python -m ashare.cli validate-financials --security-code 600519
```

### Market

```bash
python -m ashare.cli acquire-market \
  --security-code 600519 \
  --start 2026-01-01 \
  --end 2026-10-08

python -m ashare.cli show-market 600519
```

### Ownership

```bash
python -m ashare.cli import-ownership-csv ownership.csv
python -m ashare.cli import-capital-csv capital.csv
python -m ashare.cli ownership-disclosures --security-code 600519
python -m ashare.cli show-ownership 600519
python -m ashare.cli show-capital 600519
python -m ashare.cli validate-ownership --security-code 600519
```

### Regulatory and legal events (v0.9)

```bash
python -m ashare.cli catalogue-disclosures --since 2024-01-01 --until 2026-10-08 \
  --kind all --download-documents
python -m ashare.cli extract-regulatory-events --security-code 600519
python -m ashare.cli import-regulatory-document decision.pdf --security-code 600519
python -m ashare.cli show-events 600519
python -m ashare.cli regulatory-status 600519 --as-of 2026-06-30
python -m ashare.cli export all --out-dir exports
```

### R&D, human capital and ESG (v1.3)

```bash
python -m ashare.cli extract-human-capital --security-code 600519 && python -m ashare.cli human-capital 600519
python -m ashare.cli extract-esg --security-code 600519 && python -m ashare.cli esg 600519 --year 2025
```

### Segments and group structure (v1.2)

```bash
python -m ashare.cli extract-segments --security-code 600519 && python -m ashare.cli segments 600519
python -m ashare.cli extract-subsidiaries --security-code 600519 && python -m ashare.cli subsidiaries 600519
python -m ashare.cli scope-changes 600519
```

### Industry and management (v1.1)

```bash
python -m ashare.cli import-industry-csv csrc.csv --scheme CSRC_2012 --effective-date 2026-06-30
python -m ashare.cli peers 600519 && python -m ashare.cli industry-stats 600519 --metric net_margin
python -m ashare.cli extract-management --security-code 600519
python -m ashare.cli roster 600519 --as-of 2026-06-30 && python -m ashare.cli governance 600519
```

### Integrated intelligence and research (v1.0)

```bash
python -m ashare.cli validate-all
python -m ashare.cli profile 600519 --as-of 2025-12-31
python -m ashare.cli financial-series 600519 --metric revenue --vintage original
python -m ashare.cli compare --codes 600519,000858
python -m ashare.cli report 600519
python -m ashare.cli index-documents && python -m ashare.cli search-documents 资金占用
python -m ashare.cli trace financial_facts 1234
python -m ashare.cli query "SELECT ..." --out exports/q.csv
python -m ashare.cli release --formats csv,sqlite
```

### Desktop application (v0.9; redesigned in v1.0)

```text
build_windows.bat                      (once, on Windows; builds and tests)
dist\AShareScraper\AShareScraper.exe    (desktop interface)
dist\AShareScraper\ashare-cli.exe       (same commands as above)
```

### Corporate actions (v0.8)

```bash
python -m ashare.cli catalogue-disclosures --since 2025-01-01 --until 2026-10-08 \
  --kind corporate_actions --download-documents
python -m ashare.cli extract-corporate-actions --security-code 600519
python -m ashare.cli import-corporate-actions-csv actions.csv --source LICENSED_VENDOR
python -m ashare.cli show-actions 600519
python -m ashare.cli reconcile-capital --security-code 600519
```

---

## 14. Testing strategy

Every release should have:

### Unit tests

Test:

- code normalisation
- board classification
- disclosure classification
- period inference
- unit conversion
- financial extraction
- ownership classification
- corporate-action classification

### Integration tests

Test:

- database initialisation
- full pipeline sequencing
- idempotency
- source persistence
- raw-document hashing
- cross-table relationships

### Validation tests

Test:

- accounting identities
- capital reconciliation
- duplicate detection
- conflicting observations
- invalid periods
- missing provenance

### Live-source tests

Only claim success when the actual external source has been reached successfully.

Network-unavailable environments must be reported as such rather than represented as successful live integration tests.

---

## 15. Current known limitations

At v2.0 the program is complete against the end-state definition in section 18.1, with the exceptions below.

1. **Live sources only partly exercised.** The build environment has no access to the sources; the first live run (by the author, v2.0) found the Shanghai stock list gone, fixed in v2.0.1. The other endpoints have not yet been confirmed live. The self-test (v1.4) is the live test and must be run once on a networked machine; the market-wide announcement query and the Eastmoney quote list (v1.9) in particular have been implemented from their documented parameters only.
2. **Calibration needs a real corpus.** The evaluation harness, calibration and gate are in place, but parser confidence uses default priors until a golden corpus of hand-verified real reports is evaluated. The synthetic corpus is a regression gate only.
3. **Unsigned installer.** Signing hooks are in place; without a certificate, SmartScreen and some antivirus programs warn on first run.
4. **Scanned documents and diagrams.** Documents without a text layer are not read (no OCR), and ownership diagrams (方框图) are usually images, so intermediate stakes in control chains must be imported.
5. **Heuristic extraction.** PDF extraction is less reliable than native XBRL; corporate-action and regulatory extraction rely on standard drafting, and non-standard drafting produces title-only records. Event links without explicit identifiers are labelled heuristics.
6. **Accounting checks.** Balance-sheet identity and component sums are checked; a cash-flow reconciliation is not implemented.
7. **Licensed and public-feed data.** Commercial datasets require licences and are imported by the user; the free price feed is not exchange-authoritative.
8. **Pseudonymisation is not anonymisation.** Pseudonymised releases remain personal information under the PIPL and personal data under the UK and EU GDPR (see `docs/compliance.md`).

---

## 16. Research-grade design principles

The project should preserve five principles throughout subsequent development:

### 1. Source before inference

Prefer disclosed facts over model-derived guesses.

### 2. Evidence before normalisation

Never discard the raw observation merely because a cleaner canonical value has been produced.

### 3. Time before snapshots

Company attributes should be modelled as observations over time whenever they can change.

### 4. Conflicts before overwrites

Conflicting sources should produce validation flags rather than silent replacement.

### 5. Reproducibility before convenience

A researcher should be able to reconstruct why a value appears in the database and identify the document or source from which it originated.

---

## 17. End-state pipeline

```text
1. DISCOVER
   ↓
A-share security universe

2. IDENTIFY
   ↓
company / security / exchange / board / orgId

3. ACQUIRE
   ↓
CNINFO / SSE / SZSE / authorised data services

4. ARCHIVE
   ↓
raw response + original document + hash + timestamp

5. CATALOGUE
   ↓
announcement / document / reporting period

6. EXTRACT
   ↓
XBRL → structured data → PDF/table fallback

7. NORMALISE
   ↓
canonical company/security observations

8. VALIDATE
   ↓
internal identities + cross-document + cross-source

9. RECONCILE
   ↓
financials + market + ownership + corporate actions

10. EXPOSE
    ↓
research queries / exports / company intelligence

11. AUDIT
    ↓
source → document → page/tag → raw value → normalised value
```

This is the intended architecture for the project going forward.

---

## 18. Roadmap to v2.0 (end state)

### 18.1 Definition of the end state

v1.3 completed the subject-matter layers of sections 9 to 12. The end state (v2.0) is reached when the system is **verified, complete in coverage, usable for research and operable at whole-market scale**. It is defined by acceptance criteria rather than by features:

1. **Verified.** Every live endpoint has been exercised from a user machine. Each parser has a measured accuracy on a golden corpus of real reports, and that measured accuracy, not an assumed value, sets its confidence scores.
2. **Correctable.** Every low-confidence or flagged value can be reviewed and corrected in the application. Corrections are stored as separate observations with an audit trail and never overwrite the source value.
3. **Unbiased coverage.** The universe includes delisted and renamed companies, with point-in-time listing status and index membership.
4. **Research-ready.** Panel datasets (company-year, company-quarter) can be produced point-in-time, with a generated codebook, and exported to Stata, R and Parquet.
5. **Visual.** Datasets, company histories and validation results can be explored as charts inside the application. The same charts appear in reports and can be exported for publication.
6. **Operable.** Whole-market collection runs incrementally, resumes after interruption, and can be scheduled and cancelled.
7. **Distributable.** The installer is signed, schema migrations are versioned, releases respect data licences, a data-quality report accompanies every release, and full documentation is provided.

### 18.2 Working assumptions (decision points)

These defaults apply until decided otherwise. Each can be changed without redesign.

| Decision | Default adopted | Effect if changed |
|---|---|---|
| Universe scope | SSE Main, STAR, SZSE Main, ChiNext; **BSE and B-shares excluded but supported as an option** (board codes and adapters added in v1.6, disabled by default) | Enabling them adds companies and share classes only, not schema |
| Purpose | Personal research use, **with licence-aware and pseudonymised releases built anyway** (v2.0) | Publishing a dataset then requires no further engineering |
| Live testing | Run by the author with the desktop application on their own PC (a "Self-test" page produces a report file to send back) | If network access becomes available in the build environment, the same tests run there automatically |

### 18.3 Release plan

| Release | Theme | Size |
|---|---|---|
| v1.4 | Live verification and golden corpus | M |
| v1.5 | Layout-aware table extraction; review and correction workflow; charting engine (foundation) | L |
| v1.6 | Historical universe, point-in-time security master, index membership | M |
| v1.7 | Research datasets: panel builder, derived measures, event study, codebook; dataset visualisation | L |
| v1.8 | Ownership and control: top-10 holders from reports, entity resolution, control chains, SOE classification; network charts | L |
| v1.9 | Whole-market operations; remaining event types (M&A, related-party transactions, guarantees, meeting votes) | L |
| v2.0 | Distribution: migrations, signed installer, licence-aware releases, data-quality report, documentation | M |

Sizes are relative (S/M/L) and indicate build effort, not calendar time. v1.4 is a hard prerequisite for all later releases. v1.6 and v1.7 can proceed in parallel once v1.5's extraction layer is stable.

### 18.4 v1.4 — Live verification and golden corpus

**Scope**
- `self-test` command and a desktop Self-test page.
  - Each endpoint is called once: CNINFO stock lists, announcement query (one call per category code), document download, SSE and SZSE pages, Eastmoney bars.
  - The test records status, response shape, field names, record counts and timing, and compares them with the shapes the adapters expect.
  - It writes `selftest_report.json` plus a readable HTML summary.
  - No collection is performed beyond one small request per endpoint, within the normal rate limit.
- Golden corpus.
  - About 40 real reports chosen across boards (Main, STAR, ChiNext), years (2015 to 2025), report types (FY, H1, Q1, Q3) and layouts (SSE versus SZSE templates, financial-sector templates for banks and insurers).
  - Values are verified by hand in a CSV: around 25 fields per report, covering core financials, R&D table, workforce, segments, subsidiaries and officer table.
- Accuracy harness (`evaluate-parsers`).
  - Measures, per parser and field: recall (value found), precision (value found and correct within tolerance) and abstention (value not found, which is preferred to a wrong value).
- Confidence calibration.
  - Replaces the fixed confidence constants (0.4 to 0.98) with the measured precision of each parser and field, stored in a `parser_calibration` table and versioned.
- Adapter corrections arising from the self-test, for example category codes, request parameters and field names.

**Acceptance criteria**
- Every endpoint reports PASS on a user machine, or is documented as unavailable with the reason.
- Precision is at least 98% for core financial facts from XBRL and at least 95% from PDF tables for the core metrics. Below that, the metric is marked LOW by calibration rather than presented as reliable.
- The golden corpus and harness run in CI. A parser change cannot ship if precision falls by more than one percentage point on any field.

**Risks**
- Endpoints may have changed or may block automated access. If so, adapters are fixed or the source is documented as manual-import only. Access controls are never bypassed (section 8, rule 8).

**Status (delivered in v1.4).** Self-test, transport injection, golden-corpus format (one JSON file of verified values per document, in place of a single CSV, so that keyed records such as segments and officers can be checked), `corpus-template`, `evaluate-parsers`, `parser_calibration` with versioned, Wilson-lower-bound confidence, a synthetic corpus and the CI gate. The real 40-report corpus has to be assembled and verified on a machine that can reach CNINFO; until it is, extractors keep their fixed confidence constants. Two unit-detection bugs were found by the harness and fixed.

### 18.5 v1.5 — Table extraction, review workflow, charting foundation

**Table extraction**
- Adds a layout-aware PDF table extractor based on character coordinates (pdfplumber, a pure-Python library, so suitable for the Windows build) alongside the existing text extractor.
- Cells are reconstructed from x/y positions, so wrapped cells, multi-line entity names and merged headers are handled.
- Each table parser (segments, subsidiaries, officers, workforce, R&D, major subsidiaries, top-10 shareholders) runs on both extractors. A result is kept only when both agree, or when the layout extractor's calibrated precision is higher; disagreements are flagged.
- Scanned PDFs are detected (no text layer) and listed; OCR is out of scope unless the golden corpus shows material need.
- Parsers move to a plug-in registry: one module per table type and layout variant, each with its own tests and calibration.

**Review and correction workflow**
- A Review page lists the queue: validation flags, low-confidence values and parser disagreements, ordered by materiality.
- For each item the page shows the extracted value, the source page rendered as an image with the matched region highlighted, the raw text and the provenance chain (`trace`).
- Actions: Accept, Correct (enter value and reason), Reject (mark as not disclosed), Defer.
- Corrections are stored as `MANUAL_REVIEW` observations that reference the original row, with reviewer, timestamp and reason. Original values are never altered.
- Views prefer reviewed values and show that a correction was applied.
- Review statistics feed back into calibration.

**Charting foundation (see 18.11)**
- The chart-specification layer, the native in-app renderer and the SVG renderer, with the first chart types used by the Review page and the Company page.

**Acceptance criteria**
- Measured on the golden corpus:
  - table-parser recall improves by at least 15 percentage points over v1.3;
  - precision is not lower than v1.3 for any table type.
- Every flag type can be resolved from the Review page, and corrections survive re-extraction.

**Status (delivered in v1.5).**
- **Layout extractor.** Built on pypdfium2 character boxes rather than pdfplumber. pypdfium2 also renders the Review page's source images; it is a single dependency of about 7 MB in the Windows build, against pdfplumber's pdfminer plus Pillow.
- **Dual run.** Implemented for financial statements, segments, subsidiaries, R&D and workforce, and officers. Top-10 shareholders follow in v1.8.
- **Other components.** Parser registry, scanned-PDF detection, and the review queue with corrections keyed by natural key.
- **Charts.** The chart specification, SVG and Tk renderers and the optional matplotlib renderer. PNG export is available through the matplotlib option in source installations, or by saving the SVG from a browser; the Tk canvas cannot write PNG without Pillow, so the 18.11 text is amended accordingly.
- **Acceptance.** On the synthetic corpus, table recall rose by 32 to 53 points for segments and subsidiaries, with no fall in precision. The same check is pending on the real golden corpus.

### 18.6 v1.6 — Historical universe and point-in-time security master

**Scope**
- Universe history from CNINFO and the exchanges' delisting and name-change announcements, plus an import path for authorised historical lists.
- New tables:
  - `security_history` (code, name, board, listing status, valid-from and valid-to dates);
  - `listing_events` (IPO, delisting, board transfer, code change, name change).
- Delisted companies are kept with their full history, and every view accepts `as_of`.
- Universe queries become point-in-time ("all companies listed on date D"), so studies avoid survivorship bias.
- Index membership: `index_constituents` (index, code, valid-from, valid-to) for CSI 300, CSI 500, SSE 180, STAR 50, SZSE 100, ChiNext Index and others, from published constituent adjustments or licensed files.
  - Membership drives the sustainability-reporting mandate check (v1.3) and peer or benchmark selection.
- Trading calendar and suspension days, derived from market data and suspension events.
- Optional boards: BSE and B-shares (adapters and board codes present, disabled by default).

**Acceptance criteria**
- A test universe for a past date reproduces the companies listed on that date, including later-delisted ones, against a reference list.
- Name and code changes link correctly to one company identity.

**Status (delivered in v1.6).**
- **Delivered.** All listed components: listing events from announcements, list comparisons and imports; derived and imported security history; `universe-at`; index membership; the trading calendar and suspension spells; the sustainability mandate check; and the optional boards.
- **Acceptance tests.**
  - A reference universe on six dates (including a later-delisted company, a name change and a code change) is reproduced exactly.
  - The renamed and re-coded companies resolve to one identity.
- **Still needed.** Historical delisted companies need an authorised list (CNINFO's stock lists cover listed companies only). The BSE and B-share CNINFO parameters remain unverified.

### 18.7 v1.7 — Research datasets and dataset visualisation

**Derived financial measures**
- Single-quarter figures (Q2 = H1 − Q1, Q4 = FY − Q3) and trailing twelve months for flow items. Balance-sheet items are taken at period end.
- 扣除非经常性损益后的净利润 (net profit after non-recurring items) and non-recurring items, extracted from the 主要会计数据 table.
- Wider statement coverage: a mapping from CAS line items to a standard chart of about 120 items, kept as a versioned mapping table.

**Market measures**
- Market capitalisation and free-float capitalisation from capital observations × close, populating `market_snapshots`.
- Own adjustment factors from recorded corporate actions (cash dividends, bonus and capitalisation issues, rights issues), so that adjusted returns no longer depend on the provider's adjustment. Provider-adjusted series are retained for comparison and differences are flagged.
- Valuation ratios (P/E, P/B, P/S, EV) computed point-in-time from published financials only.

**Panel builder** (`build-panel`)
- Choose the unit (company-year, company-quarter or company-month), the date range, the universe (point-in-time, optionally an index), the variables (from the codebook) and the alignment rule.
- Alignment uses the publication date: a variable enters on its announcement date, with an optional reporting lag, for example values usable from 30 April.
- Options: lags and leads, winsorisation (percentiles chosen), minimum confidence class, reviewed values only, and exclusion of financial-sector companies.
- Outputs:
  - CSV, Parquet (optional dependency), Stata `.dta` (written by a small built-in writer for the needed types, so no heavy dependency) and an R-ready CSV with a types file;
  - a per-dataset manifest, as in v1.0 releases.

**Event study** (`event-study`)
- Abnormal returns around any event type (corporate actions, regulatory events, management changes) under the market model or market-adjusted returns.
- Estimation and event windows are chosen by the user, and the benchmark is an index or an equal-weighted universe.
- Outputs: cumulative abnormal returns per event, averages with t-statistics, and the average CAR plotted with confidence bands.

**Codebook**
- Generated automatically for every variable: definition, unit, formula, source tables, point-in-time rule, confidence handling, and coverage (non-missing share by year).
- Exported as Markdown and HTML for a methods appendix.

**Dataset visualisation (see 18.11)**
- A dataset explorer for any built panel: variable summaries, histograms, box plots by year, scatter plots of any two variables with a fitted line, a coverage heatmap (company × year), and correlation tables.

**Acceptance criteria**
- A panel built "as of" a past date contains no value published after that date (automated test against announcement dates).
- Own adjustment factors reproduce provider-adjusted closes within 0.5% for at least 99% of company-days in a sample, with exceptions explained.
- Event-study output matches a hand-computed example.

**Status (delivered in v1.7).**
- **Delivered.** All listed components.
- **Chart of accounts.** It has 132 items, slightly above the planned 120, because the cash-flow subtotals are included.
- **Stata writer.** It writes numbers as doubles and text as `str#`, and was validated with `pandas.read_stata`.
- **Acceptance tests.**
  - A panel built as of a date contains no value published after it. The builder enforces this and the automated tests check it.
  - Own adjustment factors reproduce a provider's forward-adjusted closes for 100% of days in the synthetic test; real data is to be checked on a user machine.
  - The event study reproduces a hand-constructed market-model example exactly.
- **Note.** The equal-weighted benchmark includes the event firm; supply an index CSV when that matters.

### 18.8 v1.8 — Ownership and control

**Scope**
- Top-10 shareholders and top-10 tradable shareholders parsed from periodic reports. This replaces CSV-only ownership.
- Pledge and release announcements.
- Entity resolution with an `entities` register.
  - Each entity has a unified social credit code where disclosed, a normalised name and aliases.
  - Shareholders, subsidiaries, associates and listed companies resolve to the same entity, and persons to a `persons` register (name plus company and role context; same-name disambiguation by tenure overlap and co-occurrence).
- Control chains from the 公司与实际控制人之间的产权及控制关系 disclosure: edges with percentages from the listed company up to the actual controller, with the date.
- Ownership type: central SOE, local SOE, private, foreign or collective, from the actual controller (for example 国务院国资委, provincial SASAC or a natural person), with the basis recorded.
- Cross-company links: interlocking directors, common controllers and group affiliation.

**Network charts (see 18.11)**
- Ownership and control diagrams, group structure trees, and interlock networks.

**Acceptance criteria**
- The top-10 table parsed from the golden corpus reaches the v1.4 precision thresholds.
- Ownership type agrees with a hand-coded sample for at least 97% of companies, with the remainder flagged for review.

**Status (delivered in v1.8).**
- **Delivered.** All listed components.
- **Control chains.** Chains are built from the text of 控股股东情况 and 实际控制人情况, plus the top-10 stakes. The report's 方框图 is usually an image, so its intermediate percentages are imported (`import-control-edges-csv`) rather than parsed.
- **Acceptance (synthetic corpus).**
  - The layout variant reads the top-10 table at 100% precision and recall; the plain extractor reaches 82% and 75%.
  - Ownership type agrees with a 30-case hand-coded sample at or above 97%.
- **Bugs fixed during the build.** The evaluation harness exposed two:
  - the actual-controller search matched the section heading "控股股东和实际控制人情况";
  - pledgor names kept a leading "公司控股股东".

### 18.9 v1.9 — Whole-market operations and remaining events

**Operations**
- Incremental collection: each source keeps a high-water mark (last announcement time, last trading date), and runs fetch only what is new.
- Job queue: resumable jobs with persistent state; desktop progress bars with a cancel button; failures retried with back-off and listed for attention.
- Scheduler: daily announcement catalogue and weekly extraction, run from the Windows Task Scheduler entry created by the application (opt-in).
- Storage management: document archive statistics, and optional pruning of PDFs after extraction while keeping hashes and URLs (documents can be fetched again).
- Database back end: SQLite remains the default. An optional PostgreSQL back end supports multi-user or whole-market databases, and an optional DuckDB export supports fast analytics.
- Performance: indexes reviewed against query plans; bulk inserts; the whole-market universe benchmarked.

**Remaining event types**
- Major asset restructurings (重大资产重组), with stages from suspension to completion.
- Related-party transactions: counterparty, amount, nature, approval body.
- External guarantees (对外担保): beneficiary, amount, whether related-party, overdue status.
- Shareholder-meeting resolutions, with voting results where disclosed.

**Acceptance criteria**
- A full-market catalogue run can be interrupted and resumed without duplication or loss.
- A daily incremental run completes within one hour at the default rate limit.

**Status (delivered in v1.9).**
- **Delivered.** All listed components. The desktop Operations page runs the daily update and jobs with progress and cancel; the Corporate actions page lists transactions.
- **Unverified endpoints.** The market-wide CNINFO query (stock field left empty, one query per exchange column and day) and the Eastmoney quote list (`clist`, 100 securities per request) are implemented from their documented parameters but have not been tried against the live sources. The self-test checks both and reports a failure clearly if either has changed.
- **Acceptance.**
  - Interruption: a five-day catalogue job cancelled after two days, then hit by a transient connection error, completes on the third run with every announcement stored once (test `test_jobs_resume_after_cancel_and_failure_without_duplicates`).
  - Daily run time: 4,000 announcements, a quarter downloaded, plus prices for 5,400 companies need about 1,000 requests, or about 16.4 minutes at one request per second.
- **Benchmark (offline, 4,700 companies, mock transport).** Universe upsert 5.0 s; `universe_at` 0.14 s; rebuilding security history 12.7 s; one catalogue day of 4,020 announcements (134 requests) processed in 4.2 s; a whole-market price snapshot processed in 6.0 s. Network time therefore dominates.
- **Bugs fixed during the build.**
  - `init_db` re-created indexes on every call, which blocked on PostgreSQL while another session held a transaction; it now runs once per process and database URL.
  - Restructuring titles that mention 关联交易 were also classed as related-party transactions; guarantee beneficiaries kept a 全资子公司 prefix.

### 18.10 v2.0 — Distribution and documentation

- **Schema migrations:** versioned migration scripts (Alembic) replace ad-hoc column additions, and databases from v0.7 onwards upgrade automatically.
- **Installer:**
  - a Windows installer that is code-signed (removing the SmartScreen and antivirus warnings) and has an update check;
  - the command-line tool included, so there is no separate add-on;
  - an optional portable zip.
- **Licence-aware releases:**
  - every source is tagged with its licence (public disclosure, licensed vendor, manual);
  - `release` excludes licensed data by default and records the exclusion in the manifest;
  - a pseudonymisation option replaces personal names (directors, natural-person shareholders) with stable identifiers for dataset release under PIPL.
- **Data-quality report with every release:**
  - coverage by layer, board and year;
  - parser precision (from calibration);
  - review statistics;
  - flag rates;
  - known gaps.
- **Documentation:**
  - user guide (desktop and command line);
  - methods document suitable for citation (sources, point-in-time rules, validation, calibration);
  - codebook;
  - developer guide (adding a parser, adding a source);
  - a suggested dataset citation with version and fingerprint.
- **Compliance review:**
  - collection behaviour checked against CNINFO and exchange terms of use;
  - rate limits documented;
  - no circumvention of access controls (unchanged principle).

**Acceptance criteria**
- A clean Windows machine installs, updates and uninstalls without warnings.
- A release built from a database containing vendor data contains none of it unless explicitly overridden.
- All seven end-state criteria in 18.1 are demonstrably met.

**Status (delivered in v2.0).**
- **Delivered.** All listed components except code signing, for which hooks are in place but no certificate was available.
  - **Migrations.** Alembic, with a baseline revision that brings any database from v0.7 onwards to the v1.9 schema (creating missing tables, adding missing columns, creating indexes) and a v2.0 revision. Revisions use idempotent helpers. `init_db` upgrades automatically after a backup copy of a SQLite file. Tests upgrade stored schemas of v0.7, v1.3 and v1.9; the built Windows program upgraded a real v1.9 database in place.
  - **Installer.** NSIS, 64-bit, per-user (no administrator rights), with both programs, the HTML documentation, Start-menu entries, optional desktop shortcut and PATH entry, and an uninstaller that keeps the data folder. 21 MB. Installed, used and uninstalled silently under Wine. A portable zip is still produced. Signing hooks: `packaging/sign.bat` (signtool, or any signing command) and `packaging/sign.sh` (osslsigncode).
  - **Update check.** Off unless an HTTPS address is configured; reports only, never downloads.
  - **Licences.** Five classes (PUBLIC_DISCLOSURE, PUBLIC_FEED, DERIVED, MANUAL, LICENSED), assigned per row from the source label, with table rules (ESG ratings and Shenwan industries are licensed; CSRC industries are public) and user tags (`set-licence`), which take precedence. Unknown imports default to LICENSED.
  - **Releases.** Rebuilt (`ashare/release.py`): a filtered SQLite snapshot on any back end, CSV and Parquet written from it, operational tables and local paths removed, the manifest recording the classes and rows excluded, the schema revision and a citation; `CITATION.cff` per release.
  - **Pseudonymisation.** HMAC-SHA256 identifiers under a key kept in the data folder; natural persons recognised by role, by disclosed nature (自然人) or by name form; organisations untouched; raw and document text dropped; names replaced in free text; optional banding of ages and dropping of free text. The manifest records the fields changed and a key fingerprint.
  - **Quality report.** Markdown, HTML and JSON, with every release and on demand.
  - **Documentation.** `docs/`: user guide, methods (for citation), codebook (generated, 185 variables), developer guide and compliance note (PIPL, Network Data Security Management Regulations, UK GDPR), converted to HTML by `packaging/build_docs.py`; a software `CITATION.cff`. Every command now has help text.
- **End-state criteria (18.1).**
  1. Verified: *pending on a networked machine* (live self-test; calibration on a real corpus). The machinery is complete.
  2. Correctable: met (v1.5).
  3. Unbiased coverage: met (v1.6; index membership by import).
  4. Research-ready: met (v1.7).
  5. Visual: met (v1.5 to v1.8; one scene drives the Tk and SVG renderers; matplotlib remains an optional renderer for source installations).
  6. Operable: met (v1.9).
  7. Distributable: met except signing.
- **Acceptance.** A release built from a database holding vendor ratings and an unlabelled import contains none of either unless overridden (test `test_release_excludes_licensed_and_local_paths`). Installation, use and uninstallation were exercised under Wine; "without warnings" requires signing.
- **v2.0.1: first live run.** The author's first run on a networked machine showed that CNINFO's Shanghai list (`sse_stock.json`) now returns 404, so the universe stayed empty and every downstream step returned nothing. CNINFO's `szse_stock.json` covers all mainland exchanges, so the adapter now reads that single list and infers the exchange from the code (address overridable with `ASHARE_CNINFO_STOCK_LIST_URL`); the self-test reports coverage per exchange; HTTP and network errors carry plain next steps; and commands warn when the company list is empty. This is the failure mode section 18.13 anticipated, and the reason the remaining endpoints still need the live self-test.
- **v2.0.2: second live run.** With the company list loaded (5,574 companies), a whole-market "Catalogue announcements" with downloads appeared stuck: it issued one query per company and printed nothing until the end. The whole-market catalogue now uses exchange-wide queries in monthly windows (adaptive splitting), downloads run as a separate, estimated and resumable phase limited to the documents the extractors read, the desktop streams progress and has a Stop button (cooperative cancellation at every request and document read), and whole-market downloads ask first. The run also showed that the point-in-time universe treated every company as listed on every date (no listing dates in CNINFO's list, and delisted companies included): listing dates now come from the public quote list, delisted companies are recognised by their CNINFO short names, and `universe_at` excludes and counts companies whose dates are unknown. New code ranges (ChiNext 302, STAR CDR 689) are recognised; missing legal names are no longer validation problems.
- **Bugs found during the build.**
  - Several extractors stored the local file path as `source_document`, which would have put the researcher's user name into releases; releases now replace it with the document URL.
  - The NSIS installer built as 32-bit would not start where only 64-bit Windows support is present (as in the test environment); it is now built for x86-64, matching the programs.
  - Alembic imports DDL modules for every SQLAlchemy dialect, which the earlier size exclusions removed; the dialects are kept (the drivers are not bundled).
  - Checkbox hints were not shown in the desktop forms.
- **v2.0.3: complete market catalogue and non-empty panels.** The live-run findings of v2.0.2 (`docs/live_run_findings_v2.0.2.md`) showed that CNINFO ignores the exchange column of a market-wide query, apparently returns at most 3,000 results to one query (so busy days were truncated and paged to the 2,000-page limit), and that every catalogue run restarted from its start date and abandoned a month on one error; the Eastmoney quote list refused every request, so panels came out empty. v2.0.3 replaces the market catalogue (`market_catalogue.py`: one query per period, de-duplicated paging that stops on repetition, splitting of busy days by category and board, a check of every day against CNINFO's total with SHORTFALL records, per-day resume in `catalogue_days`, per-day errors), adds `recatalogue-busy-days`, `catalogue-days` and `probe-cninfo-paging`, tries the quote list in several ways with a resumable download and `diagnose-quote-list`, refuses empty panels with a reason, adds a report-evidence universe for yearly panels (`universe_basis`), and summarises PDF reader messages in one line. A font experiment showed that the fontTools warnings do not affect figures when the font declares a standard encoding (2,408 of 2,428 live cases), so fontTools is not bundled (`docs/font_check_v2.0.3.md`). Bug found during the build: the desktop discarded the exit code that `typer.Exit` returns in non-standalone mode, so actions ending in an error were shown as finished; fixed. Details in `CHANGELOG.md`.

### 18.11 Visualisation workstream

**Can the programme show visualisations natively?** Yes. Charts are drawn inside the desktop application and in the HTML reports from a single chart definition, with no browser and no network required.

**Design**
- **One specification, two renderers.** A chart is a declarative specification: data, mark type, axes, encodings and annotations. A native renderer draws it on the Tkinter canvas inside the application. An SVG renderer writes the same chart into HTML reports and figure exports. The application and the reports therefore always agree, and the SVG renderer is unit-testable.
- **No heavy dependencies.** Both renderers are written in plain Python, avoiding matplotlib and numpy, which would add about 40 to 60 MB to the Windows build and slow start-up. A matplotlib "publication figures" option can be added for users running from source, but it is not required.
- **Provenance in the chart.**
  - Hovering over any point shows the value, period, publication date, source document and page, extraction method and confidence class.
  - Clicking opens the full `trace` in the Review page.
- **Honest encoding.**
  - Confidence class is shown by marker style (filled = HIGH, hollow = MEDIUM, dashed or outlined = LOW), not by colour alone.
  - Restated values carry a distinct mark, with original and latest vintages shown on request.
  - An `as_of` view draws the cut-off date as a vertical rule.
  - Missing data are shown as gaps, never interpolated.
- **Accessibility.** A colour-blind-safe palette, text labels on series, and a minimum contrast ratio of 4.5:1.
- **Export.** Each chart exports as SVG (vector, for publication) and the CSV of exactly the plotted data, with a caption that states sources and the as-of date; PNG through the optional matplotlib renderer (source installations) or by saving the SVG from a browser.

**Chart catalogue and where each appears**

| Chart | Purpose | Page | Release |
|---|---|---|---|
| Line, time series | Financial series with vintages and restatements; R&D, workforce and ESG histories | Company, People & ESG | v1.5 |
| Bar, horizontal | Segment revenue, industry counts, validation flags by rule | Business & group, Validate | v1.5 |
| Source-page viewer with highlight | Review of an extracted value | Review | v1.5 |
| Price chart with event markers | Price or adjusted price with corporate-action, regulatory and management events on the time axis | Company | v1.7 |
| Stacked bar / 100% bar | Segment mix over time, workforce composition, education | Business & group, People & ESG | v1.7 |
| Histogram and box plot | Industry distribution with the company's position marked; panel variable distributions | Board & industry, Dataset explorer | v1.7 |
| Scatter with fitted line | Peer comparison (e.g. R&D intensity against margin) with the company highlighted; any two panel variables | Board & industry, Dataset explorer | v1.7 |
| Coverage heatmap | Non-missing data by company × year or variable × year | Dataset explorer, Validate | v1.7 |
| Event-study plot | Average CAR with confidence band | Research | v1.7 |
| Ownership and control diagram | Chain from listed company to actual controller with stakes | Board & industry | v1.8 |
| Group structure tree | Subsidiaries by jurisdiction and stake, offshore entities highlighted | Business & group | v1.8 |
| Interlock network | Directors shared between companies | Board & industry | v1.8 |

**Interaction model**
- Charts appear in a chart pane above the existing output text.
- The output text remains available as a table view of the same data.
- Controls are kept minimal: time range, series toggles, as-of date, export.

**Acceptance criteria**
- Every chart in the catalogue renders identically, within pixel tolerance, in the application and in SVG.
- Tooltips show provenance.
- Exports reproduce the plotted data exactly.
- Charts render 10,000 points in under one second on a typical PC.

### 18.12 Cross-cutting engineering

- **Testing.** Unit and integration tests continue (74 at v1.3). Additions:
  - golden-corpus accuracy tests (v1.4);
  - point-in-time leakage tests (v1.7);
  - renderer snapshot tests (v1.5 onwards);
  - Windows-Python test runs and executable smoke tests in CI for every release.
- **Build size.** The desktop build is kept under 30 MB compressed as a working budget. New dependencies need a size justification. pdfplumber (v1.5) is pure Python and is expected to add about 1 to 2 MB.
- **Configuration.** One settings file covers data folder, rate limits, enabled boards, enabled sources, licence defaults and the review threshold.
- **Logging.** A structured log file per run, kept alongside `run_log.txt`.

### 18.13 Principal risks

| Risk | Effect | Mitigation |
|---|---|---|
| Live endpoints changed, blocked or restricted | Collection fails for a source | v1.4 self-test detects it early; adapters fixed or source moved to manual import; no circumvention |
| PDF layouts more varied than the corpus | Lower recall | Layout extractor (v1.5), corpus enlarged as failures are found, review workflow catches residual errors |
| Volume (about 1 TB of documents for the whole market over ten years) | Disk and time | Incremental runs, pruning after extraction, PostgreSQL option (v1.9) |
| Licensing of vendor data (Wind, CSMAR, Shenwan, ESG ratings) | Redistribution breach | Licence tags and release filtering (v2.0) |
| Personal information of officers and natural-person shareholders | PIPL exposure on release | Pseudonymisation option (v2.0) |
| Same-name persons and entities | Wrong links | Credit-code matching first; name matching only with corroboration, flagged for review (v1.8) |

### 18.14 Roadmap to v2.1

The end state (v2.0) is followed by maintenance releases driven by the author's live runs. Each release's findings are recorded under `docs/` before any code changes, and each plan is recorded before its build.

| Release | Status | Theme | Plan and findings |
|---|---|---|---|
| v2.0.1 | Released | First live run: CNINFO company list moved | Section 18.10 |
| v2.0.2 | Released | Second live run: market-wide catalogue, progress and Stop, listing dates | Section 18.10; `docs/live_run_findings_v2.0.2.md` (findings 1 to 19) |
| v2.0.3 | Released, 17 October 2026 | Catalogue complete within CNINFO's 3,000-result limit, resumable by day, errors per day; empty panels refused; warning summary | `CHANGELOG.md`; `docs/live_run_findings_v2.0.3.md` (findings 20 to 34) |
| v2.0.4 | Released, 18 October 2026 | Close the gaps on the busiest days: rows per security, a general splitter checked live, gaps by board | `docs/plan_v2.0.4.md`; `CHANGELOG.md` |
| v2.0.5 | Released, 22 October 2026 | Preparation for public release: user agent, rate ceiling, disclaimer, CONTRIBUTING and SECURITY | `CHANGELOG.md`; `docs/live_run_findings_v2.0.5.md` (findings 35 to 57) |
| v2.0.6 | Built, 23 October 2026 | Listing dates in full, extraction with progress and resume, the last catalogue gaps | `docs/plan_v2.0.6.md`; `CHANGELOG.md` |
| v2.1 | Planned | Chinese desktop interface, extraction speed, polish | `docs/plan_v2.1.md`; `docs/glossary_zh_CN.md` |

**v2.0.4 (patch; released 18 October 2026).** The first live whole-market catalogue under v2.0.3 confirmed the limit and resumption, but left 12 days short. The causes:
- overlapping board codes;
- categories still over 3,000 on one board on the April deadline days;
- announcements outside the Shanghai and Shenzhen boards;
- rows repeated for several securities.

The patch begins with a probe of CNINFO's filters (disjoint board codes, the industry field, company batches), and uses only the dimensions that probe confirms. The engine work then covers:
- a general splitter that checks every partition against its parent total;
- rows keyed by announcement ID and security code;
- gaps reported by board, so that a gap outside the enabled boards does not count as a shortfall;
- early stopping, a strategy-aware re-catalogue, rechecks of recent totals, and a "Finished with gaps" outcome.

Acceptance: re-cataloguing the 12 days leaves no gap within the enabled boards.

**v2.1.**
- **Workstream A:** an English / Simplified Chinese toggle for the desktop application only. It uses the official terminology of the approved glossary. Command-line output stays in English for now, and dataset contents are identical in both languages.
- **Workstream B:** extraction speed. The live rate is about 9 seconds per document; the target is a median of 2 seconds or less, without loss of parser accuracy. The means are a text cache, pdfium text checked against the golden corpus, and parallel extraction.
- **Workstream C:** the polish items from the v2.0.2 findings (7 to 11 and 16 to 18).
- **Workstream D (if confirmed):** publication readiness (Zenodo metadata and a publish-ready report).

**Later versions.** Translation of the command-line output, a Chinese user guide and chart captions.
