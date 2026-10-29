# User guide

A-share Company Intelligence collects, checks and organises public information about companies listed in mainland China (SSE Main Board, STAR Market, SZSE Main Board and ChiNext; the Beijing Stock Exchange and B shares can be switched on). Every value it stores keeps the document it came from, how it was read and how far it has been checked, so that a dataset built with it can be traced back to its sources.

This guide covers the desktop application and the command line. The [methods document](methods.md) explains how the data are produced; the [codebook](codebook.md) defines every panel variable.

## 1. Installing

### Windows installer

Run `AShareScraper-2.0.9-setup.exe`. It installs for the current user (no administrator rights are needed) into `%LOCALAPPDATA%\Programs\AShareScraper` and adds Start-menu entries for the application, the command line, this guide and the uninstaller. Two options are offered:

- a desktop shortcut;
- adding the program folder to your PATH, so that `ashare-cli` runs from any command prompt.

Installing a newer version over an older one replaces the program files only. Your data folder is never changed by installing, upgrading or uninstalling. Close the program first: since v2.0.8 the installer checks, and if AShareScraper.exe or ashare-cli.exe is still running (sometimes in the background after its window has closed) it asks you to close it and choose Retry. Earlier installers showed "Error opening file for writing" instead; choose Retry there too, never Ignore.

If the installer is not code-signed, Windows SmartScreen may show "Windows protected your PC". Choose **More info**, then **Run anyway**. Some antivirus programs are wary of unsigned programs built with PyInstaller; if yours quarantines a file, restore it and add an exception for the program folder.

### Portable zip

Unzip `AShareScraper-2.0.4-portable.zip` anywhere and double-click `AShareScraper.exe`. Keep the folder together: both programs need the `_internal` folder beside them.

### From source (any operating system)

Python 3.10 to 3.13 is required.

```
python -m pip install -r requirements.txt
python -m ashare.gui          # desktop application
python -m ashare.cli --help   # command line
```

Optional packages (`requirements-optional.txt`) add PNG charts (matplotlib), Parquet output (pyarrow), the PostgreSQL back end (psycopg) and DuckDB export (duckdb).

## 2. Where your data are kept

By default everything is kept in `Documents\AShareScraper`; you can choose another folder under **Settings**. The folder holds:

- `ashares.db`, the database (SQLite);
- `disclosures\` and `raw\`, the original documents and source responses, each with its SHA-256 hash;
- `exports\`, `reports\`, `panels\`, `releases\` and `charts\`, the files you create;
- `run_log.txt`, a record of every action with the equivalent command-line command;
- `pseudonym.key`, created the first time you make a pseudonymised release (keep it private, and keep a copy: the same key gives the same identifiers in later releases).

When a new version starts for the first time, it upgrades the database to its schema and first writes a backup copy beside it (`ashares.db.bak-…`). If anything goes wrong, close the program and rename the backup to `ashares.db`.

To use PostgreSQL instead of SQLite (for a shared or whole-market database), set the environment variable `ASHARE_DB_URL`, for example `postgresql+psycopg://user:password@host/ashares`. This works with the source installation; the Windows build includes only SQLite.

## 3. The desktop application

The sidebar groups the pages in the order you normally use them.

**Getting started** shows how much is in the database and the first steps.

**Collect** (pages 1 to 12) gathers the data:

1. **Universe**: the list of listed companies, from CNINFO. Run it first.
2. **Disclosures**: the announcement catalogue, with an option to download the documents.
3. **Financials**: figures and statements read from downloaded periodic reports.
4. **Market data**: daily prices from the public price feed, or a CSV file.
5. **Ownership & capital**: top-10 holders, share capital, pledges and control.
6. **Corporate actions**: dividends, bonus and capitalisation issues, rights issues, buybacks, restructurings and other transactions.
7. **Regulatory & legal**: penalties, supervisory measures, exchange discipline, litigation and listing-status events.
8. **Industry**: CSRC and other classifications (imported).
9. **Management**: directors, supervisors and officers, appointments and resignations.
10. **Segments & group**: business segments and subsidiaries.
11. **R&D, people & ESG**: R&D, workforce, patents and environmental and social disclosures.
12. **Indices & calendar**: index membership (imported), the trading calendar and suspensions.

Each page explains what its actions do. Fields marked as optional can be left blank; a blank security code means every company.

**Analyse** turns the database into results:

