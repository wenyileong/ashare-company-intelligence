# Findings register, fix plan (v2.0.8) and the visualisation engine layer

**Status:** plan, 28 October 2026; decisions taken and build design added 29 October 2026 (sections 9 to 11). v2.0.8 was built from section 10 on 29 October 2026 (`CHANGELOG.md`).

**Basis:**
- the live-run findings 1 to 95, in five files under `docs/` (section 1);
- the NVF Topology Explorer design note (version 0.2, 25 October 2026) and its prototype, the NVF Topology Tester v0.1, tested here on 28 October 2026 (section 6).

**Aims, in order:**
1. one register of every live-run finding, with its status and the action that answers it;
2. a patch, v2.0.8, that makes the data correct before anything else, since every view built later will show whatever the database holds;
3. a visualisation engine layer for the Nested Valuation Framework (NVF): a layer between the validated data and any display, so that what is shown can always be traced, dated and exported.

## Contents

1. Where things stand
2. Findings register
3. What to do now (author)
4. v2.0.8: correct data first
5. Effect on v2.1
6. The NVF Topology Tester v0.1: test results
7. The visualisation engine layer
8. Order of work
9. Decisions (29 October 2026)
10. v2.0.8 build design, after a review of the code
11. The first episode: semiconductor policy events (candidates)

---

## 1. Where things stand

| Area | What works | What is wrong or missing |
|---|---|---|
| **Catalogue** | Every day of 2026 to date matches CNINFO's own total within the enabled boards (finding 72). Resume by day, splits, gap reporting. | Nothing open. |
| **Company list and listing dates** | The exchanges' stock lists date 5,224 companies in three requests (finding 70). | Panels still ignore those dates because of a stale listing history (finding 92). About 350 probably delisted companies have no status (finding 71). |
| **Market data** | Prices import from CSV. | Eastmoney refuses every request from the author's network, so no daily prices arrive (findings 66 and 73). |
| **Document extraction** | Financial extraction shows progress and resumes (v2.0.6). Top-10 shareholders read in both layouts (v2.0.7). | The other extractors take one to five minutes a report, with no estimate or resume (findings 76, 79 and 82). Financial figures are read with the wrong unit or wrong digits in at least 77 document pairs (findings 84 and 85). Segment totals often disagree (finding 83). Controller names are rarely read (findings 78 and 89). |
| **Validation** | The checks find the faults above: that is how findings 83 to 88 were found. | The findings display is unusable at 1,778 rows (finding 91). |
| **Releases and privacy** | Natural persons are masked whatever the rows hold (v2.0.7). | Shareholder percentages are still wrong for reports not yet re-read (finding 77). |

**Count.** Of the 95 findings:
- 41 are closed by a release;
- 23 record information, an expected result or an author's action;
- 31 are open.

Of the 31 open findings, 9 are high in effect: the data faults 77, 83, 84 and 85; the universe fault 92; and the speed findings 2, 32, 76 and 82.

---

## 2. Findings register

Severity is the effect if left alone. "Release" is where the fix belongs under this plan.

### 2.1 Open findings

#### Company list, listing dates and the point-in-time universe

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 92 | Panels ignore the new listing dates: a derived listing history without start dates takes precedence over the company record | **High** | Author: "Build listing history" now. Code: a derived history without a start gives way to the company's listing date; "Update the company list" rebuilds the history for the companies it changed | v2.0.8 (A) |
| 93 | A fiscal-year panel for 2026 has no annual figures, because the year has not ended; no warning | Medium | Warn when a fiscal year has not ended; report rows without any financial figure | v2.0.8 (A) |
| 71 | About 350 companies are in CNINFO's list but in neither exchange's list; only 165 are recognised as delisted | Medium | Mark NOT_IN_EXCHANGE_LIST when both lists are whole; take delisting dates from the listing events (finding 75); check a few by name first | v2.0.8 (A) |
| 9 | Code 201872 not recognised | Low | Classify or list as out of scope | v2.1 (C) |

#### Market data

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 73 (with 4, 34, 66) | Eastmoney refuses every request from this network; the daily price snapshot depends on it, and price histories may too | Medium | Author: test "Download daily prices" for one company. Code: if price histories are refused too, a second public source or licensed CSV import as the documented route | v2.0.8 (F), on the result |
| 18 | `show-market` prints nothing when there are no prices | Low | Say why | v2.1 (C) |

#### Document extraction: speed

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 76 | Top-10 shareholders: about five minutes a report (each report read twice, every page laid out) | **High** | Targeted reading: plain-text pass to find the pages, layout of those pages only, one reading per report for all its tables | v2.0.8 (C) |
| 82 | Segments: 600 reports in 8 h 30 min (about 51 s a report) | High | As 76 | v2.0.8 (C) |
| 2, 32 | Financial extraction about 9 to 20 s a document | High | Text cache and parallel extraction | v2.1 (B) |
| 79 (with 11) | The progress line says "0.0 per second" and counts readings, not documents | Low | Documents done and left, seconds each, an estimate, for every extractor | v2.0.8 (C) |

