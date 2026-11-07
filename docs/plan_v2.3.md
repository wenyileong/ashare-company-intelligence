# Plan for v2.3.0 (8 November 2026; revised the same day after a review against the code)

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

## Review of this plan against the code (8 November 2026)

The plan was checked against the code at commit 3a5e2c5. The baseline passed: 429 tests, with 29 skipped for Tk and the browser. The review found the following, and the plan below is revised for each.

| No. | Finding | Revision |
|---|---|---|
| V1 | The stored document path is read in 92 places in 28 modules. Changing them at once is the riskiest step of the build. | B1 is split into six phases. The first adds one accessor with unchanged behaviour, so the call sites change mechanically and are proved equal before any behaviour changes. |
| V2 | The path is also copied into the `source_document` column of twelve observation tables (control, management, group, segments, workforce, ESG, regulatory, corporate actions, financial facts and others), when the document address is missing or listed second. | The resolver also serves `source_document` for display. The rewrite (B1, phase 4) covers these columns, and releases already replace them with the address. |
| V3 | `financials._find_disclosure` finds a document by an exact match of its path string. `files.check_files` compares resolved paths. | Both go through the accessor, comparing canonical forms (or the hash). Tests cover a relative and an absolute form of the same file. |
| V4 | The section-index cache is keyed by the absolute path and the file's modification time. A move would invalidate every cached index, and a copy without its times would too. | The cache key becomes the document's SHA-256 with `INDEX_VERSION`, and the old key is still read. Copies keep their times (`copystat`). |
| V5 | `init_db()` runs Alembic upgrades automatically when the program starts. A path rewrite written as a migration would run unasked on first launch. | Schema migrations stay automatic, since they add empty tables only. The path rewrite is never a migration: it is an explicit, previewed command with a backup and an undo. |
| V6 | The database lives in the data folder and is open while the program runs. The desktop program sets the folder's paths in environment variables at start (`gui.py`). | The move copies the database with SQLite's backup function (with its WAL file). It runs only when no job is running, switches the setting and restarts the program. |
| V7 | Paths written by the command-line program are relative to the folder it was run from, because the defaults (`disclosures`, `raw`) are relative. | The resolver reads a relative path as relative to the data root, then tries the tail search. The diagnostics report how many paths are of each form before anything is changed. |
| V8 | Storing GLEIF parents in `control_edges` would change the control chains read by `control_at`, the ego map, `ctrl_distance` and the topology view. | GLEIF links go into a new table, `external_relationships`, and are shown beside the report's chain, never mixed into it. |
| V9 | Fix A2 ("report not yet due") depends on the timeliness rules of B5, which were ordered after Part A. | A2 is built after B5. Until then the reason falls back to "period ended, report not catalogued". |
| V10 | B5 proposed a trading calendar derived from the market data held, which is incomplete for most companies. | The calendar is a bundled data file of exchange holidays by year, from the exchanges' published notices. The market data only check it. |
| V11 | B9 (email through the Windows credential store, Windows notifications) and B10 (RFC 3161) need new libraries and widen what can go wrong, which matters more after the author's malware incident. | B9 ships with in-program alerts only; email waits for a later version. B10 is optional and off by default, and its library is chosen and its licence checked first. |
| V12 | "Panels byte-identical" cannot hold, because a panel's manifest records the time and version. | The test compares the data and the codebook, leaving out the manifest's time and version fields. |
| V13 | Chart.js 4.4.8 is bundled. | The zoom and matrix plugins are chosen at versions that support Chart.js 4. The v2.1 and v2.2 page tests, which call `window.__chartview` and the like, must pass unchanged. |

## Scaffolding first

Every new feature is built in the same stages, so that each stage can be released, switched off or reverted without touching the others.