- **Company**: an integrated profile and an HTML report for one company, with charts.
- **Datasets**: research panels (company-year, company-quarter or company-date) with a codebook, and event studies. The dataset explorer opens a built panel with summaries, correlations and charts.
- **Validate**: all validation stages, with flags listed by rule.
- **Research**: full-text search, provenance traces, logged read-only SQL queries, exports, charts, dataset releases, the data-quality report and licence classes.

**Check** keeps the data trustworthy:

- **Review**: a queue of doubtful values (flags, parser disagreements, low confidence). Each item shows the source page with the value highlighted; you accept, correct or reject it. Corrections are stored separately and the original value is kept.
- **Operations**: the daily update, resumable jobs with progress and a cancel button, scheduling, and storage.
- **Self-test**: checks that each public source still answers in the expected shape. Run it on first use and whenever a step returns nothing.
- **Parser accuracy**: measures parsers against a golden corpus of hand-checked reports and sets the confidence attached to extracted values.

**Settings**: the data folder, optional boards, and the update check.

The output panel at the bottom shows what each action did. **Copy** copies it, for example into a bug report.

## 4. A first session

1. **Self-test** › Run the live self-test. Every check should show PASS. NETWORK UNREACHABLE means this computer cannot reach the source (check the network, proxy or firewall); FAIL means the source has changed and the program needs an update.
2. **Universe** › Update the company list.
3. **Disclosures** › Catalogue announcements, for one company first (for example 600519), with "Download documents" ticked.
4. **Financials** › Extract figures from reports.
5. **Validate** › Run all checks.
6. **Company** › Company report.

For the whole market:

- **Catalogue first, download second.** With the security code left blank, **Disclosures** › Catalogue announcements queries each exchange as a whole, month by month, so a year of periodic reports for every company takes a few hundred requests (a quarter of an hour or so). Untick "Download documents" for this first pass.
- **Download what you need.** **Disclosures** › Download catalogued documents then fetches the documents of the kinds you choose, newest first, with a size and time estimate before it starts. A year of annual reports for the whole market is over 5,000 files (roughly 30 GB) and takes several hours at the polite rate; interim and quarterly reports add as much again. Start with annual reports.
- **Progress and Stop.** Long actions print progress lines as they run. **Stop** ends an action safely after the current request: everything saved so far is kept, and running the same action again carries on where it stopped.
- **Keeping up to date.** After the first collection, **Operations** › Daily update catalogues only what was published since the last run, fetches the day's prices for the whole market and extracts only from new documents; a typical day takes about a quarter of an hour.

## 5. Building a dataset

**Datasets** › Build a panel:

- choose the unit (year, quarter or month) and the alignment. **Fiscal** rows are fiscal periods; **point in time** rows are dates (for example every 30 April), and each value is what had been published by that date;
- set an **as-of date** to reproduce what was known on a past date; nothing published later enters the panel;
- choose the universe (all companies listed at each date, an index, or a board), whether to exclude financial firms, a minimum confidence class, reviewed values only, winsorisation, and lags or leads;
- the panel is written as CSV and Stata `.dta` (Parquet with pyarrow), with an R loader, a codebook in Markdown and HTML, and a manifest with hashes.

The panel uses the point-in-time list of listed companies, so companies that later delisted are included for the years they were listed.

## 6. Releasing a dataset

**Research** › Create a dataset release writes a dated folder containing:

- one CSV per table, and a SQLite snapshot;
- `quality_report.md`, `.html` and `.json`: coverage by layer, board and year, parser precision, review results, flag rates and known gaps;
- `CITATION.cff` and, in `manifest.json`, a suggested citation with the software version and the database fingerprint;
- `manifest.json`: row counts, the licence classes included and excluded (with the number of rows left out), pseudonymisation settings and the hash of every file.

### Licences

Every row belongs to a licence class according to its source: PUBLIC_DISCLOSURE (statutory disclosures and exchange pages), PUBLIC_FEED (the free price feed, whose terms apply to redistribution), DERIVED (computed by the program), MANUAL (your own review and hand coding) or LICENSED (vendor data). **Licensed data are left out of releases unless you tick "Include licensed data"**, which is for your own use only.

The program cannot tell where an imported CSV file came from, so imports are treated as LICENSED until you tag their source label. If you import your own hand-coded file with the label `MY_CODING`, run **Research** › Tag a source's licence (or `ashare-cli set-licence MY_CODING MANUAL`) so that it is included. **Research** › Show licence classes lists the rows in each class.

### Pseudonymisation

