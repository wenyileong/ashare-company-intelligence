# China A-share Company Intelligence v2.1.0

A provenance-preserving research data system for SSE Main Board, STAR Market, SZSE Main Board and ChiNext companies. The architecture is set out in `ashare_scraper_build_plan.md`. Changes by version, and the findings behind them, are in `CHANGELOG.md`. The live-run findings are in:
- `docs/live_run_findings_v2.0.2.md`;
- `docs/live_run_findings_v2.0.3.md`;
- `docs/live_run_findings_v2.0.5.md`;
- `docs/live_run_findings_v2.0.6.md`;
- `docs/live_run_findings_v2.0.7.md`;
- `docs/live_run_findings_v2.0.8.md`.

The register of the findings, and the visualisation plan, is `docs/plan_v2.0.8_and_visualisation.md`; the plan for v2.1 is `docs/plan_v2.1.md`.

v2.1.0 closes the faults of the latest live runs (findings 96 to 109) and adds three things:

- **Data corrections.** Beijing and B-share companies are no longer treated as delisted, and are dated from their own lists. Top-10 tables keep rows only one reading found, when the table still passes its checks. Failures leave their full error in a file; findings are given as rates of what was checked; panels say why rows lack figures.
- **Speed.** Financial extraction reads only the key-figure and statement pages of a report, and every extractor reads several documents at once.
- **The topology view.** For a set of companies or a CSRC industry over a span of years, the five layers of the Nested Valuation Framework, from institutional context to market valuation, with the document behind every item and the gaps shown. It is a layered chart in the desktop and an offline interactive page (2D and 3D) adapted from the NVF Topology Tester. Management guidance (业绩预告, 业绩快报) is read as a labelled proxy for expectations.
- **A Chinese interface.** EN | 中文 switches the desktop between English and Simplified Chinese, in the official terms of the approved glossary; datasets are identical in both.

After upgrading, see `CHANGELOG.md` for the steps that re-read the reports.

v2.0.9 fixes a fault in v2.0.8: "Update the company list" failed with a TypeError when a company had a risk warning imposed and lifted on the same day. If the listing history cannot be rebuilt, the update now finishes anyway and says so.

v2.0.8 corrects data before anything else (findings 70 to 95):

- **Financial figures.**
  - Notices about a report (提示性公告, 更正公告) are no longer read as the report.
  - A table's unit is no longer borrowed from an unrelated table pages earlier.
  - Amounts cut short, and note numbers glued to amounts, are caught.
  - Figures misread before are removed when a report is read again.
- **Panels use the listing dates.** A listing history built before the dates arrived no longer hides them. A panel names any fiscal year that has not ended.
- **Faster table extraction, with progress and resume.** Shareholders, control, segments, R&D and workforce, subsidiaries and the officer roster read only the pages of their tables. They show documents done and left, and a stopped run continues with the next report.
- **Segments and controllers.** Segment tables continued over a page break are read in full, and subtotals are kept out of the sums. The actual controller is read from both exchanges' report layouts.
- **Price sources.** A second public source (Tencent), a test of each source, and a setting to choose one or none (CSV import only).
- **Installer and findings.** The installer asks for a running copy to be closed. "Show findings" opens with a summary and exports to CSV.

After upgrading, see `CHANGELOG.md` for the four steps that re-read the reports.

v2.0.7 fixes two faults found by a review of a live release (findings 68 and 69, `docs/live_run_findings_v2.0.6.md`):

- **Top-10 shareholders.** Reports with the shareholder nature after the name (the Shenzhen templates) were misread: the nature was glued to the name and every figure shifted one column. Both layouts are now read and checked, and misread rows are removed when the reports are read again.
- **Pseudonymisation.** A natural person's name with the nature glued on was not masked. Masking now fails safe: a name is masked unless it is shown to be an organisation's. **Do not share a pseudonymised release made before v2.0.7.** After upgrading:
  1. run "Extract top shareholders";
  2. run "Resolve entities";
  3. make the release again.

It also sends companies to CNINFO ten at a time (the size confirmed live), rejects a split part larger than its parent, reads listing dates from the exchanges' own stock lists first, and stops the quote list after three refused attempts in a row.

v2.0.6 is a patch from the first live runs of the v2.0.4 catalogue engine (findings 35 to 57, `docs/live_run_findings_v2.0.5.md`):

- **Listing dates for the whole list.** The quote list stopped after 1,000 companies on every run. When it stops part-way it is now read board by board, in both code orders, with retries after a pause, and the reason is shown.
- **Extraction you can follow and resume.** "Extract figures from reports" shows documents done, seconds per document and an estimated finish, and a stopped run continues with the next document (migration 0005). The Stop message says what running a command again does, only where that is true.
- **The last catalogue gaps.**
  - Busy queries are split before they are read in both time orders.
  - A query still over the limit is split by manufacturing division, by companies sent with their own exchange, or, as a last resort, by single companies.
  - Short quiet periods are read again day by day and board by board.
  - A query is never read twice in a day.
- **Reporting.** A window of quiet days is one row in "Which days are catalogued", and today is counted as kept open.

v2.0.5 is a maintenance release for the public repository. It changes no collection or extraction logic:

- **User agent.** The default user agent names the program, its version and this repository, instead of a placeholder. Researchers running large collections should still add their own contact details with `ASHARE_USER_AGENT` (`docs/compliance.md`).
- **Request-rate ceiling.** The request rate can be lowered but no longer raised above 2 requests per second, whatever `ASHARE_RPS` or `ASHARE_MARKET_RPS` say. The default stays at 1 request per second.
- **Repository documents.** A disclaimer (below), `CONTRIBUTING.md` and `SECURITY.md`.
- **Build workflows.** The GitHub workflows use the current versions of the checkout, Python set-up and artefact actions (Node 24), with a read-only token.

The release downloads are not yet code-signed, so Windows may show "Windows protected your PC" on first run (choose **More info**, then **Run anyway**). Check each download against `SHA256SUMS.txt` on the release page.

v2.0.4 is a patch that **closes the catalogue gaps on the busiest disclosure days** (live-run findings 20 to 34). The first live whole-market run under v2.0.3 confirmed CNINFO's 3,000-result limit and the resume, but left 12 days short. The causes were overlapping board codes, categories still over the limit on one board at the April deadline, announcements outside the Shanghai and Shenzhen boards, and rows repeated for several securities.

- **Rows, not IDs.** A row is one announcement for one security; announcements listed for several securities are counted and no longer taken for a shortfall.
- **A general splitter.** Busy queries are split by board (disjoint codes, or whole exchanges as a fallback, Beijing included), category, industry and batches of companies, and a query with up to 6,000 results is also read in both sort orders. Which filters CNINFO supports is checked as the run goes; only those that work are used, and a split that does not reach the whole is noted against the day.
- **Gaps by board.** Only a gap within the enabled boards makes a day short; a gap shown to lie outside them is recorded but the day is complete. A gap that cannot be placed counts as within.
- **Smaller changes:**
  - an early stop for a last pass after a split;
  - re-cataloguing only with a new method;
  - recent totals rechecked;
  - "Finished with gaps" (exit code 3) instead of "Failed";
  - unmatched rows counted by reason;
  - the new command `probe-cninfo-filters`.

v2.0.3 makes the **whole-market catalogue complete and resumable**, and **panels no longer silently empty** (live-run findings 1, 3 to 6, 12 to 15):