1. **Schema.** New tables only, added by an automatic migration (0008 onwards). They are empty, and no existing table changes shape.
2. **Module.** The module with its interface, a dry-run or no-op implementation, and its tests.
3. **Feature switch.** A switch in `ashare/features.py`, kept in Settings (`features.<name>`). New commands refuse to run while their switch is off, and their pages are hidden.
4. **Implementation**, behind the switch.
5. **Exposure.** The desktop page and the Chinese strings, then the switch turned on by default once the tests pass.

Settings > Diagnostics lists every switch, its state and the version of its schema, so a fault can be isolated by switching one feature off. Switching a feature off never deletes its data.

| Feature | Switch | On by default in v2.3.0 |
|---|---|---|
| Path diagnostics and accessor (B1, phases 0 to 2) | none (always on; behaviour unchanged) | yes |
| Relative paths for new downloads (B1, phase 3) | `storage.relative_paths` | yes, once phase 2's tests pass |
| Normalise stored paths (B1, phase 4) | `storage.normalise` | the command is available; it runs only when asked |
| Move or adopt the data folder (B1, phase 5) | `storage.move` | the command is available; it runs only when asked |
| Job ledger (B3) | `jobs.ledger` | yes (it only records) |
| Interactive chart runtime (B4) | `viz.interactive` | yes; off restores the v2.2 pages |
| Timeliness (B5) | `timeliness` | yes |
| Share dealings (B6) | `insider` | no (experimental extractor) |
| GLEIF identifiers (B7) | `gleif` | no (network source; on when the author chooses) |
| Ownership network measures (B8) | `network_measures` | yes (optional panel variables) |
| Watchlists (B9) | `watchlists` | yes (in-program alerts only) |
| Trusted timestamps (B10) | `timestamps` | no |

## Order of work

| Step | Part | Why this order |
|---|---|---|
| 1 | Feature switches and Diagnostics (scaffolding) | Every later feature uses them |
| 2 | B1 phases 0 to 3 (diagnostics, accessor, tolerant reads, relative writes) | Urgent and safe: nothing stored is rewritten |
| 3 | B2 Network patience, B3 Job ledger (recording only) | Shared by Part A and the new collectors |
| 4 | Part A fixes 140, 142 to 144, 146 | Small, and they rest on B2 and B3 |
| 5 | B1 phases 4 and 5 (normalise, move or adopt) | Built on the accessor once it has been proved |
| 6 | B4 Interactive chart runtime (R1) | Every later view uses it |
| 7 | B5 Timeliness, then fix A2 | A2 needs B5's deadlines |
| 8 | B6 Share-dealings schema and rules | |
| 9 | B7 Entity identifiers (GLEIF) | Feeds B8 and Part D |
| 10 | B8 Ownership network computations | Feeds Part D and the panel variables |
| 11 | B9 Watchlists, B10 Trusted timestamps | Operations |
| 12 | Part D Views | Built on B4, B7 and B8 |
| 13 | Part E Tests, docs, release | |

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
Built after B5, whose deadlines give `REPORT_NOT_DUE` (review V9).

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

**What is stored.**
- **Full paths.** `disclosures.local_path` and `raw_records.payload_path` hold full paths, written by the desktop program, which sets absolute folders. Paths written by the command-line program are relative to the folder it was run from.
- **Provenance columns.** The same path is copied into `source_document` in twelve observation tables (review V2).
- **Elsewhere.** The section-index cache is keyed by the absolute path (V4), the scheduled update records the folder, and the database itself lives in the folder (V6).

The work comes in six phases. Phases 0 to 3 change nothing stored. Phases 4 and 5 change stored data or move files only when the author asks, after a preview, with a backup and an undo.

**Phase 0. Diagnostics (read-only).**
- `ashare-cli paths-report`, and Settings > Data folder > "Check paths", count:
  - paths by form (absolute inside the folder, absolute elsewhere, relative), for `local_path`, `payload_path` and the `source_document` columns;
  - files present, missing, and recoverable by the tail search with a matching hash;
  - the section-index caches;
  - the folder's size and free space.
