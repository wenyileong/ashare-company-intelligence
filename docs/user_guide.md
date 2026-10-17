# User guide

A-share Company Intelligence collects, checks and organises public information about companies listed in mainland China (SSE Main Board, STAR Market, SZSE Main Board and ChiNext; the Beijing Stock Exchange and B shares can be switched on). Every value it stores keeps the document it came from, how it was read and how far it has been checked, so that a dataset built with it can be traced back to its sources.

This guide covers the desktop application and the command line. The [methods document](methods.md) explains how the data are produced; the [codebook](codebook.md) defines every panel variable.

## 1. Installing

### Windows installer

Run `AShareScraper-2.0.3-setup.exe`. It installs for the current user (no administrator rights are needed) into `%LOCALAPPDATA%\Programs\AShareScraper` and adds Start-menu entries for the application, the command line, this guide and the uninstaller. Two options are offered:

- a desktop shortcut;
- adding the program folder to your PATH, so that `ashare-cli` runs from any command prompt.

Installing a newer version over an older one replaces the program files only. Your data folder is never changed by installing, upgrading or uninstalling.

If the installer is not code-signed, Windows SmartScreen may show "Windows protected your PC". Choose **More info**, then **Run anyway**. Some antivirus programs are wary of unsigned programs built with PyInstaller; if yours quarantines a file, restore it and add an exception for the program folder.

### Portable zip

Unzip `AShareScraper-2.0.3-portable.zip` anywhere and double-click `AShareScraper.exe`. Keep the folder together: both programs need the `_internal` folder beside them.

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

Tick "Pseudonymise personal names" to replace the names of natural persons (directors, supervisors and officers, natural-person shareholders, pledgors and controllers) with identifiers such as `P3F9A0C21B7DE`. The same name always receives the same identifier when the same key is used, so panels built from different releases still link. Organisations keep their names. Raw text columns and the full text of documents are left out, and known names are replaced in titles and other free text. Two further options give stronger protection: ages and birth years in five-year bands, and dropping free text altogether.

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
| Re-catalogue busy days cut short by v2.0.2 | `ashare-cli recatalogue-busy-days --kind all` |
| Check CNINFO's 3,000-result limit | `ashare-cli probe-cninfo-paging --day 2026-04-24` |
| Why the quote list refuses requests | `ashare-cli diagnose-quote-list` |
| Build a panel | `ashare-cli build-panel --unit year --start 2018-01-01 --as-of 2026-06-30` |
| Event study | `ashare-cli event-study corporate_actions:CASH_DIVIDEND` |
| Release | `ashare-cli release --pseudonymise --author "Your Name"` |
| Data-quality report | `ashare-cli quality-report` |
| Database schema | `ashare-cli db-status` |
| Self-test | `ashare-cli self-test` |

To run the daily update automatically on weekdays, use **Operations** › Schedule, or `ashare-cli schedule --enable --at 18:30` (Windows Task Scheduler; elsewhere the command prints a cron line). Scheduling is never switched on without your action.

### The whole-market catalogue (v2.0.3)

Without a security code, "Catalogue announcements" works on the whole market:

- **One query per period.** CNINFO is asked once per period for the whole market, not once per exchange.
- **Busy days.** CNINFO returns at most 3,000 announcements (100 pages) to one query. A day with more than that is split by announcement category, and a category still over the limit by board, until every announcement arrives.
- **Checked counts.** For every day, the announcements stored are compared with CNINFO's own total. A day that falls short is recorded as SHORTFALL and listed at the end; it is not reported as done.
- **Resuming.** Finished days are remembered. Running the same action again, after Stop or an error, carries on with the first unfinished day; tick "Fetch finished days again" (`--refresh`) to fetch them anyway. Today is never treated as finished, because announcements are still being published.
- **Errors.** An error affects only the days of the period that failed. Those days are recorded as FAILED, the run carries on, and the end of the output lists them; running again retries only them. Three failed periods in a row stop the run.
- **Earlier catalogues.** Catalogues made with v2.0.2 or earlier may be missing announcements on days with more than 3,000 (in 2026: late March, most of April and late August). "Re-catalogue busy days" (`recatalogue-busy-days`) finds those days and fetches them again; `--list` shows them first.

