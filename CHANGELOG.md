# Change log

This log records what changed in each version and the important findings behind the changes. The live-run findings are kept in full in `docs/live_run_findings_v2.0.2.md` (findings 1 to 19) `docs/live_run_findings_v2.0.3.md` (findings 20 to 34) and `docs/live_run_findings_v2.0.5.md` (findings 35 to 57, the first live runs of the v2.0.4 catalogue engine) `docs/live_run_findings_v2.0.6.md` (findings 58 to 69) and `docs/live_run_findings_v2.0.7.md` (findings 70 to 95). Earlier versions are described in `README.md` and in section 18 of `ashare_scraper_build_plan.md`.

## v2.0.9 (30 October 2026)

**Aim:** fix a fault in v2.0.8 found in the author's first live run. "Update the company list" failed after about 50 seconds with `TypeError: '<' not supported between instances of 'NoneType' and 'str'`.

- **The cause.** v2.0.8 rebuilds the listing history of the companies whose dates or status changed. The rebuild sorts each company's risk-warning changes, and where a warning was imposed and lifted on the same day (two events with one date), the sort compared the warning "ST" with None. The databases in the tests had no such pair; the author's, with 21,963 regulatory events read from titles, did. "Build listing history" would have failed the same way.
- **The fix.** The changes are sorted by date alone.
- **No more failed updates from the rebuild.** If the rebuild fails for another reason, "Update the company list" still finishes, since the list and the listing dates are already saved. It then says to run "Build listing history".
- **Tests.** Two new tests: the same-day pair, and an update that survives a failed rebuild. Results:
  - 305 pass on Linux Python 3.12 (two skips);
  - 295 on Python 3.13 (ten skips);
  - 302 against PostgreSQL 16 (five skips);
  - 303 on Windows CPython 3.12 under Wine (four skips).
  
  The installer installs and uninstalls under Wine.

Nothing else changed. The steps after upgrading are those of v2.0.8 below.

## v2.0.8 (29 October 2026)

**Aim:** correct data first. The live runs under v2.0.7 (findings 70 to 95, `docs/live_run_findings_v2.0.7.md`) showed wrong financial figures, segment totals that did not add up, shareholder tables too slow to re-read, and panels that ignored the new listing dates. The plan, with a review of the code that found the causes, is `docs/plan_v2.0.8_and_visualisation.md` (sections 4 and 10).

**After upgrading:**
1. "Update the company list" (it rebuilds the listing history of the companies whose dates changed);
2. "Extract figures from reports", "Read top-10 shareholders", "Read controlling shareholder and actual controller" and "Extract segments from reports": each reads every report again once, because its version is new, and a stopped run continues where it stopped;
3. "Run all checks";
4. build panels for a fiscal year that has ended (for example `--start 2025-01-01 --end 2025-12-31`).

### Universe and panels (findings 92, 93 and 71)

- **Listing dates used (finding 92).** A listing history derived before the listing dates were known has no start date. It hid the company's listing date, so 5,223 of 5,225 panel rows came from report evidence. Such a history now gives way to the company record. "Update the company list" rebuilds the history of every company whose listing date or status it changed.
- **Fiscal years not ended (finding 93).** A fiscal-year row for a year that has not ended has no annual figures. The panel now names such years and counts rows with no financial figure, in the output and the manifest. The desktop form ends at the last complete fiscal year.
- **NOT_IN_EXCHANGE_LIST (finding 71).** A company in neither exchange's whole list, and not named as delisted, gets this status. It is treated as delisted on an unknown date, until a delisting event in the listing events gives the date.

### Financial figures (findings 84 to 87)

- **Notices are not reports.**
  - **The fault.** Titles such as 年度报告披露提示性公告, 关于…年度报告的更正公告 and 补充公告 were classed as annual reports, so their figures were compared with the report's.
  - **The fix.** They are now `report_notice`. Stored kinds are reclassified at the start of each extraction, and the figures read from notices are removed.
  - **Corrected reports.** A corrected full report (更正后, 修订版) is still a report.
- **Units.** A table without its own unit took the unit of an unrelated table any number of pages earlier, for example 万元 from a fund-raising table. The search now stops at the page before. A figure whose unit is not declared there is marked `CNY_ASSUMED`, with lower confidence.
- **Power of ten within a document.** When the headline reader and the statement reader of one document differ by exactly 1,000, 10,000, a million or a hundred million, the statement reading, whose unit is declared on its page, is kept. The note records the rescaling.
- **Amounts cut short.** An amount in yuan must have two decimals ("22,103" and "1,355.2" are no longer read); amounts in larger units may have up to four.
- **Glued note numbers.** A note reference glued to an amount ("1" + "1,791,960,892.40") gives a well-formed number. When the other reading of the same figure is the same digits without the one or two in front, it is kept.
- **Old readings removed.** A figure the readers no longer produce from a document is removed when the document is read again, with its review items.
- **Restatements (finding 86).** A difference between documents filed the same day is no longer "explained" by a restatement. It is CORRECTED_REPORT (information) when one of them is a corrected report.
- **Patterns named.** Each difference is labelled DIGITS_GLUED, POWER_OF_TEN, SIGN or OTHER, to guide review.
- `EXTRACTOR_VERSION` is "financials-2", so every report is read again once.

### Targeted reading, progress and resume (findings 76, 77, 79 and 82)

- **One reading per report.** `ashare/reportreader.py` opens a report once. It finds the sections sought with pdfium's page text, and reads the plain text and layout only of those pages, each at most once. The pages index is kept beside the documents, so the other extractors skip the search. Without a section, or without pdfium, the whole document is read as before.
- **The extractors moved to it:** top-10 and tradable holders (one reading for both tables), control, segments, R&D and workforce, subsidiaries, and the management roster.
- **Measured on a generated 251-page report**, with the two shareholder tables on two pages:
  - v2.0.7 read both tables in 84.5 seconds;
  - v2.0.8 reads them in 20 seconds the first time and in under one second once the index exists;
  - the same rows come out.
  
  The first pass is dominated by loading each page in pdfium, which is slow for this file's non-embedded fonts. Reports with embedded fonts should be faster, and the author's run will show by how much.
