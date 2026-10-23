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

**Second log (findings 44 to 51).** A later copy of the same log adds three actions: extraction stopped after 5 min 37 s; "Re-catalogue busy days" run again, which finished 23 to 30 April in 2 h 15 min; and "Update the company list". It corrects finding 42.

**Status:** findings only; no code has been changed. Numbering continues from the v2.0.3 findings (`docs/live_run_findings_v2.0.3.md`, findings 20 to 34).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 35 | The disjoint board codes, the category filter and the industry filter work live; 31 March, 21 April and 22 April are now complete | Information (findings 22 and 23 resolved for those days) | Confirmed |
| 36 | 23 to 30 April had not yet been re-catalogued under the v2.0.4 engine; the run was stopped first | Information | Closed by finding 44 |
| 37 | CNINFO's explicit time order is unstable: a sorted query repeats rows across its own pages far more than the default order does | High (the both-orders reading reaches less than designed) | Confirmed from counts; cause inferred |
| 38 | The sorted passes stop well before their last page | High (rows left unread) | Probable, inferred from the progress lines |
| 39 | 9 to 12 January still lacks 13 rows: the window is under the limit, so the engine has no split to try | Medium (13 of 2,954 rows) | Confirmed |
| 40 | A window's gap is shown against every day in it | Low (reporting) | Confirmed |
| 41 | No company has a listing date, so every panel row is included by report evidence | High (the point-in-time universe is not in use) | Cause found: finding 50 |
| 42 | Extraction reads only documents already downloaded | Information | Corrected by finding 51 |
| 43 | Smaller points: the current day is counted as "finished"; no recent totals had grown; 27 January is now complete | Low | Confirmed |
| 44 | 23 to 30 April are re-catalogued: six of the seven days are complete, and the seven days' gap fell from 11,597 rows to 20 | Information (findings 23 and 24 resolved) | Confirmed |
| 45 | The last 20 rows on 29 April sit in one query over the limit that no available filter can split | Medium (20 of 26,066 rows) | Confirmed |
| 46 | The same over-limit query was read twice on 29 April, and another twice on 30 April | Low (efficiency) | Confirmed |
| 47 | The engine turned the time order off during the run | Information | Confirmed; cause inferred |
| 48 | The company-batch filter does not work as built | Medium (no fallback below industry) | Confirmed; reason to probe |
| 49 | 9 to 12 January was not fetched again, as designed | Information | Confirmed |
| 50 | The quote list stops after 10 of 56 pages, and the reason is not shown; listing dates are filled for the companies fetched | High (finding 41) | Confirmed; cause inferred |
| 51 | Extraction prints no progress and does not resume, although its Stop message says it does | Medium (wording; and every rerun starts again) | Confirmed from the code |

**The overall state.** After the first log, 284 of 296 days were DONE, 1 OPEN (the current day) and 11 SHORTFALL. After the second, only five days remain short: 29 April by 20 rows (finding 45), and the 9 to 12 January window by 13 rows in all (findings 39 and 40). That is 33 rows in all, against 29,020 announcements on those five days.

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

**Assessment.** Extraction works only on documents already downloaded, so reports catalogued without download are not extracted until `download-documents` fetches them. (This finding first said that extraction prints a line every 25 documents. That is wrong: see finding 51.)

## 43. Smaller points

- **The current day.** The catalogue summary says "6 day(s) finished" while `catalogue-days` shows 23 October as OPEN. The current day is deliberately kept open and fetched again, as the second run did (its total grew from 1,552 to 1,556). The summary should say "5 finished; today kept open".
- **Recheck of recent totals.** `days_rechecked` was empty: no recent finished day had grown (plan v2.0.4, item 7).
- **27 January** is now complete. The default reading fell short, and the oldest-first reading brought in the rest.
- **The paging limit** was confirmed again (LIMIT_CONFIRMED, 24 April).
- **Unmatched rows** are now reported by reason: on 18 to 23 October, 305 Beijing, 5 B shares and 4 codes not recognised.

## 44. 23 to 30 April are re-catalogued

**Evidence.** The second "Re-catalogue busy days" skipped the January window (finding 49) and fetched the seven April days: 110,806 rows in 5,320 queries, 2 h 15 min (about 0.66 queries a second). Six days ended "complete": 23, 24, 25, 27, 28 and 30 April. 29 April ended 26,046 of 26,066. Before the run, the seven days were short by 11,597 rows in all (from 586 on 23 April to 4,728 on 29 April); now they are short by 20. 8,684 rows were new to the database, and 5,302 of the rows were Beijing announcements, which are outside the enabled boards.

**Assessment.** The v2.0.4 engine closes the April gaps. The splits used were the disjoint boards and the categories, with the industry filter on 28, 29 and 30 April. This is the live acceptance the v2.0.4 plan asked for (section 6), short of 20 rows on one day.

## 45. The last 20 rows on 29 April: one query that cannot be split further

**Evidence.** On 29 April, 日常经营 (`rcjy`) on the Shenzhen main board, restricted to manufacturing (制造业), holds 3,024 announcements, 24 more than one query returns. The reading stopped at page 100 with 3,000 rows, and the Shenzhen main board ended at 9,068 of 9,088. The query is already split by board, category and industry. The run's summary shows why nothing further was tried: `'filters': {'board_scheme': 'disjoint', 'sort': False, 'stock': False}`. The company-batch filter does not work (finding 48), and the time order had been turned off (finding 47).