#### Document extraction: correctness

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 84 | 174 differences between two readings of the same period, 168 between two documents filed the same day; 100 differ by a power of ten (wrong unit) | **High** | Unit from the table that holds the figure, never assumed; documents that are not the report itself left out; the author's query identifies the pairs first | v2.0.8 (B) |
| 85 | Digits glued to figures (a note number) or cut at a separator: equity 11,791,960,892.40 against 1,791,960,892.40 | High | The v2.0.7 number check (`_WELL_FORMED`) applied to the financial readers; the note column kept apart | v2.0.8 (B) |
| 87 | The balance-sheet identity fails in 37 of 351 balance sheets | Medium | Expected to fall with 84 and 85; recheck after the re-extraction | v2.0.8 (B), acceptance |
| 86 | A difference between documents filed the same day counts as "explained" by any restatement filed that day | Low | Explained only by a restatement or corrected report that names the document | v2.0.8 (B) |
| 88 | The two parsers disagree on 1,345 figures | Medium | The review queue, and `evaluate-parsers` on hand-checked reports to learn which reader is more often right | v2.0.8 (B), measure only |
| 83 | Segment sums disagree with the reported total in 248 cases, with a median difference of 35% | **High** | Rows over page breaks and subtotal rows, checked against flagged reports | v2.0.8 (D) |
| 77 | The shareholder re-extraction stopped after about 100 reports; misread rows remain | **High** | Re-read all reports after the targeted reading (76) | v2.0.8 (C), then the author |
| 78, 89 | Actual controller named in 6 of 293 reports; a column heading, 与本公司的关系, read as a name | Medium | Controller parser for both exchanges' layouts; headings never accepted as names | v2.0.8 (D) |
| 1, 19 | PDF font handling: text may be incomplete for some fonts, and layout results can depend on the machine's fonts | Medium | Monitored; covered by the font check of v2.0.3. Revisit with the pdfium text pass of 76 | v2.1 (B) |

#### Validation and reporting

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 91 | "Show findings" prints 1,778 rows (about 10,000 lines), without the company code | Low | Count by rule and company first; company code per row; CSV export | v2.0.8 (E) |
| 8 | Empty results give no reason (compare, transactions, regulatory events, calendar) | Low | Say why | v2.1 (C) |
| 17 | The dataset explorer opens blank on an empty panel | Low | Say why | v2.1 (C) |

#### Desktop and installation

| # | Finding | Severity | Action | Release |
|---|---|---|---|---|
| 74 | The installer fails with a Windows error when the earlier version is running | Low | The installer checks for a running copy first and asks for it to be closed | v2.0.8 (E) |
| 7 | Parquet offered without pyarrow; partial panel files on failure | Low | Offer only what the build supports; write files atomically | v2.1 (C) |
| 10 | Optional-board settings can change during a run | Low | Lock during a run | v2.1 (C) |
| 16 | Intermittent DNS failures | Medium (environmental) | Longer retries for name-resolution failures | v2.1 (C) |

### 2.2 Information, expected results and the author's actions

| # | Content |
|---|---|
| 20, 21, 31, 33, 35, 36, 44, 49, 52, 53, 60, 63, 64, 67 | Live confirmations of the catalogue engine and the self-test |
| 42 | Corrected by finding 51 |
| 70, 72, 75 | Exchange lists work; 29 April complete; listing events read (130 listings, 1,050 delistings) |
| 80 | Transactions (41,388) and regulatory events (21,963) from titles only: details need the documents |
| 81 | Share-capital reconciliation had no data |
| 90 | Corporate actions read after the checks: run "Link events" and "Run all checks" again |
| 94 | 352 companies outside the 2026 panel, consistent with finding 71 |
| 95 | The corporate-action output was the earlier run |

### 2.3 Closed by a release

| Release | Findings |
|---|---|
| v2.0.3 | 3, 5, 6, 12, 13, 14, 15 |
| v2.0.4 | 22, 23, 24, 25, 26, 27, 28, 29, 30 |
| v2.0.6 | 37, 38, 39, 40, 43, 46, 47, 48, 50, 51, 54, 55, 56, 57 |
| v2.0.7 | 4 and 66 (listing dates; prices remain under 73), 41, 45, 58, 59, 61, 62, 65, 68, 69 |

Two of these are closed in the code but not yet in the data. The listing dates of finding 41 are not used by panels until finding 92 is fixed. The shareholder fix of finding 68 is only partly applied until the re-extraction finishes (finding 77).

---

## 3. What to do now (author)

These need no new build, and their results shape v2.0.8.

1. **"Build listing history"** (`rebuild-security-history`). Then build the panel for fiscal year 2025: `build-panel --unit year --align fiscal --start 2025-01-01 --end 2025-12-31 --universe-basis auto`. Expect most rows with `universe_basis = LISTING_RECORD` (findings 92 and 93).
2. **Identify the document pairs** behind finding 84, and send the output:
   `ashare-cli query "SELECT id, announcement_date, kind, title_cn FROM disclosures WHERE id IN (9,10,57,58,126,128,129,255,256)"`
3. **Check the controller** in one Shanghai and one Shenzhen report, and send the output: `ashare-cli control 600519` and `ashare-cli control 000001` (finding 78).
4. **Test price histories**: "Download daily prices" for one company (finding 73).
5. **Link and check again**: "Link events", then "Run all checks" (finding 90).
6. **Hold** any release meant for shareholder, segment or financial analysis until v2.0.8 and its re-extraction (findings 77, 83 to 85). A release for other purposes is safe from the privacy side: names are masked whatever the rows hold.

---

## 4. v2.0.8: correct data first

**Theme:** the figures in the database are right, the universe uses the listing dates, and the document extractors finish in hours, not days.

### Workstream A: the universe and panels (findings 92, 93, 71)

