# v2.0.4 patch plan: a complete catalogue on the busiest days

**Status:** implemented as v2.0.4, 18 October 2026 (see `CHANGELOG.md`). Departures from the plan, decided during the build:
- the engine checks every filter as it runs, as well as the separate probe command;
- both sort orders were added as a split;
- the early stop applies only after a split;
- the outcome for gaps is exit code 3, not 2, because the command-line library uses 2 for usage errors.
**Basis:** the v2.0.3 live-run findings 20 to 34 (`docs/live_run_findings_v2.0.3.md`).
**Aim:** close the catalogue gaps on the busiest disclosure days (late March and the April annual-report deadline), before the v2.1 work begins. This is a patch: no interface language, speed or polish work belongs here.

## 1. What the live runs established

**Confirmed working:**
- CNINFO returns at most 3,000 results to one query (finding 20; `probe-cninfo-paging` gave LIMIT_CONFIRMED live).
- Paging stops correctly, resume by day works (finding 21), and the quote list answers (finding 33).
- All periodic reports were catalogued in full.

**Still wrong.** Twelve days are short of CNINFO's total, for four reasons:

| Cause | Finding | Effect |
|---|---|---|
| Board codes overlap: `sz` includes ChiNext and `sh` includes STAR | 22 | The board split never isolates the main boards; queries repeat |
| A category is still over 3,000 on one board (日常经营, 公司治理, 中介报告 on 28 to 30 April) | 23 | Announcements beyond 3,000 are lost; up to 18% of a day |
| Announcements on neither the Shanghai nor the Shenzhen board (probably Beijing) | 24 | They make a day SHORTFALL although Beijing is outside the default scope |
| Rows sharing one announcement ID (one row per security) | 25 | Small "shortfalls" that may be false alarms |

**Smaller problems:**
- re-catalogue repeats the same queries (26);
- the last pass pages without gain (27);
- totals grow after the fact (28);
- "Failed" wording for a completed run (29);
- the unmatched count needs a check (30).

## 2. Step 1: probes before any engine change

The fixes depend on CNINFO behaviour that is not documented. The first deliverable is therefore a probe command, `probe-cninfo-filters --day 2026-04-29`, which needs about 60 to 120 requests. It reports each test with a verdict and saves the raw answers.

| Test | What it checks | Accepted when |
|---|---|---|
| Disjoint boards | Totals for `szmb`, `szcy`, `shmb`, `shkcp` and `bj` (candidate codes; others tried if these fail) | Main board and ChiNext add up to `sz`; Shanghai main board and STAR add up to `sh`; all five add up to the day's total |
| Industry filter | 日常经营 on one board, split by the `trade` field over the CSRC industry sections | The industry totals add up to the parent total, and each part is under 3,000 |
| Company batches | The `stock` field with several companies at once | The batch total equals the sum of single-company totals |
| Title keyword | The `searchkey` field (last resort) | Totals are consistent and partition the parent (keywords rarely do, so this is used only as a supplement) |
| Repeated rows | For the quiet windows of 9 to 12 and 27 January, whether repeated IDs carry different security codes | Different codes: rows per security (a false alarm); the same code: unstable ordering |

The engine uses only the split dimensions the probe confirms. It also re-checks every split while it runs (section 3, item 2), so a later change at CNINFO shows up as a reported gap and never as silent loss.

## 3. Step 2: engine changes (`market_catalogue.py`)

1. **Disjoint boards.** The confirmed codes for the Shenzhen main board, ChiNext, the Shanghai main board, STAR and Beijing replace the overlapping list. Beijing is always queried in the split, even when it is off for the dataset, so that the day's total can be accounted for.
2. **A general splitter.** Any query over 3,000 is split along the next confirmed dimension, in the order day, category, board, industry, then company batches, until every part is under the limit.
   - Each split is checked: the parts' totals must add up to the parent's total.
   - A shortfall in that check is recorded as "partition incomplete", with the amount. It is never ignored.
3. **Rows, not just IDs.** Rows are keyed by announcement ID and security code, so a second security of the same announcement is kept (and linked, where it is in scope).
   - The day's completeness check compares rows with CNINFO's total.
   - Repeated IDs are counted separately and reported as "rows for several securities".