- **Progress and resume.** Every one of these extractors counts the documents first, then prints "250 of 9,800 documents; 8.7 s each; about …". Each document read is recorded in `extraction_state` with the extractor's version (migration 0006), so a stopped run continues with the next report. `--again`, or "Read reports again" in the desktop, reads them all.
- **New versions.** The top-10, control and segment extractors start at new versions, so a normal run re-reads every report. This finishes the shareholder re-extraction that v2.0.7 needs (finding 77).

### Segments and control (findings 83, 78 and 89)

- **Segments.**
  - **Page breaks.** A table continued on the next page keeps its dimension, unit and kind; v2.0.7 lost the rows after a page break.
  - **Subtotals and breakdowns.** "其中：" rows are not segments, and "小计" rows are subtotals.
  - **Where tables end.** Cost-analysis and output tables after the segment tables are no longer read as segments.
  - **Table kind.** Each row records its table: composition, listing every segment, or margin, listing only those above 10% of revenue. A dimension read only from the margin table, without its own total, is not compared with the whole revenue.
- **Control.**
  - **Shenzhen reports.** The parser now reads the section headed "公司实际控制人及其一致行动人", and the header-row layout ("实际控制人姓名 与本公司的关系 国籍 …" with the values on the next row).
  - **Headings.** A heading is never taken as a name (finding 89: "与本公司的关系").
  - **Persons acting together** are kept together ("王传福、吕向阳").
  
  The layout and the plain text of the control pages are both read, and the reading that names more parties is kept.

### Installer and findings (findings 74 and 91)

- **Installer.** The installer and the uninstaller check that AShareScraper.exe and ashare-cli.exe are not running before they copy or delete. If either is, they ask for it to be closed (Retry or Cancel); in silent mode they stop with exit code 5.
- **Show findings.** It opens with counts by rule and severity and the 20 companies with most findings. Every row carries the company code. `--details`, `--rule` or `--security-code` lists the rows, and `--export file.csv` writes them all.

### Price sources (finding 73)

- **A second public source.** Tencent's daily bars (`TENCENT_PUBLIC`), read two years per request.
  - **Status.** Like Eastmoney's, it is an unofficial feed, not exchange-authoritative, and its terms are the user's to check.
  - **Not tested live.** Its request format follows its public use. The build environment could not reach it, so "Test price sources" is how it is confirmed.
- **Test price sources** (`diagnose-prices CODE`). It asks each source for one company's last month and stores nothing. It then says which source answered and whether to change the setting.
- **The choice.** Settings > Price source: Eastmoney, Tencent or None (CSV import only). `ASHARE_PRICE_SOURCE` does the same from the command line. "Download daily prices" can override the choice for one run.
- **The daily update** follows the setting:
  - **None** asks for nothing;
  - **Tencent** brings the day through the backfill;
  - **Stopping.** The backfill stops after three companies refused in a row, instead of asking for each of about 5,500 companies a day while Eastmoney refuses them all.
- **Preference.** An imported (CSV) price is preferred to any public feed's for the same day.

### Tests

- **New tests.** 56 in `tests/test_v208.py`:
  - each fault above;
  - the synthetic corpus read in full and targeted, giving the same records from every table family;
  - the Tencent request and response;
  - a listing history left stale by an earlier update.
- **Changed tests.** Two v1.5 tests now ask for a second reading with `again`, and one v2.0.6 test fixes its table width.
- **Results:**
  - 303 pass on Linux Python 3.12 (two skips);
  - 293 on Python 3.13 (ten skips, the desktop tests without tkinter);
  - 300 against PostgreSQL 16 (five skips);
  - 301 on Windows CPython 3.12 under Wine (four skips);
  - GitHub CI passes.
- **The installer under Wine.** It installed; it stopped with exit code 5 over a running copy; it reinstalled once the copy was closed; and it uninstalled.

## v2.0.7 (24 October 2026)

**Aim:** fix two faults found by a review of a live release, then close the last catalogue gap and give listing dates a second source. The findings are 58 to 69 in `docs/live_run_findings_v2.0.6.md`.

### Shareholders and privacy (findings 68 and 69)

**Do not share a pseudonymised release made before v2.0.7.** After upgrading:
1. run `extract-top-holders`;
2. run `resolve-entities`;
3. make the release again.

- **Top-10 shareholders.**
  - **Both layouts.** `parse_top10_pages` now reads both column orders: nature at the end (older), or nature after the name (Shenzhen). Before, the second was read as the first: the nature was glued to the name, the percentage was read as the change, and stray figures (0, 46, −519) were read as percentages.
  - **Checks.** A row with a percentage outside 0 to 100 is left out, and a table whose percentages add up to more than 100 is rejected. A number made of two cells run together is not read.
  - **Wrapped names** are joined, in the top-10 and tradable tables.
  - **Old rows removed.** Rows read by an earlier version and not by this one are removed when the document is read again, with their review items. `resolve-entities` removes entities left only by such rows, and recognises a natural person whose nature is glued to the name.
- **Pseudonymisation fails safe.**
  - **The rule.** A shareholder, pledgor or controller name is masked unless a legal-person nature or an organisation word shows it to be an organisation's. Before, only names that looked like short Chinese names were masked, so "张三境内自然人" or "JOHN SMITH" could be released as they stood.
  - **Glued natures.** A nature glued to a name is taken off, and the bare name gets the same identifier, so it is replaced in free text too.
  - **The manifest** records the rule (`pseudonymisation.rule`).
- **The synthetic corpus** now uses the Shenzhen layout in half its reports, a quarter with the nature glued to the name, so the parser accuracy gate covers it. On this corpus the text reader's precision for the top-10 table is 100% (82.1% before, on the older corpus); the tradable table's text reader went from 83.8% to 90.2%.

