# Plan for v2.3.0 (8 November 2026)

## Scope

This plan covers everything that can be built without new test results from the author.

1. **Fixes.** The fixes from the v2.2.0 live run (findings 140 to 146, `docs/live_run_findings_v2.2.md`).
2. **Interactive charts.** The requirement that every graph and visualisation be scalable and interactive (R1, `docs/requirements_next_build.md`).
3. **Infrastructure.**
   - The infrastructure planned for v2.3, brought forward: entity identifiers, common ownership and the market map's scaling.
   - The infrastructure suggested by the review of related tools (OpenCorporatesCLI, capitol-cli, The OSINT Rack): disclosure timeliness, directors' and officers' share dealings, watchlists and trusted timestamps.

**Version.** The build is numbered v2.3.0, not v2.2.1, because it changes the database schema and adds features. The market map, common-ownership and sector views, planned for v2.3, are included as Part D. If they slip, they ship as v2.3.1 without changing anything else.

**Waits on the author.** Two fixes need the author's samples and stay out of this build:
- the quarterly top-10 layout (finding 134);
- rejoining a lost balance-sheet digit at the source (finding 132, rule 3).

Neither blocks anything here. The v2.2 re-read (financials-5, control-4) has not been confirmed on the author's data. This build changes neither extractor, so the confirmation can come at any time.

**Legal rules to verify before coding.** The timeliness and blackout-window rules (B5, B6) are taken from statute and CSRC and exchange rules that were revised in 2024. Each rule is entered with its source, article and effective date, and is checked against the current official text (CSRC, SSE and SZSE websites, or the National Database of Laws and Regulations) before the code that uses it is written. A rule that cannot be confirmed is left out and listed in the build record.

## Order of work

| Step | Part | Why this order |
|---|---|---|
| 1 | B1 Relocatable storage (finding 145) | Urgent: the author may reset Windows after the malware incident, and restoring the data folder elsewhere would orphan every document |
| 2 | B2 Network patience, B3 Job ledger | Shared by the fixes in Part A and the new collectors |
| 3 | Part A Fixes 140 to 144, 146 | Small, and they rest on B2 and B3 |
| 4 | B4 Interactive chart runtime (R1) | Every later view uses it |
| 5 | B5 Timeliness, B6 Share-dealings schema | New layers on existing data |
| 6 | B7 Entity identifiers (GLEIF) | Feeds B8 and Part D |
| 7 | B8 Ownership network computations | Feeds Part D and the panel variables |
| 8 | B9 Watchlists and alerts, B10 Trusted timestamps | Operations |
| 9 | Part D Views | Built on B4, B7 and B8 |
| 10 | Part E Tests, docs, release | |

## Part A. Fixes from the v2.2.0 live run

### A1 (finding 140): ego map, events without a named authority
- Events with neither `authority` nor `authority_name` are drawn under one node, "Authority not named" (kind `authority`, flag `UNNAMED`), linked by `ACTS_ON` with the count.
- The coverage note counts:
  - events shown;
  - events without an authority;
  - events published after the date;
  - events outside the depth or relation filter.

  It no longer says "no regulatory event published by then" when events exist.
- The readiness check counts the events published by the view's date, not every row.
- **Interference:** the relation filter "regulators" includes the new node. Snapshot schema version 2 is unchanged (a new flag value only).

### A2 (finding 141): guidance against outcome, unpaired reasons
Each unpaired guidance item is given a reason. The order is the order of checks; the first that applies wins.
1. `PERIOD_NOT_ENDED` (the reporting period ends after the date);
2. `REPORT_NOT_DUE` (the statutory deadline is after the date; uses B5);
3. `REPORT_NOT_CATALOGUED`;
4. `REPORT_NOT_DOWNLOADED`;
5. `REPORT_NOT_READ` (no extraction state for financials-5 or earlier);
6. `NO_FIGURE` (read, but no `net_profit_parent` for the period).

The view adds a table `unpaired` (reason, count, example codes). The summary line becomes "105 of 2,208 paired; 1,640 report not yet read; …".