- Writes nothing. It can be run before a Windows reset, to see what a move would involve.

**Phase 1. One accessor, behaviour unchanged.**
- `ashare/storepaths.py` gives:
  - `data_root()`: the Settings value, or `ASHARE_HOME` when set, which wins;
  - `document_path(d)` and `raw_path(r)`: return a `Path` or `None`;
  - `display_source(text)`: for `source_document`;
  - `same_file(a, b)`.
- In phase 1, `document_path(d)` returns exactly `Path(d.local_path)`. The 92 call sites in 28 modules are changed to use it, mechanically.
- **Tests.** The full suite passes unchanged. A grep test fails the build if any module other than `storepaths.py` builds a path from `local_path` or `payload_path` directly. `financials._find_disclosure` and `files.check_files` move to `same_file` (V3).

**Phase 2. Tolerant reads.**
- The accessor resolves:
  - a relative path against the data root;
  - an absolute path that exists, as it is;
  - an absolute path that does not exist, by the tail after the last `disclosures/`, `raw/` or `market_raw/` under the current root, accepted only when the file's SHA-256 matches the stored hash. The result is cached for the run.
- Nothing is written to the database. Extraction runs report "found after a move" counts.
- The section-index cache is keyed by SHA-256 with `INDEX_VERSION`, and the old key is still read (V4).

**Phase 3. Relative paths for new downloads** (switch `storage.relative_paths`).
- New downloads and archived responses store root-relative paths with forward slashes (`disclosures/600519/<sha256>.pdf`). Phase 2 reads both forms, so old and new rows work side by side.
- Turning the switch off returns to absolute paths for new rows. Nothing else changes.

**Phase 4. Normalise stored paths** (an explicit command; never a migration, V5).
- `ashare-cli paths-normalise` (preview by default; `--apply` to write), and Settings > Data folder > "Normalise paths". It:
  - backs up the database (SQLite backup function; for PostgreSQL, a dump is advised and the command asks for confirmation);
  - writes every change to a new table, `path_rewrites` (table, row, column, old value, new value, run ID);
  - rewrites absolute paths under the root as relative, and recovered paths (phase 2) to their new place;
  - rewrites the `source_document` columns that hold a local path the same way;
  - verifies by re-resolving every rewritten row.
- `ashare-cli paths-undo RUN_ID` restores the old values from `path_rewrites`.
- Paths that cannot be resolved are left as they are and listed.

**Phase 5. Move or adopt the data folder** (an explicit command).
- **Dry run first, always.** `ashare-cli move-data-folder TARGET --dry-run`, and Settings > Data folder > "Move…", report:
  - the files and their total size;
  - free space on the target;
  - whether the target is empty;
  - whether it is under OneDrive or another synced folder (a warning);
  - whether the target is on the same drive.
- **Move**, which runs only when no job is running:
  1. On the same drive, the folder is renamed (fast, atomic). Otherwise every file is copied with its times (`copystat`), and each document's hash is checked against the database.
  2. The database is copied with SQLite's backup function (V6). Settings, the run log and the pseudonym key are copied with the folder.
  3. Phase 4 runs on the copy, so stored paths become relative.
  4. The setting is switched, the scheduled update is re-created for the new folder, and the move is recorded in the run log with a manifest of what was copied.
  5. The program restarts.
- **Undo.** After a copy, the old folder is left untouched until the author deletes it, so switching the setting back undoes the move. After a rename on the same drive, "Move back" renames it again.
- **Adopt a folder already moved** (for example, restored after a Windows reset) switches without copying, after phase 0's report on the new folder and a hash check on a sample of documents. Phase 2 then finds every document, and phase 4 can be run when the author chooses.

**Tests (all phases).**
- A seeded folder with absolute, relative and command-line-relative paths:
  - moved by rename, by copy, and adopted after a "restore";
  - every document is found;
  - the extraction state is unchanged (nothing re-read);
  - the section indexes are still used.
