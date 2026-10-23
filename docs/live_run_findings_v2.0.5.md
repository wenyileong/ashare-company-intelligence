# v2.0.5 live-run findings: the first live run of the v2.0.4 catalogue engine

**Source:** the author's desktop log of 23 October 2026. The catalogue engine is the one introduced in v2.0.4 and unchanged in v2.0.5. The log has seven actions:

1. a whole-market catalogue, kind "all", 29 April to 23 October 2026: 6 days fetched, 172 skipped, 183 queries, 4 min 34 s;
2. "Re-catalogue busy days" for 15 days, stopped by the author at 23 April after 1 h 36 min;
3. "Build a panel", yearly, 2026;
4. "Which days are catalogued", problems only;
5. the paging-limit probe (`probe-cninfo-paging`, 24 April);
6. the whole-market catalogue run again (1 day fetched, the current day);
7. "Extract figures from reports", kind "all", which had just started when the log ended.

`probe-cninfo-filters` was not run. The engine checked the filters itself during the re-catalogue (finding 35).

**Status:** findings only; no code has been changed. Numbering continues from the v2.0.3 findings (`docs/live_run_findings_v2.0.3.md`, findings 20 to 34).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 35 | The disjoint board codes, the category filter and the industry filter work live; 31 March, 21 April and 22 April are now complete | Information (findings 22 and 23 resolved for those days) | Confirmed |
| 36 | 23 to 30 April have not yet been re-catalogued under the v2.0.4 engine; the run was stopped first | Information | Open: run again |
| 37 | CNINFO's explicit time order is unstable: a sorted query repeats rows across its own pages far more than the default order does | High (the both-orders reading reaches less than designed) | Confirmed from counts; cause inferred |
| 38 | The sorted passes stop well before their last page | High (rows left unread) | Probable, inferred from the progress lines |
| 39 | 9 to 12 January still lacks 13 rows: the window is under the limit, so the engine has no split to try | Medium (13 of 2,954 rows) | Confirmed |
| 40 | A window's gap is shown against every day in it | Low (reporting) | Confirmed |
| 41 | No company has a listing date, so every panel row is included by report evidence | High (the point-in-time universe is not in use) | Confirmed; cause to check |
| 42 | Extraction reads only documents already downloaded; the log ends before its first progress line | Information | Open |
| 43 | Smaller points: the current day is counted as "finished"; no recent totals had grown; 27 January is now complete | Low | Confirmed |

**The overall state.** Of 296 days, 284 are DONE, 1 is OPEN (the current day) and 11 are SHORTFALL. Seven of the eleven (23 to 30 April) still carry their v2.0.3 results (finding 36). The other four are the 9 to 12 January window, which is short by 13 rows in all (findings 39 and 40).

## 35. The board, category and industry filters work live

**Evidence.** The re-catalogue split the busy days by the disjoint board codes (`szmb`, `szcy`, `shmb`, `shkcp`, `bj`), which CNINFO honoured.
- **22 April.** The five board totals (1,673, 2,315, 2,173, 832 and 583) add up exactly to the day's 7,576.
- **21 April.** The four Shanghai and Shenzhen boards hold 7,983 of 8,367. The remaining 384 match the Beijing board, which brought no progress line because it is under 600 rows.
- **31 March.** The four Shanghai and Shenzhen boards hold 11,898 of 12,213, leaving 315 for Beijing.

All three days ended "complete": 31 March with 12,213 rows (method `board_disjoint+sort_both+category+trade`), and 21 and 22 April with the board split alone.

The category split works. On 31 March the Shenzhen main board (3,445) was complete after its 26 categories. The industry filter (`trade`) also works. The Shanghai main board on 31 March reached 3,877 of 3,878 by category, and the industry split (for example 制造业, 2,335 rows) brought in the last row.

**Assessment.** Plan items 1 and 2 of v2.0.4 (disjoint boards; a general splitter) hold live. The company-batch filter (`stock`) was not needed and remains untested live.

## 36. 23 to 30 April are still to be re-catalogued

**Evidence.** The re-catalogue was stopped at 23 April after 1 h 36 min ("stopped by the user; everything saved so far is kept"). In `catalogue-days`, 23 to 30 April still show the v2.0.3 method (`CATEGORY_AND_PLATE_SPLIT`), with the old gaps: for example, 21,338 of 26,066 on 29 April.

**Assessment.** This is not a fault. Running "Re-catalogue busy days" again resumes with these seven days. Together they hold about 111,000 announcements, so the run will take several hours. Their result shows whether the engine closes the April gaps, and is needed before the next patch is settled.

## 37. The explicit time order is unstable

**Evidence.** The progress lines give the distinct rows collected so far within one query, which shows how often a query repeats rows across its own pages.

| Query | Order | Rows after 20 pages (of 600 read) |
|---|---|---|
| 9 to 12 January | CNINFO's default | 598 (2,380 after 80 pages) |
| 9 to 12 January | newest first | 570 |
| 9 to 12 January | oldest first | 515 |
| 31 March, Shenzhen main board | newest first | 466 |
| 31 March, Shenzhen main board | oldest first | 444 |
| 31 March, Shanghai main board | newest first | 458 |
| 31 March, Shanghai main board | oldest first | 468 |
| Every board query in the default order | CNINFO's default | 600 |

The reported total also varied between requests for the same window: 2,954 in the default and oldest-first queries, 2,952 newest first.

