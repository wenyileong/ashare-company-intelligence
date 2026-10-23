# v2.0.6 patch plan: listing dates, extraction you can follow, and the last catalogue gaps

**Status:** planned, 23 October 2026; not yet built.
**Basis:** the v2.0.5 live-run findings 35 to 57 (`docs/live_run_findings_v2.0.5.md`): three logs of 23 October 2026, including `probe-cninfo-filters` for 29 April.
**Aim:** a patch before v2.1, in order of importance:
1. listing dates for the whole company list, so that panels can use the point-in-time universe;
2. an extraction that shows its progress and can be stopped and resumed;
3. the last 33 catalogue rows (29 April, and the 9 to 12 January window).

No interface language, speed or polish work belongs here; that is v2.1.

## 1. What the live runs established

**Confirmed working:**
- **Disjoint board codes.** These partition every busy day exactly (findings 35 and 52).
- **Category and industry filters.** These also partition exactly (findings 35 and 53).
- **The April gaps.** These fell from 11,597 rows to 20 (finding 44).
- **Re-catalogue.** It skips days whose gap recurs under the current method (finding 49).
- **Listing dates.** These are filled correctly for every company whose quote-list page arrives (finding 50).

**Still wrong:**

| Problem | Findings | Effect |
|---|---|---|
| The quote list stops at page 10 every time, and the error is not shown | 50, 57 | Listing dates for about 1,000 of 5,577 companies; panels fall back on report evidence |
| Extraction prints no progress and restarts from the beginning, though its Stop message says it resumes | 42, 51 | A long run cannot be followed or interrupted |
| 29 April: 日常经营, Shenzhen main board, manufacturing, holds 3,024 rows, and no working filter splits it | 45, 53 | 20 rows missing |
| The company filter fails, or the probe cannot tell | 48, 54 | No split below industry |
| Rows move between pages in a query, in both orders, and sorted reading stops at the first repeated page | 37, 38, 56 | 13 rows missing in 9 to 12 January |
| One error turns sorting off for the whole run | 47, 55 | Sorting lost where it could help |
| The same leaf query is read twice | 46 | About 165 wasted queries on two days |
| A window's gap is shown against each day, and the current day is counted as finished | 40, 43 | Misleading reports |

## 2. Workstream A: the quote list (findings 50 and 57)

1. **Print the error.** When a page fails, the message names the page and what each variant returned (for example "page 11: answer without data (rc=...)").
2. **Read the list in parts.** If a page beyond the first fails while earlier pages answered, the list is read one board at a time (the `fs` field takes one board: Shenzhen main, ChiNext, Shanghai main, STAR), each in both code orders (`po` 1 and 0). This covers up to 2,000 companies per board, if the cause is a limit of 1,000 rows per query. The rows are merged by code, and the list counts as complete when every board's total is reached.
3. **Retry with a pause.** A failed page is retried after 30 seconds and again after two minutes before the part is given up. Only then is the list reported incomplete.
4. **Pace.** The quote list runs at no more than one request every two seconds.
5. **Diagnosis.** `diagnose-quote-list` also requests page 11, and page 11 of one board, and reports both. This confirms or refutes the cause, at about four extra requests.

**Accepted when** "Update the company list" adds listing dates for at least 5,000 companies, and the panel's `excluded_no_listing_date` falls accordingly.

## 3. Workstream B: extraction (findings 42 and 51)

1. **Progress.** A line every 25 documents, and at least once a minute: documents done and remaining, seconds per document, and an estimated finish (for example "250 of 9,800 documents; 8.7 s each; about 23 hours left"). The total is counted before the first document.
2. **Resume.** Each document records the parser version that last read it, whether or not it yielded facts (migration 0005: two columns on `disclosures`). A rerun skips documents already read by the current version, so a stopped run continues where it stopped. `--again` reads every document anyway.
3. **Stop wording.** The Stop message says what is true for each command. For extraction it becomes "documents read so far are saved; running it again continues with the rest".
4. **Kind.** The desktop action uses `--kind reports`, the periodic reports, by default. "All downloaded documents" is a separate choice, since most announcements carry no financial statements.