Tick "Pseudonymise personal names" to replace the names of natural persons (directors, supervisors and officers, natural-person shareholders, pledgors and controllers) with identifiers such as `P3F9A0C21B7DE`. The same name always receives the same identifier when the same key is used, so panels built from different releases still link. Organisations keep their names.

Since v2.0.7 the rule fails safe. A shareholder, pledgor or controller name is masked unless a legal-person nature, or a word only organisations use (公司, 基金, 银行, LIMITED, BANK and the like), shows it to be an organisation's. Before v2.0.7, a person's name was masked only if it looked like a short Chinese name. A name with its shareholder nature glued on by the PDF text ("张三境内自然人"), or a name in Latin letters, could therefore be released unmasked. Each release records the rule in `manifest.json` (`pseudonymisation.rule`). **Do not share a pseudonymised release made before v2.0.7.** Make it again after these three steps:
1. "Extract top shareholders" (`extract-top-holders`);
2. "Resolve entities" (`resolve-entities`);
3. the release itself. Raw text columns and the full text of documents are left out, and known names are replaced in titles and other free text. Two further options give stronger protection: ages and birth years in five-year bands, and dropping free text altogether.

Pseudonymised data are still personal information in law. Read the [compliance note](compliance.md) before sharing a release.

## 7. Command line

`ashare-cli` offers every function of the desktop application, which shows the equivalent command for each action in `run_log.txt`. `ashare-cli --help` lists the commands and `ashare-cli COMMAND --help` explains one. Common commands:

| Task | Command |
|---|---|
| Update the company list | `ashare-cli update-universe` |
| Daily update (market-wide) | `ashare-cli daily-update` |
| Catalogue one company's reports | `ashare-cli catalogue-disclosures --since 2024-01-01 --until 2026-06-30 --security-code 600519 --download-documents` |
| Extract financials | `ashare-cli extract-financials --security-code 600519` |
| Validate everything | `ashare-cli validate-all` |
| Company report | `ashare-cli report 600519` |
| Catalogue the whole market (resumes by day) | `ashare-cli catalogue-disclosures --since 2026-01-01 --until 2026-10-16 --kind all --no-download-documents` |
| Days catalogued, with shortfalls | `ashare-cli catalogue-days --kind all --problems` |
| Re-catalogue busy days (failed, or short under an earlier version) | `ashare-cli recatalogue-busy-days --kind all` |
| Check which CNINFO search filters work | `ashare-cli probe-cninfo-filters --day 2026-04-29` |
| Check CNINFO's 3,000-result limit | `ashare-cli probe-cninfo-paging --day 2026-04-24` |
| Why the quote list refuses requests | `ashare-cli diagnose-quote-list` |
| Build a panel | `ashare-cli build-panel --unit year --start 2018-01-01 --as-of 2026-06-30` |
| Event study | `ashare-cli event-study corporate_actions:CASH_DIVIDEND` |
| Release | `ashare-cli release --pseudonymise --author "Your Name"` |
| Data-quality report | `ashare-cli quality-report` |
| Database schema | `ashare-cli db-status` |
| Self-test | `ashare-cli self-test` |

To run the daily update automatically on weekdays, use **Operations** › Schedule, or `ashare-cli schedule --enable --at 18:30` (Windows Task Scheduler; elsewhere the command prints a cron line). Scheduling is never switched on without your action.

### The whole-market catalogue (v2.0.3, extended in v2.0.4 and v2.0.6)

Without a security code, "Catalogue announcements" works on the whole market:

- **One query per period.** CNINFO is asked once per period for the whole market, not once per exchange.
- **Busy days.** CNINFO returns at most 3,000 results (100 pages) to one query; this was confirmed live. A query with more is split again and again until every part is under the limit. The splits used, in order of preference, are:
  - board: the separate codes for the Shenzhen main board, ChiNext, the Shanghai main board, STAR and Beijing; or, where those codes do not work, the two whole exchanges and Beijing;
  - announcement category;
  - industry;
  - for manufacturing, its divisions (if CNINFO accepts them);
  - batches of companies, sent with each company's own exchange;
  - as a last resort, single companies seen in the query (at most 1,500 queries for one busy day).

  Splits come first. Reading a query newest-first and oldest-first is only a last pass, because rows move between pages in CNINFO's time order.