- **Busy days.** CNINFO appears to return at most 3,000 announcements (100 pages) to one query, so v2.0.2 lost announcements on days with more, and then paged on to 2,000 pages. Paging now stops when a page brings nothing new. A day over the limit is split by announcement category (and a category over it by board). Each day's stored count is checked against CNINFO's total, and a gap is recorded and reported as SHORTFALL rather than passing as done. `recatalogue-busy-days` fetches again the days earlier versions cut short; `probe-cninfo-paging` checks the limit directly (pages 1, 100, 101 and 150 of 24 April 2026; four requests).
- **One query, resume, errors per day.** One market-wide query per period instead of one per exchange (CNINFO ignored the exchange, so v2.0.2 fetched everything twice). Finished days are recorded (`catalogue_days`, migration 0003), so a rerun after Stop or an error carries on with the first unfinished day. An error marks only that period's days as FAILED, the run continues, and the failed days are listed; `catalogue-days` shows each day's status. Progress lines now appear within a busy day as well as within long queries.
- **Quote list and panels.** The Eastmoney quote list (listing dates) refused every request in the live runs. It is now tried in several ways (other host names, a browser's Referer, http, a smaller page size), always with the program's own user agent, and the way that works is remembered. `diagnose-quote-list` reports what each way returned. The download is resumable and a partial list is applied. "Build a panel" refuses to write a panel with no rows and says why and what to do. For yearly panels, a company with an incomplete listing record counts as listed in a year when it published a periodic report for that year; such rows are marked `universe_basis = REPORT_EVIDENCE`.
- **PDF reader messages.** The flood of pypdf warnings (2.1 MB of a 2.2 MB log) is now one summary line per command, with details in `logs/`. The fontTools font warning was checked against an embedded CFF font: figures are not lost when the font declares a standard encoding, as 2,408 of the 2,428 live warnings did, so fontTools is not bundled (`docs/font_check_v2.0.3.md`).
- **Desktop.** An action that ended with an error code (a refused panel, failed catalogue days) was shown as finished; it is now shown as failed. The new commands are on the Disclosures and Universe pages.

Live confirmation is still needed for the paging limit, the quote-list variants and the re-catalogue (see `CHANGELOG.md`, "Still to confirm live").

v2.0.2 fixes what the **second live run** found:

- **Whole-market catalogue.** Without a security code, cataloguing queried CNINFO once per company (over 5,500 requests, several hours with downloads) and printed nothing until the end, so it looked stuck. It now queries each exchange as a whole in calendar-month windows (split automatically where a month holds more than one query returns), which takes a few hundred requests; `--per-company` keeps the old method. Downloads run as a second phase with a size and time estimate, and only for the documents the extractors read (full reports, not summaries or English versions). `download-documents` downloads catalogued documents of chosen kinds later.
- **Progress and Stop.** The desktop output now shows progress lines as an action runs, and a **Stop** button ends any action safely after the current request or document; everything saved is kept and running the action again resumes. Long extractions print a line every 25 documents.
- **Whole-market warnings.** The desktop asks before whole-market downloads and price histories, with an estimate.
- **Listing dates and status.** "Update the company list" now also reads listing dates from the public quote list (about 60 requests) and sets each company's status: LISTED, DELISTED (recognised from CNINFO short names such as 国华退 or PT金田A) or NOT_IN_QUOTE_LIST. Point-in-time lists and panels now leave out companies whose listing date, or delisting date, is unknown, and say how many, instead of treating every company as listed on every date.
- **Code ranges.** ChiNext codes beginning 302 (for example 302132, AVIC Chengdu Aircraft) and STAR depositary receipts beginning 689 are recognised. Codes not collected are summarised by reason (Beijing Stock Exchange and B shares, which are off by default).
- **Validation.** A missing full legal name is no longer reported as a problem for every company (CNINFO's list carries short names only); "Check the company list" reports it as a count, with the number of companies lacking a listing date.

v2.0.1 fixes what the **first live run** found:

- **Company list.** CNINFO no longer serves its separate Shanghai list (`sse_stock.json` returns 404), so "Update the company list" failed and every later step had nothing to work on. CNINFO's remaining list (`szse_stock.json`) covers Shanghai, Shenzhen and Beijing despite its name; the program now reads that one list and infers each company's exchange from its code. If CNINFO moves the list again, `ASHARE_CNINFO_STOCK_LIST_URL` overrides the address.
- **Self-test.** The list check now reports the number of Shanghai and Shenzhen (and, when enabled, Beijing) securities separately, so a list that silently loses an exchange fails visibly.
- **Clearer messages.** HTTP and network errors now say what to do next (for a 404: run the Self-test). Commands that need companies warn when the company list is empty, and "Check the company list" no longer reports success on an empty list.

v2.0 is the **end-state release: distribution and documentation** (build plan, section 18.10):

- **Schema migrations.** The schema is versioned with Alembic (`ashare/migrations`). Databases written by any version from v0.7 onwards are upgraded automatically on start, after a backup copy is saved beside a SQLite file (`ashares.db.bak-…`). `db-status` shows the revision and history; `db-upgrade` runs the upgrade by hand. Old-schema fixtures from v0.7, v1.3 and v1.9 are upgraded in the tests.
- **Installer.** A per-user Windows installer (`AShareScraper-2.0.2-setup.exe`, NSIS) installs the desktop application and the command line together, with the documentation, Start-menu entries, an optional desktop shortcut, an option to put `ashare-cli` on the PATH, and an uninstaller that leaves the data folder alone. A portable zip is still produced. Signing hooks (`packaging/sign.bat`, `sign.sh`) sign the executables and installer when a certificate is configured; this build is unsigned.
- **Update check.** Off unless an update address is set (Settings, or `ASHARE_UPDATE_URL`); it reports a newer version and its hash and never downloads anything (`check-update`).
- **Licence-aware releases.** Every row is classed by its source as public disclosure, public feed, derived, manual or licensed (`licences`, `set-licence`). `release` leaves licensed rows out unless `--include-licensed` is given, can leave out further classes (`--exclude PUBLIC_FEED`), and records what it left out in the manifest. Imports count as licensed until their source label is tagged.
- **Pseudonymisation.** `release --pseudonymise` replaces the names of natural persons (directors, supervisors and officers, natural-person shareholders, pledgors and controllers) with stable keyed identifiers (HMAC-SHA256; the key stays in the data folder), drops raw text and document text, and replaces known names in titles and free text. `--coarsen` bands ages and birth years; `--drop-free-text` removes free text altogether. Organisations keep their names. Local file paths are removed from every release.
- **Data-quality report** with every release and on demand (`quality-report`): coverage by layer, board and year; parser precision from calibration; review statistics; flag rates; confidence classes; computed and standing gaps.
- **Citation.** Each release has a `CITATION.cff` and a suggested citation with the software version and database fingerprint; the software has its own `CITATION.cff`.
- **Documentation** (`docs/`, also installed as HTML): a user guide, a methods document suitable for citation, the codebook of all panel variables, a developer guide and a compliance note on licences, PIPL and UK GDPR. `packaging/build_docs.py` regenerates the codebook and the HTML.
- **Smaller changes.** Every command now has help text. Releases build their SQLite snapshot on any back end, including PostgreSQL.

v1.9 adds **whole-market operations and the remaining event types** (build plan, section 18.9):

- **Incremental daily update.** `daily-update` catalogues every announcement published since the last run, one market-wide query per exchange and day, rather than one query per company. It fetches the day's quotes for the whole market in about 54 requests, and extracts only from new documents. Each source keeps a high-water mark (`high-water-marks`), so a second run on the same day sends no announcement queries at all. Only the document kinds that the extractors read are downloaded; the rest are catalogued with their URLs.
- **Resumable jobs.** Long runs are jobs (`job-create`, `job-run`, `job-cancel`, `jobs`, `job`). Each item is committed as it finishes, so a cancelled or interrupted job resumes where it stopped without duplicating or losing records. Transient network errors are retried with back-off, up to three attempts, and failures are listed for attention. The Operations page shows progress with a cancel button.
- **Request budget.** `estimate-daily` estimates the requests and minutes a daily run needs at the configured rate. A day of 4,000 announcements with a quarter downloaded takes about 16 minutes at one request per second.
- **Scheduling (opt in).** `schedule --enable` creates a Windows Task Scheduler entry for the daily update (elsewhere it prints a cron line). `--dry-run` shows the command without creating anything.
- **Storage management.** `storage-stats` reports the archive by document kind. `prune-documents` removes PDFs of chosen kinds after extraction, keeping the hash and URL; it is a dry run unless `--apply` is given and never touches files outside the documents folder. `refetch-document` downloads a pruned file again and checks its hash.
- **Back ends.** SQLite remains the default and now uses write-ahead logging and composite indexes for the common queries. PostgreSQL can be used by setting `ASHARE_DB_URL` (for example `postgresql+psycopg://user:password@host/ashares`); the whole test suite runs against it. `export-duckdb` writes chosen tables to a DuckDB file for fast analysis (optional dependency).
- **Remaining events.** `extract-transactions` and `transactions` cover:
  - major asset restructurings (重大资产重组), with stages from planning and suspension to plan, draft, approval, completion or termination; the stages of one deal share a case number;
  - related-party transactions: counterparty, amount, nature (purchase, sale, lease, financing, guarantee and others) and approval body;
  - external guarantees (对外担保): beneficiary, amount, cumulative balance, whether the beneficiary is related and whether any guarantee is overdue;
  - shareholder-meeting resolutions, with the share of votes for, against and abstaining for each proposal where they are disclosed.
- **Self-test.** Two new checks cover the market-wide announcement query and the Eastmoney quote list. Neither endpoint has been verified against the live source yet; run the Self-test once on a networked machine before relying on the daily update.

v1.8 adds **ownership and control** (build plan, section 18.8):

- **Top-10 holders.** The top-10 shareholder table (holding, change, stake, restricted shares, pledged or frozen shares, holder nature) and the top-10 tradable-holder table are now read from the reports (`extract-top-holders`). Both the plain and the layout extractor are used; long fund names that wrap onto two lines are rebuilt.
- **Pledges.** Pledge and release announcements are read from both narrative and table layouts (`extract-pledges`, `pledges`). Each record gives the pledgor, pledgee, shares, share of the holding and of total capital, start and release dates, and the cumulative amount pledged.
- **Control.** The controlling shareholder and the actual controller are read from 控股股东情况 and 实际控制人情况 (`extract-control`, `control`), as is a statement that a company has no actual controller.
  - **Ownership type.** Each company is classed as central SOE, local SOE, private, foreign, collective, no controller or unknown, and the basis of the classification is stored with it. It agrees with a 30-case hand-coded sample; unknown types are flagged for review.
  - **Control chain.** Each link is stored with its stake, taken from the top-10 table where it can be. The percentages in the report's ownership diagram (方框图) can be imported with `import-control-edges-csv`.
- **Entity register.** `resolve-entities` builds a register of organisations, resolved by unified social credit code (check digit verified, GB 32100-2015) or by normalised name. It covers shareholders, subsidiaries, controllers and listed companies, and links each to its observations. `import-entities-csv` adds credit codes and aliases; `entity` shows an organisation's shareholdings, subsidiaries and the companies it controls.
- **Person register and interlocks.**
  - `resolve-persons` groups directors and officers across companies by name, gender and birth year (birth year within one). Names without an age are kept separate rather than merged.
  - `interlocks` lists companies that share a director.
  - `common-controllers` groups companies under the same actual controller.
- **Diagrams.** A control-chain diagram, a group-structure tree (subsidiaries grouped by jurisdiction, offshore entities highlighted) and an interlock network. They appear in the chart window and are available through `chart control | group-tree | interlocks`.
- **Validation.** New flags: `OWNERSHIP_TYPE_UNKNOWN`, `ACTUAL_CONTROLLER_CHANGED` and `TOP_HOLDERS_EXCEED_100PCT`.
- **Panel variables.** `ownership_type`, `soe`, `top10_pct` and `top_holder_pledged`. Each uses only reports published by the row's cut-off.
- **Matplotlib.** The optional renderer now uses CJK fonts where they are installed, and declines diagram kinds, which are SVG only.

v1.7 turns the database into **research datasets** (build plan, section 18.7):

- **Statements.**
  - A versioned chart of 132 CAS line items (`chart-of-accounts`) is read from the consolidated balance sheet, income statement and cash-flow statement. The parser reads only those pages, stops at the parent-company statements, and records the chart version on each value.
  - A plain number after a label counts as a note reference only when two amounts follow it.
  - The statement parser also has a layout variant and a place in the accuracy gate.
- **Derived measures.** Single quarters from year-to-date reports, trailing twelve months, net profit excluding non-recurring items (扣非净利润) and the non-recurring items themselves (`quarterly`, `ttm`, `non-recurring`).
  - Every derived value carries the latest publication date of its inputs and the lowest confidence class among them.
- **Own adjustment factors.** `adjustment-factors` computes ex-date factors from recorded dividends, bonus and capitalisation issues and rights issues. Adjusted returns therefore no longer depend on a provider's adjustment. Provider-adjusted closes are compared with the program's own, with the share of days within 0.5% reported.
- **Valuation.** `market-snapshots` and `valuation` give market cap, free-float cap, P/E and P/S (TTM), P/B and EV (market cap + interest-bearing debt − cash). Each uses only financial values published on or before the date, and lists the inputs it used.
- **Panel builder.** `build-panel`, or Analyse › Datasets in the desktop application.
  - **Rows:** company-year or company-quarter (fiscal alignment), or company-date (point-in-time alignment, e.g. every 30 April or every month end).
  - **Variables:** about 170, covering statements, TTM, ratios, market values and returns, governance, workforce, segments, ownership, index membership, listing status, industry and penalties.
  - **Options:** as-of date, index universe, board filter, exclusion of financial firms, minimum confidence class, reviewed values only, winsorisation, lags and leads, and publication-date columns.
  - **Survivorship.** The universe for each row is the point-in-time list.
  - **Look-ahead guard.** The builder refuses any value published after a row's cut-off, and the manifest records the latest publication date used.
  - **Outputs:** CSV, Stata `.dta` (written by a built-in writer, no pandas needed), optional Parquet, an R loader and types file, a codebook in Markdown and HTML (definition, formula, source, point-in-time rule, coverage by year), and a hashed manifest.
- **Event studies.** `event-study` measures abnormal returns around corporate, regulatory, management or listing events, or around events listed in a CSV.
  - **Models:** market model, market-adjusted or mean-adjusted.
  - **Benchmark:** equal-weighted, or an index supplied as a CSV.
  - **Outputs:** per-event CARs, the mean with its t-statistic, and the average CAR by day with a 95% band, as CSVs and a chart.
- **Charts.** New chart kinds: scatter with a least-squares line, histogram, box plot by year, coverage heatmap, stacked and 100% bars, shaded bands, and event markers on time axes. New charts built from them:
  - a price chart with corporate, regulatory, management and listing events;
  - segment mix and workforce composition over time;
  - the industry distribution with the company marked;
  - an industry-peer scatter.
- **Dataset explorer.** A window for any panel, with a summary table, correlations, histograms, distributions by year, scatter plots with a fitted line, and coverage. It is also available from the command line as `panel-chart`.
- **Interface.** A new Analyse page, "Datasets". Form fields now check numbers and whole numbers.

v1.6 adds a **point-in-time security master** (build plan, section 18.6):

- **Listing events.** IPOs, delistings, and changes of short name, full name, code and board. These come from three sources, each kept with its source and a date basis:
  - **Announcements** (上市公告书, 终止上市/摘牌, 变更证券简称, 证券代码变更, 转板). These give the effective date (`extract-listing-events`).
  - **Changes noticed between two downloads of the official list.** These are dated when detected, not when they took effect. A company that drops off the list is recorded as `MISSING_FROM_LIST` for review, not as delisted.
  - **Imported historical lists** (`import-listing-events-csv`, `import-security-history-csv`). These bring in companies delisted before the collector started, and imported periods take precedence over derived ones.
- **Security history.** `rebuild-security-history` turns the events, together with the ST and *ST risk warnings from the regulatory layer, into dated periods of code, short name, full name, board, listing status and risk warning. `security-history` shows them with the events behind them.
- **Universe on a date.** `universe-at 2015-06-30` lists the companies listed on that date, under the codes and names they had then, including those delisted since, so samples avoid survivorship bias. The company profile shows the name, board and status on its *as of* date.
- **Index membership.** `import-index-csv` accepts membership periods or adjustment lists (ADD/REMOVE or 调入/调出). `index-members` and `company-indices` answer membership questions for any date. Index codes for CSI 300, CSI 500, CSI 1000, SSE 50, SSE 180, STAR 50, SZSE 100, SZSE Component and ChiNext are named.
- **Sustainability-report mandate.** Under the 2024 SSE and SZSE guidelines, constituents of SSE 180, STAR 50, SZSE 100 and the ChiNext Index must publish a sustainability report from fiscal 2025, by 30 April of the following year.
  - The ESG profile now states whether a report was mandatory and why.
  - Validation flags `SUSTAINABILITY_REPORT_NOT_OBSERVED` when a mandatory report has not been catalogued by its deadline.
  - Overseas dual listings, which are also covered by the guidelines, are not visible in this database.
- **Trading calendar and suspensions.** `build-calendar` derives trading days from stored prices; `import-calendar-csv` loads an official calendar instead. `suspensions` lists spells of open days without trading next to the suspension announcements.
- **Optional boards.** BSE (codes 920, 43, 83, 87, 88) and B-shares (SSE 900, SZSE 200, with their USD and HKD currencies) are off by default. To turn them on, use **Settings › Optional boards** or set `ASHARE_OPTIONAL_BOARDS=BSE,B_SHARE`. `boards` shows what is collected.
  - The BSE stock-list URL and the BSE and B-share disclosure-query parameters follow CNINFO's patterns but are unverified against the live site. The self-test checks the BSE list when that board is enabled.
- **Interface.** The Universe page gains cards for listing events, history and "Companies listed on a date". A new Collect page, "Indices & calendar", is added, and Collect pages are now numbered automatically.

v1.5 adds **layout-aware table extraction**, a **review workflow** and **native charts** (build plan, section 18.5):

- **Layout extractor.** Rows and cells are rebuilt from character positions (pypdfium2). A cell that wraps onto a second line, such as a long subsidiary name or a role like "董事、总经理、党委副书记", is merged back into its row whether the row is top-aligned or vertically centred. Headings, sentences and header rows are never merged.
- **Dual run.** Each table parser (financial statements, segments, subsidiaries, R&D and workforce, officers) runs on both the plain and the layout text. The variant with the higher calibrated confidence is kept, and the result is recorded in `extraction_note`:
  - when both variants agree, confidence rises by 0.05;
  - when they read different values for the same item, the value is capped at 0.4 and flagged `PARSER_DISAGREEMENT`, with the other reading attached;
  - rows the plain extractor broke into fragments are dropped and counted.
- **Parser registry.** `ashare.parsers` registers every parser and variant with its key, fields, method and version. New layouts can be added with `register()`. The evaluation harness scores each variant separately; `parsers` lists them.
- **Measured gain.** On the synthetic corpus, half of whose reports draw tables cell by cell with wrapped cells:
  - segment recall rises from 68% to 100%, subsidiary recall from 47% to 100%, and officer recall from 95% to 100%;
  - precision is 100% for every layout variant.
- **Scanned documents.** `scan-documents` records each PDF's text layer (FULL, PARTIAL or NONE) and lists scanned reports. No parser can read these, so their values must be entered by hand or imported. OCR is out of scope.
- **Review workflow.** **Check › Review** (or `build-review-queue`, `review-queue`, `review-show` and `review`) lists validation findings, parser disagreements and low-confidence values, ordered by materiality. Materiality weighs severity, size relative to revenue, and lack of confidence.
  - Selecting an item shows the value, raw text, method and finding, and renders the source page with the matched text outlined.
  - The actions are Accept, Correct (value and reason), Not disclosed and Defer.
  - Decisions go to `manual_corrections` with reviewer, time and reason, and are keyed by the observation's natural key (company, document, period, item), so they survive re-extraction. Rebuilding the queue keeps decisions already taken. Original observations are never changed.
  - Views apply decisions when they read: financial series, segments, subsidiaries, R&D and workforce, ESG and officers. A corrected financial value is HIGH confidence and carries `review` and `original_value`. Table exports remain raw; `manual_corrections` is exported alongside them.
  - `correct` records a correction without a queue item. `review-stats` shows outcomes by table and method, which are not merged into calibration because reviewed items are a biased sample.
- **Charts.**
  - **One specification, two renderers.** A chart is a specification turned into drawing primitives once; the SVG renderer (reports, exports) and the Tk renderer (application) paint the same primitives, so the two agree.
  - **Honest encoding.** Confidence is shown by marker style (filled, hollow or dashed), restatements by a diamond and reviewed values by a square. Missing values leave gaps. An *as of* date is drawn as a rule. Lines are labelled by name, and the palette is Okabe–Ito, which is colour-blind safe.
  - **Provenance.** Hovering over a point shows its value, publication date, source, page, method and confidence. Clicking a point prints its full trace.
  - **Where charts appear.** "Show a company's figures", "Business segments", "R&D and workforce history" and "Show findings" open a chart window, from which charts can be saved as SVG or as a CSV of exactly the plotted data. `chart` exports from the command line. The HTML report now includes revenue and profit, segment and R&D charts.
  - **PNG.** PNG export needs the optional matplotlib renderer, available in source installations (`pip install matplotlib`). It is not in the Windows build, which keeps the download small. Elsewhere, open the SVG in a browser and save it as an image.
  - **Speed.** Ten thousand points render in about 0.05 seconds.
- **Traceability.** `trace` now covers segments, subsidiaries, R&D and workforce, ESG and officers. It also shows the dual-run note and any review decision.

v1.4 adds **live verification** and **measured parser accuracy** (build plan, section 18.4):

- **Self-test.** `self-test` (desktop: Check › Self-test) calls each public endpoint once, at the normal rate: the CNINFO stock lists, the announcement query for every category code, one document download, the SSE and SZSE list pages and the Eastmoney daily bars. Each check is PASS, WARN, FAIL (the site answered in an unexpected shape, so an adapter needs updating) or NETWORK_UNREACHABLE (no connection from this computer, which says nothing about the adapter). Results go to `selftest_report.json` and an HTML summary. `--offline` runs the same checks against built-in responses.
- **Golden corpus and evaluation.** `corpus-template` adds a report to a corpus with a draft of what the parsers read; you correct the draft against the report and mark it verified. `evaluate-parsers` then measures precision, recall and abstention for each parser and field: financial statements, segments, subsidiaries, R&D and workforce, officers, ESG, corporate actions and regulatory events.
- **Calibrated confidence.** With `--calibrate`, results are stored in `parser_calibration`. Extractors then use the lower bound of the 95% interval for each parser's measured precision, once at least 30 values have been checked, in place of the fixed constants. Text heuristics are capped at 0.9, so they never reach HIGH without a passed validation. Calibration is tied to the parser version, and is ignored after a parser changes until it is re-measured. Synthetic corpora are never used for calibration.
- **Regression gate.** `synthetic-corpus` generates report-like documents with known values (units of 元 and 万元, label variants, note references, wrapped labels, offshore entities). CI evaluates the parsers on it and fails if precision falls by more than one percentage point against `packaging/parser_baseline.json`.
- **Fixes found by the harness.**
  - The financial-statement parser took its unit from the first "万元" or "亿元" anywhere in the document, so a sentence such as "实现营业收入1,500亿元" or a pay table in 万元 could scale a statement in 元 by 10,000 or more. Units now come from the nearest preceding unit declaration (单位：…).
  - The R&D, segment and subsidiary parsers did not recognise "单位：人民币万元" or "金额单位：万元"; they now share one declaration rule, applied line by line.
- **Testable adapters.** Every HTTP client accepts an injected transport, so adapters are tested offline against `httpx.MockTransport`.

v1.3 completes the longer-term enrichment of section 12 with **R&D and human capital** and **ESG**:

- **R&D.** From the annual report's 研发投入 table, in both SZSE and SSE/STAR layouts: R&D staff and their share, R&D investment, expensed and capitalised R&D, R&D-to-revenue ratio and capitalised share.
- **Workforce.** From 员工情况: employees of the parent and principal subsidiaries, total employees, retirees whose costs the company bears, composition by function, and education.
- **Patents.** Narrative counts, and the STAR-market 知识产权列表 table.
- **Derived measures.** Computed and reported R&D intensity, capitalisation share, R&D-staff and technical-staff shares, postgraduate and degree shares, revenue per employee, and R&D investment per R&D employee. A history view runs across periods.
- **ESG disclosures.**
  - Whether the company is a key pollutant-discharge unit (重点排污单位).
  - Emissions of COD, ammonia nitrogen, SO₂, NOₓ and particulates; greenhouse-gas emissions and reductions; environmental investment.
  - Donations and rural-revitalisation spending.
  - Which years have a sustainability, CSR or ESG report (a new `sustainability_report` disclosure kind).
  - Third-party ESG ratings, imported from licensed data.
- **More regulators.** The regulatory layer now recognises environmental regulators (生态环境局), tax authorities, market regulators and emergency-management (safety) regulators as issuing authorities, so environmental penalties are identified as such.
- **ESG profile.** One view per fiscal year: disclosed E and S data, governance indicators (v1.1), regulatory actions (v0.9), audit opinions, sustainability reporting and ratings. **No composite ESG score is computed**, because any weighting would be a judgement rather than an observation.
- **New validation flags:** `RD_RATIO_INCONSISTENT`, `RD_COMPONENTS_MISMATCH`, `WORKFORCE_COMPOSITION_MISMATCH` and `EDUCATION_SUM_MISMATCH`.
- **Interface.** A Collect page "11 R&D, people & ESG", an Analyse page "People & ESG", new report sections, and checked year fields.

v1.2 continued section 12 of the build plan with **segments** and **group structure**:

- **Segment revenue.** Revenue by industry, product, region and sales model is read from the 营业收入构成 table of annual and interim reports. Cost and gross margin come from the segment-margin table. CSV import is also available.
- **Segment analysis.** Shares and growth, overseas revenue share (Hong Kong, Macau and Taiwan count as overseas, following the 境内/境外 presentation), revenue concentration (HHI and effective number of segments), and each segment's history across reports.
- **Subsidiaries and associates.** Read from 企业集团的构成 (direct and indirect stakes, principal and registered place, business nature, acquisition method) and 主要控股参股公司分析 (registered capital, total and net assets, revenue, net profit), or imported from CSV.
- **Jurisdiction classes.** Mainland, Hong Kong, Macau, Taiwan, offshore (Cayman, BVI, Bermuda, Samoa, Seychelles, Mauritius and similar centres used in red-chip and VIE structures), and foreign.
- **Group-structure analysis.** Counts by relationship and jurisdiction, wholly owned subsidiaries, offshore entities, and subsidiaries consolidated with 50% or less, listed for review because control may rest on agreements. Changes in the consolidation scope between two reports are also shown.
- **New validation flags:** `SEGMENT_SUM_MISMATCH`, `SUBSIDIARY_PCT_INVALID` and `CONSOLIDATED_WITH_MINORITY_STAKE`.
- **Report and desktop.** New report sections, a Collect page "10 Segments & group", and two new Analyse pages, "Business & group" and "Board & industry", which keep the Company page short.

v1.1 began the longer-term enrichment of section 12 of the build plan:

- **Industry classification over time.** CSRC 2012, Shenwan 2021 or any other scheme, imported from classification lists with English or Chinese headers. CSRC codes are checked against the 19 sections and their division ranges; Shenwan level-1 names against the 31 industries.
- **Industry analysis.** Point-in-time peer groups, industry statistics (median, quartiles, mean) for any metric or ratio, the company's percentile within its industry, and counts per industry.
- **Directors, supervisors and executives.**
  - Appointments, elections, resignations and dismissals are read from announcements. This includes resignations that take effect only once a successor is elected, and whether the person stays with the company.
  - The officer table of annual reports supplies roles, gender, age, tenure, shareholdings, pay and related-party pay.
  - Rosters can also be imported from CSV.
- **Governance variables.** Board size, independent directors and independence ratio, female directors, CEO duality, departures from key roles in the last 12 months, and total disclosed pay.
- **Screening checks** against the CSRC's 2023 independent-director rules: at least one third of the board, and no more than six consecutive years.
- **Integration.** Validation flags, company profile and report sections, and two new desktop pages (8 Industry, 9 Management), plus new cards on the Company page.

v1.0 completed the integrated company-intelligence layer (build plan, section 11):

- **Company profiles and timelines.** One view across all layers, optionally *as of* a past date, using only information published by then (no look-ahead bias).
- **Point-in-time financial series.** As originally reported or latest, with the number of vintages and restatement marks.
- **Cross-company comparison** with derived ratios, and **price statistics** (return, volatility, drawdown, liquidity) for one series at a time.
- **HTML company report.** Self-contained, prints to PDF.
- **Integrated validation (all five stages of section 7).** Cross-document checks for restatements, interim figures exceeding annual ones, ownership against capital, and changed distribution terms; cross-source conflicts; confidence classes HIGH / MEDIUM / LOW / UNVALIDATED. Findings go to `validation_flags`, and the data are never changed.
- **Event linking.** Investigation → prior notice → decision; filing → judgment; enquiry → response; suspension → resumption; distribution proposal → implementation. Each link records its basis, and heuristic links are labelled as such.
- **Tradable-share reconciliation** alongside total-share reconciliation.
- **Document search and inspection.** Full-text index of downloaded documents (trigram, so Chinese works), page view, and file-hash verification.
- **Audit trail.** `trace` follows any observation back to its document, page, raw text and method, and re-checks the file hash (build plan, section 6).
- **Reproducible research.** Read-only SQL queries, logged with a data fingerprint and output hash. **Dataset releases** contain CSVs, a SQLite snapshot (and optionally Parquet) and a hashed `manifest.json`.
- **A redesigned desktop application.** Sidebar sections in workflow order, a short explanation on every page and card, field hints, required-field and date checks, and a home page with a suggested first run.

## Desktop application (Windows)

### Ready-built programs

- `AShareScraper-2.0.4-setup.exe` installs both programs (desktop and command line) and the documentation for the current user. No administrator rights and no Python are needed.
- `AShareScraper-2.0.4-portable.zip` holds the same folder without the command line, and `ashare-cli-2.0.4-portable-addon.zip` adds `ashare-cli.exe` (unzip both into the same place; they share the `_internal` folder). Run `AShareScraper\AShareScraper.exe`. The portable copy is split only to keep each download under 30 MB; the installer contains both programs.

The build was produced with Windows CPython 3.12 and PyInstaller. It passed the full test suite on Windows Python, and both executables were exercised end to end before release. It is unsigned: Windows SmartScreen may show "Windows protected your PC", in which case choose **More info → Run anyway**. Some antivirus products are wary of unsigned PyInstaller programs; if yours quarantines it, rebuild it locally as below, or sign it (see `docs/developer_guide.md`).

### Building the .exe yourself

PyInstaller builds executables only for the operating system it runs on. On Windows:

1. Install Python 3.12 (64-bit) from python.org, ticking **Add python.exe to PATH**.
2. Unzip this project and double-click **`build_windows.bat`**. The script creates a private build environment, installs the dependencies, runs the test suite, and builds the app only if the tests pass.
3. The result is `dist\AShareScraper\`, a portable `AShareScraper-<version>-portable.zip` and, when NSIS is installed, the installer `AShareScraper-<version>-setup.exe`. Executables and installer are signed when `ASHARE_SIGN_CERT` is set. No Python is needed on the machine that runs the result.

Alternatively, push the project to GitHub and run the **build-windows** workflow (`.github/workflows/build-windows.yml`). The built app can then be downloaded as an artifact.

The executable is unsigned, so Windows SmartScreen may show "Windows protected your PC" the first time it runs. Choose **More info → Run anyway**. `build_unix.sh` builds the equivalent for macOS or Linux.

### Using it

- **No command line is needed.** Each tab (Universe, Disclosures, Financials, Market, Ownership, Corporate actions, Regulatory, Export) offers the pipeline steps as forms with a **Run** button. Output appears in the lower pane.
- **Data folder.** The default is `Documents\AShareScraper`; change it with **Change…**. The folder holds `ashares.db` and the raw archives (`raw\`, `disclosures\`, `market_raw\`), and exports go to `exports\` inside it.
- **Reproducibility.** Every GUI run is appended to `run_log.txt` in the data folder, with its timestamp, version, exact equivalent command and output, so any dataset produced through the GUI can be regenerated from the command line.
- **Same engine as the CLI.** The GUI builds the same arguments as the CLI and runs them through it, so the two cannot diverge. A test checks that every GUI form is a valid CLI call.
- **Command line.** `ashare-cli.exe` in the same folder accepts every command below, for example `ashare-cli.exe regulatory-status 600519`.

## Installation

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt     # runtime: requirements.txt
python -m ashare.cli init-db
python -m pytest -q
python -m ashare.app                    # desktop interface
```

`init-db` is safe to run on any older database (v0.7 onwards): it upgrades it with the Alembic migrations, after saving a backup copy of a SQLite file.

## Pipeline

```bash
# Universe
python -m ashare.cli update-universe
python -m ashare.cli validate-universe

# Disclosures (CNINFO)
python -m ashare.cli catalogue-disclosures --since 2025-01-01 --until 2026-10-08 \
  --kind reports --download-documents
python -m ashare.cli catalogue-disclosures --since 2025-01-01 --until 2026-10-08 \
  --kind corporate_actions --download-documents

# Financials
python -m ashare.cli extract-financials --security-code 600519
python -m ashare.cli validate-financials --security-code 600519
python -m ashare.cli show-financials 600519 --metric revenue

# Market
python -m ashare.cli acquire-market --security-code 600519 --start 2026-01-01 --end 2026-10-08
python -m ashare.cli import-market-csv prices.csv --source LICENSED_VENDOR

# Ownership and capital
python -m ashare.cli import-ownership-csv ownership.csv --source LICENSED_VENDOR
python -m ashare.cli import-capital-csv capital.csv --source LICENSED_VENDOR
python -m ashare.cli validate-ownership --security-code 600519

# Corporate actions (v0.8)
python -m ashare.cli extract-corporate-actions --security-code 600519
python -m ashare.cli import-corporate-actions-csv actions.csv --source LICENSED_VENDOR
python -m ashare.cli show-actions 600519
python -m ashare.cli reconcile-capital --security-code 600519

# Regulatory and legal events (v0.9)
python -m ashare.cli catalogue-disclosures --since 2024-01-01 --until 2026-10-08 \
  --kind all --download-documents
python -m ashare.cli extract-regulatory-events --security-code 600519
python -m ashare.cli import-regulatory-document decision.pdf --security-code 600519
python -m ashare.cli show-events 600519
python -m ashare.cli regulatory-status 600519 --as-of 2026-06-30

# R&D, human capital and ESG (v1.3)
python -m ashare.cli extract-human-capital --security-code 600519
python -m ashare.cli human-capital 600519
python -m ashare.cli human-capital-history 600519
python -m ashare.cli extract-esg --security-code 600519
python -m ashare.cli import-esg-ratings-csv ratings.csv --source VENDOR
python -m ashare.cli esg 600519 --year 2025
python -m ashare.cli human-capital-items && python -m ashare.cli esg-items   # item codes for CSV import

# Segments and group structure (v1.2)
python -m ashare.cli extract-segments --security-code 600519
python -m ashare.cli segments 600519 --dimension REGION
python -m ashare.cli segment-history 600519 --dimension PRODUCT
python -m ashare.cli extract-subsidiaries --security-code 600519
python -m ashare.cli subsidiaries 600519
python -m ashare.cli scope-changes 600519 --from 2024-12-31 --to 2025-12-31

# Industry and management (v1.1)
python -m ashare.cli import-industry-csv csrc_2026q2.csv --scheme CSRC_2012 --source CSRC --effective-date 2026-06-30
python -m ashare.cli show-industry 600519
python -m ashare.cli peers 600519 --scheme CSRC_2012 --level 2
python -m ashare.cli industry-stats 600519 --metric net_margin --min-class MEDIUM
python -m ashare.cli industry-summary --level 1
python -m ashare.cli extract-management --security-code 600519
python -m ashare.cli roster 600519 --as-of 2026-06-30
python -m ashare.cli show-management-events 600519
python -m ashare.cli governance 600519

# Integrated intelligence (v1.0)
python -m ashare.cli validate-all                       # links events, runs every check
python -m ashare.cli show-flags --severity WARN
python -m ashare.cli profile 600519 --as-of 2025-12-31
python -m ashare.cli financial-series 600519 --metric revenue --vintage original
python -m ashare.cli compare --codes 600519,000858 --metrics revenue,net_profit,total_assets
python -m ashare.cli timeline 600519
python -m ashare.cli market-stats 600519 --start 2026-01-01
python -m ashare.cli report 600519                      # reports/600519.html

# Research tools (v1.0)
python -m ashare.cli index-documents
python -m ashare.cli search-documents 资金占用
python -m ashare.cli inspect-document 42 --page 3
python -m ashare.cli trace financial_facts 1234
python -m ashare.cli query "SELECT metric, COUNT(*) FROM financial_facts GROUP BY metric" --out exports/q.csv
python -m ashare.cli release --formats csv,sqlite

# Export
python -m ashare.cli export all --out-dir exports
python -m ashare.cli export regulatory_events --security-code 600519
```

## v1.3 R&D, human capital and ESG

### R&D and workforce

Values are stored as (category, item, value). The categories are RD, WORKFORCE, EDUCATION and PATENT; `human-capital-items` lists the item codes. Percentages are stored as fractions, money in yuan, and people and patents as counts. Each value keeps its label, page and raw line.

**Parser safeguards.** In the R&D table, only a bracketed unit may sit between a label and its value. A narrative sentence such as "研发投入金额同比增长11%" is therefore not read as the R&D amount.

**Checks.**
- `RD_RATIO_INCONSISTENT`: the reported R&D ratio differs by more than 0.5 percentage points from R&D investment divided by revenue.
- `RD_COMPONENTS_MISMATCH`: expensed plus capitalised R&D does not equal total R&D.
- `WORKFORCE_COMPOSITION_MISMATCH` and `EDUCATION_SUM_MISMATCH`: the categories do not sum to total employees (tolerance 0.1%).

**Research note.** A high capitalised share of R&D is a widely studied indicator of discretion over reported earnings. It is reported as a variable, not flagged.

### ESG

| Pillar | Items |
|---|---|
| E | key pollutant-discharge unit (yes/no), COD, ammonia nitrogen, SO₂, NOₓ, particulates (tonnes), greenhouse-gas emissions and reductions (tCO₂e), environmental investment, environmental regulatory actions |
| S | donations, rural revitalisation, employees and R&D-staff share (v1.3), female directors (v1.1), tax / market-regulation / safety regulatory actions |
| G | board size, independence, CEO duality (v1.1), securities regulatory actions, non-standard audit opinions (v0.9) |
| Reporting | sustainability/CSR/ESG report published for the year |
| Ratings | latest rating per provider, as imported (the provider's own scale) |

**Sources.** Data points are read from annual reports and from sustainability reports that have been downloaded. Point-in-time views use publication dates.

**Mandatory reporting.** The exchanges' 2024 self-regulatory guidelines on sustainability reporting require certain index constituents and dual-listed companies to publish sustainability reports, starting with the 2025 reporting year; other companies may report voluntarily. The absence of a report is therefore shown as "not observed", not as a breach. Check the current scope of the guidelines before relying on mandatory status.

## v1.2 segments and group structure

### Segments

**Dimensions.** `INDUSTRY` (分行业), `PRODUCT` (分产品), `REGION` (分地区), `SALES_MODEL` (分销售模式 / 分渠道) and `REPORTABLE_SEGMENT` (分部). The table's own total row (营业收入合计) is stored as `TOTAL`.

**Parsing.**
- For each row the parser reads the name, amount, share, prior-year amount and growth from the composition table, and revenue, cost and gross margin from the margin table.
- The two tables are merged per segment.
- Units follow the table's 单位 line (元, 千元, 万元, 百万元 or 亿元).
- Rows keep their page and raw text, at confidence 0.55.

**Point in time.** Segments are dated by publication of the source report, so `--as-of` excludes reports not yet published.

**Measures.**

| Measure | Definition |
|---|---|
| share | segment revenue ÷ the table total (or the segment sum if there is no total) |
| HHI | Σ share², from about 1/n (even) up to 1 (single segment) |
| effective segments | 1 ÷ HHI |
| overseas share | revenue of segments classed OVERSEAS ÷ total; the share that could not be classified is reported separately |

**Validation.** `SEGMENT_SUM_MISMATCH` (WARN) is raised when a dimension's segments differ from the reported total by more than 1%. Typical causes are an "other" line that was not parsed, intersegment eliminations, or a parsing miss.

### Group structure

**What is parsed from 企业集团的构成:** name, principal place, registered place, business nature, direct and indirect stakes (a dash means none), and acquisition method. The acquisition methods are:
- established (设立);
- business combination under common control (同一控制下企业合并);
- business combination not under common control (非同一控制下企业合并);
- other.

**What is parsed from 主要控股参股公司分析:** relationship (子公司 = subsidiary, 参股公司 = associate), registered capital, total assets, net assets, revenue and net profit, scaled by the table's unit. Records are merged by entity name.

**Jurisdiction classes:**

| Class | Examples |
|---|---|
| `MAINLAND` | provinces, major cities, or a name ending in 省/市/县/自治区 |
| `HONG_KONG`, `MACAU`, `TAIWAN` | 香港, Macau, 台湾 |
| `OFFSHORE` | Cayman, British Virgin Islands, Bermuda, Samoa, Seychelles, Mauritius, Jersey, Guernsey, Isle of Man, Labuan, Bahamas, Panama |
| `FOREIGN` | other named countries and regions |
| `UNKNOWN` | not recognised; never guessed |

**Analysis.**
- `subsidiaries` summarises the structure at a reporting date.
- `scope-changes` compares two dates and lists entities added, removed, or with a changed stake or status. Entities are matched by exact name, so a renamed subsidiary appears as one removed and one added.
- `CONSOLIDATED_WITH_MINORITY_STAKE` (INFO) lists subsidiaries consolidated with a total stake below 50%. Under the consolidation standard (CAS 33), control rather than shareholding decides consolidation. Such cases often rest on agreements (VIE), board control or acting-in-concert arrangements, and deserve a look.

## v1.1 industry and management

### Industry classification

| Scheme | Content | Validation on import |
|---|---|---|
| `CSRC_2012` | 上市公司行业分类指引 (2012): 19 sections A–S, 90 divisions 01–90 | Section letter; division within that section's range (e.g. C = 13–43) |
| `SW_2021` | Shenwan Hongyuan 2021: 31 level-1 industries | Level-1 name in the 2021 list |
| `CNINFO`, `CSRC_OTHER`, `CUSTOM` | Any other scheme | None |

Notes:

- **Point in time.** Classifications are observations with an effective date, so peer groups follow reclassifications.
- **Accepted headers.** Imports accept English or Chinese headers (证券代码, 门类代码, 大类代码, 大类名称, 一级行业, 行业代码 …). A code such as `C-15` or `C15` yields section C (制造业) automatically.
- **Invalid codes** are stored with `FAILED_CODE_CHECK` and flagged `INDUSTRY_CODE_INVALID`. Where two sources disagree for the same scheme and date, the result is `INDUSTRY_SOURCE_CONFLICT`.
- **Sources.** The tool does not download classification lists, because no stable public endpoint has been verified. The CSRC publishes its classification results periodically, and Shenwan data are licensed. Import the file you obtain.

`industry-stats` returns the minimum, quartiles, median, mean and maximum of a metric across peers, as known at `--as-of`. It also gives the company's percentile (share of peers below it, ties counting half). Ratios available: `net_margin`, `roa`, `roe`, `liabilities_to_assets` and `rd_intensity`. `--min-class` excludes peer values below a confidence class, and the number excluded is reported.

### Management

**Roles.** These are normalised:

- **Board:** chair, vice-chair, director, independent director, employee director.
- **Supervisory board:** chair, supervisor, employee supervisor.
- **Executives:** general manager, deputy GM, CFO, board secretary, chief engineer, other executive.

One person can hold several roles; "董事长兼总经理" gives two rows.

**Events from announcements.** Each announcement yields events of type appointment, election, board renewal, resignation, dismissal, death, or unable to perform duties.

- The person's name is read from the text before 先生/女士, and the role from the surrounding clause.
- **Effective date.** A resignation that would take the board below its legal minimum, or the independent directors below one third, takes effect only when a successor is elected. Such resignations are stored with no effective date and listed as pending.
- **Other details:** the reason category (personal, work arrangement, retirement, term expiry, health, regulatory ineligibility), and whether the person remains with the company.

**Annual-report officer tables.** These are read heuristically, one row per person (confidence 0.5). The parser takes name, roles, gender, age, status, tenure start and end, shareholdings, pay before tax (converted from 万元 where the table says so) and related-party pay. Layouts vary between companies; where the parser misses rows, import the table from CSV.

**Roster on a date.** `roster` starts from the latest officer table on or before the date, then applies later announcements. Every entry states its basis.

**Governance checks.** `governance` reports the research variables listed above and three screening checks:

- independent directors at least one third of the board (上市公司独立董事管理办法, CSRC 2023);
- no independent director serving more than six consecutive years (same instrument);
- a board secretary in office.

These checks are screening aids, not legal conclusions. Under the Company Law as revised with effect from 1 July 2024, a company may use an audit committee of the board in place of a supervisory board, so the absence of supervisors is not itself treated as a defect.

New validation flags: `INDUSTRY_CODE_INVALID`, `INDUSTRY_SOURCE_CONFLICT`, `TENURE_END_BEFORE_START`, `SERVING_AFTER_DEPARTURE` (a person still listed in a later roster after an effective departure, with no reappointment), `INDEPENDENT_DIRECTORS_BELOW_ONE_THIRD` and `INDEPENDENT_DIRECTOR_TENURE_OVER_SIX_YEARS`.

**Personal data.** Names, gender, age and pay of directors and officers are publicly disclosed under mandatory rules. They are stored only as disclosed, for research. Handle exports with the care appropriate to personal information.

## v1.0 integrated intelligence

### Point in time

Each information type is admitted on the date it became known:

| Information | Date used for `--as-of` |
|---|---|
| Financial facts | Announcement date of the source document |
| Corporate actions | Capital-effective date (ex or listing date), else announcement date |
| Regulatory events | Event date (receipt, decision or signature), else announcement date |
| Market bars | Trading date |
| Ownership and capital | Observation date (the only date those sources carry; note that a register dated 30 June is typically published weeks later) |

`financial-series --vintage original` gives values as first reported. `latest` (the default) gives the most recently published value known at `as_of`, including restated comparatives. From v1.0, the XBRL extractor keeps the comparatives each report discloses (prior-year period; prior year-end for balance sheets), which is what makes restatements detectable. The PDF heuristic still reads current-period values only.

### Validation flags

| Rule | Severity | Meaning |
|---|---|---|
| `MISSING_PROVENANCE` | ERROR | A fact with no source document |
| `RESTATEMENT_OR_DISCREPANCY` | WARN | Two XBRL vintages of one figure differ by more than 0.5% |
| `RESTATEMENT_EXPLAINED` | INFO | As above, with a 会计差错更正 announcement between the two |
| `EXTRACTION_DISCREPANCY` | WARN | As above where at least one value is PDF-heuristic |
| `INTERIM_EXCEEDS_ANNUAL` | WARN | A cumulative H1 or Q3 flow figure exceeds the annual figure |
| `OWNERSHIP_PCT_INCONSISTENT` | WARN | Reported % differs from shares ÷ total shares by more than 0.05pp |
| `DISTRIBUTION_TERMS_CHANGED` | INFO | Per-share terms changed between proposal and implementation (often a legitimate re-basing) |
| `MARKET_BAR_INCONSISTENT` | ERROR | High below low, close outside the range, or negative volume |
| `CROSS_SOURCE_PRICE_CONFLICT`, `CROSS_SOURCE_CAPITAL_CONFLICT` | WARN | Sources disagree on the same observation |

Confidence classes: **HIGH** (native XBRL, or confidence ≥ 0.85 with a passed check), **MEDIUM** (≥ 0.6, or passed), **LOW** (below 0.6, or any failed check), **UNVALIDATED** (no confidence recorded).

### Tradable shares

When both capital observations report tradable shares, reconciliation also rolls tradable shares forward and reports a separate `tradable_status`. It assumes:

- public offerings, rights issues and conversions are tradable on issue;
- placements, share-for-asset issues and incentive grants are locked up until an unlock announcement;
- bonus and capitalisation shares accrue pro rata;
- cancellations of repurchased incentive shares reduce restricted shares, and other cancellations reduce tradable shares.

Each assumption used is written into the result notes.

### Reproducibility

Every `query` and `release` is logged in `research_queries` with:

- the query text and its SHA-256;
- a fingerprint of the database (table row counts and maximum ids);
- the row count;
- the output path and its SHA-256;
- the software version.

Queries run on a read-only connection, so they cannot alter data whatever they contain. Every desktop action is also appended to `run_log.txt` with the equivalent command.

## v0.9 regulatory and legal events

### Instrument versus stage

Each event records two things separately:

- **The legal character of the instrument** (`legal_classification`), taken from the document itself. A warning letter (警示函) is an `ADMINISTRATIVE_SUPERVISORY_MEASURE`, not an `ADMINISTRATIVE_PENALTY`. Exchange 纪律处分 is `SELF_REGULATORY_DISCIPLINARY`, as distinct from a 监管函 (`SELF_REGULATORY_MEASURE`) or a 问询函 (`SELF_REGULATORY_ENQUIRY`).
- **The procedural stage** (`status`). An investigation (立案, `INITIATED`), a prior notice of penalty (事先告知书, `PRIOR_NOTICE`) and a penalty decision (`DECIDED`) are three separate events.

| Event type | Legal classification | Typical source |
|---|---|---|
| `CSRC_INVESTIGATION` | `ADMINISTRATIVE_INVESTIGATION` | 立案告知书 |
| `CRIMINAL_INVESTIGATION` | `CRIMINAL` | 公安机关立案, 移送公安 |
| `ADMINISTRATIVE_PENALTY` | `ADMINISTRATIVE_PENALTY` | 行政处罚事先告知书, 行政处罚决定书 |
| `SUPERVISORY_MEASURE` | `ADMINISTRATIVE_SUPERVISORY_MEASURE` | 警示函, 责令改正, 监管谈话 |
| `EXCHANGE_DISCIPLINARY` | `SELF_REGULATORY_DISCIPLINARY` | 纪律处分, 公开谴责, 通报批评 |
| `EXCHANGE_REGULATORY_MEASURE` | `SELF_REGULATORY_MEASURE` | 监管函, 监管警示 |
| `REGULATORY_ENQUIRY` | `SELF_REGULATORY_ENQUIRY` | 问询函, 关注函, 监管工作函 (`RECEIVED` / `RESPONDED`) |
| `LITIGATION`, `ARBITRATION` | `CIVIL_LITIGATION`, `ARBITRATION` | 诉讼, 仲裁 (filed, judgment/award, appeal, settled, withdrawn, enforcement) |
| `AUDIT_OPINION` | `AUDIT_OPINION` | 审计报告; 非标准审计意见专项说明 (qualified, adverse, disclaimer, emphasis of matter) |
| `ACCOUNTING_RESTATEMENT` | `ACCOUNTING_IRREGULARITY` | 会计差错更正, 追溯调整 |
| `DELISTING_RISK` | `LISTING_STATUS` | *ST, ST, lifting, possible delisting, termination of listing |
| `TRADING_SUSPENSION` | `TRADING_STATUS` | 停牌 / 复牌, with the reason (planned corporate event, abnormal trading, listing status) |

The plan's "disclosure violations" and "accounting irregularities" are recorded as **violation categories** on the events that establish them (`FALSE_RECORDS`, `MISLEADING_STATEMENTS`, `MATERIAL_OMISSION`, `LATE_OR_NON_DISCLOSURE`, `FINANCIAL_FRAUD`, `ILLEGAL_GUARANTEE`, `FUND_OCCUPATION`, `INSIDER_TRADING`, `MARKET_MANIPULATION` and others). This avoids treating an allegation in an investigation notice as a finding.

### What is extracted from the documents

- **Issuing authority.** The CSRC, a local bureau (e.g. 浙江证监局), SSE, SZSE, a named court, an arbitral body, the police, or the auditor.
- **Reference numbers.** The document number (e.g. 〔2026〕88号, 沪证监决〔2026〕12号) and the court case number (e.g. (2026)京01民初1234号).
- **Event date.** The date of receipt, the start of a suspension, or the signature date of a regulator's decision.
- **Cited provisions.** Normalised as instrument, article and paragraph, so `《证券法》第一百九十七条第二款` is stored as Securities Law, article 197, paragraph 2. Chinese numerals are converted.
- **Sanctions by party.** Warning, order to rectify, fine, confiscation, and market ban (number of years or life), parsed clause by clause so that fines are not attributed to the wrong party. Total fines and fines on the company are stored separately.
- **Litigation and arbitration.** The amount in dispute and the company's role (plaintiff, defendant, applicant, respondent or third party).
- **Audit opinion type.** A 保留意见 that is part of a 无保留意见 is not counted as a qualified opinion.

### Sources

1. **Regulator documents** (`import-regulatory-document`). A CSRC or exchange decision you have downloaded, or its URL. The document is archived and hashed. The company is identified from the given code, a code in the text, or the full legal name, and the method used is reported. No regulator website is crawled and no endpoint is guessed.
2. **Company announcements on CNINFO** (`extract-regulatory-events`). These must first be catalogued with `--kind all`, because penalties and litigation are filed under several CNINFO categories.
3. **Authorised structured data** (`import-regulatory-csv`).

### Point-in-time status

`regulatory-status CODE --as-of DATE` uses only events dated on or before that date. It reports:

- listing status (ST, *ST or lifted) and trading status;
- investigations, each marked either `POSSIBLY_OPEN` or `FOLLOWED_BY_DECISION_OR_CLOSURE`;
- penalties with their fines;
- events establishing disclosure violations;
- non-standard audit opinions;
- litigation with no closing-stage announcement recorded.

Every derived state cites the event IDs it rests on. "Possibly open" is deliberately not "open": the system cannot know about events it has not observed.

## v0.8 corporate actions

### Coverage

`corporate_actions` covers these action types: `CASH_DIVIDEND`, `BONUS_SHARES` (送股), `CAPITALISATION_ISSUE` (资本公积转增), `RIGHTS_ISSUE`, `PRIVATE_PLACEMENT`, `PUBLIC_OFFERING`, `SHARE_ISSUANCE` (including share-for-asset issues and equity-incentive grants), `SHARE_BUYBACK`, `SHARE_CANCELLATION`, `STOCK_SPLIT`, `SHARE_CONSOLIDATION`, `CONVERTIBLE_CONVERSION`, `WARRANT_CONVERSION`, `RESTRICTED_SHARE_UNLOCK` and `OTHER_CAPITAL_CHANGE`.

Each observation records:

- its lifecycle status: `PROPOSED`, `APPROVED`, `IMPLEMENTATION_ANNOUNCED`, `IN_PROGRESS`, `COMPLETED`, `TERMINATED` or `ANNOUNCED`;
- announcement, record, ex, payment, listing and effective dates;
- base, old and new share counts, the share delta and the shares affected;
- the ratio, cash per share (pre-tax), total cash, and subscription or issue price;
- the source document and page, the matched text excerpt (`raw_value`), the normalised fields as JSON (`normalised_value`), the extraction method, confidence and validation status.

### Conventions

- `ratio`: for bonus, capitalisation and rights issues, this is new shares per existing share (每10股转增4股 gives 0.4). For splits and consolidations, it is post-event shares per pre-event share.
- `cash_amount`: cash per share, pre-tax where the document says 含税.
- `share_delta`: the change in issued (total) share capital. A buyback leaves issued capital unchanged until the shares are cancelled. Its count is stored in `shares_affected` and its `share_delta` is 0.
- A proposal does not carry a `share_delta`, because it has not yet changed capital.

### Extraction

`extract-corporate-actions` works through the disclosures that have already been catalogued:

1. It classifies each title into candidate action types and a lifecycle status. Periodic reports, enquiry letters, meeting resolutions, dividend policies and nil-distribution notices are excluded.
2. It parses the downloaded document (`DOCUMENT_TEXT_REGEX`, confidence 0.6 to 0.7). If there is no document, it parses the title (`TITLE_REGEX`).
3. If no quantities are found, it stores a `TITLE_ONLY` observation (confidence 0.3). This keeps the event visible and makes the gap explicit.

The parser recognises standard PRC disclosure phrasing, including 以总股本X股为基数, 每10股派X元(含税), 每10股送/转增X股, 总股本由X股变更为Y股, 配股价格, 发行数量/发行价格, 累计回购股份, 注销股份 and 转股数量. It reads dates from both "label: date" text and SSE/SZSE date tables. Dash placeholders, such as "－" for 最后交易日, keep the table columns aligned.

### Reconciliation

`reconcile-capital` checks the following for each pair of consecutive capital observations from the same source:

```text
total_shares(t0) + eligible actions in (t0, t1] = total_shares(t1)
```

The rules are:

- Only `IMPLEMENTATION_ANNOUNCED` and `COMPLETED` actions are counted.
- Ratio actions take effect on their listing or ex date. Conversions take effect at the end of the conversion period. Other actions take effect on their effective, listing or announcement date.
- If the same event appears in several disclosures (for example a 发行情况报告书 and a 上市公告书), the duplicates are merged. Each merge is noted.
- Buybacks are reported in the notes but do not change issued capital.
- Each window gets one result: `RECONCILED`, `UNEXPLAINED_DIFFERENCE` or `INSUFFICIENT_DATA`. The residual, tolerance, action IDs and notes are stored in `capital_reconciliations`.
- Observed values are never altered. Only `validation_status` is updated on the actions involved.
- Issuances and cancellations whose disclosed before and after totals contradict their stated share change are flagged `FAILED_INTERNAL_SHARE_COUNT`.

### CSV import for licensed data

Required columns: `security_code` and `action_type`. Recommended columns: `action_id` (the vendor's key), `status`, `announcement_date`, `ex_date`, `listing_date`, `effective_date`, `ratio`, `share_delta`, `shares_affected`, `cash_amount`, `issue_price`, `source_document`, `source_page` and `confidence`. Set `status` explicitly: an action imported with the default `ANNOUNCED` status is not counted in reconciliation.

## Corrections to v0.7 (v0.7.1)

| # | Defect in v0.7 | Effect | Fix |
|---|---|---|---|
| 1 | `SessionLocal()` returned a `sessionmaker`, not a session | Every database write and read crashed (universe, disclosures, financials, market, ownership) | It now returns a session from a cached engine |
| 2 | `CNInfoDisclosureAdapter` called `RateLimitedClient()` without a user agent | Disclosure cataloguing failed at start-up | The configured user agent and rate are passed |
| 3 | `extract-financials` filtered on kinds (`annual`, `interim`…) that the classifier never produces | No periodic report was ever extracted | It filters on `annual_report`, `interim_report` and `quarterly_report` |
| 4 | Reporting period read from title and body together | An annual report containing a 第一季度 breakdown was dated 03-31; the annual fallback year was the announcement year | The title decides, and the fallback uses the prior year for annual reports |
| 5 | XBRL contexts, `scale` and `sign` were ignored | Prior-year comparatives could overwrite current values; amounts in 万 were understated 10,000-fold; negative values lost their sign | Contexts are parsed, the current year-to-date default scope is selected, dimensional scopes are kept separately, and scale and sign are applied |
| 6 | PDF labels matched inside longer labels; years and note references were captured as values | 净利润 picked up 归属于母公司…净利润; values such as "2025" or "61" were stored | Labels must stand alone, dates and percentages are excluded, formatted amounts are preferred, and the matched label is stored |
| 7 | The employee count was multiplied by the currency unit | Headcount was inflated by up to 10^8 | No longer scaled |
| 8 | Balance-sheet validation grouped facts across documents | Facts from different reports were mixed | Grouped per document and method |
| 9 | Ownership: 万股/亿股 suffixes were stripped without scaling; missing flags were recorded as False; 股东大会 notices were classed as shareholder disclosures | Share counts understated; unknown control status recorded as "no"; false positives | Values scaled; flags tri-state; meeting notices excluded; dates normalised |
| 10 | Configuration paths were fixed at import time | `ASHARE_DB` overrides were ignored, so tests could not isolate databases | Paths are resolved at call time |
| 11 | Tests covered pure helpers only | Defects 1 to 3 passed the suite | 39 tests, including database-level integration tests on temporary databases |
| 12 | Minor: version strings (`0.3.0`, README v0.6); Eastmoney volume unit undocumented; market raw payloads absent from `raw_records`; `datetime.utcnow` deprecated | Provenance and consistency gaps | All corrected; `volume_unit` added |

The CNINFO category `category_yjdbg_szsh` is the first-quarter report. The v0.7 key `quarterly_preview` was a misnomer and is kept only as an alias of `q1`.

## Live-source status

The build environment cannot reach CNINFO, SSE, SZSE or Eastmoney: its egress proxy refuses the connection, and the v1.4 self-test run there reports NETWORK_UNREACHABLE for every check. **No live integration test has been run for this release.** All tests use offline fixtures. On your own computer, run **Check › Self-test** (or `ashare-cli self-test`) first; it confirms points 1 to 3 below automatically. Before relying on the data, the first local run should confirm:

1. `update-universe` returns about 5,000 records across the four boards.
2. `catalogue-disclosures --kind corporate_actions` returns announcements. The corporate-action CNINFO category codes added in v0.8 (`category_qyfpxzcs_szsh`, `category_zf_szsh`, `category_pg_szsh`, `category_kzzq_szsh`, `category_gqjl_szsh`, `category_jj_szsh`, `category_gqbd_szsh`) follow CNINFO's announcement-category filter but are unverified against the live endpoint. If any returns nothing, use `--kind all`, which catalogues everything; `extract-corporate-actions` classifies by title regardless of category.
3. The v0.9 `regulatory` category codes (`category_fxts_szsh`, `category_tbclts_szsh`, `category_tszlq_szsh`, `category_cqdq_szsh`) are likewise unverified. For full coverage, use `--kind all` in any case.
4. `extract-corporate-actions` on a known distribution, such as 600519's 2025 annual distribution, reproduces the per-share cash amount, record date and ex date.
5. `extract-regulatory-events` on a company with a known CSRC penalty reproduces the document number, the fines and the cited provisions.

The collector does not attempt to defeat CAPTCHAs, authentication, access controls or rate limits.

## Database

v1.3 adds `human_capital_observations`, `esg_observations` and `esg_ratings`. v1.2 added `segment_observations`, `subsidiary_observations`, `human_capital_observations`, `esg_observations` and `esg_ratings`. v1.1 added `industry_classifications`, `management_events`, `management_observations`, `segment_observations` and `subsidiary_observations`. v1.0 added `validation_flags`, `document_pages` (with the `document_fts` full-text index) and `research_queries`. Full list: `companies`, `securities`, `sources`, `raw_records`, `disclosures`, `financial_facts`, `market_bars`, `market_snapshots`, `ownership_observations`, `capital_structure_observations`, `corporate_actions`, `capital_reconciliations`, `regulatory_events`, `validation_flags`, `document_pages`, `research_queries`, `industry_classifications`, `management_events` and `management_observations`.

## Known limitations

- PDF text extraction is heuristic. Multi-column tables, scanned documents and line-wrapped labels can defeat it. Native XBRL should be preferred where available.
- Corporate-action parsing covers standard phrasing. Unusual drafting yields `TITLE_ONLY` records, which reconciliation reports as `INSUFFICIENT_DATA` rather than guessing.
- Reconciliation covers total issued shares only. Tradable-share reconciliation (unlocks against restricted shares) is not yet implemented.
- Distribution schemes with differentiated treatment (差异化分红) are captured through the disclosed base share count. Where the base is absent, the ratio is applied to the rolled-forward total, and a note records this assumption.
- `market_snapshots` is defined but not yet populated by any adapter.
- Event links without an explicit identifier (such as a case number) are chronological heuristics and are labelled as such in `link_basis`.
- Patents are counts as disclosed by the company; no patent-office data are linked.
- ESG extraction covers the common Chinese phrasings for each item. Tabular emission data in sustainability reports, and units such as kg/year, may need CSV import.
- The segment and subsidiary tables are parsed heuristically. Layouts vary, and multi-line cells (long entity names or business descriptions wrapped over two lines) can be missed. Use CSV import where the parser falls short.
- Persons are identified by name within one company. The same name at two companies is not linked, and two people with the same name at one company cannot be told apart.
- Sanction parsing assumes the standard 对X…；对Y… drafting of CSRC and exchange decisions. Decisions drafted otherwise keep their text excerpt but may lack per-party sanctions.

## Changes in v0.9 beyond the regulatory layer

- **Timezone.** Announcement timestamps are converted with a fixed UTC+8 offset instead of `zoneinfo`, which needs the separate `tzdata` package on Windows. Without this change, disclosure cataloguing would have failed in the Windows build.
- **Requirements.** `pandas` and `pydantic` were listed but never used, and have been removed. Development requirements are now in `requirements-dev.txt`.
- **Error messages.** The command line now prints a one-line error, for example on a network failure, instead of a traceback. Set `ASHARE_DEBUG=1` for the full traceback.

## Disclaimer

A-share Company Intelligence is research software, provided as is and without warranty of any kind (see the licence). In particular:

- **No affiliation.** The program is independent. It is not affiliated with, endorsed by or supported by CNINFO, the Shanghai, Shenzhen or Beijing stock exchanges, the China Securities Regulatory Commission, Eastmoney or any other source it reads.
- **Accuracy.** Collected and extracted data may be incomplete, out of date or wrong: sources change without notice, and automated extraction from PDF documents makes mistakes. Verify any figure that matters against the original disclosure before relying on it.
- **Not advice.** Nothing produced by the program is investment, financial or legal advice. The compliance note (`docs/compliance.md`) explains the design choices; it is not legal advice either.
- **Responsibility of the person running it.** Whoever runs the program is responsible for complying with the sources' terms of use and with the law that applies to them, including data-protection law for the personal information that listed-company disclosures contain, and for any dataset they build or share.

## Licence

A-share Company Intelligence is licensed under the **PolyForm Strict License 1.0.0** (`LICENSE.md`); copyright Leong, Wen Yi. In short, and subject to the full terms:

- you may use the software for any **noncommercial** purpose, including personal research and study, and use by educational institutions, public research organisations and other noncommercial organisations;
- you may **not distribute** the software or **make changes or new works** based on it;
- it comes **without any warranty**.

For uses these terms do not permit, contact the licensor. The licence covers the software only; datasets you build with it are subject to the licences of their sources, as described under licence-aware releases.

## Third-party components

The Windows downloads bundle third-party components: the Python runtime (with the software it incorporates, such as OpenSSL, SQLite, expat and zlib), Tcl/Tk, PyInstaller's bootloader, and libraries including pypdf, pypdfium2 with PDFium, SQLAlchemy, Alembic, httpx, lxml, Beautiful Soup, Typer and Rich. **Bundled components keep their own licences.** The PolyForm Strict licence of this program does not apply to them, and nothing in it changes the terms on which they are licensed.

Every download includes `THIRD_PARTY_NOTICES.txt`, which lists each bundled component with its version, and reproduces its licence text and copyright notices in full. The file is generated during each build by `packaging/third_party_notices.py`, from PyInstaller's own record of what was bundled. The build stops if any component lacks a licence text, so a download never ships with a notice missing. The source code of each component is available from its home page or from the Python Package Index; the notices give the details.

## Acknowledgements

The software was designed and directed by Wen Yi Leong. Its code, tests and documentation were written with Claude (Anthropic), an AI assistant, working to the author's build plan and the findings of the author's live runs. Commits are made in the author's name; this section is the record of Claude's contribution.
