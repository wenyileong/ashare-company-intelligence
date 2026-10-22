# Methods

This document describes how A-share Company Intelligence (version 2.0) acquires, extracts, validates and releases data on companies listed in mainland China. It is written to be cited in the data section of research that uses a dataset built with the program. A suggested citation is given in section 9.

## 1. Scope and sources

The universe is the A-share market: the Shanghai Stock Exchange (SSE) Main Board and STAR Market, and the Shenzhen Stock Exchange (SZSE) Main Board and ChiNext. The Beijing Stock Exchange and B shares are supported but excluded by default.

Sources are ranked by authority, and a lower-ranked source never silently replaces a higher-ranked one:

1. **Statutory disclosures and exchange publications.** The CNINFO disclosure platform (巨潮资讯网), designated by the China Securities Regulatory Commission (CSRC) for information disclosure by listed companies, supplies the company list, the announcement catalogue and the documents (periodic reports, notices and circulars). Exchange pages (SSE, SZSE) supply supervisory measures and disciplinary decisions.
2. **Public market feeds.** Daily prices and quotes come from a free public feed (Eastmoney). These data are not exchange-authoritative and are labelled as such; licensed price data can be imported instead and are then preferred.
3. **Licensed and manual data.** Vendor data (for example ESG ratings, Shenwan industry classifications, index constituent files) and the researcher's own hand coding are imported from CSV files and keep their own source labels.

Acquisition is polite and transparent: one request per second by default (never more than two, whatever the settings), an identifying user agent, no circumvention of authentication, CAPTCHAs, access controls or rate limits, and no use of licensed data beyond its licence. Every response and document is stored as received, with its URL, retrieval time and SHA-256 hash.

## 2. Provenance

Every observation records its source, the source document (with hash), the page, the raw text or cell, the normalised value and unit, the extraction method, a confidence score and a validation status. Corrections made in review are stored in a separate table keyed to the observation's natural key, so that the original extraction is never overwritten and survives re-extraction. The command `trace` (or the Review page) reconstructs the full chain for any value and re-checks the document hash.

## 3. Point-in-time rules

The program distinguishes the period a value describes from the date on which it became known.

- **Publication date.** Each value carries the announcement date of the document it was read from. A value is "known at date D" if it was published on or before D.
- **Vintages and restatements.** When a later document reports a different value for the same company, period and item (for example the comparative column of the next annual report), both vintages are kept. A point-in-time query returns the latest vintage published by D, and restated values are marked.
- **Universe.** The list of companies at date D is rebuilt from listing, delisting, name, code and board events (security history), so samples include companies that later delisted and use the names and boards they had at D. This removes survivorship bias from the universe.
- **Derived values.** Single-quarter values are differences of year-to-date reports; trailing-twelve-month (TTM) values add the latest annual figure to the current year-to-date figure and subtract the corresponding prior-year figure. A derived value carries the latest publication date among its inputs and the lowest confidence class among them.
- **Panels.** In a fiscal-aligned panel each row is a fiscal period and each financial variable is the latest vintage known at the as-of date. In a point-in-time panel each row is a date D (for example 30 April each year, or each month end) and each variable is what had been published by D, less an optional reporting lag. With an as-of date, no value published after it enters the panel; the builder enforces this as a look-ahead guard and records the latest publication date used in the manifest.

## 4. Extraction

Documents are read from their text layer; scanned documents without one are listed and not parsed (there is no optical character recognition).

**Parsers.** Each kind of content (headline financials, consolidated statements under a versioned chart of 132 Chinese Accounting Standards line items, segments, subsidiaries, R&D and workforce, officer tables, top-10 shareholders, control, pledges, corporate actions, regulatory events, transactions, ESG items) has a registered parser. Table parsers have two variants: one reads the text stream, the other reconstructs table rows from character positions on the page (rebuilding cells that wrap onto several lines).

**Dual running.** Both variants are run. The variant with the higher calibrated precision supplies the value. If both produce the same value, the agreement is recorded and confidence rises by 0.05; if they disagree, confidence is capped at 0.4, the alternative value is stored, and the value is flagged `PARSER_DISAGREEMENT` for review.

**Units.** The unit of each table is taken from the nearest preceding unit declaration (for example 单位：万元 or 单位：人民币千元), never from an unrelated part of the document.

**Classification.** Announcements are classified by title into kinds (periodic reports, distributions, corporate actions, regulatory events, management changes, pledges, transactions and others). Regulatory events are classified by the legal instrument named in the document (administrative penalty, administrative supervisory measure, exchange discipline, civil or criminal proceedings), not by inferred severity. Ownership type (central state-owned, local state-owned, private, foreign, collective, no controller) is classified from the actual-controller section, with the basis of the classification stored; unclassifiable cases are flagged.

**Entities and persons.** Organisations are resolved by unified social credit code (with the check digit verified under GB 32100-2015) or by normalised name. Directors and officers are resolved across companies by name, gender and birth year (within one year); people without an age are not merged.

## 5. Validation

Validation runs in stages and only ever adds flags; it never changes a value.