### The catalogue (findings 61 and 62)

- **Company batches of 10** (`BATCH_SIZE`), the size the probe confirmed live. CNINFO did not apply a batch of 150: each batch reported 8,871 rows for a query of 3,024, and the engine read about 3,000 pages for nothing.
- **A part larger than its parent** (by more than 1%) now means the filter was not applied. It is not used, and not used again in the run.
- **Costly splits counted only when needed.** Company batches and manufacturing divisions are counted only if the boards, categories and industries leave rows missing; company splits are made within one board.
- **The probe** also tests batches of 25 and 50 companies, and reports whether CNINFO applied each.

### Listing dates (findings 58, 59 and 66)

- **The exchanges' stock lists** are now the first source: Shanghai main board and STAR (JSON), and Shenzhen A shares (an Excel file, read with a small built-in reader, so no new dependency). That is three requests, each response kept in the raw archive. The quote list is asked only for companies they leave without a date, and the output reports each list and how many dates came from each source. The lists are read as the exchanges' own pages read them; this needs a live check.
- **Three refused attempts stop the quote list.** Three in a row stop the whole reading: the request, again after 30 seconds and again after two minutes, and any success resets the count. Before, every board paused in turn (49 minutes in the live run). When the whole list stops part-way, the first board's page 1 is one of the three attempts, so the board-by-board reading still runs if the boards answer.
- **The note** lists every board read, including one refused at its first page, and says when the source is refusing requests.

**Tests.**
- `tests/test_v207.py` (23 tests): both shareholder layouts, the checks, removal of old rows and entities, the fail-safe rule and a release with a glued name, the manifest, the three-refusal rule and its pauses, the exchange lists, batches of 10, the parent check and the lazy splits.
- The v2.0.4 mock CNINFO gained a limit on the number of companies at once.

**Verification.**
- Linux Python 3.12: 247 tests passed (2 skipped).
- Linux Python 3.13: 238 passed (9 skipped).
- PostgreSQL 16: 244 passed (5 skipped).
- Windows CPython 3.12 under Wine: 245 passed (4 skipped).
- The parser accuracy gate passes on the extended corpus.
- The Windows installer installs, passes its offline self-test (20 of 20) and uninstalls cleanly.

**Still to confirm live.**
- "Update the company list" reads the exchanges' lists and dates nearly every company.
- `recatalogue-busy-days` closes 29 April with batches of 10.
- After re-extraction, 陕国投A's top-10 rows have their real percentages.

## v2.0.6 (23 October 2026)

**Aim:** listing dates for the whole company list, an extraction that can be followed and resumed, and the last catalogue gaps. The plan is in `docs/plan_v2.0.6.md`, and the findings behind it are 35 to 57 in `docs/live_run_findings_v2.0.5.md`, from three live logs of 23 October 2026.

**What the live runs showed.** The v2.0.4 engine closed the April gaps from 11,597 rows to 20, and the disjoint board codes, categories and industries partition exactly. Three problems remained:
- the quote list stopped at page 10 of 56 on every run, so only about 1,000 companies had listing dates;
- extraction gave no useful progress and started again from the beginning, although its Stop message said it resumed;
- 33 rows were still missing: on 29 April one query (日常经营, Shenzhen main board, manufacturing) held 3,024 rows with no working filter to split it, and on 9 to 12 January rows moved between pages.

### Listing dates (findings 50 and 57)

- **The list in parts.** When the whole list stops part-way, it is read one board at a time (Shenzhen main board, ChiNext, Shanghai main board, STAR), each in both code orders. This covers up to 2,000 companies a board, if, as is probable, one query returns at most 1,000 rows.
- **The row limit.** A limit is taken as confirmed when a board stops at the same number of rows as the whole list. It is then remembered for the day, so that the boards are not waited on; the next run tries once more beyond it.
- **Retries.** A page that fails is retried after 30 seconds and again after two minutes.
- **Pace.** The quote list is asked at most once every two seconds.
- **Messages.** The note says how many companies were fetched, which board fell short, and the error, which was kept but not printed before.
- **Diagnosis.** `diagnose-quote-list` also requests page 11 of the whole list and of the Shanghai main board, and says whether the list appears to stop at 1,000 rows.
- **Prices.** The daily price snapshot is read the same way, and fails with the reason instead of storing part of the market.

### Extraction (findings 42 and 51)

- **Progress.** `extract-financials` counts the documents first. It then reports every 25 documents and at least once a minute: documents done, seconds per document and an estimated finish.
- **Resume.** Each document read is marked with the extractor version (`EXTRACTOR_VERSION`, migration `0005_v206_extraction_state`: `extracted_version` and `extracted_at` on `disclosures`). A rerun skips documents already read, so a stopped run continues. `--again` (desktop: "Read documents again") reads them all, and a document downloaded again with new content is read again.
- **Stop wording.** The Stop message now says what running the command again does, and only where that is true. Before, every command said it resumed.
- **The heartbeat.** The old counter counted reads of a document's text, several per document, and is silent during extraction now. The desktop explains that `all` reads every downloaded document, most of which carry no statements.

### Catalogue (findings 37 to 40, 43, 45 to 49, 54 to 56)

- **Splits before sorting.** A query over the limit is split first. Reading it newest-first and oldest-first is now only a last pass, because CNINFO's time order is unstable (finding 37). A sorted request that fails is recorded as a gap; it no longer turns sorting off for the run (finding 55). Whether the order is honoured is decided per kind of query.
- **Finer splits (finding 45):**
  - manufacturing by its 31 CSRC divisions, used only if CNINFO's industry field accepts them, which is checked as the run goes;
  - batches of companies, sent with the companies' own exchange (`column`), one exchange per batch, without and then with a board code (finding 54);
  - as a last resort, single companies seen in the query, within 1,500 queries a day; if the first three return nothing in both forms, company queries are not used again.