4. **Gaps by board.** Each day records its gap within the enabled boards and its gap outside them (for example Beijing when off).
   - A day is DONE when the gap within the enabled boards is zero.
   - A gap outside the enabled boards is noted but does not make the day a shortfall.
5. **Early stop for the last pass.** A query that brings no new row for 5 consecutive pages stops. On 24 April this would have saved about 300 queries.
6. **Strategy-aware re-catalogue.** Each day records the strategy version that produced it.
   - `recatalogue-busy-days` selects shortfall days whose strategy is older than the current one, and the days earlier versions cut short.
   - A day whose gap recurs unchanged under the current strategy is not fetched again. The command says plainly that the gap is a limit of CNINFO's search, not a network error.
7. **Recheck recent totals.** At the start of each whole-market run and in the daily update, the totals of the last 30 finished days are compared with CNINFO's current totals (about 15 queries). A day whose total has grown is fetched again.
8. **Outcome wording.** A run that finishes with gaps ends with exit code 3 and "Finished with gaps (N days; see the list)". The desktop shows that instead of "Failed". Exit code 1 stays for errors.
9. **Unmatched announcements.** The count is split by reason (Beijing, B shares, bonds and funds, unknown code), and the counting is checked against the stored rows (finding 30).

## 4. Database

Migration `0004_v204_catalogue_detail` adds columns to `catalogue_days`:
- rows expected;
- rows stored;
- rows for several securities;
- the gap within and outside the enabled boards;
- the partition check result;
- the strategy version.

Existing records keep their values, and the new columns are filled when a day is next fetched.

## 5. Tests

The mock CNINFO is extended to behave as the live service does:
- overlapping board codes (`sz` containing ChiNext; `sh` containing STAR);
- a Beijing board;
- a category over 3,000 on one board;
- rows repeated for several securities;
- totals that grow between runs;
- an industry filter and company batches.

New tests cover:
- **The acceptance day:** a day shaped like 29 April 2026 (26,066 announcements, with 日常经营 at 8,772 on Shenzhen) stored in full within the enabled boards.
- **Partition checks:** a split whose parts do not add up is recorded as "partition incomplete".
- **Rows for several securities:** reported separately and not counted as a shortfall.
- **Gaps by board:** a Beijing-only gap leaves the day DONE when Beijing is off.
- **Early stop:** the last pass stops after 5 pages with nothing new.
- **Re-catalogue:** skips days whose gap recurred under the current strategy.
- **Recheck:** a day whose total grew is fetched again.
- **Exit codes:** 3 for gaps and 1 for errors, with the desktop wording.
- **Probe verdicts** for each test.

The full matrix runs as for v2.0.3:
- Linux Python 3.12 and 3.13;
- PostgreSQL 16;
- Windows under Wine;
- GitHub CI.

## 6. Live acceptance (user)

1. `ashare-cli probe-cninfo-filters --day 2026-04-29`. Keep the output.
2. `ashare-cli recatalogue-busy-days --kind all`. This re-catalogues the 12 shortfall days; expect a few hours, since the busiest days need well over 1,000 queries each.
3. `ashare-cli catalogue-days --kind all --problems`. The expected result is no day with a gap within the enabled boards.
4. 24 April: the rows within the enabled boards match CNINFO's total for those boards.

If a gap remains after step 3, its size and the probe output decide whether a further dimension is needed. The gap stays recorded and reported in the meantime.

## 7. User actions now possible with v2.0.3

These need no new build:
- **Listing dates.** The quote list answers now (finding 33), so run "Update the company list" to fill them in.
- **Panels.** Then build a panel by quarter or month; it should have rows without the report-evidence fallback.
- **Daily prices.** The whole-market price download had started when the log ended; its output will show whether it completes (finding 34).

## 8. Release

- Version 2.0.4.
- CHANGELOG.md with changes and findings.
- The user guide section on the whole-market catalogue updated.
- Windows build, installer and portable zips.
- Commits in the user's name only.