- **Short quiet days.** A query under the limit that comes back short is read again in parts: a period of quiet days day by day, and a day board by board, since smaller queries lose fewer rows. Paging goes on past a page that only repeats earlier rows, and stops after five such pages or at page 100.
- **Only splits that work are used.** Which of these CNINFO supports is checked as the run goes: a filter CNINFO ignores, or that returns nothing, is not used again. A split whose parts do not reach the whole is noted against the day.
- **Rows.** CNINFO lists an announcement once for each security it concerns. The counts are of these rows, so an announcement for two securities is no longer mistaken for a missing one.
- **Checked counts, by board.** For every day, the rows stored are compared with CNINFO's own total.
  - Any gap is attributed to boards where CNINFO's board totals allow.
  - A day with a gap within the enabled boards is recorded as SHORTFALL and listed at the end.
  - A gap that is shown to lie outside them (for example Beijing announcements when Beijing is off) is recorded, but the day counts as complete.
  - A gap that cannot be placed counts as within the enabled boards.
- **Outcome.** A run that finishes with such gaps ends with "Finished with gaps" (exit code 3 on the command line) rather than "Failed". A failed day or a stopped run still ends with an error (exit code 1).
- **Resuming.** Finished days are remembered. Running the same action again, after Stop or an error, carries on with the first unfinished day; tick "Fetch finished days again" (`--refresh`) to fetch them anyway. Today is never treated as finished, because announcements are still being published.
- **Recent days rechecked.** CNINFO's totals can grow after the fact. At the start of a run that reaches the last 30 days, and once a day in the daily update, the totals of finished recent days are rechecked, and any day whose total has grown is fetched again.
- **Errors.** An error affects only the days of the period that failed. Those days are recorded as FAILED, the run carries on, and the end of the output lists them; running again retries only them. Three failed periods in a row stop the run.
- **Re-cataloguing.** "Re-catalogue busy days" (`recatalogue-busy-days`) fetches again:
  - failed days;
  - days short under an earlier version;
  - days that versions before v2.0.3 cut short at 3,000.

  A day whose gap recurred under the current method is not repeated, because the same queries cannot close it; `--include-current` overrides this. `--list` shows the days first.
- **Checking CNINFO's filters.** "Check CNINFO's search filters" (`probe-cninfo-filters`, about 200 to 270 requests) reports which board codes, industry filters (with manufacturing divisions), company queries and sort orders work, and why some rows repeat. The company test uses companies that have announcements in the query, and tests one, two, three, ten, 25 and 50 together, so that a failure shows where it starts. The catalogue sends companies ten at a time, the size confirmed live; CNINFO did not apply a list of 150.

`catalogue-days` shows each day's status (DONE, SHORTFALL, FAILED, or OPEN for today) with:
- CNINFO's total and the rows stored;
- the gap within and outside the enabled boards;
- the rows for several securities;
- the method;
- notes on any split that did not reach the whole.

Several consecutive quiet days fetched together share one total and one gap, so they are shown as one row, for example "2026-01-09~2026-01-12 (window)", and counted once in the status line. "One row per day" (`--by-day`) lists the days separately, with the per-day total left blank. The summary at the end of a run counts today as "kept open", not as finished.

### Listing dates and panels (v2.0.3, extended in v2.0.6 and v2.0.7)

- **The exchanges' stock lists (v2.0.7).** "Update the company list" first reads the Shanghai Stock Exchange's lists (main board and STAR) and the Shenzhen Stock Exchange's A-share list (main board and ChiNext). These are three requests, and every response is kept in the raw archive. These are the exchanges' own records of each company's listing date. The output reports what each list returned, for example "Exchange lists: Shanghai main board 1,690 of 1,690 dated; ...". Eastmoney's quote list is asked only if the exchanges' lists leave companies without a listing date; when it is not needed, the output says so. The exchanges' lists are read as their own web pages read them. If an exchange changes its page, its list is reported as failed, and the quote list fills the gap.
- **Listing dates.** These come from Eastmoney's public quote list, read during "Update the company list". If the list refuses requests, "Diagnose the quote list" (`diagnose-quote-list`) tries each way of asking (about six requests), then page 11 of the whole list and of one board, and reports what each returned. A way that works is remembered and used first from then on. The download keeps every page fetched that day, so a run that stops part-way carries on where it stopped, and the listing dates already fetched are applied. A company is set to "not in the quote list" only from a complete list.
- **Refusals (v2.0.7).** Three refused attempts in a row stop the quote list: the request, again after 30 seconds and again after two minutes, and any success resets the count. The note then says that Eastmoney may be refusing requests from this network for a while. In October 2026 it refused every request, page 1 included, for hours.
- **A list longer than one query returns (v2.0.6).** In October 2026 the list stopped after 1,000 companies on every run, probably because one query returns at most 1,000 rows. When the whole list stops part-way, it is read one board at a time, each board in both code orders, which covers up to 2,000 companies a board. A page that fails is retried after 30 seconds and again after two minutes; the quote list is asked no more than once every two seconds. When the list is still incomplete, the note says which board fell short and why. The daily price snapshot is read the same way.
- **Companies in each row.** "Build a panel" now has a setting for this (`--universe-basis`):
  - `listing`: a company is in a row when its listing record covers the row date.
  - `auto` (the default): as `listing`; and, for yearly rows only, a company whose listing record is incomplete (no listing date, or delisted on an unknown date) also counts as listed in a year when it published a periodic report for that year. For point-in-time rows, the report must have been published by the row's cut-off.
  - `report-evidence`: yearly rows from report evidence alone.

  The `universe_basis` column records which applies to each row: LISTING_RECORD or REPORT_EVIDENCE.