- **Short queries under the limit (findings 39 and 56).** A period of quiet days that comes back short is read again day by day, and a short day board by board.
- **Paging (finding 38).** Paging no longer stops at the first page that repeats earlier rows, but after five such pages, and never goes past page 100.
- **No repeats (finding 46).** Within a day, a query already read, or a count already asked for, is reused.
- **Strategy 3.** Days short under strategy 2 (9 to 12 January and 29 April) are fetched again by `recatalogue-busy-days`.
- **The probe (finding 54).** `probe-cninfo-filters` tests company queries with companies that have announcements in the query, sent with their own exchange, with and without a board code, one, two, three and up to ten together. It also tests the manufacturing divisions. Verdicts: WORKS, SINGLES_ONLY, IGNORED, PARTIAL or FAILS.

### Reporting (findings 40 and 43)

- **Windows.** `catalogue-days` shows a window of quiet days as one row with its total, its stored rows and its gap once, and counts it once in the status line. `--by-day` (desktop: "One row per day") lists the days.
- **Today.** The catalogue summary counts today as "kept open", not as finished.

**Tests.** `tests/test_v206.py` (31 tests):
- the quote list with a 1,000-row limit, a board over 2,000, retries, the error in the note, the snapshot and the diagnosis;
- extraction progress, resume, `--again`, a changed download and the Stop wording;
- the 29 April shape split by company batches, single companies or divisions, and recorded when none works;
- a leaf read once, short windows split by day, paging rules, a failed sorted request, strategy 3 and the probe verdicts;
- window rows and the current day.

The v2.0.4 mock CNINFO gained switches for whole-exchange codes, company queries that need their own exchange, and manufacturing divisions. Tests whose expectations changed with the new order of splitting were updated, and each change was checked.

**Found during the build.** The PostgreSQL run found two faults that SQLite does not show:
- **Method too long.** The longer method names of v2.0.6 can exceed the 60 characters of `catalogue_days.method`. They are now shortened to whole parts ("...+..."), and the day is recorded.
- **Lost FAILED marking.** A failure while recording a day (as that one was) left the day neither recorded nor FAILED, because it was counted as finished before the write. Days are now counted only once recorded.

It also showed that the single-company fallback could run for a whole day, where it cannot place a gap. It is now used only for a leaf within one board and one category. Tests cover all three.

**Verification.**
- Linux Python 3.12: 224 tests passed (2 skipped).
- Linux Python 3.13: 215 passed (9 skipped: optional parts not installed there).
- PostgreSQL 16: 221 passed (5 skipped).
- Windows CPython 3.12 under Wine: 222 passed (4 skipped).
- The Windows installer was installed, its offline self-test passed 20 of 20, and it was uninstalled cleanly.
- A database shaped like v2.0.5 was upgraded to migration 0005.

**Still to confirm live.**
- "Update the company list" adds listing dates for at least 5,000 companies.
- `probe-cninfo-filters` shows which company queries and whether divisions work.
- `recatalogue-busy-days` closes 9 to 12 January and 29 April.
- A stopped extraction continues.

## v2.0.5 (22 October 2026)

**Aim:** prepare the public repository and the first public release. No collection or extraction logic changed, and no database migration is needed.

- **User agent.** The default user agent was `AshareResearchDataCollector/2.0.4 (research use; replace-contact-before-production)`. It now follows the package version and names the repository: `AshareResearchDataCollector/2.0.5 (research use; +https://github.com/wenyileong/ashare-company-intelligence)`. `ASHARE_USER_AGENT` still replaces it, and the compliance note asks researchers running larger collections to add their own contact details.
- **Request-rate ceiling.** `ASHARE_RPS` and `ASHARE_MARKET_RPS` could set any rate. Every client now runs at between 0.1 and 2 requests per second (`MAX_REQUESTS_PER_SECOND`), so a mistyped setting cannot put load on the sources. The default stays at 1.
- **Repository documents.**
  - A disclaimer in the README: no affiliation with the sources, no warranty of accuracy, not investment or legal advice, and the responsibility of the person running the program.
  - `CONTRIBUTING.md`: issues are welcome; pull requests are not accepted, since the licence permits no changes.
  - `SECURITY.md`: private reporting through GitHub, supported versions and scope.
  - Where the documents meant the author, "the user" now reads "the author"; "the user" remains where it means anyone running the program.
- **Workflows.** `actions/checkout`, `actions/setup-python` and `actions/upload-artifact` moved from v4/v5 (Node 20, past its end of life) to v7 (Node 24). Both workflows now run with a read-only token and do not keep the checkout credentials.
- **Release.** The first public release carries `SHA256SUMS.txt`. The downloads are not yet code-signed.

**Tests.** `tests/test_v205.py` (4 tests): the default user agent, its override, the ceiling and the floor.

## v2.0.4 (18 October 2026)

**Aim:** close the catalogue gaps on the busiest disclosure days. The plan is in `docs/plan_v2.0.4.md`, and the findings behind it are 20 to 34 in `docs/live_run_findings_v2.0.3.md`.

The first live whole-market catalogue under v2.0.3 confirmed the 3,000-result limit and the resume, but left 12 days short. The causes:
- `sz` and `sh` cover whole exchanges, so the board split never isolated the main boards (finding 22);
- categories still over 3,000 on one board on the April deadline days (23);
- announcements on neither the Shanghai nor the Shenzhen board (24);
- rows repeated for several securities (25).

Whether CNINFO supports finer splits (separate main-board codes, the industry field, several companies at once, sort order) is not documented anywhere. v2.0.4 is therefore built to find out as it runs and to use only what works, rather than to assume.

### Licence (19 October 2026)