**Assessment.** In the default order a query repeats few rows: 20 in 2,400 for the January window, none for the board queries. Sorted explicitly by time, it repeats between 5% and 26% of the rows within its first 20 pages. The probable cause is that many announcements share one publication time, and CNINFO orders such ties differently from one request to the next. The both-orders reading (v2.0.4) therefore reaches fewer than the 6,000 rows it was designed for. It still helped: 27 January is now complete (finding 43). On 31 March the category split, not the sorted reading, completed both main boards.

## 38. The sorted passes stop before their last page

**Evidence.** Progress lines are printed every 20 pages.
- **9 to 12 January** (99 pages). The newest-first pass prints pages 20 and 40 and nothing after, and so does the oldest-first pass.
- **31 March.** The Shenzhen main board's newest-first pass stops printing after page 60 of 100, and its oldest-first pass after page 20. The Shanghai main board's two passes both stop after page 20.

**Assessment (probable).** The reading of a query ends at the first page that brings no row new to that query. In the default order that reliably means CNINFO has run out of rows. With the unstable time order of finding 37, a whole page of repeats can occur long before the end, so the sorted passes probably stop early and leave rows unread. The log does not show the page each pass stopped at, so this is inferred, not confirmed.

## 39. 9 to 12 January: 13 rows short, with no split to try

**Evidence.** The window holds 2,954 announcements (four days, under the 3,000 limit, so it is read as one query). The default reading, then both sorted readings, brought 2,941 rows: "SHORTFALL, 2,941 of 2,954 rows received; 13 missing within the enabled boards". No split was tried.

**Assessment.** Under v2.0.4 a query is split only when it exceeds the limit. Below the limit, when rows are missing, the engine only reads the query again in the two time orders, which finding 37 shows to be the least stable readings. Finding 25 (v2.0.3) noted repeated rows on these quiet days. The present runs record no rows for several securities (`rows_multi` is 0 throughout), so the repeated rows are better explained by unstable ordering than by securities sharing an announcement. The likely remedy is to split a short window even under the limit: into single days first, then by the disjoint boards (finding 35). Smaller queries are read in fewer pages and give ties less room to move.

## 40. A window's gap is shown against every day

**Evidence.** `catalogue-days` lists 9, 10, 11 and 12 January each with a gap of 13 within the enabled boards, and no expected total. The rows stored are 1,168, 1,230, 0 and 543 (11 January is a Sunday). The gap is one gap of 13 for the window, but the table reads as 52, and the status line counts the window as four SHORTFALL days.

**Assessment.** A reporting fault. The window's total and gap should be recorded and shown once, for example as "9 to 12 January (window): 13 short", with the days marked as part of it.

## 41. No company has a listing date

**Evidence.** The yearly panel for 2026 has 5,225 rows: `included_by_report_evidence: 5225`, `excluded_no_listing_date: 5576`. Every row is included by report evidence, which means no company in the list has a listing date. The panel's `max_published_date` is empty, consistent with no financial facts having been extracted yet (finding 42).

**Assessment.** The quote list answered in the v2.0.3 live self-test (finding 33). Listing dates are filled when "Update the company list" runs, and the log does not show that action. The probable cause is that it has not been run since v2.0.3, but this needs checking. Next step: run "Update the company list" and note the number of listing dates it reports. If that number is zero while the quote list answers, the filling of listing dates is at fault and belongs in the next patch.

## 42. Extraction reads only downloaded documents

**Evidence.** "Extract figures from reports" (kind "all") had printed only its first line when the log ended. Both catalogue runs used `--no-download-documents`.

**Assessment.** Extraction works only on documents already downloaded, so reports catalogued without download are not extracted until `download-documents` fetches them. Extraction prints a line every 25 documents. At about 9 seconds per document (finding 32), the first line comes after about 4 minutes, so the empty log is no sign of a fault. The speed is the subject of v2.1, workstream B.

## 43. Smaller points

- **The current day.** The catalogue summary says "6 day(s) finished" while `catalogue-days` shows 23 October as OPEN. The current day is deliberately kept open and fetched again, as the second run did (its total grew from 1,552 to 1,556). The summary should say "5 finished; today kept open".
- **Recheck of recent totals.** `days_rechecked` was empty: no recent finished day had grown (plan v2.0.4, item 7).
- **27 January** is now complete. The default reading fell short, and the oldest-first reading brought in the rest.
- **The paging limit** was confirmed again (LIMIT_CONFIRMED, 24 April).
- **Unmatched rows** are now reported by reason: on 18 to 23 October, 305 Beijing, 5 B shares and 4 codes not recognised.

## Proposed next steps

**For the author, before any build:**
1. Run "Re-catalogue busy days" again to finish 23 to 30 April (finding 36). Keep the log.
2. Run "Update the company list" and note how many listing dates it reports (finding 41).
3. Optionally, `probe-cninfo-filters --day 2026-04-29`, which also tests the company-batch filter.

**Probable contents of a v2.0.6 patch,** to be settled once those results are in:
1. Sorted passes stop only after several pages with nothing new, or at their last page, not at the first repeated page (finding 38).
2. A window or query short of its total is split even when under the limit, first into single days, then by board and category (finding 39).
3. A window's gap is recorded and shown once (finding 40); the summary distinguishes the current day (finding 43).
4. Listing dates, if step 2 shows they are not filled (finding 41).
5. Whatever 23 to 30 April show under the current engine.