- **Empty panels.** A panel with no rows is not written. The command says why, for example missing listing dates, filters that exclude every company, or dates that give no rows, and what to do. It then ends with an error, so the desktop shows "Last action failed".

### Panels and fiscal years (v2.0.8)

A fiscal-year row (`--align fiscal`) takes the figures of the year ending 31 December. For a year that has not ended, those figures do not exist yet. "Build a panel" then names the year, and says how many rows have no financial figure at all; the manifest records both. For the last complete year, end the panel on 31 December of the year before, which is the desktop form's default. For this year's interim figures, use `--unit quarter`. Since v2.0.8, a listing history built before the listing dates arrived no longer hides them, and "Update the company list" rebuilds the history of the companies whose dates changed. A company in neither exchange's list is marked NOT_IN_EXCHANGE_LIST and treated as delisted on an unknown date, until a delisting announcement gives the date.

### Extracting figures (v2.0.6)

"Extract figures from reports" (`extract-financials`) first counts the documents to read, then reports progress every 25 documents and at least once a minute, for example "250 of 9,800 documents; 8.7 s each; about 23 h 05 min left". Each document read is marked with the extractor's version, so a stopped run continues with the next document when run again; "Read documents again" (`--again`) reads them all. A document downloaded again with new content is read again. The default, `--kind reports`, reads the periodic reports; `all` reads every downloaded document, most of which carry no financial statements. Extraction reads only documents already downloaded: catalogue with downloads, or use "Download documents", first.

### What v2.0.8 changed in the figures

- **Notices.** A notice about a report (年度报告披露提示性公告, 更正公告, 补充公告) is not read as the report; its figures are removed.
- **Units.** A figure's unit is taken from its own page, or the end of the page before. With no unit declared there, the figure is marked `CNY_ASSUMED`.
- **Two readers, one document.** When the headline reader and the statement reader of a document differ by an exact power of ten, the statement reading is kept and the note says so.
- **Cut and glued amounts.** An amount in yuan needs two decimals, so a figure cut at a separator is not read. A note number glued to an amount is removed when the other reading shows the figure without it.
- **Old readings.** Figures an earlier version read from a document, and this one does not, are removed when the document is read again.

"Extract figures from reports" reads every report once more after the upgrade, because the extractor's version changed.

### Table extraction: only the table pages, with progress and resume (v2.0.8)

These actions read only the pages of the tables they need, found by a quick pass over the page text:
- "Read top-10 shareholders" (`extract-top-holders`);
- "Read controlling shareholder and actual controller" (`extract-control`);
- "Extract segments from reports" (`extract-segments`);
- "Extract R&D and workforce" (`extract-human-capital`);
- "Extract subsidiaries" (`extract-subsidiaries`);
- the officer roster in "Extract from announcements and annual reports" (`extract-management`).

The pages found are remembered beside the documents (`disclosures/.section_index`), so the other actions skip the pass. Each action counts the reports first, then reports progress every 25 reports and at least once a minute ("250 of 9,800 documents; 8.7 s each; about …"). A stopped run continues with the next report; "Read reports again" (`--again`) reads them all. A report in which no table heading is found is read whole, as before.

### Segments and controllers (v2.0.8)

- **Segment tables.**
  - **Over a page break.** A table continued on the next page is read in full.
  - **Subtotals and breakdowns.** "小计" rows are subtotals, and "其中：" rows are breakdowns, not segments.
  - **Table kind.** Each row records whether it came from the composition table, which lists every segment, or the margin table, which lists only segments above 10% of revenue. A dimension read only from the margin table is not compared with the whole revenue.