- **The licence.** A-share Company Intelligence is now licensed under the **PolyForm Strict License 1.0.0**: noncommercial use only, no distribution and no changes, without warranty. `LICENSE.md` holds the licensor and copyright line (Leong, Wen Yi), then the licence text exactly as the PolyForm Project publishes it; a test checks the text against the published file's checksum.
- **Where it appears.**
  - The README has a "Licence" section.
  - `CITATION.cff` gives `license: PolyForm-Strict-1.0.0`.
  - `READ_ME_FIRST.txt` and the third-party notices name the licence.
  - Every download includes `LICENSE.md`.
  - The installer shows the licence on an "I Agree" page before installing, matching the licence's acceptance clause.
  - The uninstaller removes the file.
- **Bundled components.** These keep their own licences. The notices state that the PolyForm Strict licence does not apply to them.

### Packaging addendum (19 October 2026): third-party notices

The executables bundle the Python runtime and some thirty libraries, whose MIT, BSD, Apache and PSF licences permit redistribution only with their copyright and licence notices. The first v2.0.4 downloads included almost none of these notices. The installer and portable zips were rebuilt to include them; the programs themselves are unchanged.

- **The notices file.** Every download now includes `THIRD_PARTY_NOTICES.txt`. It lists each bundled component with its version, and reproduces its licence texts and copyright notices in full. The 31 components include:
  - the Python 3.12.7 runtime;
  - the software Python incorporates, such as OpenSSL under the Apache License 2.0, expat, libffi, zlib and libmpdec, taken from CPython's own `Doc/license.rst` at v3.12.7;
  - pypdfium2, with the licences of everything compiled into PDFium (FreeType, ICU, libjpeg-turbo, libpng, OpenJPEG, zlib and others);
  - Tcl/Tk;
  - the PyInstaller bootloader;
  - the Microsoft runtime.
- **How it is generated.** `packaging/third_party_notices.py` runs on every build (`build_windows.bat` and the GitHub Windows build). It reads PyInstaller's record of what was bundled, so it lists exactly what ships. It stops the build if a component has no licence text, or if the notices for the bundled Python version are missing.
- **Source code.** The notices say where each component's source code is available. certifi's Mozilla Public License 2.0 requires this.
- **Installer.** The installer installs the notices and the uninstaller removes them; tested under Wine.
- **README and quick-start note.** The README now has a "Third-party components" section, stating that bundled components keep their own licences. `READ_ME_FIRST.txt` points to the notices.
- **Tests.** New tests in `tests/test_third_party_notices.py` check:
  - that the notices list what the build bundled;
  - that the program's own package is left out;
  - that a missing licence text stops the build;
  - that the Python 3.12 notices cover OpenSSL, expat, libffi, zlib and libmpdec.

### Changed: the catalogue engine (`ashare/market_catalogue.py`)

- **Rows, not announcement IDs (finding 25).** A row is one announcement for one security, keyed by announcement ID and security code. CNINFO's total counts rows, so the completeness check now compares like with like.
  - Announcements listed for several securities are counted (`rows_multi`) and are no longer taken for a shortfall.
  - Each listed company's row is stored. Storage was already one record per company and announcement.
- **A general splitter (findings 22 and 23).** A query over 3,000 is split along the next dimension that reaches its total. The dimensions, in order of preference:
  - board, by the disjoint codes (`szmb`, `szcy`, `shmb`, `shkcp`, `bj`), or by whole exchanges (`sz`, `sh`, `bj`) where those do not work;
  - category;
  - industry (the CSRC sections, in the `trade` field);
  - batches of companies (`stock`, 150 at a time, halved while a batch is over the limit).

  How each dimension is checked:
  - The parts' totals are checked against the whole.
  - A filter CNINFO ignores (every part reports the whole) or rejects (every part is empty) is not used again in the run.
  - Categories are never switched off, since an empty category split can be legitimate.
  - A split that does not reach the whole is noted against the day (`partition`).
- **Both sort orders.** A query with up to 6,000 results is read newest-first and oldest-first. Whether CNINFO honours the order is detected on first use; if it does not, sorting is not tried again. A window under the limit that comes back short (rows moving between pages) is also read in both orders.
- **Gaps by board (finding 24).** A gap is attributed to boards from CNINFO's board totals and the security codes of the rows received.
  - Only a gap within the enabled boards makes a day SHORTFALL.
  - A gap shown to lie outside them (for example Beijing when it is off) is recorded (`gap_out_scope`), and the day is DONE.
  - A gap that cannot be placed counts as within the enabled boards, so a missing filter can never hide a shortfall.
- **Early stop (finding 27).** After a split, the last pass over a query that cannot be read in full stops after five pages that bring nothing new. A query with no usable split is still read in full: in testing, an early stop there missed rows that came after a run of known ones.
- **Re-catalogue only with a new method (finding 26).** Each day records the strategy that produced it.
  - `recatalogue-busy-days` fetches failed days, days short under an earlier version, and days that versions before v2.0.3 cut short.
  - A day whose gap recurred under the current method is held back with a plain explanation; `--include-current` overrides this.
- **Recent totals rechecked (finding 28).** The totals of finished days in the last 30 days are rechecked (one query per recorded window), and grown days are fetched again. This happens at the start of a run that reaches those days, and once a day in the daily update.
- **Unmatched rows by reason (finding 30).** Rows for securities outside the company list are counted by reason (Beijing, B shares, bonds and so on). The count is now of distinct rows, where v2.0.3 counted an announcement again for each overlapping split.
- **Progress** lines appear every five parts of any split, not only categories.

### Changed: commands and the desktop