1. `universe_at`: a derived history without a start date falls back to the company record's listing date; it never excludes a company that has one.
2. "Update the company list" rebuilds the derived history for every company whose listing date or status it changed, and says so.
3. `build-panel`: for a fiscal-year row whose year has not ended, a warning before the build and a count of rows without any financial figure after it. The desktop form proposes the last complete fiscal year.
4. NOT_IN_EXCHANGE_LIST status when both exchange lists are whole and a company is in neither; its delisting date from the listing events where one exists.

**Accepted when** the author's 2025 panel has at least 4,500 rows on LISTING_RECORD, and a test reproduces finding 92 (history built before the dates) and passes.

### Workstream B: financial figures (findings 84 to 88)

1. **Units.** A figure takes its unit from a declaration in the same table, or the same page above it. With none, it is stored as UNIT_UNKNOWN and flagged; it is not assumed to be in yuan.
2. **Numbers.** The financial readers (text heuristic and statement table) use the well-formed number check of v2.0.7. A note reference (附注 column) is read as a separate column, never joined to the figure.
3. **Documents.** Only the report itself is read: titles such as 更正公告, 提示性公告 and 补充公告 are classed apart (after the author's query, section 3 item 2, confirms what the pairs are). A corrected report (更正后) replaces the original and records the link.
4. **Restatements.** A same-day difference is "explained" only by a corrected report or a restatement announcement that names the report.
5. **Re-extraction.** `EXTRACTOR_VERSION` moves to "financials-2", so a normal run re-reads every report.

**Accepted when** these targets are met after the author's re-extraction:
- `EXTRACTION_DISCREPANCY` findings with a power-of-ten ratio fall to zero;
- balance-sheet failures fall below 3% of the balance sheets checked;
- the golden corpus passes with no loss of accuracy;
- new corpus cases cover the five examples of finding 85.

### Workstream C: targeted reading, progress and resume (findings 76, 77, 79, 82)

1. **Find the pages.** A plain-text pass (pdfium) finds the pages that hold each section sought (top-10 shareholders, tradable holders, controller, segments), with the page after each.
2. **Lay out only those pages.** The layout reader works on those pages alone.
3. **Read once.** Each report is read once for all its tables; extractors register the sections they need.
4. **Follow and resume** for every document extractor, as for financials: total first, then documents done and left, seconds each, an estimate, and resume by extractor version.

**Accepted when:**
- top-10 extraction runs at 20 seconds a report or less on the author's machine;
- a stopped run resumes with the next report;
- the full re-extraction of shareholders finishes, and `show-ownership 000563` shows 26.80 and 16.76.

### Workstream D: segments and control (findings 83, 78, 89)

1. **Segments.** Join rows across page breaks; recognise subtotal rows (小计, 合计, 其中); compare the sum with the table's total and keep the table only when they agree within 1%, or flag it.
2. **Control.** Read the actual controller from both exchanges' layouts (table and narrative). A column heading is never a name.

**Accepted when** these targets are met, as judged by the author's check output (section 3 item 3):
- segment-sum findings fall below 10% of the tables read;
- controller names are found in at least 80% of reports that name one.

### Workstream E: installation and the findings display (findings 74, 91)

1. **Installer.** The installer checks for a running AShareScraper.exe or ashare-cli.exe and asks for it to be closed.
2. **Findings display.** "Show findings" opens with a count by rule and company. Each row carries the company code, and the findings can be exported to CSV.

### Workstream F: price sources the author chooses (finding 73)

Decided on 29 October 2026 (section 9): the program lets the author choose, rather than deciding for them.
- **Test.** "Test price sources" asks each public source for one company's last month of prices and reports what each returned.
- **Choose.** A price-source setting: Eastmoney (the present source), a second public source (Tencent's public daily-bar service), or none (CSV import only). Downloads, the backfill job and the daily update all follow it.
- **Import.** CSV import stays available whatever the setting, and an imported price is preferred to a public-feed price for the same day.

### Tests and release

- **Mock data.** The mock data gains:
  - a history built before listing dates arrive;
  - a document pair whose unit is declared only on another page;
  - a figure with a glued note number;
  - a segment table across a page break;
  - a controller table with its heading.
- **Test matrix.** As for v2.0.7: Linux Python 3.12 and 3.13, PostgreSQL 16, Windows under Wine (with the installer), GitHub CI.
- **Release.** The CHANGELOG, user guide and release follow as before. Commits are in the author's name only.

---

## 5. Effect on v2.1

`docs/plan_v2.1.md` stands, with two changes:
- **Workstream B (extraction speed).** It keeps the financial extractor (findings 2 and 32). The document extractors move to v2.0.8 (C), whose pdfium pass v2.1 reuses for its text cache.
- **Workstream C (polish).** It adds finding 9, and keeps 7, 8, 10, 16, 17 and 18. Finding 11 is answered by v2.0.8 (C).

---

## 6. The NVF Topology Tester v0.1: test results

The prototype was unpacked and tested on 28 October 2026, apart from the scraper's repository. The table records what was run and what it showed.

| # | Test | Result |
|---|---|---|
| P1 | The prototype's unit tests (`python -m unittest discover -s tests`) | **Pass**: 5 of 5, once its requirements are installed. Without `requests` the suite fails to import; it is listed in `requirements.txt`, so this is expected |
| P2 | `node --check app.js` | **Pass** |
| P3 | Loading the page as published (libraries from the jsdelivr CDN) | **Fails where the CDN is unreachable**: all three libraries were refused in the test environment, so the graph and charts are absent. The page reports this in plain words, as designed |
| P4 | Loading the page with the same library versions served locally (3d-force-graph 1.80.1, force-graph 1.52.0, Chart.js 4.4.8, from npm) | **Renders with no errors**: header, figures, filters, 3D graph (33 nodes, 31 links), revenue and net-profit charts, coverage table and observations. First visual check of the browser rendering |
| P5 | Switching to "2D slice" | **Fails**: a script error, `linkOpacity is not a function`. `linkOpacity` exists in the 3D library but not in force-graph 1.52.0, so the chain of settings stops and the 2D graph is blank |
| P6 | The 3D layout against the design ("fixed, meaningful coordinates for the five NVF layers") | **Not met**: nodes are given layer coordinates but are not fixed until 250 ms later. By then the force simulation has moved them, so the layers are not where the design puts them. The graph sits off centre, with one long edge leaving the view |
| P7 | Separation of calculation and display (design note, section 6) | **Not met**: the graph is assembled in the browser (`buildGraphData`), with company lanes, the policy identifier and the Cambricon R&D series written into the code. It does not generalise beyond the three companies |
| P8 | Sources | Figures come from Sina mirror pages of the reports and an ETF holdings page, not from the exchange filings. The scraper already holds the CNINFO originals with their hashes. The figures were not re-checked in this test |
| P9 | `refresh_data.py` live | Not run here: the test environment reaches only package registries. Its guard (no overwrite when a field fails) is covered by P1's fixtures only |
| P10 | Evidence inspector (clicking a node) | Not tested in the headless browser |

**What carries over.**
- **Kept:** the five-layer model, the evidence-status vocabulary, the coverage table that shows gaps rather than hiding them, the inspector, and the caution notes.
- **Not carried over:** the scraping script and the hand-assembled snapshot. The scraper's own database replaces them.
- **Rebuilt:** the browser code, after the engine layer (section 7) supplies the data. P5 to P7 are fixed there rather than in the prototype.

---

## 7. The visualisation engine layer

### 7.1 Purpose and principles

**Purpose.** A research instrument for the NVF: to inspect how institutional arrangements may connect to productive capability, corporate fundamentals, investor expectations and market valuation over time, for a defined set of companies. It sits between the validated data and any display. Charts, the 2D layered view, the interactive graph and exports all read the same prepared view, so they cannot disagree.

**Principles** (from the design note, section 8, and build plan section 18.11):
1. **No calculation in a renderer.** Every node, edge, value, date and status is decided in Python, tested there, and only drawn by the display.
2. **Every edge has an evidential status:**
   - **documented fact:** a document states the relationship;
   - **observed association:** a stated method computed it from data;
   - **estimated relationship:** a model with its uncertainty;
   - **theoretical proposition:** the NVF itself.
   
   The status is drawn by line style as well as colour, never by colour alone.
3. **Point in time by default.** A view at date *t* uses only what was published by *t*. Event date, publication date and observation date are kept apart and can each drive the timeline.
4. **Gaps are shown.** A layer or company without validated data appears as a gap, with the reason; nothing is interpolated.
5. **Provenance one step away.** Any node or edge leads to its document, page, extraction method, confidence class, review state and validation findings (the existing `trace`).
6. **Exportable.** Every view exports the exact observations behind it (CSV) and the view itself (JSON), with a manifest.
7. **Privacy and licences as in releases.** A view of shareholders or controllers applies the same pseudonymisation rule and licence filter as `release` (findings 68 and 69). The viewer never receives a natural person's name that a release would mask.
8. **Proximity is not causation.** Layout, adjacency and temporal order are never presented as evidence of control or effect; the inspector says what kind of evidence an edge is.

### 7.2 Architecture

```
  Stored data (SQLite or PostgreSQL)        existing: disclosures, facts, ownership, events, history
            |
  Analytical layer (Python)                 existing: panel, derived, valuation, eventstudy, validation
            |                               new: nvf.layers (variable -> layer), nvf.measures (registry)
            |
  View layer: the graph snapshot (Python)   new: ashare/viz/  build -> validate -> export
            |   snapshot.json + observations.csv + manifest.json (schema-versioned, deterministic)
            |
  Renderers
    R1  native 2D layered view              extends ashare/charts (Tk and SVG), publication figures
    R2  interactive viewer (optional)       one offline HTML file: 2D and 3D graph, timeline, inspector
    R3  later: research-suite-core          reads the same snapshot format
```

The snapshot is the contract. R1, R2 and any later suite read it and nothing else.

### 7.3 The graph snapshot (schema version 1)

**Snapshot.**
- **Identity:** `schema_version`, `built_at`, scraper version, a database fingerprint and the parameters (companies, episode, period, `as_of`, date basis).
- **Policy:** the coverage table by layer, the pseudonymisation rule, the licence filter, and the measure definitions used (with versions).

**Nodes.**

| Field | Content |
|---|---|
| `id`, `kind` | company, institution, policy_event, disclosure, observation, measure, shareholder, sector, data_gap |
| `layer` | institutional, capability, fundamentals, expectations, valuation, or none |
| `label`, `label_zh` | Display names (the zh label follows the approved glossary) |
| `company_code`, `sector` | Where applicable |
| `dates` | `event_date`, `published_date`, `observed_date`, `valid_from`, `valid_to` |
| `value`, `unit`, `period` | For observations and measures, in yuan or stated units |
| `provenance` | disclosure id, document hash, page, method, confidence class, review state, source URL |
| `flags` | Validation findings on the underlying rows |
| `masked` | True when a name was pseudonymised |

**Edges.**

| Field | Content |
|---|---|
| `id`, `source`, `target`, `relation` | For example HOLDS_SHARES, CONTROLS, REPORTS, NAMES_POLICY, RECEIVES_GRANT, PRECEDES, ASSOCIATED_WITH, NVF_PROPOSITION |
| `evidence_status` | DOCUMENTED_FACT, OBSERVED_ASSOCIATION, ESTIMATED_RELATIONSHIP, THEORETICAL_PROPOSITION |
| `basis` | The document and page for a fact; the method and its parameters for an association; the model specification and interval for an estimate; the paper's section for a proposition |
| `dates` | As for nodes |

**Rules checked when a snapshot is built.**
- An edge marked DOCUMENTED_FACT has a provenance record.
- An edge from a policy to a company is never a fact unless a company document names the policy or the support (for example a tax preference or a government grant in its report).
- No date is after `as_of` on the chosen basis.
- Masked names stay masked.
- The same parameters give the same file, byte for byte.

### 7.4 What the scraper can supply for each layer

| NVF layer | Existing in the scraper | Blocked by | New work |
|---|---|---|---|
| **Institutional coordination** | Regulatory events (titles; documents optional) | 80 (titles only) | Policy events as a curated import (`import-policy-events-csv`: issuer, date, document, scope, sector codes). Documented exposure from companies' own reports: tax preferences (高新技术企业, the integrated-circuit preferences) and government grants (政府补助) as extraction items |
| **Productive capability** | R&D staff, R&D investment and intensity, workforce composition, patents (`human_capital.py`); capital expenditure where the cash-flow statement is read | 76, 82 (speed); 84, 85 (numbers) | Capex from the PDF cash-flow statement; comparability notes by business model |
| **Corporate fundamentals** | Financial statements, segments, restatements, validation classes | 83 to 88 | None beyond v2.0.8 |
| **Investor expectations** | Earnings forecasts and flash reports are classified by title (业绩预告, 业绩快报), not read | 80 | Read forecast ranges and dates. They are labelled as **management guidance**, a disclosed proxy, not investor expectations. Analyst forecasts only by licensed CSV import. The layer stays a visible gap until a source is chosen |
| **Market valuation** | Prices (import or Eastmoney), adjustment factors, market capitalisation and point-in-time ratios (`valuation.py`) | 73 (prices refused); 81 (no share capital) | Share capital from reports, or by import |
| **Ownership and control (edges)** | Top-10 shareholders, controller chain, entity resolution | 77, 78, 89 | None beyond v2.0.8 |
| **Universe and time** | Point-in-time security master, listing events | 92, 93, 71 | None beyond v2.0.8 |

The engine can start with what is unblocked, but no view of fundamentals, capability or ownership should be shown to others before v2.0.8 and the re-extraction.

### 7.5 Measures: defined before computed

`nvf.measures` is a registry of measure definitions. Each definition records:
- an identifier and version;
- the inputs, by variable and layer;
- the time rule;
- the formula or procedure;
- the falsification condition;
- a status: PROPOSED, DEFINED or ESTIMATED.

The engine computes only DEFINED measures. A view shows each measure's status and its alternative definitions side by side, with missing observations counted.

The NVF's own constructs, Institutional Visibility and the Fractal Investment Clock, enter as PROPOSED. They become DEFINED only when the author has fixed their variables, intervals and falsification conditions (design note, section 10). Candidates for the author to consider, not decisions:
- **Investment intervals:**
  - days from a policy event's publication to the first company document naming it;
  - then to a rise in capital expenditure or R&D beyond a stated threshold;
  - then to a change in revenue;
  - then to a valuation change.
  
  Each interval is measured per company and episode. "Fractal" is a hypothesis about how these intervals compare across scales, tested only once the intervals are defined.
- **Institutional Visibility:** the market's response to capability disclosures, for example abnormal returns around R&D or capacity announcements, using the existing event-study module. Its definition depends on prices (finding 73).

### 7.6 Renderers

**R1: native 2D layered view (first).** A new chart kind, `layers`, in the existing chart specification.
- **Layout:** the five layers as fixed columns and companies or sectors as rows, with edges styled by evidential status.
- **Time:** small multiples by year or by `as_of` date.
- **Rendering:** drawn by the Tk renderer in the desktop and by the SVG renderer for reports and publication figures, so it carries the existing guarantees: provenance tooltips, confidence markers, gaps shown, CSV of the plotted data.
- **Why first:** it answers the design note's own baseline (2D and tables before 3D), and needs no new dependency.

**R2: interactive viewer (optional, after R1).**
- **Format:** one HTML file written next to the snapshot, with the snapshot embedded, so it opens from disk with no local server and no network. The desktop opens it with the system browser ("Open topology view").
- **Libraries:** the graph libraries (3d-force-graph, force-graph, Three.js) and Chart.js are bundled at pinned versions, never fetched from a CDN (finding P3). They are MIT-licensed; THIRD_PARTY_NOTICES records them. About 1.8 MB.
- **Behaviour:**
  - 2D and 3D graphs, with layer coordinates fixed when the nodes are created and no force simulation on the layer axis (P5, P6);
  - force layout only for exploratory company networks within a layer;
  - a timeline driven by the chosen date basis;
  - filters for company, layer, relation and evidential status;
  - the inspector, which shows the snapshot's provenance and opens the source document;
  - export of the view's observations.
- **No calculation** in the page (P7): it draws the snapshot.

**R3: the research suite.** Because the snapshot is a documented format, `research-suite-core` can later read it without touching the scraper's code. The suite stays a separate repository that only reads from the tools.

### 7.7 Phases and acceptance

| Phase | Content | Accepted when |
|---|---|---|
| **V0. Contract** | `ashare/viz/`: schema (JSON Schema), builder for a list of companies and a period, validation rules (7.3), export with manifest; `nvf.layers` mapping of panel variables to layers | Snapshots are deterministic. Every DOCUMENTED_FACT edge traces to a page. A masked name never appears. No date passes `as_of`. All of this is tested on the synthetic corpus |
| **V1. 2D layered view** | Chart kind `layers` in Tk and SVG; "Topology" page in the desktop; export | Renders identically in the desktop and SVG (existing pixel tolerance). The CSV export reproduces the plotted observations |
| **V2. Interactive viewer** | Offline HTML with bundled libraries; 2D and 3D; timeline; inspector | Opens with the network off. P5 and P6 are fixed. The inspector matches `trace` for every node tested. 1,000 nodes stay interactive on a typical PC |
| **V3. First episode: semiconductors** | Inclusion rules (CSRC division C39 and stated additions), episode dates, source hierarchy; policy-event import and exposure coding from companies' reports | A researcher can reconstruct why each node and edge appears, tell observed from inferred, and export the observations used (the design note's success criterion) |
| **V4. Measures** | Registry; computation of DEFINED measures only; alternative definitions and missingness shown | Each computed value names its definition and version. PROPOSED measures are shown as such and not computed |
| **V5. Is 3D worth it?** | A small task study: fixed tasks (find the source of an edge; order a company's capability and valuation observations; spot a coverage gap) in table, 2D and 3D, timed and scored | A decision recorded under `docs/`: 3D kept, kept as optional, or dropped |

### 7.8 Risks

| Risk | Mitigation |
|---|---|
| Wrong figures drawn persuasively | Built only on data past v2.0.8; confidence and findings shown on every node; review state visible |
| A layout read as causation | Evidential status on every edge, line styles, the inspector's wording; THEORETICAL_PROPOSITION edges never attached to a company |
| Policy relevance read as company exposure | Exposure edges only from a company's own document; otherwise a sector-level link, labelled as such |
| Personal data in shared views | The release pseudonymisation rule applied in the builder, tested |
| Dependencies and installer size | R1 needs none; R2 bundles about 1.8 MB of MIT-licensed scripts, loaded only by the viewer |
| Scope drift into a general graph tool | One episode first (V3); whole-market graphs only after V5 |

---

## 8. Order of work

| Step | Content | Depends on |
|---|---|---|
| 1 | Author's actions (section 3) | Nothing |
| 2 | v2.0.8 A (universe) and B (financial figures) | Step 1, items 1 and 2 |
| 3 | v2.0.8 C (targeted reading) and D (segments, control), then E and F | Step 1, items 3 and 4 |
| 4 | Author: full re-extraction under v2.0.8; checks and panel again | v2.0.8 |
| 5 | v2.1 (language, financial extraction speed, polish) | v2.0.8 |
| 6 | Visualisation V0 and V1 (v2.2) | v2.0.8 released; can run beside v2.1 |
| 7 | V2 and V3 (v2.2 or v2.3) | V1; the author's episode rules |
| 8 | V4 and V5 (v2.3) | The author's measure definitions |

V0 can be designed while v2.0.8 is built, since it touches no extractor. Nothing visual is released before step 4.

---

## 9. Decisions (29 October 2026)

| # | Question | Decision | Where it goes |
|---|---|---|---|
| 1 | Where the viewer lives | Inside this repository, as an optional part of the desktop | V0 to V2 under `ashare/viz/`; the snapshot format stays documented so `research-suite-core` can read it later |
| 2 | Order against v2.1 | Visualisation V0 and V1 beside v2.1 | After v2.0.8 (section 8, step 6) |
| 3 | First episode | Semiconductors (CSRC division C39) | Policy events and dates proposed in section 11, for the author to confirm |
| 4 | Expectations | Management guidance (业绩预告 and 业绩快报) first, labelled as a proxy, with the structure ready for licensed analyst forecasts | Section 10.7 |
| 5 | Prices | Selectable: the author's test, a public source, or CSV import | v2.0.8, Workstream F (section 4); design in section 10.6 |
| 6 | NVF measures | Still open: defined by the author before anything is computed | Section 7.5 |

---

## 10. v2.0.8 build design, after a review of the code

Before building, each workstream was traced through the code that it changes, to test the plan's logic and look for faults the findings had not yet shown. The review changed the plan in eight places; they are marked **(review)**.

### 10.1 Universe and panels (Workstream A)

- **The fault (finding 92).** `universe_at` uses the derived history whenever a company has one. A derived period without a start date then excludes the company, and its listing date is never read.
- **The fix.** A derived history whose first period has no start is ignored in favour of the company record, which has the listing date and status. Imported histories keep priority as before.
- **Update the company list.** It rebuilds the derived history of every company whose listing date or status it changed, and reports how many.
- **NOT_IN_EXCHANGE_LIST (finding 71).** A company is given this status only when:
  - both exchange lists are whole;
  - the company is in neither;
  - its name does not mark it as delisted (those stay DELISTED).
  
  **(review)** The present code sets NOT_IN_QUOTE_LIST only from a complete quote list. Since v2.0.7 skips the quote list when the exchange lists are whole, that status was never set; the new one replaces it in that case.
- **Panels (finding 93).** The result carries `fiscal_years_not_ended` and `rows_without_financials`, and the command prints a warning for both. The desktop form's default period becomes the last complete fiscal year.

### 10.2 Financial figures (Workstream B)

- **Which documents (finding 84).** **(review)** The title classifier calls any title containing 年度报告 an annual report. That includes "关于2025年年度报告的更正公告" (a correction notice), "2025年年度报告披露提示性公告" (a notice that the report is out, often filed the same day as the report) and 补充公告 (a supplement). These short notices are the most likely second documents of finding 84's same-day pairs. They are now classed `report_notice`, and stored kinds are reclassified at the start of each extraction. A corrected full report (年度报告（更正后）, 修订版) stays a report.
- **Units (finding 84).** **(review)** `declared_unit` searches back through every earlier page and takes the nearest declaration. A figure in a key-figures table with no declaration of its own can therefore take the unit of an unrelated table pages earlier, for example 万元 from a fund-raising table. The search is limited to the figure's own page (above the figure) and the end of the page before. With no declaration there, the figure is stored in 元 but marked `unit: CNY_ASSUMED`, its confidence lowered, and checked against the statement reader below.
- **Power-of-ten check within a document.** When the headline reader and the statement reader give the same metric in the same document, and the values differ by 1,000, 10,000, a million or a hundred million, the statement reading (whose unit is declared on its page) is kept, the headline reading is rescaled, and the note records it.
- **Numbers (finding 85).** **(review)** The well-formed check of v2.0.7 does not catch this fault, because a glued note number gives a well-formed figure: "1" + "1,791,960,892.40" reads as "11,791,960,892.40". Two rules replace it:
  - a figure that directly follows a note reference (七、1, 五、45, 附注) with no space is ambiguous. Both readings, one-digit and two-digit note, are tried. The reading is kept only if one of them matches another reader of the same document; otherwise it is dropped and counted;
  - an amount in 元 must carry two decimals ("22,103" and "1,355.2" are rejected); in 万元 or larger units, up to four.
- **Restatements (finding 86).** A difference between two documents filed on the same day is never "explained". If one of them is a corrected report, the finding is CORRECTED_REPORT (information); otherwise it stays EXTRACTION_DISCREPANCY.
- **Re-extraction.** `EXTRACTOR_VERSION` becomes "financials-2".

### 10.3 Targeted reading, progress and resume (Workstream C)

- **One reader per report.** A `ReportReader` opens the PDF once. It keeps:
  - the fast page text (pdfium, the whole page at a time) for finding sections;
  - the plain text (pypdf) of the pages asked for only;
  - the layout rows of the pages asked for only.
- **Sections.** Each extractor names the sections it needs, by pattern (for example 前十名股东持股情况), and how many pages after each heading belong to it. The reader returns pages of the full length, blank outside the sections, so page numbers and the parsers are unchanged.
- **Fallbacks.** If no section is found, or pdfium is not installed, the whole document is read as before, so nothing that worked before is lost.
- **The extractors moved to it:** top-10 and tradable holders (one reading for both), control, segments, R&D and workforce, subsidiaries, and the management roster.
- **Resume.** A new table, `extraction_state`, records each (document, extractor) pair with the extractor's version (migration 0006). Financial extraction keeps its own columns from v2.0.6.
- **Progress.** One helper gives every extractor the line financial extraction has: total first, then documents done and left, seconds each, and an estimate (finding 79).
- **Versions.** The top-10, control and segment extractors start at new versions. A normal run therefore re-reads every report and finishes the shareholder re-extraction (finding 77).

### 10.4 Segments and control (Workstream D)

- **Segments (finding 83).** **(review)** The review found three faults in the parser:
  - The parser forgets the table's dimension and unit at each new page, and skips a page without a heading. Rows continued on the next page are therefore lost, which explains most sums below the total. The state now carries over to the next page while the table continues.
  - "小计" rows and "其中：" breakdown rows are counted as segments, which explains sums above the total. They are now kept out of the sum, and stored with `is_total` for subtotals and not stored for breakdowns.
  - The margin table (主营业务分行业…, "占公司营业收入或营业利润10%以上") lists only major segments by rule. A dimension read only from that table is compared with its own 合计 row if it has one, and otherwise not compared with total revenue. The table kind is stored (`table_kind`, migration 0006).
- **Control (findings 78 and 89).** **(review)** Two faults explain 6 of 293:
  - Shenzhen reports head the controller section "公司实际控制人及其一致行动人", which the parser never looks for.
  - Shenzhen reports lay the section out as a header row ("控股股东名称 法定代表人/单位负责人 成立日期 …" or "实际控制人姓名 与本公司的关系 国籍 …") with the values on the next row. The parser took the next word after 姓名, which is the heading 与本公司的关系 (finding 89).
  
  The new parser reads both layouts:
  - label and value (Shanghai);
  - header row and value row (Shenzhen);
  - the 实际控制人性质 and 类型 lines.
  
  A set of known headings is never accepted as a name, and several natural persons joined by 、 are kept together.

### 10.5 Installer and findings display (Workstream E)

- **Installer (finding 74).** Before copying, the installer tries to open the installed AShareScraper.exe and ashare-cli.exe for writing. If either is locked, it asks for the program to be closed, with Retry and Cancel. In silent mode it stops with an error code instead of writing over a running program.
- **Findings (finding 91).** "Show findings" opens with counts by rule and severity and the 20 companies with most findings. Every row has the company code. `--details` lists the rows, and `--export file.csv` writes them all.

### 10.6 Price sources (Workstream F)

- **Providers.** A small registry: `eastmoney` (push2his daily bars) and `tencent` (the public daily-bar service, labelled TENCENT_PUBLIC). Both are unofficial public feeds, not exchange-authoritative; their terms are the user's to check, as the release notes already say for Eastmoney. The Tencent request format is taken from its public use, and was not reachable from the build environment; "Test price sources" is how the author confirms it.
- **Setting.** `price_source`: eastmoney, tencent or none. It is chosen in the desktop's Settings and applies to "Download daily prices", the backfill job and the daily update.
- **(review)** When the daily snapshot fails, the daily update queues a backfill for every company without a recent bar. With Eastmoney refusing, that is about 5,500 failing requests a day. The backfill now follows the setting, and stops after three refused companies in a row, as the quote list does.
- **Preference.** One close per day is kept: imported (CSV) first, then the chosen public source.

### 10.7 Expectations: guidance first, analyst forecasts later

Built with V0, beside v2.1 (decision 2), not in v2.0.8.
- **Table.** `expectation_observations` holds one row per company, period and measure. Each row records:
  - the measure (net profit attributable, revenue, and so on);
  - the low and high values, and the change range in per cent;
  - `source_kind`: MANAGEMENT_GUIDANCE or ANALYST_FORECAST;
  - the issuer (the company, or the broker for a forecast);
  - the publication date, and the document and page.
- **Guidance.** 业绩预告 and 业绩快报 are read for their ranges and dates.
- **Analyst forecasts.** `import-analyst-forecasts-csv`, with the licence recorded, fills the same table with `source_kind = ANALYST_FORECAST`. The visualisation's expectations layer reads either, says which, and never mixes them in one series.

### 10.8 Tests written before the code

Each fault above gets a test that fails on v2.0.7 and passes on v2.0.8:
- the stale history;
- the fiscal year not ended;
- NOT_IN_EXCHANGE_LIST;
- a notice title classed as a report;
- a unit taken from an unrelated earlier page;
- a glued note number;
- a figure cut at a separator;
- a same-day "explained" restatement;
- a segment table continued over a page, with 小计 and 其中 rows;
- both controller layouts;
- the backfill after a failed snapshot;
- resume after a stop for the new extractors;
- targeted reading giving the same rows as a full reading on the synthetic corpus.

---

## 11. The first episode: semiconductor policy events (candidates)

For the author to confirm before V3. Dates are the issuing or registration dates as stated by the sources. The authoritative document is listed first. Where only a secondary source was checked, the table says so, and the primary document should be retrieved before use.

| Date | Event | Type | Source checked |
|---|---|---|---|
| 2014-06-24 (published 26 June 2014) | 《国家集成电路产业发展推进纲要》, approved by the State Council and issued by MIIT; provides for a national industry investment fund | Strategy | Reposted text on the Cyberspace Administration of China site (cac.gov.cn, 26 June 2014). The issue date of 24 June is to be confirmed against MIIT's original |
| 2014-09-24 | National IC Industry Investment Fund (国家集成电路产业投资基金, "Big Fund I") established | Funding vehicle | Secondary only (The Paper, 25 October 2019, citing public information) |
| 2019-07-22 | STAR Market opens: a listing route used by many semiconductor firms | Market institution | Not checked here; to confirm from SSE |
| 2019-10-22 | Big Fund II registered, capital RMB 204.15 bn | Funding vehicle | Secondary (The Paper, citing the National Enterprise Credit Information Publicity System) |
| 2020-07-27 (published 4 to 6 August 2020) | 国发〔2020〕8号, 新时期促进集成电路产业和软件产业高质量发展若干政策: tax, financing, R&D, import and export, talent, IP, market and international policies | Policy package | Ministry of Ecology and Environment repost of the State Council notice (mee.gov.cn): 成文日期 27 July 2020; publication date to confirm on gov.cn |
| 2022-10-07 | United States export controls on advanced computing and semiconductor manufacturing items (Federal Register 2022-21658, published 13 October 2022) | External shock | Federal Register API record |
| 2023 (date to confirm) | 财税〔2023〕17号: an additional VAT deduction for listed IC enterprises, for 2023 to 2027 | Tax preference | Referred to by the 2023 and 2025 list notices on chinatax.gov.cn; the notice itself, its rate and date to retrieve |
| 2023-08-28 | 工信部联电子函〔2023〕228号: requirements for the 2023 list of IC enterprises eligible for the VAT deduction | Eligibility list | State Taxation Administration policy database (fgk.chinatax.gov.cn) |
| 2024-03-22 | NDRC and others: the 2024 list of IC and software enterprises and projects eligible for tax preferences | Eligibility list | NDRC notice (ndrc.gov.cn), as used in the prototype |
| 2024-05-24 | Big Fund III registered, capital RMB 344 bn | Funding vehicle | Secondary (China Securities Journal, cs.com.cn, citing the National Enterprise Credit Information Publicity System) |
| 2025-09-16 | 工信部联电子函〔2025〕234号: the 2025 VAT-deduction list | Eligibility list | State Taxation Administration policy database |

**Exposure.** None of these events is linked to a company until the company's own document shows exposure, for example:
- a report naming the preference it enjoys;
- a government grant;
- the Big Fund among its top-10 shareholders.

That last case can be read from the top-10 tables once v2.0.8 has re-read them. The fund's shareholdings in listed companies are a documented, dated and company-specific link, which makes them the strongest first exposure measure.

**Inclusion rule (proposed).** Companies classified in CSRC 2012 division C39 (计算机、通信和其他电子设备制造业) whose segment tables name integrated circuits, semiconductors, wafers, chips or semiconductor equipment and materials. The list is frozen at each panel date, with the classification history of `industry.py`.
