# Change log

This log records what changed in each version and the important findings behind the changes. The live-run findings are kept in full in `docs/live_run_findings_v2.0.2.md` (findings 1 to 19) and `docs/live_run_findings_v2.0.3.md` (findings 20 to 34). Earlier versions are described in `README.md` and in section 18 of `ashare_scraper_build_plan.md`.

## v2.0.4 (18 October 2026)

**Aim:** close the catalogue gaps on the busiest disclosure days. The plan is in `docs/plan_v2.0.4.md`, and the findings behind it are 20 to 34 in `docs/live_run_findings_v2.0.3.md`.

The first live whole-market catalogue under v2.0.3 confirmed the 3,000-result limit and the resume, but left 12 days short. The causes:
- `sz` and `sh` cover whole exchanges, so the board split never isolated the main boards (finding 22);
- categories still over 3,000 on one board on the April deadline days (23);
- announcements on neither the Shanghai nor the Shenzhen board (24);
- rows repeated for several securities (25).

Whether CNINFO supports finer splits (separate main-board codes, the industry field, several companies at once, sort order) is not documented anywhere. v2.0.4 is therefore built to find out as it runs and to use only what works, rather than to assume.

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

These need the user's network. The build environment cannot reach CNINFO or Eastmoney.

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