- **New command `probe-cninfo-filters --day 2026-04-29`** (desktop: **2 Disclosures** › Check CNINFO's search filters; about 70 to 120 requests). It reports a verdict for each of:
  - both board schemes;
  - the industry filter;
  - company batches;
  - the sort orders;
  - the cause of repeated rows on a quiet window.
- **Outcome wording (finding 29).** A catalogue that finishes with gaps within the enabled boards ends with "Finished with gaps" and exit code 3; the desktop shows "Finished with gaps" instead of "Failed". Failed days and stopped runs still end with exit code 1. Code 3 was chosen because the command-line library already uses 2 for usage errors.
- **`catalogue-days` shows more:** the gap within and outside the enabled boards, rows for several securities, the method and the split notes.
- **The daily update** rechecks recent totals once a day (a second run on the same day still sends no announcement query).

### Database

Migration `0004_v204_catalogue_detail` adds six columns to `catalogue_days`: `rows_multi`, `gap_in_scope`, `gap_out_scope`, `partition`, `strategy` and `window_expected`. Existing rows keep their values; days recorded by v2.0.3 have no strategy, so they count as produced by an earlier method.

### Fixed during the build

- **Categories switched off for the whole run.** A category split that came back empty for one part of a day (for example Beijing's uncategorised announcements) would have switched categories off for the rest of the run. Now only the board, industry and company filters are switched off on empty results.
- **Early stop.** The early stop judged a page "idle" after its rows had already been recorded, so every page would have looked idle. It now judges each page before recording it, and applies only after a split (see above).

### Findings from this build

1. **The finer splits are still unverified live.** The engine was tested against a simulated CNINFO in every combination: each filter working, ignored, rejected, or the sort order honoured or not. In every combination, either every row arrived or the gap was recorded per board. Which combination the live service matches is shown by the first run's `filters` line, or by `probe-cninfo-filters`.
2. **Without company batches or the sort order, some gaps remain possible.** Uncategorised announcements beyond 3,000 within one industry and board cannot be reached by any other means. They are recorded, and the probe's output will show whether a further dimension (for example a title keyword) is worth adding.
3. **A gap that cannot be attributed counts against the dataset.** This is deliberately conservative. If the Beijing code does not work, unreached Beijing announcements make a day SHORTFALL even though they are outside the default scope.

### Still to confirm live

1. `ashare-cli probe-cninfo-filters --day 2026-04-29`: keep the output.
2. `ashare-cli recatalogue-busy-days --kind all`: the 12 days short under v2.0.3 are fetched again with the new method.
3. `ashare-cli catalogue-days --kind all --problems`: the expected result is no day with a gap within the enabled boards.

### Testing

- New tests in `tests/test_v204.py` (18) use a simulated CNINFO that reproduces the live behaviour (overlapping board codes, the 3,000 limit, uncategorised and Beijing announcements, rows for several securities), with switches for each unknown filter. They cover:
  - the acceptance day shaped like 29 April with every filter working;
  - the same day with only whole-exchange boards and company batches, and with industry only;
  - unreachable rows recorded per board;
  - both sort orders;
  - a Beijing-only gap;
  - the conservative rule;
  - rows for several securities;
  - unstable ordering with and without sort order;
  - the early stop;
  - the recent-total recheck;
  - re-catalogue holding and overriding;
  - v2.0.3 shortfalls fetched again;
  - exit codes in the command line and the desktop;
  - the probe verdicts;
  - the migration.
- Three v2.0.3 tests were updated where v2.0.4 deliberately changes behaviour (method names, and a current-method shortfall no longer re-catalogued by default).
- An end-to-end run through the desktop's command path checked:
  - Stop and resume;
  - 29 April complete when only whole-exchange boards and company batches work;
  - with company batches also off, the remaining 155 rows recorded and the run ending "Finished with gaps";
  - the re-catalogue holding that day;
  - the probe naming each filter's behaviour.
- Results by platform:

  | Platform | Passed | Skipped |
  |---|---:|---:|
  | Linux, Python 3.12 | 184 | 2 |
  | PostgreSQL 16 | 181 | 5 (three are the SQLite-only migration fixtures) |
  | Windows CPython 3.12 under Wine | 182 | 4 |
  | Python 3.13 | 176 | 8 |

  No test fails on any platform. A real v2.0.3 database was also upgraded to migration 0004: its recorded shortfall was kept and selected for re-cataloguing. The Windows executable reports version 2.0.4, passes the offline self-test (20 checks) and migrates a new database to 0004.

## v2.0.3 (17 October 2026)

**Aim:** a whole-market catalogue that is complete, resumable and honest about gaps, and panels that are never silently empty. The plan followed the order suggested in the findings file:

1. busy days (finding 6);
2. catalogue mechanics (findings 3, 13 and 14);
3. empty panels (finding 4);
4. a check of the font warnings (finding 1).

It also covers progress within a busy day (finding 15) and the warning flood (finding 5). Speed and polish (findings 2, 7 to 11 and 16 to 18) are left for v2.1.

### Changed: the whole-market catalogue (findings 3, 6, 13, 14 and 15)

The market-wide catalogue was rewritten as `ashare/market_catalogue.py`. `disclosure_pipeline.catalogue_market` and the daily update (`ops.catalogue_market_day`) both use it.

- **One query per period, not one per exchange (finding 3).** With the stock field empty, CNINFO ignores the `column` parameter: the SSE and SZSE queries in the live log returned identical totals, so every run fetched everything twice. The engine now sends one query (column `szse`, any value works) and takes each announcement's exchange from its security code.
- **Paging stops when nothing new arrives (finding 6).** Paging is de-duplicated by announcement ID. It stops at:
  - an empty page;
  - a page that brings no new ID (CNINFO repeating earlier results);
  - the point where every announcement CNINFO reported has arrived;
  - `hasMore` false;
  - one page past the last page CNINFO's total implies.

  v2.0.2 paged up to its 2,000-page limit while CNINFO kept saying there was more.
- **Busy days are split (finding 6).** A period over 3,000 results is halved down to single days. A single day over 3,000 is split into CNINFO's 26 announcement categories (`category_*_szsh`). A category still over 3,000 on that day is split by board (`sz`, `szcy`, `sh`, `shkcp`). If the categories still add up to less than the day's total, a last pass queries the whole day by board. Announcements filed under several categories are counted once.
- **Counts checked against CNINFO (finding 6).** For every day, the distinct announcements received are compared with CNINFO's `totalAnnouncement`. A gap is recorded as **SHORTFALL**, listed at the end of the run and makes the command end with an error code. It is never reported as done.
- **Resume by day (finding 13).** Every finished day is recorded in the new table `catalogue_days` (migration `0003_v203_catalogue_days`), with:
  - status (DONE, SHORTFALL, FAILED, OPEN);
  - CNINFO's total;
  - the number stored;
  - the period it was fetched in;
  - the method (WINDOW, DAY, CATEGORY_SPLIT, PLATE_SPLIT, CATEGORY_AND_PLATE_SPLIT, with `+BOARD_REMAINDER` where the last pass found more);
  - the query count.

  A rerun skips finished days. `--refresh` fetches them again; `--retry-shortfalls` fetches SHORTFALL days again. Today (China time) is recorded as OPEN and never skipped.
- **Errors per day (finding 14).** An error now affects only the period being fetched. Its unfinished days are recorded as FAILED with the error, and the run carries on with the next period. The failed days are listed by date at the end; a rerun retries only them. Three failed periods in a row still stop the run with a plain explanation (finding 16, DNS outages).
- **Progress within a busy day (finding 15).** Lines appear every 20 pages of a query, and every five categories of a split day, with the counts so far.
- **Daily update.** It uses the same engine for each day (`refresh` on), and a day with failures makes the job item fail, so the job's retry applies.

New commands, also in the desktop under **2 Disclosures**:

| Command | What it does |
|---|---|
| `recatalogue-busy-days [--kind all] [--since] [--until] [--threshold 2500] [--list]` | The one-step repair for catalogues made by earlier versions. Busy days are days recorded as SHORTFALL or FAILED, plus days with no v2.0.3 record that have at least 2,500 stored announcements (in 2026: late March, most of April, late August). Each is fetched again with splitting. |
| `catalogue-days [--kind] [--since] [--until] [--problems]` | Each day's status, totals and method. |
| `probe-cninfo-paging [--day 2026-04-24]` | The built-in test of the limit: reads pages 1, 100, 101 and 150 and gives a verdict of LIMIT_CONFIRMED, NO_LIMIT, UNCLEAR or INCONCLUSIVE (four requests). |

`catalogue-disclosures` gains `--refresh` and `--retry-shortfalls`. The live self-test gains the check `cninfo_paging_limit`.

### Changed: listing dates and panels (findings 4 and 12)

- **Quote-list variants (finding 4).** The new module `ashare/quotelist.py` asks Eastmoney's quote list in up to six ways:

  | Variant | Host and scheme | Headers | Page size |
  |---|---|---|---|
  | `push2` | https, push2 | as before | 100 |
  | `push2+referer` | https, push2 | browser Referer and Origin | 100 |
  | `82.push2+referer` | https, 82.push2 | browser Referer and Origin | 100 |
  | `push2delay+referer` | https, push2delay | browser Referer and Origin | 100 |
  | `push2+referer+pz20` | https, push2 | browser Referer and Origin | 20 |
  | `http-push2+referer` | http, push2 | browser Referer and Origin | 100 |

  Every variant keeps the program's own user agent. The variant that answers is remembered (`market_raw/quote_list_variant.json`) and tried first next time. The daily market snapshot uses the same variants.
- **`diagnose-quote-list`** (desktop: **1 Universe** › Diagnose the quote list). It tries each variant once and reports what each returned (HTTP status, error or a sample of rows), with a verdict and what to do. The self-test's quote-list check also tries the variants and names the one that answered.
- **Resumable listing-date download.** Every page fetched is kept in `market_raw/quote_list_pages/listing_<date>.json`, so a failed run carries on from the next page the same day. A partial list is applied: listing dates and LISTED for the companies it holds. "Not in the quote list" is set only from a complete list (all pages, at least 3,000 codes). The status line says when status could not be determined instead of printing "0 listed" (finding 12).
- **Panels with no rows are refused.** `write_panel` raises `EmptyPanel`, and "Build a panel" writes no files, prints why and what to do, and ends with an error code. The reasons it can give are:
  - the company list is empty;
  - the dates give no row;
  - most companies lack listing dates (pointing to `diagnose-quote-list`);
  - the filters exclude every company;
  - every company is financial.
- **Report-evidence fallback for yearly panels.** The new option `--universe-basis` (desktop: "Companies in each row") takes three values:
  - `listing`: the v2.0.2 behaviour.
  - `auto` (the default): as `listing`; for yearly rows, a company whose listing record is incomplete (no listing date, or delisted on an unknown date) also counts as listed in a year when it published a periodic report for that year. In point-in-time rows the report must be published by the row's cut-off (a report for that year, or the previous year's report published that year).
  - `report-evidence`: report evidence only.

  A new identifier column, `universe_basis` (LISTING_RECORD or REPORT_EVIDENCE), marks each row. It is described in the codebook. `universe_at` now also reports which companies it excluded (`excluded_codes`).

### Changed: PDF reader messages (findings 1 and 5)

- **One summary line (finding 5).** pypdf's warnings are collected during each command instead of being printed (`ashare/pdfwarnings.py`). At the end of the command, one line counts them by kind and by number of documents, and the details go to `logs/pdf_warnings_<time>.txt`, documents needing a check first. The kinds are:
  - font notices with a standard encoding;
  - font notices without one;
  - damaged cross-references;
  - other.
- **Font check (finding 1); fontTools not bundled.** See `docs/font_check_v2.0.3.md`. pypdf issues the warning only for embedded CFF Type1 fonts without a ToUnicode map. Without fontTools it then decodes through the font's declared `/Encoding`. In the live log, 2,408 of the 2,428 notices were fonts declaring `/WinAnsiEncoding` (Helvetica Neue, Myriad, Avenir). The remaining 20 cover character codes 24 to 31 only, so they cannot hold digits. An experiment with a real embedded CFF font showed:
  - with WinAnsi declared, figures are extracted correctly without fontTools;
  - they are lost only for a font with a non-standard built-in encoding and no declared encoding;
  - pdfium also fails in that case.

  The test `test_font_check_figures_survive_without_fonttools` keeps this as a regression check. It passes with pypdf 6.19 (the Windows build) and 6.21 (what `pip` installs today, used by CI), which keeps the fontTools switch in a different module but decodes the same way.

### Fixed

- **The desktop showed failed actions as finished.** `gui.run_command` calls the command line with `standalone_mode=False`. In that mode, `typer.Exit(code)` *returns* the code instead of raising it, and the return value was discarded. Every command that ended with an error code therefore showed "Ready" in the desktop. This affected v2.0.2 and earlier; it was found while testing the panel refusal. `run_command` now uses the returned code.
- `tests/test_v19.py` mocked CNINFO as filtering by exchange, which the live service does not do. The mock now returns the whole market whatever the column, as the live service does.
- Tests no longer write into the working folder. Some older tests created `ashares.db` there, and the new quote-list check created `market_raw/`. An automatic fixture in `tests/conftest.py` now points the database, archives and logs of every test at its own temporary folder.
- The offline self-test (canned responses) no longer records a quote-list variant as working; only a live answer is remembered.

### Important findings from this build

1. **The 3,000-result limit is still an inference.** The engine is built for a limit at 100 pages but does not depend on it: it stops on repetition, splits whenever CNINFO's total exceeds 3,000 and checks every day against the total. `probe-cninfo-paging` settles the question on the live site in four requests.
2. **The category split may not account for every announcement.** If CNINFO holds announcements under none of the 26 categories, the categories add up to less than the day's total. The engine then makes a last pass over the whole day by board (at most four more queries of up to 100 pages each), keeping only announcements not yet seen; method `…+BOARD_REMAINDER`. On a very busy day, a board with more than 3,000 announcements can still hide some uncategorised ones. That day is recorded as SHORTFALL with the exact gap, never as done. If live runs show persistent small shortfalls, the missing category codes are the likely cause.
3. **Per-day totals for quiet periods.** Consecutive quiet days fetched in one query (fewer than 3,000 together) are recorded with the number stored per day. CNINFO's total is known only for the period as a whole, so the per-day expected count is blank, method WINDOW. The completeness check is made on the period.
4. **The quote-list fix is unverified.** The cause of the live 502s cannot be seen from the build environment, which has no access to Eastmoney. If no variant answers live, the report-evidence fallback still gives yearly panels with rows, once the periodic reports are catalogued. Panels by quarter or month still need listing dates (imported if necessary).
5. **The font warning was a false alarm for the live documents.** It still deserves monitoring (see above), not a 4 MB dependency.
6. **A silent failure mode in the desktop** (see Fixed) meant that earlier refusals and error exits would have looked like successes. Any future `typer.Exit` paths are covered by `test_gui_reports_refusals_as_failures`.

### Still to confirm live

These need the author's network. The build environment cannot reach CNINFO or Eastmoney.

1. `ashare-cli probe-cninfo-paging --day 2026-04-24`: expected verdict LIMIT_CONFIRMED.
2. `ashare-cli diagnose-quote-list`: which variant, if any, answers.
3. `ashare-cli recatalogue-busy-days --kind all`. Then `ashare-cli catalogue-days --kind all --since 2026-04-24 --until 2026-04-24`; stored should equal 15,382.
4. Stop a whole-market catalogue part-way, run it again, and confirm that the output says "N already finished (skipped)" and starts at the first unfinished day.
5. "Build a panel": either rows, with REPORT_EVIDENCE rows marked, or a refusal with the reason.

### Testing

- New tests in `tests/test_v203.py` (19) use a mock CNINFO that, like the live one, ignores the exchange column, caps a query at 100 pages, repeats page 100 thereafter and filters by category and board. They cover:
  - a 15,382-announcement day stored in full;
  - a 6,500-announcement day queried once per category;
  - uncategorised announcements recovered by the board pass;
  - shortfall recording;
  - runaway paging;
  - Stop and resume;
  - per-day failures and retries;
  - the three-failure stop;
  - today kept OPEN;
  - re-catalogue of days left by earlier versions;
  - the probe verdicts;
  - quote-list variants, resume and partial lists;
  - diagnosis;
  - the empty-panel refusal (library, command line and desktop path);
  - the report-evidence fallback (fiscal and point in time);
  - the warning summary;
  - the font check.
- An end-to-end run through the desktop's command path, using the same mock, confirmed the success criteria:
  - stopped after six seconds with four days finished;
  - the rerun skipped those four and finished the other seven;
  - 24 April stored 15,382 of 15,382;
  - a panel without listing dates was refused with the reason and exit code 1.
- Results by platform:

  | Platform | Passed | Skipped |
  |---|---:|---:|
  | Linux, Python 3.12 | 166 | 2 |
  | PostgreSQL 16 | 163 | 5 (three are the SQLite-only migration fixtures) |
  | Windows CPython 3.12 under Wine | 164 | 4 |
  | Python 3.13 | 159 | 7 |

  No test fails on any platform.
- The Windows build was checked under Wine:
  - executables built with PyInstaller;
  - the offline self-test passed 20 checks, including `cninfo_paging_limit`;
  - the installer installed silently, reported version 2.0.3 and uninstalled cleanly;
  - sizes: installer 22.4 MB, portable zip 27.8 MB, command-line add-on 10.5 MB.

### Deferred to v2.1

- Extraction speed (finding 2): a text cache and faster extraction.
- Parquet offered without pyarrow, and partial files on failure (finding 7).
- Reasons for other empty results (finding 8).
- Code 201872 (finding 9).
- Locking settings during a run (finding 10).
- The progress rate display (finding 11).
- Longer retries for DNS failures (finding 16).
- The explorer on an empty panel (finding 17; now rarer, since empty panels are not written).
- `show-market` with no prices (finding 18).