- **The actual controller** is read in both layouts:
  - the Shanghai form, "名称 …" or "姓名 …";
  - the Shenzhen form, a header row such as "实际控制人姓名 与本公司的关系 国籍 …" with the values on the next row.
  
  Persons acting together are kept together ("王传福、吕向阳").

### Price sources (v2.0.8)

Prices come from a public feed you choose under **Settings > Price source**:
- **Eastmoney** (`EASTMONEY_PUBLIC`);
- **Tencent** (`TENCENT_PUBLIC`);
- **None:** import prices from CSV only.

Neither public feed is exchange-authoritative, and their terms are yours to check. "Test price sources" (`diagnose-prices 600519`) asks each feed for one company's last month and stores nothing. It then says which answered from your network and whether to change the setting.
- **Downloads and the daily update** follow the setting; "Download daily prices" can override it for one run (`--provider`).
- **Refusals.** The daily backfill stops after three companies refused in a row; the rest wait for the next run.
- **Preference.** Prices imported from CSV are always preferred to a public feed's for the same day.

### Findings (v2.0.8)

"Show findings" (`show-flags`) opens with the number of findings by rule and severity, and the 20 companies with most findings. A company, a rule (`--rule SEGMENT_SUM_MISMATCH`) or "List every finding" (`--details`) lists the rows, each with its company code. `--export exports/findings.csv` writes them all to a CSV file.

### Top shareholders (v2.0.7)

"Extract top shareholders" (`extract-top-holders`) reads the top-10 shareholder tables in both column orders used in periodic reports: the older one with the nature at the end, and the one with the nature after the name, as in the Shenzhen templates. A row whose figures fail the checks is left out rather than misread. Rows read from a document by an earlier version, and not by this one, are removed when the document is read again. Before v2.0.7, reports in the second layout gave shareholder names with the nature glued on, and figures one column out of place. After upgrading, run "Extract top shareholders" and then "Resolve entities".

### PDF reader messages (v2.0.3)

The PDF reader used for text extraction warns about unusual fonts and damaged cross-reference tables, often thousands of times in a large run. These messages are no longer printed one by one. At the end of the command, one line counts them by kind and document, and the details go to `logs/pdf_warnings_*.txt` in the data folder.

The common font message ("fontTools is required ...") does not affect the text when the font declares a standard encoding, as almost all do; see `docs/font_check_v2.0.3.md`. Messages for fonts without a standard encoding are counted separately, and their documents are listed first in the details file, so that figures from them can be checked.

## 8. Updates

The program contacts no update server unless you enter one under **Settings** (or set `ASHARE_UPDATE_URL`). The check then reports whether a newer version is published, with its download address and SHA-256 hash; it never downloads or installs anything itself.

## 9. Troubleshooting

- **A step returns nothing.** Check first that the company list is not empty (Getting started shows the count); almost every step works on that list. Then run the Self-test. Sources change their pages and interfaces without notice; the report says which check failed.
- **Panels are empty, or "Update the company list" adds no listing dates.** Run "Diagnose the quote list" (`diagnose-quote-list`). If every way of asking is refused (HTTP 5xx), Eastmoney may be refusing automated requests from your network; try later or from another network. Meanwhile, yearly panels can include companies by report evidence (the default, `--universe-basis auto`, once the reports are catalogued).
- **A catalogue reports SHORTFALL days.** `catalogue-days --problems` shows the gap within the enabled boards and the note recorded for each day. Days short under an earlier version are fetched again by "Re-catalogue busy days". If a day is still short under the current version, keep the output of `catalogue-days --problems` and `probe-cninfo-filters` and report it.
- **"Update the company list" fails with HTTP 404.** CNINFO has moved its list. Run the Self-test and report the result; meanwhile, if you know the new address, set the environment variable `ASHARE_CNINFO_STOCK_LIST_URL` to it.
- **"Database is locked".** Another copy of the program, or a scheduled update, is writing. Wait for it to finish.
- **A figure looks wrong.** Open it under **Review** or with `ashare-cli trace TABLE ID`: the trace shows the document, page, raw text, extraction method and checks. Correct it there; the original is kept.
- **A scanned report.** Documents without a text layer cannot be read (there is no OCR). `ashare-cli scan-documents` lists them.
- **Restore an earlier database.** Close the program and rename `ashares.db.bak-…` to `ashares.db`.

When reporting a problem, include the output panel text (Copy), `run_log.txt` and, for source problems, `selftest_report.json`.