### A3 (finding 142): duplicated codes
Codes are de-duplicated (after zero-padding) in every command that takes a list. The output notes "dropped duplicates: 688012". One helper, `parse_codes()` in `ashare/util.py`, is used by every such command, and a test runs every command with a duplicated code.

### A4 (finding 143): gateway time-outs
Server errors are waited out, not counted as failures at once (B2). The catalogue counts a window as failed only after the waiting is spent. The rule "three windows in a row" stays, measured after the waits.

### A5 (finding 144): whole-market price download
Rebuilt on the job ledger (B3):
- progress per company (count, seconds each, time left);
- resume by default: a company is skipped when its stored bars cover the period from the same source and adjustment;
- `--refetch` to fetch again;
- a stop keeps what has been fetched and prints the result so far;
- errors are listed by company in the ledger.

### A6 (finding 146): wording
- Correct singular and plural throughout the catalogue messages (one helper, `plural()`).
- A single day is shown as one date.
- The failed days are listed once.

## Part B. Infrastructure

### B1 (finding 145): relocatable storage
**Problem.** `disclosures.local_path` and `raw_records.payload_path` store absolute paths. The scheduled update stores the folder's path.

**Design.**
1. **Data root.**
   - `ashare/storage_paths.py` gives one function, `data_root()`. It takes the Settings value or the `ASHARE_HOME` environment variable, the variable winning, as `CAPITOL_HOME` does in capitol-cli.
   - Every stored path is written relative to the root, with forward slashes: `disclosures/600519/<sha256>.pdf`.
   - `resolve(stored)` returns the absolute path.
2. **Reading old paths.** When a stored path is absolute:
   - if it exists, it is used and rewritten as relative on the next write;
   - if it does not exist, the tail after the last `disclosures/` (or `raw/`) is tried under the current root;
   - the file is accepted only if its SHA-256 matches the stored hash.
3. **Migration.** A new Alembic migration rewrites every absolute path that lies under the current root as relative. Paths outside the root are left, and reported by "Check files".
4. **"Move data folder" (Settings, and `ashare-cli move-data-folder TARGET`).**
   - Checks free space on the target.
   - Copies, verifies each file's hash, and switches the setting.
   - Re-creates the scheduled update with the new folder.
   - Records the move in the run log.
   - Leaves the old folder in place, to be deleted by the author after checking.
   - "Adopt a folder already moved" switches without copying, after the same hash check on a sample and a count of files.
5. **"Check files"** reports paths outside the root, missing files and hash mismatches, by table.

**Interference.** Every read of `local_path` or `payload_path` goes through `resolve()`. A grep test fails the build if any module opens either column directly.

**Tests.**
- Move a seeded data folder, both by copy and by adoption.
- Stored absolute paths from a "previous machine" resolve after the move.
- A hash mismatch is refused.
- The scheduled task is re-created (mocked).
- A Windows path with a different user name resolves, under Wine.

### B2: network patience
- One retry policy in `ashare/http.py`, by error class:
  - network or DNS errors: as now;
  - 429: honour `Retry-After`;
  - 502, 503 and 504: growing pauses of 15, 30, 60, 120 and 120 seconds, five minutes in all;
  - other 4xx: no retry.
- Every pause can be stopped like the run, and progress reports the wait ("CNINFO is not answering (504); waiting 60 s").
- The policy is recorded in the run log.
- **Tests:** a mocked server returning 504 three times, then 200; a stop during a wait.

### B3: job ledger
- A table `job_items` holds one row per unit of work: job kind, key (company, document, day), state, attempts, last error, seconds, started and finished.
- Used by:
  - the market download (A5);
  - the extractors ("Extract figures", "Read controller", "Read top-10", ESG, guidance);
  - the catalogue's days, which keep their present table, linked to the ledger.