**Accepted when** a stopped extraction, run again, starts with the next document. A test covers this.

## 4. Workstream C: the catalogue engine (findings 37 to 40, 43, 45 to 48, 54 to 56)

1. **A probe that can tell.** `probe-cninfo-filters` and the engine test the company filter with companies known to have announcements that day (from the stored rows), sending each company's own exchange (`column`) and board.
   - The probe tests one company, two and three, then a batch, and reports where a failure starts.
   - It also tests whether the industry field accepts a manufacturing division (for example 计算机、通信和其他电子设备制造业).
2. **A finer split, in this order, for a query that is over the limit after board, category and industry:**
   1. Manufacturing divisions, if the probe shows that the industry field accepts them.
   2. Company batches, if the probe shows that batches work.
   3. Single companies, as a last resort. Only the companies that appear in the query's rows are queried, so a query just over the limit costs at most a few hundred requests. A missing row may belong to a company not yet seen in the query, so this step can leave a gap. The number of requests is reported, and the step is skipped when it would exceed 1,500 requests; any gap is then recorded as before.
3. **Short windows and days.** A window or day under the limit that is still short after its readings is split by day, then by disjoint board, and the parts are read again. A smaller query moves fewer rows between pages (finding 56).
4. **Sorted reading.**
   - Sorted passes stop after 5 pages with nothing new, or at their last page, not at the first page of repeats.
   - Sorting is turned off only when the first pages match on a query of more than one page. A request that fails is retried like any other, and then counts as a gap, not as proof that sorting is unsupported.
5. **No repeated leaves.** Within a day, a query read once (the same date, board, category, industry and companies) is not read again; its rows are reused.
6. **Strategy 3.** Days recorded under strategy 2 with a gap are fetched again by `recatalogue-busy-days` (the January window and 29 April), since the method has changed.

## 5. Workstream D: reporting (findings 40 and 43)

- **Windows.** A window's total and gap are recorded once. `catalogue-days` shows them on one row (for example "2026-01-09~2026-01-12 (window) SHORTFALL 2,954 2,941 13"), and the status counts windows, not their days.
- **The current day.** The catalogue summary says "5 day(s) finished; today kept open" when the current day is included.

## 6. Tests

The mock CNINFO gains:
- unstable paging (rows moving between pages, in the default order and sorted);
- a leaf over the limit that only manufacturing divisions or single companies can split;
- a company filter that needs the company's own exchange;
- a sorted request that fails once.

The mock quote list stops serving after 1,000 rows per query.

Tests cover each item of sections 2 to 5, including:
- the 29 April acceptance shape (3,024 rows in one leaf);
- the January shape (2,954 rows, moving between pages);
- extraction resume and progress;
- the quote list read in parts.

The full matrix runs as for v2.0.5: Linux Python 3.12 and 3.13, PostgreSQL 16, Windows CPython under Wine (with the installer installed and uninstalled), and GitHub CI.

## 7. Live acceptance (author)

1. "Update the company list". Expect listing dates for at least 5,000 companies. If not, run `diagnose-quote-list` and keep the output.
2. `ashare-cli probe-cninfo-filters --day 2026-04-29`. Keep the output.
3. `ashare-cli recatalogue-busy-days --kind all`. This fetches 9 to 12 January and 29 April again, which probably takes 30 to 60 minutes.
4. `ashare-cli catalogue-days --kind all --problems`. The expected result is no day with a gap within the enabled boards.
5. "Extract figures from reports". Stop it after a few minutes, start it again, and check that it continues and shows its progress.
6. Rebuild the panel. Expect most rows with `universe_basis` from the listing record, not `REPORT_EVIDENCE`.

## 8. Release

- Version 2.0.6.
- Migration 0005.
- CHANGELOG.md with changes and findings.
- The user guide sections on the company list, extraction and the catalogue updated.
- Windows build, installer, portable zips and `SHA256SUMS.txt`.
- Commits in the author's name only.
- The GitHub release published by the author, as for v2.0.5.
