# v2.0.3 live-run findings

**Source:** the user's desktop log of 18 October 2026, with three actions:

1. a whole-market catalogue, kind "all", 1 January to 18 October 2026: 291 days, 8 h 45 min, 22,036 queries;
2. the same action run again;
3. "Re-catalogue busy days", stopped by the user after 1 h 44 min.

An "Extract figures from reports" action had started, but had printed nothing by the end of the log.

**Status:** findings only; no code has been changed. Numbering continues from the v2.0.2 findings (`docs/live_run_findings_v2.0.2.md`, findings 1 to 19).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 20 | CNINFO's 3,000-result limit per query is confirmed live | Information | Confirmed by behaviour |
| 21 | Resume works: the rerun skipped 290 finished days and fetched only the open day | Information | Confirmed |
| 22 | Board codes overlap: `sz` covers all of Shenzhen (including ChiNext) and `sh` all of Shanghai (including STAR) | High (wasted queries; the board split cannot work as designed) | Confirmed from totals |
| 23 | On the busiest April days, some category and board combinations still exceed 3,000, so announcements are lost | **Critical** (missing data on the busiest disclosure days) | Confirmed |
| 24 | Some announcements are on neither the Shenzhen nor the Shanghai board (probably Beijing), and the last pass cannot reach them | Medium (probably outside the dataset's scope) | Inferred; to confirm |
| 25 | Small shortfalls on quiet days coincide with repeated rows within one query | Medium (possibly false alarms) | Confirmed pattern; cause inferred |
| 26 | "Re-catalogue busy days" repeats the same queries and cannot close a gap that the limit causes | High (hours spent for no gain) | Confirmed |
| 27 | The last pass by board pages to the limit even when it brings nothing new | Medium (efficiency) | Confirmed |
| 28 | CNINFO's totals change after the fact | Medium (finished days can grow) | Confirmed |
| 29 | A completed run with shortfalls is shown as "Failed" | Low (wording) | Confirmed |
| 30 | "Unmatched" is exactly 24,000 | Low | To check |
| 31 | The probe and quote-list checks were not run; the extraction step produced no output | Information | Open |

**Periodic reports are complete.** On every day, the periodic-report categories (年度报告, 半年度报告, 第一季度报告, 第三季度报告) stayed within the limit for each board, so no annual, interim or quarterly report was lost. The gaps fall in other announcement categories (finding 23) and on the Beijing board (finding 24).

## 20. The 3,000-result limit is confirmed live

**Evidence.** Every query whose total exceeded 3,000 stopped at exactly 3,000 announcements on page 100. For example: "2026-04-24 remainder/sz: page 100 of 302 (3,000 of 9,046)", after which the engine moved on, because later pages repeated. Queries with totals just under the limit completed in full, for example "2026-01-17~2026-01-20: page 100 of 100 (2,997 of 2,997)".

**Assessment.** This confirms the inference behind finding 6 without `probe-cninfo-paging`. The engine's stop-on-repetition worked: no query paged beyond about 101 pages, so v2.0.2's runaway paging to 2,000 pages did not recur.

## 21. Resume works

**Evidence.**
- The first run recorded 291 days. Today (18 October) was kept OPEN.
- The rerun printed "1 day(s) to fetch, 290 already finished (skipped)", fetched only 18 October and finished in 1.5 seconds.

**Assessment.** Success criterion 2 of the v2.0.3 plan (stop, restart and continue) holds live. The re-catalogue was also stopped by the user, and ended cleanly with the "everything saved so far is kept" message.

## 22. Board codes overlap

**Evidence.**
- On 28 March, the last pass by board reported 3,075 announcements for `sz`, 1,058 for `szcy`, 4,079 for `sh` and 820 for `shkcp`. The day's total was 7,154.
- 3,075 + 4,079 = 7,154 exactly. So `sz` already includes `szcy` (ChiNext), and `sh` already includes `shkcp` (STAR). The four board queries are not a partition of the day.

**Effect.**
- **Wasted queries.** The ChiNext and STAR queries repeat announcements the `sz` and `sh` queries already cover.
- **The split cannot get under the limit.** A category over the limit cannot be brought under it by board when the largest "board" is a whole exchange. The Shenzhen main board on its own is never queried.

**For a future build.**
- Use disjoint boards: Shenzhen main board, ChiNext, Shanghai main board, STAR and Beijing.
- The codes for the two main boards are not yet known. CNINFO's search page is likely to use `szmb` and `shmb`, but this is unverified.
- A probe can verify the codes: the disjoint board totals must add up to the day's total.

## 23. Category and board combinations over the limit (critical)

**Evidence.** On the April shortfall days, some category and board queries exceeded 3,000. Each one returned only 3,000.

| Day | Total | Stored | Gap | Queries over 3,000 (category/board: total) |
|---|---:|---:|---:|---|
| 31 March | 12,213 | 11,856 | 357 | 日常经营/sz: 3,367 |
| 23 April | 13,196 | 12,610 | 586 | 日常经营/sh: 3,398 |
| 24 April | 15,382 | 14,399 | 983 | 日常经营/sz: 4,435 |
| 25 April | 13,724 | 13,275 | 449 | 日常经营/sh: 3,467; 日常经营/sz: 3,349 |
| 28 April | 22,654 | 19,284 | 3,370 | 日常经营/sz: 6,690; /szcy: 3,726; /sh: 3,444 |
| 29 April | 26,066 | 21,338 | 4,728 | 日常经营/sz: 8,772; /szcy: 4,264; /sh: 3,691; 公司治理/sz: 3,172; 中介报告/sz: 3,126 |
| 30 April | 12,639 | 11,613 | 1,026 | 日常经营/sh: 4,355 |

(日常经营 is CNINFO's category `rcjy`, 公司治理 `gszl`, 中介报告 `zj`.)

**Assessment.**
- The categories most affected are daily operations (日常经营), governance (公司治理) and intermediary reports (中介报告, such as audit reports and legal opinions).
- These are the attachments and accompanying announcements filed with annual reports at the deadline.
- On 28 and 29 April the losses are large: about 15% and 18% of the day.
- This is the cause of most of the gap. Disjoint boards (finding 22) reduce it but will not remove it: on 29 April, 日常经营 for all of Shenzhen was 8,772, and the Shenzhen main board alone probably still exceeds 3,000.

**For a future build.** One more split dimension is needed for a category and board still over the limit. In order of preference:
1. **Industry.** The search's `trade` field (CSRC industry sections, about 19). Unverified with an empty stock field.
2. **Company batches.** The `stock` field filled with groups of companies. Whether it accepts several companies at once is unverified.
3. **Title keyword.** The `searchkey` field (for example 董事会, 独立董事, 律师), as a last resort.

Each needs a short probe on a busy day before it is relied on. The day-level check against CNINFO's total stays as the safeguard.

## 24. Announcements on neither the Shenzhen nor the Shanghai board

**Evidence.** On several days, the day's total exceeds the Shenzhen plus Shanghai totals.

| Day | Total | sz + sh | On neither | Gap |
|---|---:|---:|---:|---:|
| 21 April | 8,367 | 7,983 | 384 | 163 |
| 22 April | 7,576 | 6,993 | 583 | 252 |
| 27 April | 7,165 | 6,048 | 1,117 | 455 |

On these days no category and board query exceeded 3,000. So the whole gap lies among announcements on neither board that fall under no category: the categories found the rest, and the last pass, which queries only `sz`, `szcy`, `sh` and `shkcp`, cannot reach them.

**Assessment.**
- These are most likely Beijing Stock Exchange announcements; possibly also other securities CNINFO lists (for example bonds or delisted companies). Beijing is off by default, so most of these are outside the dataset's scope.
- They are still counted against CNINFO's total, so they turn a complete day into SHORTFALL.

**For a future build.**
- Include the Beijing board in the last pass.
- Report the gap by board, so that a gap outside the enabled boards is shown as such and does not make the day a shortfall for the dataset.

## 25. Small shortfalls on quiet days and repeated rows

**Evidence.**
- 9 to 12 January: 2,917 of 2,952 (35 missing). 27 January: 1,613 of 1,614. Both windows are under the limit.
- In both, the progress lines show repeated rows within the query. For example, "page 20 of 99 (597 of 2,952)": 20 full pages should hold 600 distinct announcements, and the shortfall grows page by page.
- The same pattern recurred on the rerun ("page 20 ... (597 of 2,954)").
- These are the only queries in the run with repeated rows.

**Possible causes (not yet distinguished):**
- **Rows sharing an ID.** CNINFO lists one announcement once for each security it concerns (for example a company's A and B shares, or a share and a bond), with the same announcement ID. The engine counts distinct IDs, so the second row looks "missing" although nothing is lost. A second security's link would still be lost (it matters only if that security is in scope).
- **Unstable ordering.** Rows move between pages while paging, so some are never seen.

**For a future build.**
- Key rows by announcement ID and security code, not ID alone.
- Record repeated IDs with their security codes.
- Report "rows sharing an ID" separately from genuine shortfalls.

If the repeated rows carry different security codes, the cause is the first, and these shortfalls are false alarms.

## 26. "Re-catalogue busy days" cannot close these gaps

**Evidence.** The re-catalogue fetched the shortfall days again with the same splits. Every gap recurred with the same count:
- 31 March: 11,856 again;
- 21 to 23 April: 8,204, 7,324 and 12,610 again;
- 9 to 12 January: 2,925 of a new total of 2,954.

It ran for 1 h 44 min before the user stopped it at 24 April.

**Assessment.** The gaps are structural (findings 22 to 25), not transient, so repeating the same queries cannot help.

**For a future build.**
- Re-catalogue only with a strategy the day has not yet had (the new split dimension).
- When a gap recurs unchanged, say so plainly: "the same gap recurred; this is a limit of CNINFO's search, not a network error".

## 27. The last pass pages to the limit even when it finds nothing

**Evidence.** On 24 April, the last pass read 100 pages each for `sz`, `szcy` and `sh`, and all 41 for `shkcp`. That is about 340 queries, and it added nothing: 14,399 announcements before and after.

**For a future build.**
- Stop a last-pass query after a run of pages (for example 5) that bring nothing new.
- Skip the overlapping boards (finding 22).

This would also shorten the whole-market run, which took 8 h 45 min.

## 28. CNINFO's totals change after the fact

**Evidence.** The window 9 to 12 January reported 2,952 announcements in the first run and 2,954 in the re-catalogue, months after those days.

**Assessment.** Announcements can appear later under earlier dates, for example corrections or late uploads. A day recorded as DONE can therefore become incomplete later.

**For a future build.** Recheck the totals of recent finished days, such as the last 30 days, at the start of each run or in the daily update, and fetch any day whose total has grown.

## 29. A completed run with shortfalls is shown as "Failed"

**Evidence.** The first run finished all 291 days ("0 failed") but ended "Failed after 31493.9s". The shortfalls set the error exit code, which the desktop now reports faithfully (the v2.0.3 fix).

**For a future build.** Use a distinct outcome such as "Finished with gaps (12 days short of CNINFO's total)", so that a run with shortfalls is not confused with a run that broke.

## 30. "Unmatched" is exactly 24,000

**Evidence.** The first run reported `'unmatched': 24000`: announcements whose security code is not in the company list (Beijing, B shares, bonds and so on).

**Assessment.** A round figure is possible by chance, but it is worth one check that unmatched announcements are counted, not capped.

## 31. Checks still outstanding

- `probe-cninfo-paging` was not run. Finding 20 makes it less necessary, but its output would still be useful for the record.
- `diagnose-quote-list` was not run, so the quote-list fix (finding 4) is still unverified, and panels by quarter or month may still lack listing dates.
- "Extract figures from reports" had printed nothing when the log ended, so extraction speed (finding 2) and the PDF warning summary (finding 5) cannot yet be assessed from this log.

## What this means for the v2.0.3 success criteria

| Criterion | Result |
|---|---|
| 24 April stored in full (15,382) | **Not met:** 14,399 stored (93.6%). Up to 967 of the missing rows are on neither board, probably Beijing (finding 24); the rest are lost to the limit (finding 23) |
| Stop and restart continue from the last finished day | **Met** (finding 21) |
| A panel with rows, or a refusal with the reason | Not tested in this log |

## Suggested order for the next build

1. **Findings 22 and 23.**
   - Verify disjoint board codes, and choose and verify a further split dimension (industry, company batches or keyword), with short probes.
   - Then re-catalogue the 12 shortfall days.
2. **Findings 24 and 25.**
   - Include the Beijing board.
   - Key rows by announcement ID and security code.
   - Report gaps by board, and separate rows sharing an ID from genuine shortfalls.
3. **Findings 26, 27 and 29.** A re-catalogue only with a new strategy, an early stop for the last pass, and clearer outcome wording.
4. **Finding 28.** Recheck the totals of recent days.

These items come before the v2.1 work in `docs/plan_v2.1.md`, as its section 1 provides, because they concern missing data.