- Gives, for any job:
  - progress with the time left;
  - resume;
  - "not read, and why" by reason (as capitol-cli's `paper` command does): scanned, encrypted, no matching table, parse error, timed out.
- A new Files page section, "Documents not read", lists them by extractor and reason, with a link to the document.
- **Interference:** the extraction-state table stays the authority on what has been read; the ledger records attempts.

### B4 (R1): interactive chart runtime
1. **Library.** chartjs-plugin-zoom (MIT) with Hammer.js (MIT) is bundled in `ashare/viz/viewer/vendor/`, with licences, and listed in `THIRD_PARTY_NOTICES.txt`. Nothing is fetched from the network.
2. **One runtime.** `chart_runtime.js` gives every chart:
   - wheel and pinch zoom, on both axes or one (a toggle);
   - drag to pan, and box zoom (shift-drag);
   - reset (a button and a double-click);
   - axes that re-tick as the range changes;
   - typed "from" and "to" ranges;
   - linear or logarithmic scale where the values are positive;
   - units: yuan, 10,000 yuan or 100 million yuan;
   - a hover readout with the exact stored value, unit, period, document ID and page.

   It is used by the topology page's charts, every series view and the dataset explorer.
3. **Heatmaps.** The coverage heatmap, and later the sector heatmaps, are drawn as a matrix chart (chartjs-chart-matrix, MIT) with the same zoom. The hover gives listed, with data and share. The table stays below.
4. **Relational maps.** Added to force-graph:
   - zoom to a node and its neighbours;
   - labels sized to stay legible at each zoom;
   - level of detail: groups collapse when zoomed out, used by the market map.
5. **Desktop charts.** Each Tk chart window gains "Open interactive" (writes the series page and opens it) and keeps its PNG and SVG export.
6. **Thinning.** A series with more than 5,000 points is thinned (largest-triangle three-buckets) when zoomed out and shown in full when zoomed in. The page says "thinned for display; zoom in for every point".
7. **Publication figures** stay static vector SVG with their CSV. A figure can be written from a zoomed range only by an explicit "Write figure of this range", which records the range in the manifest.

**Tests (playwright).**
- For each interactive page, zoom and box zoom change the axis range, and reset restores it.
- The hover readout equals the stored value.
- There are no console errors and no network requests.
- Publication files are byte-identical before and after use.
- The notices list each new library.
- Pages with 6,000 nodes and 50,000 points are timed.

### B5: disclosure timeliness
1. **Rule table.** `ashare/rules/disclosure_deadlines.yaml` is versioned and records, for each rule:
   - the kind of document and the deadline;
   - the counting (calendar days or trading days);
   - the source (instrument, article) and the effective dates.

   To verify, for each:
   - **Annual reports:** within four months of the year end (Securities Law, art. 79).
   - **Half-year reports:** within two months of the half-year end (Securities Law, art. 79).
   - **First- and third-quarter reports:** within one month of the quarter end (CSRC Measures for the Administration of Information Disclosure by Listed Companies).
   - **Earnings forecasts:** the exchange rules' deadline for annual forecasts (by 31 January for the conditions that require one).
2. **Trading calendar.** A local SSE and SZSE trading calendar, built from the market data already held and checked against the exchanges' published holiday notices, for rules counted in trading days.
3. **Computation.** For every periodic report:
   - days from the period end to publication;
   - the deadline that applied;
   - late or not;
   - postponement announcements (延期披露) linked when catalogued.
4. **Panel variables:** `report_delay_days`, `report_late`, `late_reports_3y`.
5. **Topology and coverage:** an optional marker for late reports.
6. **Tests:** rule selection by effective date; a trading-day count over a holiday; a late annual report flagged; a report on the deadline day not flagged.

### B6: directors' and officers' share dealings (schema and rules)
1. **Schema.** A new table `insider_dealings` holds:
   - company and person (pseudonymised as `PersonRole`);
   - relation: self, spouse, parent, child or other related party;
   - date, direction, shares, price and amount, and holdings before and after;
   - the method (auction, block trade, incentive, other);
   - the source document and page, the extraction method and the observation date.
2. **Collection.** Announcements titled as share changes of directors, supervisors or senior managers (董监高, 增减持, 持股变动) are catalogued and classified now. The extractor reads their tables where they are text, and is marked experimental. Exchange disclosure pages for these changes are named as a possible source only after their terms and access are checked; they are not scraped behind any bot protection.
3. **Rules,** in `ashare/rules/insider_rules.yaml`, each with its source and effective dates, to verify:
   - the report deadline for a change (2 trading days);
   - prior disclosure of a reduction plan (15 trading days before the first sale);
   - blackout windows before periodic reports, forecasts and flash reports, and around major events.
4. **Flags.**
   - Late report.
   - Sale without a prior plan.
   - Dealing in a window.

   Each flag states the rule and the dates. The interface and the codebook state that a flag is a fact to examine, not a finding of breach.
5. **Panel variables (optional):** `insider_net_buy_12m`, `insider_sales_in_window_12m`.

### B7: entity identifiers (GLEIF)
1. **Schema.** A new table `entity_identifiers` holds entity, scheme (LEI, USCC, ISIN, REGISTRY), value, source, observed date and confidence. The existing `entities.credit_code` is copied in, and kept for compatibility.
2. **GLEIF client.**
   - `ashare/gleif.py` queries `api.gleif.org/api/v1` (no key, public data): search by name, lookup by LEI, registration authority, direct and ultimate parent relationships.
   - It uses the polite HTTP client (B2) and archives raw records like other sources.
   - The data's reuse terms are checked and recorded in `docs/compliance.md` before the first release that includes them.
3. **Matching.**
   - Automatic only on an exact match of the credit code (GLEIF `registeredAs` with the SAMR registration authority) or of the LEI.
   - Name matches go to the Review queue as candidates, with the GLEIF record beside the entity.
   - Nothing is merged without review.
4. **Parents.** GLEIF direct and ultimate parents are stored as `ControlEdge` rows with source `GLEIF`, never overriding a report's chain. A disagreement is listed in Review.
5. **Registry reference.** Each entity shows a link to the official register:
   - for China, SAMR's National Enterprise Credit Information Publicity System (国家企业信用信息公示系统), as a link only, with no scraping;
   - elsewhere, the register named by GLEIF.
6. **Commands:** `gleif-match --codes` (or the whole universe), and `gleif-refresh`.
7. **Effect on the views.**
   - The ego map shows LEIs in the inspector.
   - `UNRESOLVED` holders fall as matches are accepted.
   - The ego map's coverage note gives the share of entities with an identifier.

### B8: ownership network computations
These were planned for v2.3 with the market map, and are built here as a module (`ashare/network_measures.py`) with panel variables:
- `holder_overlap_n`: listed companies sharing at least one top-10 holder (excluding nominee and custodian accounts, by a maintained list);
- `mhhi_delta`: the modified Herfindahl index increment from common ownership (O'Brien and Salop), from top-10 stakes. It is labelled as a lower bound, because top-10 tables omit smaller holders;
- `interlock_n`: listed companies sharing a director or officer in the roster window.

**Network construction.** Bipartite holder–company and person–company graphs as known on a date, projected to company–company links weighted by shared stake or shared persons.

**Statistics.** The codebook states that network observations are not independent and recommends clustered or network-robust standard errors.

**Tests:** hand-computed MHHI for a three-company, three-holder example; nominee exclusion; date filtering.

### B9: watchlists and alerts
- A table `watchlists` holds a name, companies, kinds of announcement or event (regulatory letter, guidance, change of controller, insider dealing flag, late report) and a channel.
- The first run records a baseline; later runs report only new items, as capitol-cli's `watch` does.
- Runs with the scheduled daily update.
- **Channels:**
  - an entry in the desktop program's new "Alerts" page, and a Windows notification;
  - optional email by SMTP, with the password kept in the Windows credential store, never in settings;
  - no public push services by default.
- **Commands:** `watch-add`, `watch-run`, `watch-list`.

### B10: trusted timestamps
- Release manifests and topology and view manifests can be timestamped by an RFC 3161 time-stamping authority. A free authority is set in Settings; none is used by default.
- The token (`manifest.tsr`) is stored beside the manifest, and `verify-release` checks it.
- This proves that a dataset existed in that form on that date, which supports the point-in-time claims of the paper.
- **Tests:** a mocked authority; a verification that fails on a changed manifest.

## Part C. Panels, codebook and interface

- New optional panel variables:
  - from B5: `report_delay_days`, `report_late`, `late_reports_3y`;
  - from B6: `insider_net_buy_12m`, `insider_sales_in_window_12m`;
  - from B8: `holder_overlap_n`, `mhhi_delta`, `interlock_n`.

  None is among the defaults, so existing panels are unchanged.
- New interface pages:
  - Settings > Data folder (move or adopt);
  - Files > Documents not read;
  - Review > Identifier matches;
  - Operations > Watchlists and Alerts;
  - Visualise additions (Part D).
- Every new string goes into the Chinese catalogue. New terms go into glossary part 14: LEI, common ownership, MHHI increment, blackout window (窗口期), disclosure timeliness, watchlist, trusted timestamp.

## Part D. Views (planned for v2.3; built on B4, B7 and B8)

1. **Market map** (`viz-market-map`). Every listed company as known on a date, linked by:
   - shared controller (the controller-group identifier);
   - shared top-10 holders (weighted);
   - shared persons.

   Grouped by CSRC section or board. Zoomed out, groups collapse with counts; zoomed in, the companies and links appear (B4.4). Filters cover relation, minimum weight and section.
2. **Common ownership** (`viz-common-ownership`). For a sector or a list of codes: a holder–company matrix (zoomable heatmap), the projected company network, and MHHI increments by pair and by year.
3. **Sectors** (`viz-sectors`). By CSRC section and year:
   - coverage;
   - median and interquartile range of chosen ratios (labelled `nvf-0` descriptive proxies);
   - the share of state control;
   - late reports;
   - regulatory events.

   Shown as zoomable heatmaps and small multiples.
4. **Disclosure timeliness** (`viz-timeliness`). The distribution of delays by year and board, with late reports listed.

Each view has readiness checks, an interactive page, data, publication figures and a manifest, as in v2.2. The ego map gains the GLEIF identifiers and parents (B7), and the market map's scale test (6,000 nodes) is part of B4's tests.

## Part E. Interference checks, tests and release

**Interference.**
- **Extractors.** None of the extractors' versions change (financials-5, control-4, top10-3 and the rest), so nothing is re-read.
- **Schema.** The schema changes are additive (new tables) except the path rewrite (B1), which is reversible: the migration's downgrade restores absolute paths under the current root.
- **Snapshots.** The topology view and its snapshot schema are unchanged. View snapshots stay at schema version 2, with new optional fields only.
- **Panels.** Built with the default variables, they are byte-identical to v2.2.0.

**Tests.**
- A test file `tests/test_v23.py`, with the tests named under each part.
- The full matrix:
  - Linux Python 3.12 and 3.13;
  - PostgreSQL 16;
  - Windows CPython under Wine, including a data-folder move on a Windows path;
  - GitHub's Windows build with the 32-bit installer stub.
- `CITATION.cff` validated.

**Docs.**
- `docs/live_run_findings_v2.2.md`: findings 140 to 146 marked fixed.
- CHANGELOG, README and user guide: data folder, Documents not read, interactive charts, timeliness, share dealings, identifiers, watchlists, timestamps and the new views.
- `docs/compliance.md`: GLEIF terms, insider-dealing flags, alerts.
- Glossary part 14.
- The build plan's status.
- A build record in this plan.

**Release.**
- Version 2.3.0 in `__init__`, the installer, READ_ME_FIRST, CITATION.cff and the user guide.
- Windows build, installer, zips and checksums.
- Commit and push in the author's name only.
- The GitHub release and Zenodo archive, then edit the Zenodo record's licence to PolyForm Strict (release checklist step 8).

## Not in this build

- **The quarterly top-10 layout (finding 134).** Needs `inspect-tables ID --table top10` for two or three quarterly reports without rows.
- **Rejoining a lone digit at the source (finding 132, rule 3).** Needs `inspect-tables 31 --table balance_sheet` and `inspect-tables 76 --table balance_sheet`.
- **Exchange share-dealing pages as a source.** Only after their terms and access are checked (B6.2).
