# v2.1 build plan

**Status:** plan, revised 30 October 2026. It now carries the fixes planned as v2.0.10 (`docs/plan_v2.0.10.md`, merged here at the author's request) and the first two phases of the visualisation layer (decided on 29 October: V0 and V1 beside v2.1). The plan was tested for logic against the code in six rounds, until a round found nothing new; the faults found and how the plan answers them are in section 12. Nothing in it is built yet.

**Earlier version:** 18 October 2026: the language toggle, extraction speed and polish. Those three workstreams are kept, revised where the live runs since then changed them.

**Theme:**
1. Correct data first: the remaining faults from the live runs.
2. Extraction fast enough for the whole market.
3. A Chinese desktop interface.
4. The first visualisation layer.

## Contents

1. Where things stand
2. Scope
3. Workstream A: data corrections from the live runs (findings 98 and 104 to 109)
4. Workstream B: extraction speed (findings 2, 32, 101 and 107)
5. Workstream D: interface language toggle (desktop only)
6. Workstream C: polish (findings 7 to 10 and 16 to 18)
7. Workstream E: visualisation layer, V0 and V1
8. Workstream G: publication readiness (proposed; confirm)
9. Schema and versions
10. Order of work
11. Testing and release
12. Logic review: six rounds against the code
13. Decisions needed
14. Deferred to later versions

---

## 1. Where things stand

**Fixed and confirmed in the live runs (v2.0.6 to v2.0.9):**
- the catalogue is complete within the enabled boards;
- listing dates come from the exchanges' lists, and panels use them;
- the company-list update works;
- the table extractors read only their pages, about 170 times faster, with progress and resume;
- the actual controller is named in 88% of reports.

The register of every finding is `docs/plan_v2.0.8_and_visualisation.md`, section 2; the latest findings are `docs/live_run_findings_v2.0.8.md` (96 to 111).

**Open, and in this release:**

| # | Finding | Severity | Workstream |
|---|---|---|---|
| 104 | Beijing and B-share companies marked "in neither exchange's list", and without listing dates | **High** | A1 |
| 98 | Top-10 shareholder rows from only 167 of 905 reports | **High** | A2 |
| 101, 107 | Financial extraction reads every page, about 35 s a document | **High** | B1 |
| 2, 32 | Extraction speed in general | High | B2 to B4 |
| 96 | A failed action leaves only a one-line error | Medium | A3 |
| 108 | Discrepancy and segment counts cannot be read as rates | Medium | A4 |
| 109 | The panel does not say why rows have no figures | Low | A5 |
| 106 | The self-test reports only the last variant's error | Low | A6 |
| 7 to 10, 16 to 18 | Polish from the first live run | Low | C |

**Open, and not in this release:**
- **Waiting on the author.** The top-10 parser for new layouts (after `inspect-tables`, A2) and the segment and discrepancy patterns (after the findings CSV, A4).
- **Monitored.** Findings 1 and 19.

## 2. Scope

**In scope:** workstreams A to E as below. G only if confirmed.

**Out of scope for v2.1:**
- **Translation of the command line's output.** It stays in English, including the lines the command line writes into the desktop's output panel.
- **Any change to dataset contents caused by the interface language.** Variable names, column names, codebook identifiers, file names and manifest fields are unaffected by the language setting. Dataset contents do change where workstream A corrects them.
- **Visualisation phases V2 to V5** (the interactive viewer, the semiconductor episode, measures, the 3D study).
- **A Chinese user guide**, and Chinese chart captions.

## 3. Workstream A: data corrections from the live runs (findings 98 and 104 to 109)

### A1. The optional boards (finding 104)

**The fault.** The exchanges' lists cover the Shanghai main board and STAR, and Shenzhen's A shares. v2.0.8 marks NOT_IN_EXCHANGE_LIST any company absent from them, whatever its board. With the Beijing Stock Exchange and B shares enabled, 684 listed companies were marked so, treated as delisted, and left without listing dates.

**The fix.**
1. **Which boards each list covers.** Shanghai main → SSE_MAIN; STAR → STAR; Shenzhen A → SZSE_MAIN and CHINEXT; and, new, Shanghai B → SSE_B and Shenzhen B → SZSE_B.
2. **Status.** NOT_IN_EXCHANGE_LIST is set only for a company whose own board's list was read whole in this run and does not contain it (review round 3).
3. **Repair.** A company marked NOT_IN_EXCHANGE_LIST is set back to LISTED when either:
   - its board has no list (the Beijing Stock Exchange); or
   - its board's list was read whole and contains it.
   
   If its board's list failed in this run, its status is left as it is, so a failed request does not make statuses flap (review round 3).
4. **B-share listing dates.** When B shares are enabled, the exchanges' B-share lists are read: Shanghai's list with `STOCK_TYPE=2`, Shenzhen's with `TABKEY=tab2`. These are two requests, archived like the others.
5. **Beijing listing dates.** When the Beijing Stock Exchange is enabled and its companies lack dates, the quote list is asked for that board alone (filter `m:0+t:81+s:2048`): about seven requests. `quotelist.fetch_pages` gains a board argument for this (review round 1).
6. **Quote list.** It is asked for whatever the lists leave undated, by board. In v2.0.9 it was asked only when a company in the lists lacked a date, so the Beijing companies, which are in no list, never triggered it (review round 1).
7. **Output.** The output reports each list, and the companies still undated, counted by board.

**Not verified offline.** The B-share list parameters and the Beijing filter follow the exchanges' and Eastmoney's own pages. "Update the company list" is their live test, and a failed list leaves the others in place.

**Accepted when:**
- on the author's database, the Beijing and B-share companies are LISTED and mostly dated;
- NOT_IN_EXCHANGE_LIST counts about 188.

### A2. Top-10 shareholder coverage (finding 98)

**The fault (as far as can be told without the reports).**
- **The count.** 167 of 905 reports gave rows.
- **Two readings disagree.** The kept reading found 1,145 rows. The other found 1,684 rows under other names, which the dual run dropped as fragments of broken rows.

**The fix.**
1. **`inspect-tables DISCLOSURE_ID --table top10`** writes a text file with:
   - the section's pages in both readings;
   - the parser's decision on each line: header, row read, row rejected (and by which check), or ignored.
   
   The author can send it instead of the PDF. It also covers `--table segments` and `--table control`.
2. **Rows only one reading found.**
   - **Matching.** The two readings of one table are matched by **share count**, not by name or rank. Rank is the parser's own row counter (`rank = len(out) + 1`), so a reading that misses a row numbers every later row differently (review round 2).
   - **Adding.** A row of the other reading whose share count matches no kept row is added.
   - **Checking the result.** The merged table must pass the table checks of v2.0.7: no more than ten rows; each percentage between 0 and 100; the percentages adding up to no more than 100.
   - **If it fails.** The kept reading alone is used, as now.
   - **Ranks.** They are re-assigned by share count. Added rows are marked SINGLE, with lower confidence, and go to the review queue.
3. **The tradable table** is matched to the top-10 rows by name as now, and by tradable share count where the names differ (review round 2).
4. **Version.** The extractor's version becomes "top10-3", so the next run re-reads all 905 reports (about 25 minutes at the measured pace).

The parser itself is changed for new layouts only once `inspect-tables` output or PDFs show them, in a patch after v2.1 if needed.

### A3. Errors in full (finding 96)

- **The desktop.** Every failed action writes its full error, with the traceback, to `logs/error_<time>.txt`, and a line naming that file to `run_log.txt`. The output panel keeps the plain message, with the file's name.
- **The command line.** The command line run directly prints the traceback, as now, and writes the same file through an exception hook in the launcher.

### A4. Findings as rates (finding 108)

- **Counts saved.** `validate-all` saves what each check examined to `validation_summary.json` in the data folder: segment tables compared, document pairs compared, balance sheets checked, ownership tables checked. It saves them for the scope it ran on (the whole database, or one company, kept apart).
- **Show findings** then gives each rule as a rate. It splits:
  - segment mismatches by size (within 10%, within 50%, beyond);
  - discrepancies by pattern (DIGITS_GLUED, POWER_OF_TEN, SIGN, OTHER).
- **Without a saved summary**, for example before the first `validate-all` under v2.1, it shows counts only and says so (review round 3).

### A5. Panel coverage (finding 109)

The panel's warning names how many companies have financial figures for the period and how many have downloaded reports, for example "Financial figures exist for 170 of 5,181 companies; reports are downloaded for 295".

### A6. The self-test (finding 106)

The quote-list check reports every variant's result, and the one that answered, as "Diagnose the quote list" does.

### A7. Earlier findings now closed

These need no work: 73 (prices: selectable since v2.0.8; Eastmoney answers again), 90, 92, 96, 99 to 103 and 110.

## 4. Workstream B: extraction speed (findings 2, 32, 101 and 107)

**Measured so far.**
- **The table extractors.** They went from 51 to 300 seconds a report to 1 to 1.7 seconds under v2.0.8 (findings 97 and 100).
- **Financial extraction.** It still reads every page: about 35 seconds a document (findings 101 and 107).

**Target.** A median of 2 seconds or less per document for every extractor on the author's machine, with no loss of parser accuracy.

### B1. Financial extraction reads only its pages

1. **Sections.**
   - **New.** The key figures (主要会计数据和财务指标, 主要财务数据), and the consolidated balance sheet, income statement and cash-flow statement (合并资产负债表, 合并利润表, 合并现金流量表).
   - **Already used by R&D and workforce.** The employee and R&D pages, for the headline employees and R&D figures.
   - **Also included:** the cover page, for period inference, and **the page before each heading**, so that a unit declared at the foot of that page is still found by the unit rule of v2.0.8 (review round 1).
2. **Short documents are read whole.**
   - **Which.** Any document of 30 pages or fewer: announcements, earnings flash reports (业绩快报), forecasts.
   - **Why.** Their figures sit under other headings (for example 主要财务数据和指标 in a flash report), and skipping them would lose what `--kind all` reads today (review round 1).
   - **Cost.** Short documents are fast to read whole; the slowness is in long reports.
3. **Long documents without the headings** are read whole, as before.
4. **Version.** `EXTRACTOR_VERSION` becomes "financials-3".
   - **Why.** Reading only the sections can change which occurrence of a label is read first: the key-figures table rather than a figure quoted in the management discussion. That is intended, and should remove some of finding 84's "OTHER" differences. But it means the readings are not the same as financials-2's (review round 1).
   - **The cost.** All documents are read again once, about an hour at the target pace.

### B2. pdfium as the primary text layer (evaluated first)

pypdfium2 is already bundled, and is much faster than pypdf for plain text.
- **The test.** Both are run over the golden corpus, and the switch is made only if precision and recall do not fall (`evaluate-parsers`). The comparison is recorded.
- **If switched.**
  - Every extractor's version is raised, because every text variant's output can change.
  - The parser calibration is rebuilt (`calibration`), because it is kept per variant (review round 2).
  - The re-read costs about an hour at the target pace.

### B3. Parallel extraction

**How it works.**
- **Workers.** Several documents are parsed at once, in worker processes (default: processor cores minus one, configurable).
- **Writes.** The workers only read and parse. The main process writes every result, in order, so SQLite sees one writer (review round 2).
- **Workers report what they found:**
  - the records;
  - the dual-run counts;
  - the PDF reader's notices, so that the end-of-run summary stays complete;
  - the section index, written to its cache by the worker.
- **Stop.** Stop ends submission, waits for nothing, and stops the workers. Documents in progress are not marked read, so the next run reads them (review round 2).

**Windows requirements.**
- Workers are started with `spawn`, and the launcher calls `multiprocessing.freeze_support()`, which a frozen PyInstaller program needs.
- That call comes first in `packaging/launcher.py`, before `ashare.app.main`. `main` treats any command-line argument as a command for the command line, and a spawned worker is started with arguments of its own (review round 5).
- Workers write nothing to standard output: the desktop program has none, and `main`'s substitute is set up only after the worker would start (review round 5).
- Workers inherit the data folder from the environment the desktop sets.

**Tested in the frozen program under Wine**, not only from source (review round 4).

### B4. Profiling, and the text cache reconsidered

- **Profiling.** One run over 200 real reports (the author's) is profiled before and after, and recorded.
- **The text cache.** The earlier plan's whole-document text cache is dropped, because targeted reading and the section index (`disclosures/.section_index`) already avoid reading a document twice. It is reconsidered only if profiling shows the page-text pass as the bottleneck (review round 2).

## 5. Workstream D: interface language toggle (desktop only)

### 5.1 What is translated

The text the desktop application itself shows:

- the sidebar groups and the 25 page titles and introductions;
- the labels and notes of the 110 actions;
- the labels and hints of the 125 form fields, and the options of choice fields;
- buttons, menus, dialogs, confirmation messages (for example the whole-market download warning) and the status bar;
- the Getting started page and Settings;
- the windows for review, the dataset explorer and charts, wherever their text is the application's own;
- error explanations produced for the desktop (`friendly_error`), and the desktop's own summary lines (for example "Last action failed (see output)").

There are roughly 700 to 900 strings, to be counted exactly at the start of the build, after workstreams A to C have added theirs (section 10: the strings are extracted last).

### 5.2 What stays in English in both modes

| Item | Reason |
|---|---|
| Command names and the command recorded in `run_log.txt` | The log must stay reproducible and readable in bug reports |
| The output of each command, as shown in the output panel | Command-line translation is deferred; showing it unchanged avoids two versions of the same message |
| Variable and column names, codebook identifiers, file names, manifest and release metadata | A panel built in Chinese mode must be byte-for-byte identical to one built in English mode, so that the interface language never becomes a hidden variable in research data |
| Source data (company names, announcement titles) | Already in Chinese from the source; unaffected |

The output panel will therefore show Chinese interface text above English command output. This mix is accepted for v2.1, and the user guide says so.

### 5.3 Behaviour

- **Toggle:** a compact "EN | 中文" switch in the window header, mirrored in Settings.
- **Persistence:** saved in the existing `settings.json` (`"language": "en"` or `"zh_CN"`).
- **First start:** follows the Windows display language (Chinese for any `zh` locale, otherwise English).
- **Switching:** immediate, without a restart. Every page is built from one specification (`SECTIONS`), so the window rebuilds its pages in the new language. Form values already typed are kept.
- **During an action:** the toggle is disabled while an action is running, consistent with the settings lock (finding 10, section 6).
- **Fonts:** in Chinese mode, Microsoft YaHei UI is the primary interface font (it is already the second fallback). Line wrapping and field widths are checked on screen at 100% and 150% scaling.
- **Dates and numbers:** unchanged (ISO dates, Western digits) in both modes, because they are also inputs to commands.

### 5.4 Terminology and the glossary

The interface uses official disclosure and regulatory terms only, as used by the China Securities Regulatory Commission (CSRC), the exchanges, CNINFO and the reports themselves. It never uses the casual terms of financial portals and trading apps (for example 年报 for 年度报告, or 分红 used loosely where the report says 利润分配 or 现金红利).

Process:

1. The glossary (`docs/glossary_zh_CN.md`) lists every recurring term with its rendering and authority.
2. **Done, 18 October 2026:** the author approved every proposed rendering, including the interface's own terms (part 10). Two facts are still to be confirmed during the build: the supervisory-board transition date, and the successor to the 2012 industry classification. The settled labels stand meanwhile.
3. All interface strings are then translated from the settled glossary. A term outside the glossary is added to it, and reviewed, rather than translated ad hoc.
4. The author reviews the full Chinese interface in a pre-release build (screenshots of every page, plus the build itself).

### 5.5 Implementation

- **Catalogues:** `ashare/i18n/en.json` and `ashare/i18n/zh_CN.json`, keyed by stable identifiers (for example `action.update_universe.label`, `field.since.hint`). English is the source and the fallback, so a missing translation shows English and never a blank.
- **Lookup:** a small `t(key)` function. `SECTIONS`, `A()` and `F()` carry keys rather than literal text; the English strings move into `en.json` unchanged.
- **Stale translations:** each Chinese entry records a hash of the English text it was translated from. If the English text changes later, the entry is flagged as stale.
- **Packaging:** the catalogues are bundled with the executables.

### 5.6 Tests

- Every key in `en.json` exists in `zh_CN.json`, and no entry is empty.
- No stale entries (English changed since translation).
- Every glossary term that appears in an English string is rendered with its glossary translation in the Chinese string.
- Placeholders such as `{n:,}` match between languages.
- A panel built after switching to Chinese is byte-for-byte identical to one built in English (same CSV, DTA and manifest except the timestamp).
- The run log records identical commands in both modes.
- The desktop opens and switches language under Wine on Windows; screenshots of every page in both languages are produced for review.

### 5.7 Acceptance

- Every page, action, field, dialog and status message appears in Chinese when 中文 is selected, with no English left except command output and the items listed in section 3.2.
- The author has approved the glossary and the screenshots.
- The data-identity test passes.


## 6. Workstream C: polish (findings 7 to 10 and 16 to 18)

| Finding | Change |
|---|---|
| 7 | Parquet is offered only when pyarrow is available. A failed write removes the partial files, so a panel is written in all requested formats or not at all |
| 8 | Empty results give a reason and a next step (compare, transactions, regulatory events, calendar), as panels now do |
| 9 | Code 201872 is investigated and its range recognised, or reported with a clear reason |
| 10 | Settings are locked while an action is running: optional boards, the price source and the language toggle (review round 4) |
| 16 | Name-lookup (DNS) failures are retried for longer (up to about five minutes) before a period counts as failed |
| 17 | The dataset explorer explains an empty or missing panel instead of opening blank |
| 18 | `show-market` says when there are no prices and how to fetch them |

Finding 11 was answered in v2.0.8 (progress in documents, seconds each and an estimate).

## 7. Workstream E: visualisation layer, V0 and V1

As set out in `docs/plan_v2.0.8_and_visualisation.md`, section 7, with the decisions of 29 October.

### E1. V0: the graph snapshot

- **`ashare/viz/`.** The schema (JSON Schema), a builder for a list of companies and a period, the validation rules of section 7.3, and the export (`snapshot.json`, `observations.csv`, `manifest.json`).
- **`nvf.layers`.** Panel variables mapped to the five NVF layers.
- **Pseudonymisation.** The builder applies the release rule (`release.is_natural_person`, `strip_nature`). It is imported, not copied, so the viewer and a release can never mask differently (review round 3).

### E2. Expectations: guidance first, analyst forecasts later

- **Table.** `expectation_observations` (migration 0007), with `source_kind` MANAGEMENT_GUIDANCE or ANALYST_FORECAST, as in section 10.7 of the earlier plan.
- **Guidance.** 业绩预告 and 业绩快报 are read for their ranges and dates.
- **Downloads needed.** These are announcements, and the author's catalogue ran without downloads. "Read guidance" therefore starts with "Download documents" for the kind `earnings_forecast_or_flash` only, a few thousand short documents (review round 3).
- **Analyst forecasts.** `import-analyst-forecasts-csv` fills the same table with `source_kind = ANALYST_FORECAST`, with the licence recorded.
- **Never mixed.** The expectations layer says which source a value came from, and never mixes the two in one series.

### E3. V1: the 2D layered view

- **The chart kind.** A new kind, `layers`, in `ashare/charts`, drawn by the Tk and SVG renderers.
- **The desktop.** A "Topology" page and an export.
- **Language.** Chart labels stay in English in both interface languages, as chart captions are deferred (section 14). The page and its controls are translated with the rest (review round 4).

**Accepted when:**
- the snapshot rules of section 7.7 (V0) are met;
- the Tk and SVG drawings agree within the existing pixel tolerance;
- the CSV export reproduces the plotted observations.

## 8. Workstream G: publication readiness (proposed; confirm)

This workstream was offered after the question about publishing the dataset. It is included only if confirmed.

- `release --zenodo` writes `.zenodo.json` (title, creators with ORCID, licence, keywords, related identifiers for the software) beside the release.
- A "publish-ready" report lists:
  - the licence classes included and excluded;
  - whether personal names are pseudonymised;
  - that no document text or PDFs are included;
  - that a data licence is set;
  - the dataset and software citations.
- Prerequisite decisions for the author: a licence for the code and one for the data (CC BY 4.0 is the usual choice for data).


## 9. Schema and versions

- **Migration 0007:**
  - `expectation_observations` (E2);
  - nothing for A4, whose summary is a file, so that the database need not change for a report (review round 3).
- **Extractor versions raised:**
  - financials-3 (B1);
  - top10-3 (A2);
  - all of them again if pdfium becomes the text layer (B2).
  
  At the target pace, one full re-read of the author's 1,514 documents takes about an hour.
- **Section index.** `INDEX_VERSION` becomes 2, because sections are added (B1), so cached indexes are rebuilt once (review round 2).
- **Once only.** Every version is raised once, to its final value, in the release build, so the author re-reads each document once whatever B2 decides (review round 5).

## 10. Order of work

| Step | Content | Why in this order |
|---|---|---|
| 1 | A1, A3, A6 | Small, independent fixes; A3 makes every later failure diagnosable |
| 2 | B1, then B2 (evaluation only), then B3 | B1 is the largest gain; B2 decides the text layer before B3 is tuned to it |
| 3 | A2, A4, A5 | A2's re-read should follow B2's decision on the text layer, so reports are read again once, not twice; A4 and A5 need the extractors final |
| 4 | E1, E2, E3 | Reads the corrected data model |
| 5 | C | Polish touches the desktop forms the next step translates |
| 6 | D (language) | Last of the features: every new string from steps 1 to 5 is extracted once, with the glossary extended and reviewed for the new terms |
| 7 | G, if confirmed | |
| 8 | Full test matrix, Windows build, change log, push | |

## 11. Testing and release

**Tests written before the code**, each failing on v2.0.9:
- **A1.** A Beijing and a B-share company with only the A-share lists read, with the B-share lists read, and with a board's list failing (status unchanged).
- **A2.** Two readings of one top-10 table with different names for the same holder (same share count: one row) and a genuinely missing row (added). A merged table that breaks the checks falls back to the kept reading.
- **A3.** A failed action leaves its traceback file and the run-log line.
- **A4.** Rates with and without a saved summary.
- **A5.** The panel's coverage line.
- **A6.** The self-test lists every variant.
- **B1.**
  - Targeted and whole financial reading on the synthetic corpus give the same facts, or the differences are listed and justified.
  - A unit declared at the foot of the page before a statement is found.
  - A 25-page announcement is read whole, and a 250-page report without the headings is read whole.
  - A generated 251-page report is read in a tenth of v2.0.9's time.
- **B2.** The text-layer comparison report.
- **B3.**
  - Parallel and serial runs give identical records and extraction states.
  - Stop leaves no half-written document.
  - It works in the frozen program under Wine.
- **D.** As in 5.6.
- **E.** As in E3, plus the privacy test: no masked name in any snapshot.
- **C.** One test per finding.

**The full matrix:**
- Linux Python 3.12 and 3.13;
- PostgreSQL 16;
- Windows CPython 3.12 under Wine, with the installer installed, upgraded over a running copy and uninstalled;
- GitHub CI;
- the parser accuracy report unchanged or better.

**Release.**
- Version 2.1.0 everywhere it appears.
- CHANGELOG with changes and findings, and the user guide updated.
- Executables, installer and portable zips, each under 30 MB.
- Commits in the author's name only.

**After installing (author):**
1. "Update the company list".
2. "Extract figures from reports" (reports).
3. "Read top-10 shareholders".
4. "Run all checks".
5. "Show findings" and `show-flags --export`.
6. `inspect-tables` for two or three reports still without top-10 rows.

## 12. Logic review: six rounds against the code

Each round traced the plan through the code it changes, looking for a step that would fail, contradict another, or lose data. The faults found were corrected in the sections above; a round was repeated until it found nothing new.

### Round 1: data paths

| # | Fault in the plan as first written (v2.0.10) | Where | Correction |
|---|---|---|---|
| 1 | Beijing companies are in no list, and the quote list was asked only for companies in the lists without a date (`pipeline.enrich_listing_status`, `missing`), so they would never get dates | A1 | The quote list is asked for whatever is undated, by board; `fetch_pages` takes a board filter |
| 2 | Skipping documents without statement headings would drop the figures that `--kind all` reads today from flash reports (业绩快报, under 主要财务数据和指标) and other short announcements | B1 | Documents of 30 pages or fewer are read whole |
| 3 | The unit rule looks at the figure's page and the page before; a targeted reading without the page before would lose units declared at the foot of it | B1 | The page before each heading is included |
| 4 | v2.0.10 kept `EXTRACTOR_VERSION` "financials-2" on the ground that targeted reading gives the same facts. It does on the synthetic corpus, but on real reports the first occurrence of a label can move from the narrative to the key-figures table, so readings would mix two methods | B1 | financials-3, with one full re-read |
| 5 | Period inference reads the head of the document when the title does not settle it; a targeted reading may blank the cover | B1 | The cover page is always read |

### Round 2: concurrency, versions and matching

| # | Fault | Where | Correction |
|---|---|---|---|
| 6 | The v2.0.10 idea of matching two readings of a top-10 table by rank fails: `rank` is the parser's own counter (`control.parse_top10_pages`: `len(out) + 1`), so one missed row shifts every later rank | A2 | Matched by share count; ranks re-assigned afterwards |
| 7 | The tradable table is matched to top-10 rows by name only, so an added row with a variant name would get no tradable shares | A2 | Also matched by tradable share count |
| 8 | Workers writing to SQLite concurrently would lock the database | B3 | Workers only parse; the main process writes |
| 9 | The PDF reader's notices are collected per process, so a parallel run's summary would undercount | B3 | Workers return their notices with their results |
| 10 | A stopped parallel run could mark documents read that were not written | B3 | Only the main process marks, after writing |
| 11 | Switching the text layer changes every text variant's output, but calibration is stored per variant name and would describe the old layer | B2 | Calibration rebuilt; every version raised |
| 12 | New sections leave stale section indexes cached under the old definition | B1, 9 | `INDEX_VERSION` 2 |
| 13 | A whole-document text cache would duplicate what the section index and targeted reading already save, at a cost in disk space | B4 | Dropped; reconsidered only after profiling |

### Round 3: state, privacy and reporting

| # | Fault | Where | Correction |
|---|---|---|---|
| 14 | Setting NOT_IN_EXCHANGE_LIST whenever "the lists are whole" would still mark a board whose own list failed in this run, and resetting on any failure would make statuses flap between runs | A1 | Set and reset only on the evidence of the company's own board's list in this run |
| 15 | Rates need what each check examined, but `validation_flags` holds only the findings | A4 | A summary file written by `validate-all`, by scope; without it, counts only |
| 16 | A per-company `validate-all` would overwrite the whole database's denominators | A4 | Kept apart by scope |
| 17 | A viewer that masked names with its own rule could disagree with a release | E1 | It imports the release's rule |
| 18 | Guidance is in announcements, which the author's catalogue did not download | E2 | "Read guidance" downloads that kind first |

### Round 4: the desktop and Windows

| # | Fault | Where | Correction |
|---|---|---|---|
| 19 | Translating before the other workstreams add their strings would leave new labels untranslated | D, 10 | Language last; strings extracted once |
| 20 | The settings lock (finding 10) listed only the language toggle; the optional boards and price source can also change mid-run | C | All settings locked |
| 21 | Multiprocessing in a frozen Windows program without `freeze_support` starts the whole application again in each worker | B3 | `freeze_support()` in the launcher; tested in the frozen program under Wine |
| 22 | Chart text would be the one untranslated part of the new Topology page | E3 | Page and controls translated; chart labels in English by the deferral of section 14, said in the user guide |

### Round 5: the corrected plan, traced again

| # | Fault | Where | Correction |
|---|---|---|---|
| 23 | A spawned worker of the frozen program is started with arguments, and `ashare.app.main` runs any argument as a command-line command, so each worker would start a second program | B3 | `freeze_support()` first in the launcher, before `main` |
| 24 | The desktop program has no standard output; a worker that printed would fail before `main`'s substitute exists | B3 | Workers return everything and print nothing |
| 25 | financials-3 (B1), top10-3 (A2) and a text-layer switch (B2) would each force a re-read, possibly twice for the same documents if built in that order | 9, 10 | Versions raised once in the release build; A2 after B2 |

### Round 6

The plan was traced once more through the files it changes:
- `pipeline.py`, `exchange_lists.py`, `quotelist.py` and `security_master.py` (A1);
- `parsers/__init__.py` and `control.py` (A2);
- `gui.py`, `app.py` and `packaging/launcher.py` (A3, B3, C, D);
- `crossvalidation.py` (A4) and `panel.py` (A5);
- `financials.py`, `cas.py` and `reportreader.py` (B1);
- `extractstate.py` (B3);
- `release.py` (E1) and `disclosure_pipeline.py` (E2).

No new fault was found.

**What this review cannot settle.**
- **Requests the build environment cannot reach.** The B-share lists, the Beijing filter and the Tencent prices are tested on the author's network only.
- **Real layouts.** The top-10 layouts that real reports use are shown only by `inspect-tables` or the PDFs.
- **Speed.** The speed target is checked only by profiling real reports.

## 13. Decisions needed

| # | Decision | Default if not decided |
|---|---|---|
| 1 | Glossary entries for the new terms (price source, 价格来源; findings summary; topology view; guidance, 业绩预告 as a proxy). Proposed with step 6, for approval | The proposals stand until reviewed |
| 2 | Workstream G (publication readiness) | Left out of v2.1 |
| 3 | Licences for the code and the data | Code stays PolyForm Strict; data licence unset |
| 4 | Parallel workers by default (cores minus one) | On; a setting turns it off |

The earlier decisions stand: glossary approved (18 October); viewer inside this repository; V0 and V1 beside v2.1; semiconductors as the first episode (V3, later); guidance first, analyst forecasts by import; price source selectable.

## 14. Deferred to later versions

- Translation of the command line's output.
- A Chinese user guide and Chinese chart captions.
- Visualisation V2 to V5.
- The top-10 parser for new layouts, once shown (a patch after v2.1 if needed).
- Traditional Chinese, only if there is demand.