- A hash mismatch is refused.
- An interrupted copy leaves the old folder in use.
- `paths-undo` restores every value.
- The scheduled task command is re-created (mocked).
- Under Wine: a Windows path with a different user name.
- With PostgreSQL, the database is not copied and the command says so.

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
- **Interference:** the extraction-state table stays the authority on what has been read; the ledger only records attempts and never decides what is skipped. With the switch off, nothing is recorded and every job behaves as in v2.2.

### B4 (R1): interactive chart runtime
1. **Library.** chartjs-plugin-zoom (MIT) with Hammer.js (MIT), at versions that support the bundled Chart.js 4.4.8, is bundled in `ashare/viz/viewer/vendor/`, with licences, and listed in `THIRD_PARTY_NOTICES.txt`. Nothing is fetched from the network.
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
7. **Switch.** With `viz.interactive` off, every page is written exactly as in v2.2; the v2.1 and v2.2 page tests run with the switch on and off.
8. **Publication figures** stay static vector SVG with their CSV. A figure can be written from a zoomed range only by an explicit "Write figure of this range", which records the range in the manifest.

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
2. **Trading calendar.** A bundled data file of SSE and SZSE holidays by year (`ashare/rules/trading_holidays.yaml`), from the exchanges' published notices, with its source for each year. The market data held only check it (review V10). A year missing from the file stops a trading-day count with a message, rather than guessing.
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
1. **Schema.** A new table `entity_identifiers` holds entity, scheme (LEI, USCC, ISIN, REGISTRY), value, source, observed date and confidence. `entities.credit_code` stays the authority for the credit code and is read, not moved; the new table adds other schemes.
2. **GLEIF client.**
   - `ashare/gleif.py` queries `api.gleif.org/api/v1` (no key, public data): search by name, lookup by LEI, registration authority, direct and ultimate parent relationships.
   - It uses the polite HTTP client (B2) and archives raw records like other sources.
   - The data's reuse terms are checked and recorded in `docs/compliance.md` before the first release that includes them.
3. **Matching.**
   - Automatic only on an exact match of the credit code (GLEIF `registeredAs` with the SAMR registration authority) or of the LEI.
   - Name matches go to the Review queue as candidates, with the GLEIF record beside the entity.
   - Nothing is merged without review.
4. **Parents.** GLEIF direct and ultimate parents go into a new table, `external_relationships` (entity, related entity, relation, source, observed date), never into `control_edges`, so the control chains read from reports, the ego map, `ctrl_distance` and the topology view are unchanged (review V8). The ego map can show them as a separate relation, `GLEIF_PARENT`, off by default. A disagreement with a report's chain is listed in Review.
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
- **Channels.** In v2.3.0, alerts appear only on the desktop program's new "Alerts" page, with a count on its side-panel entry, and in a CSV the command line writes (review V11). Email and Windows notifications wait for a later version, after their libraries and the storage of credentials have been reviewed. No public push services are used.
- **Commands:** `watch-add`, `watch-run`, `watch-list`.

### B10: trusted timestamps
- Release manifests and topology and view manifests can be timestamped by an RFC 3161 time-stamping authority, set in Settings. The feature is off by default, and no authority is used until the author chooses one (review V11).
- The library that builds and checks the requests is chosen and its licence checked before the code is written. If none is suitable, the feature waits for a later version.
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
- **Panels.** Built with the default variables, their data and codebook are identical to v2.2.0's; only the manifest's time and version differ (review V12).
- **Switches.** With every new switch off, the full v2.2.0 suite passes unchanged, and so does every page test.

**Tests.**
- A test file `tests/test_v23.py`, with the tests named under each part, plus `tests/test_v23_paths.py` for B1's phases.
- The suite runs twice: with the v2.3 switches at their defaults, and with every switch off.
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
