# Findings register, fix plan (v2.0.8) and the visualisation engine layer

**Status:** plan, 28 October 2026. Nothing in it is built yet.

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
9. Decisions needed

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

### Workstream F (conditional): prices (finding 73)

If the author's test (section 3 item 4) shows that price histories are refused too:
- a second public source, chosen after a check of its terms;
- otherwise, CSV import as the documented route, with the user guide saying so.

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

## 9. Decisions needed

1. **Where the viewer lives.** Inside this repository, as an optional part of the desktop (recommended for V0 to V2, so it shares the provenance, privacy and release code). Or in `research-suite-core` from the start, reading the snapshot.
2. **Order against v2.1.** Visualisation V0 and V1 beside v2.1, or after it.
3. **The first episode.** Semiconductors (CSRC C39) with which policy events and dates.
4. **Expectations.** Accept management guidance (业绩预告) as a labelled proxy, obtain licensed analyst forecasts, or leave the layer as a gap.
5. **Prices.** Depends on the author's test (section 3, item 4): a second public source, or CSV import only.
6. **The NVF measures.** Variables, intervals and falsification conditions for Institutional Visibility and the Fractal Investment Clock, before any are computed.