**Assessment.** A finer dimension is needed for queries like this one, which will recur each April as the number of companies grows. Possible dimensions, in order of preference:
1. **Sub-industries.** The CSRC manufacturing section has about 30 divisions (C13 to C43). Whether CNINFO's industry field accepts division codes is not known; the probe can test it in a few requests.
2. **Single companies.** The per-company query is known to work (`--per-company`). It would cost one query per manufacturing company on the board (roughly a thousand) for 24 rows, so only as a last resort and only for a query just over the limit.
3. **Title keywords** (the `searchkey` field), as a supplement only.

## 46. The same query read twice

**Evidence.** On 29 April the query `rcjy/szmb/制造业` (100 pages) was read once within the category split of the Shenzhen main board, and again within its industry split (`szmb/制造业` by category). On 30 April `rcjy/shmb/制造业` (65 pages) was read twice in the same way.

**Assessment.** A split by category then industry and a split by industry then category reach the same leaves. About 165 queries were repeated on these two days. The engine should remember the leaves already read in a day and not fetch them again.

## 47. The time order was turned off

**Evidence.** Sorted passes appear on 23 April (`szcy/desc`, `shmb/desc`) and on no later day; the summary records `'sort': False`. No oldest-first pass follows the newest-first ones on 23 April.

**Assessment (inferred).** The engine turns sorting off when the first page oldest-first matches the first page newest-first, which it takes to mean the order is ignored. Under a board filter CNINFO may ignore the order, or the ties of finding 37 may make the first pages match. With finding 37, sorting is of little use either way. Turning it off saved queries: the April days were read by splits alone. The switch applies to the whole run, so it also removes sorting from queries where it may work; a patch should either decide per kind of query or drop the sorted reading.

## 48. The company-batch filter does not work as built

**Evidence.** The summary records `'stock': False`. The engine sets this when a split by batches of companies returns nothing, or returns the parent's total for every batch.

**Assessment.** The engine asks for up to 150 companies at once (`code,orgId;code,orgId;...`). CNINFO either rejects the list or ignores it. Whether a single company works within a day query, and whether smaller batches work, is not known. `probe-cninfo-filters` tests this and shows which; it is the next step for finding 45.

## 49. 9 to 12 January was not fetched again

**Evidence.** "Not fetched again: 4 day(s) whose gap recurred under the current method (2026-01-09 ... 2026-01-12)".

**Assessment.** As designed (plan v2.0.4, item 6): the same queries cannot close the gap. The window is fetched again once a later version changes the method (finding 39).

## 50. The quote list stops after 10 pages

**Evidence.** "Update the company list" reported: "999 listing dates added. Note: quote list incomplete: 10 of 56 pages fetched (1000 companies); their listing dates were applied." The status line counts 994 listed and 165 delisted, both for the companies fetched only. The run took 65 seconds.

**Assessment.** Listing dates are filled correctly for the companies whose pages arrived, so finding 41 is not a fault in the filling. The download stops at page 11 because every request variant failed for that page. The program keeps the error but does not print it, so the cause cannot be read from the log. The likely cause is that Eastmoney refuses further requests after about ten in quick succession. The cache keeps the pages fetched today, so running the action again continues at page 11, and about five more runs would finish the list if each gets ten pages. A patch should print the error, wait and retry before giving up (for example 30 seconds, then a few minutes), and pace the quote list more slowly than the other sources.

## 51. Extraction prints no progress and does not resume

**Evidence.** "Extract figures from reports" printed only its first line and was stopped after 5 min 37 s: "Stopped: stopped by the user; everything saved so far is kept, and running it again resumes". The code of `extract-financials` prints nothing until it has finished every company. The line every 25 documents belongs to a different command (the disclosure pipeline). On a new run it starts again at the first company and reads every downloaded document again. Facts already saved are updated, not duplicated.

**Assessment.** The Stop message is wrong for this command, and finding 42's statement about progress lines was wrong. A long extraction gives no sign of progress, and stopping it throws away its place. A patch should:
- print progress: documents done and remaining, seconds per document, and an estimated finish;
- skip documents already extracted with the current parser version, so that a rerun continues;
- give a Stop message that is true for the command.

Speed itself remains v2.1, workstream B. With `--kind all` the command reads every downloaded document, not only periodic reports; `--kind reports` (the default) is the usual choice.

## Proposed next steps

**For the author, before any build:**
1. Run `ashare-cli probe-cninfo-filters --day 2026-04-29` (about 70 to 120 requests) and keep the output. It shows why the company-batch filter fails and whether the time order is honoured (findings 45, 47 and 48).
2. Run "Update the company list" again, perhaps a few minutes apart, until the note about an incomplete quote list disappears (finding 50). Then rebuild the panel.

**Probable contents of a v2.0.6 patch:**
1. **The quote list:** print the error, wait and retry, and pace it more slowly (finding 50).
2. **Extraction:** progress, resume and a true Stop message (finding 51).
3. **A finer split for queries just over the limit:** sub-industries if CNINFO accepts them, otherwise single companies as a last resort, settled by the probe (finding 45).
4. **Short windows under the limit:** split into single days, then by board (finding 39). The sorted passes stop only after several pages with nothing new, or are dropped (findings 38 and 47).
5. **No repeated leaves:** a query read once in a day is not read again (finding 46).
6. **Reporting:** a window's gap shown once (finding 40), and the current day distinguished (finding 43).