1. **Schema.** Valid codes, exchanges, boards, dates and numbers, and required provenance.
2. **Internal accounting.** Total assets must equal total liabilities plus equity within 0.5% (or 1,000 yuan); segment revenues, R&D components and workforce breakdowns must add up to their reported totals; the top-10 shareholdings may not sum to more than 100%; interim figures may not exceed the annual figure for the same year. A cash-flow reconciliation is not yet implemented.
3. **Cross-document.** A report against the comparative figures of the next report; share capital at t0 plus recorded corporate actions against capital at t1; ownership disclosures against later capital changes; sustainability-report mandates against observed reports.
4. **Cross-source.** Where an authorised second source is imported, values are compared and differences flagged.
5. **Confidence class.** Each value is classed HIGH, MEDIUM, LOW or UNVALIDATED from its confidence and validation status. HIGH requires confidence of at least 0.95, or at least 0.85 with a passed check; a failed check caps the class at LOW.

## 6. Calibration

Confidence scores are calibrated against a golden corpus: real documents whose expected values a researcher has verified by hand. For each parser the program counts correct, wrong, missed and spurious values and computes precision, recall and the lower bound of the 95% Wilson score interval for precision. When at least 30 values have been scored with the current parser version, that lower bound (capped at 0.9 for text heuristics) replaces the parser's default confidence. Calibration is tied to the parser version, so a changed parser falls back to its default until it is re-evaluated. A synthetic corpus generated by the program is used only as a regression gate in testing (precision may not fall by more than one percentage point), never for calibration.

The review queue gives a second, independent measure: the share of reviewed values accepted, corrected or rejected. Because values are chosen for review when they are doubtful, these rates overstate the error rate and are reported beside calibration, not merged with it.

## 7. Market measures

**Adjustment.** Price-adjustment factors are computed from the recorded corporate actions rather than taken from a provider. At each ex-date, the reference price is (P minus cash dividend plus rights ratio times rights price) divided by (1 plus share ratio plus rights ratio), where P is the last unadjusted close before the ex-date; the factor is P divided by the reference price, and cumulative factors are products of factors. Provider-adjusted series are kept and compared with the program's own.

**Valuation.** Market capitalisation is the close times total shares from the latest capital observation on or before the date. P/E uses TTM net profit attributable to the parent, P/B equity attributable to the parent, P/S TTM revenue; enterprise value adds interest-bearing debt and subtracts cash. Only financial values published on or before the date are used.

**Event studies.** Day 0 is the company's first trading day on or after the event date. Abnormal returns follow the market model, market-adjusted or mean-adjusted returns, with an estimation window of trading days −250 to −31 and an event window of −1 to +1 by default. The benchmark is an equal-weighted market average or an imported index. Reported statistics are the mean cumulative abnormal return, its cross-sectional standard deviation, t = mean / (sd / √N), and the share of positive CARs.

## 8. Releases

A release is a dated, self-describing folder with one CSV per table, a SQLite snapshot, a data-quality report, a citation file and a manifest recording the software version, schema revision, database fingerprint, row counts and the SHA-256 hash of every file.

**Licences.** Each row is assigned a licence class from its source: public disclosure, public feed, derived, manual, or licensed. Licensed rows are excluded by default; the manifest records the classes included and excluded and the number of rows left out per table. Imports are treated as licensed until the researcher tags their source otherwise.

**Pseudonymisation.** Optionally, names of natural persons (directors, supervisors and officers, natural-person shareholders, pledgors and controllers) are replaced with identifiers formed from the HMAC-SHA256 of the normalised name under a secret key held outside the release. The same name receives the same identifier in every release made with that key, and identical names map to the same identifier, so pseudonymisation neither adds nor removes linkage relative to the names. Raw text columns and document text are dropped, known names are replaced in free text, and ages and birth years can be banded. Organisations keep their names.

**Data-quality report.** Coverage by layer, board and year (the share of companies with at least one observation), parser precision from calibration, review statistics, validation-flag rates per 100 companies, the distribution of confidence classes, and known gaps, both computed (for example layers without data, scanned documents) and standing limitations (section 10).

## 9. Citing a dataset

Cite the release by its name, the software version and the database fingerprint given in `manifest.json` and `CITATION.cff`, for example:

> A-share Company Intelligence dataset release 'ashare_release_20261008T120000Z' (2026), built with A-share Company Intelligence v2.0.2; database fingerprint 3f9a0c21b7de4a55. Created 2026-10-08.

State in the data section the as-of date of any panel, the universe and filters used, the minimum confidence class, whether only reviewed values were used, and whether the release was pseudonymised.

## 10. Limitations

- Source adapters depend on the current form of public websites and interfaces, which change without notice. The self-test detects such changes; it is run on the user's machine because the build environment has no access to the sources.
- Heuristic extraction is imperfect. Confidence scores are only as good as the golden corpus used to calibrate them; without one, default priors apply.
- Scanned documents are not read, and ownership diagrams (方框图) are usually images, so intermediate stakes in control chains must be imported.
- The free price feed is not exchange-authoritative.
- Reports prepared under accounting standards before the 2006 Chinese Accounting Standards for Business Enterprises may not map cleanly to the chart of line items.