`catalogue-days` shows each day's status (DONE, SHORTFALL, FAILED, or OPEN for today) with CNINFO's total and the number stored. For several consecutive quiet days fetched together, CNINFO gives only the total for the whole period, so the per-day total is left blank.

### Listing dates and panels (v2.0.3)

- **Listing dates.** These come from Eastmoney's public quote list, read during "Update the company list". If the list refuses requests, "Diagnose the quote list" (`diagnose-quote-list`) tries each way of asking (about six requests) and reports what each returned. A way that works is remembered and used first from then on. The download keeps every page fetched that day, so a run that stops part-way carries on where it stopped, and the listing dates already fetched are applied. A company is set to "not in the quote list" only from a complete list.
- **Companies in each row.** "Build a panel" now has a setting for this (`--universe-basis`):
  - `listing`: a company is in a row when its listing record covers the row date.
  - `auto` (the default): as `listing`; and, for yearly rows only, a company whose listing record is incomplete (no listing date, or delisted on an unknown date) also counts as listed in a year when it published a periodic report for that year. For point-in-time rows, the report must have been published by the row's cut-off.
  - `report-evidence`: yearly rows from report evidence alone.

  The `universe_basis` column records which applies to each row: LISTING_RECORD or REPORT_EVIDENCE.
- **Empty panels.** A panel with no rows is not written. The command says why, for example missing listing dates, filters that exclude every company, or dates that give no rows, and what to do. It then ends with an error, so the desktop shows "Last action failed".

### PDF reader messages (v2.0.3)

The PDF reader used for text extraction warns about unusual fonts and damaged cross-reference tables, often thousands of times in a large run. These messages are no longer printed one by one. At the end of the command, one line counts them by kind and document, and the details go to `logs/pdf_warnings_*.txt` in the data folder.

The common font message ("fontTools is required ...") does not affect the text when the font declares a standard encoding, as almost all do; see `docs/font_check_v2.0.3.md`. Messages for fonts without a standard encoding are counted separately, and their documents are listed first in the details file, so that figures from them can be checked.

## 8. Updates

The program contacts no update server unless you enter one under **Settings** (or set `ASHARE_UPDATE_URL`). The check then reports whether a newer version is published, with its download address and SHA-256 hash; it never downloads or installs anything itself.

## 9. Troubleshooting

- **A step returns nothing.** Check first that the company list is not empty (Getting started shows the count); almost every step works on that list. Then run the Self-test. Sources change their pages and interfaces without notice; the report says which check failed.
- **Panels are empty, or "Update the company list" adds no listing dates.** Run "Diagnose the quote list" (`diagnose-quote-list`). If every way of asking is refused (HTTP 5xx), Eastmoney may be refusing automated requests from your network; try later or from another network. Meanwhile, yearly panels can include companies by report evidence (the default, `--universe-basis auto`, once the reports are catalogued).
- **A catalogue reports SHORTFALL days.** Run "Re-catalogue busy days" or `catalogue-disclosures ... --retry-shortfalls`. If the same days still fall short, keep the output of `catalogue-days --problems` and `probe-cninfo-paging` and report it.
- **"Update the company list" fails with HTTP 404.** CNINFO has moved its list. Run the Self-test and report the result; meanwhile, if you know the new address, set the environment variable `ASHARE_CNINFO_STOCK_LIST_URL` to it.
- **"Database is locked".** Another copy of the program, or a scheduled update, is writing. Wait for it to finish.
- **A figure looks wrong.** Open it under **Review** or with `ashare-cli trace TABLE ID`: the trace shows the document, page, raw text, extraction method and checks. Correct it there; the original is kept.
- **A scanned report.** Documents without a text layer cannot be read (there is no OCR). `ashare-cli scan-documents` lists them.
- **Restore an earlier database.** Close the program and rename `ashares.db.bak-…` to `ashares.db`.

When reporting a problem, include the output panel text (Copy), `run_log.txt` and, for source problems, `selftest_report.json`.
