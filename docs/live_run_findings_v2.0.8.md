# v2.0.8 live-run findings

**Source:** the author's desktop log of 30 October 2026. It includes the first table extractions under v2.0.8:
- "Update the company list" (failed three times);
- "Extract figures from reports" (`--kind all`; stopped, then running at 225 of 1,511 when the log was copied);
- "Read controlling shareholder and actual controller" (stopped once, then complete);
- "Read top-10 shareholders from reports" (complete, then rerun);
- "Extract segments from reports" (complete).

**Second log (findings 103 to 111), 30 October 2026, under v2.0.9.** It covers:
- "Update the company list";
- "Check the company list";
- "Diagnose the quote list";
- the catalogue to 30 October;
- six stopped runs of "Extract figures from reports" (`--kind all`);
- the live self-test;
- "Run all checks";
- a panel for fiscal year 2025.

**Status:** findings only; no code has been changed since v2.0.9. The fixes are planned in `docs/plan_v2.0.10.md`. Numbering continues from `docs/live_run_findings_v2.0.7.md` (findings 70 to 95).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 96 | "Update the company list" failed with a TypeError | High (no company-list updates) | Cause found and fixed in v2.0.9; to confirm on v2.0.9 |
| 97 | Top-10 shareholders: 905 reports in 25 minutes, 1.7 seconds each, against about five minutes each under v2.0.7 | Information (findings 76 and 77 answered for speed) | Confirmed |
| 98 | Top-10 shareholders: only 167 of 905 reports gave rows, 6.9 holders each on average, while the other reader found 1,684 rows the kept one did not | **High** (most reports without shareholder data) | Confirmed from counts; cause to check against reports |
| 99 | The actual controller is now named in 257 of 292 reports (6 of 293 under v2.0.7) | Information (findings 78 and 89 answered) | Confirmed |
| 100 | Segments: 600 reports in 10 minutes, 1.0 second each (51 seconds under v2.0.7); 561 with segments; 72 old rows removed | Information (finding 82 answered) | Confirmed; the sums to check with "Run all checks" |
| 101 | Financial extraction still takes about 36 seconds a document, and `--kind all` gives it 1,511 documents, most of them announcements: about 14 hours | Medium (a long run, mostly for nothing) | Confirmed |
| 103 | "Update the company list" works under v2.0.9; the listing history was rebuilt for 5,230 companies, and the 2025 panel now takes 5,162 of 5,181 rows from the listing record | Information (findings 92 and 96 closed) | Confirmed |
| 104 | The Beijing Stock Exchange and B shares, enabled under Optional boards, are marked "in neither exchange's list" and have no listing dates | **High** (684 listed companies treated as delisted and left out of panels) | Confirmed from counts and the code |
| 105 | Eastmoney answers again: the quote list (over HTTPS) and price histories | Information (finding 73: Eastmoney usable for now) | Confirmed |
| 106 | The self-test showed only the last variant's error for the quote list, an HTTP address, although it tried all of them | Low (misleading) | Confirmed from the code |
| 107 | Financial extraction ran six times with "all" for about 8.5 hours in all: 859 of 1,514 documents read, about 35 seconds each | Medium (finding 101 again) | Confirmed |
| 108 | After the re-reads: balance sheets fail in 7.7% (11% before); discrepancies 260 and segment mismatches 345, both up, with many documents still unread | Medium (cannot be judged until extraction finishes) | Confirmed counts |
| 109 | 5,011 of the 5,181 panel rows have no financial figure: reports are downloaded for 295 companies only | Information (coverage, not a fault) | Confirmed |
| 110 | Corporate actions are now grouped (34,871) | Information (finding 90 closed) | Confirmed |
| 111 | The ownership check covers 166 companies, with two failures | Information | Confirmed |
| 102 | Resume works for the table extractors: the second control run skipped the 14 reports read before the stop, and the second top-10 run skipped all 905 | Information (finding 79 answered) | Confirmed |

## 96. "Update the company list" failed

**Evidence.** "Error: TypeError: '<' not supported between instances of 'NoneType' and 'str'", three times (after 54.5, 50.8 and 162.5 seconds).

**Assessment.**
- **Cause.** v2.0.8 rebuilds the listing history of the companies whose dates changed, and of those whose history had no start date. The rebuild sorted each company's risk-warning changes as pairs of date and warning. A warning imposed and lifted on the same day compared "ST" with None.
- **The fix in v2.0.9.** The changes are sorted by date alone. A failed rebuild no longer fails the update: the update finishes and says to run "Build listing history".
- **Which version failed.** The third failure may have come after v2.0.9 was delivered, but the log does not show which version ran it. If it fails on v2.0.9, the full error is needed: run `ashare-cli update-universe` in a command prompt, where the whole traceback is printed.

## 97. Top-10 shareholders: speed

**Evidence.** "905 of 905 documents; 1.7 s each", done after 1,527 seconds. Five reports were read whole because no table heading was found (`read_whole`), and four are scans without text.

**Assessment.** Targeted reading works on the author's reports: about 170 times faster than the five minutes a report of finding 76. The rerun skipped all 905 reports, as designed.

## 98. Top-10 shareholders: most reports gave no rows

**Evidence.** `{'reports': 167, 'holders': 1145, ..., 'dual_run': {'agree': 147, 'disagree': 159, 'single': 839, 'secondary_only': 1684}}`.

**Assessment.**
- **The shortfall.** Of 905 periodic reports, 167 gave shareholder rows, at 6.9 holders on average where nearly every report has ten.
- **The other reader found more.** It found 1,684 rows under names the kept reader did not produce. The dual run drops such rows on the assumption that they are fragments of broken rows; at this scale they are probably real rows the kept reader missed.
- **Why it matters now.** The rows that were found replace the misread rows of finding 68, but reports without rows keep nothing, so ownership data covers about a fifth of the reports.
- **Cause unknown.** Targeted reading is not shown to be the cause: on the synthetic corpus it gives the same rows as a full reading, and the headings were found in all but five reports. The likelier cause is table layouts the parser does not recognise, as with the Shenzhen layout in finding 68.

**To check.** A few reports without rows:
1. `ashare-cli query "SELECT d.id, c.security_code, d.kind, d.title_cn, d.local_path FROM disclosures d JOIN companies c ON c.id = d.company_id WHERE d.kind IN ('annual_report','interim_report','quarterly_report') AND d.local_path IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ownership_observations o WHERE o.disclosure_id = d.id) ORDER BY d.announcement_date DESC LIMIT 20"`
2. Attach two or three of the PDFs it lists, from both exchanges and one quarterly report, so that the layouts can be read directly.

## 99. The actual controller

**Evidence.** `{'reports': 292, 'with_controller': 257, 'types': {'LOCAL_SOE': 119, 'NO_CONTROLLER': 27, 'CENTRAL_SOE': 54, 'PRIVATE': 77, 'FOREIGN': 7, 'UNKNOWN': 8}}`, at 1.4 seconds a report.

**Assessment.** The new parser names the controller in 88% of reports (257 of 292), and 27 more state that there is none: 97% in all. The plan's target was 80%. The eight UNKNOWN reports are the ones to look at, with `show-flags --rule OWNERSHIP_TYPE_UNKNOWN` after "Run all checks".

## 100. Segments

**Evidence.** `{'reports': 561, 'segments': 5841, 'inserted': 2054, 'updated': 3787, 'dual_run': {'agree': 4146, 'disagree': 1144, 'single': 551, 'secondary_only': 2246}, 'read_whole': 8, 'removed': 72}`, at 1.0 second a report.

**Assessment.**
- **Speed.** About 50 times faster than finding 82.
- **More rows.** 2,054 rows are new: rows after page breaks that v2.0.7 lost. 72 old rows were removed, most likely cost-analysis rows or rows cut at a page break.
- **Still to check.** The readers still disagree on 20% of rows, and the other reader again found many rows the kept one did not (2,246). Whether the sums now match is for "Run all checks" to show: SEGMENT_SUM_MISMATCH should fall from 248 (finding 83).

## 101. Financial extraction: whole documents, and announcements too

**Evidence.** `extract-financials --kind all`: "1,511 document(s) to read from 295 companies", then about 36 seconds a document and "about 13 h 15 min left" at document 225.

**Assessment.**
- **Announcements.** `--kind all` reads every downloaded document. About 900 of the 1,511 are announcements, most of which carry no financial statements (user guide, "Extracting figures"). `--kind reports`, the desktop default ("Reports: reports"), reads the 600 or so periodic reports, which would take about 6 hours at this pace.
- **Speed.** Financial extraction is the one table extractor still reading whole documents: plain text and layout of every page, for the headline figures and the three statements. Targeted reading has the same remedy here: the key-figures page and the consolidated statements are found by their headings (主要会计数据和财务指标, 合并资产负债表, 合并利润表, 合并现金流量表), and only those pages are read. The other table extractors went from 50 seconds to 1 second a report this way. This was planned for v2.1 (workstream B) and can be brought forward.

## 102. Resume

**Evidence.** Control: stopped after 31 seconds, then "586 document(s) to read …; 14 already read by this version are skipped". Top-10: "0 document(s) to read …; 905 already read by this version are skipped".

**Assessment.** As designed. The progress lines at uneven counts ("71 of 905", "4 of 600", "355 of 600") are the once-a-minute lines between every 25th document.

## 103. The company list under v2.0.9

**Evidence.** "Listing history rebuilt for 5,230 companies whose dates or status changed. Done after 307.3s". The 2025 panel: `'dropped': {'included_by_report_evidence': 19, 'excluded_no_listing_date': 1029, 'excluded_delisting_date_unknown': 6}`.

**Assessment.** The fix of v2.0.9 works on the author's database. The panel now takes 5,162 of its 5,181 rows from the listing record, against 2 of 5,225 in finding 92. Status DELISTED rose from 165 to 386, because the delisting events now reach the companies' history.

## 104. The Beijing Stock Exchange and B shares

**Evidence.**
- **Counts.** "Count by board": 608 BSE, 41 SSE B and 35 SZSE B companies. The author enabled both optional boards before this update.
- **Status.** "872 in neither exchange's list (probably delisted …)".
- **Listing dates.** "1029 companies have no listing date".

**Assessment (from the code).**
- **Which lists exist.** The exchanges' lists read since v2.0.7 cover the Shanghai main board and STAR, and Shenzhen's A shares. They do not cover the Beijing Stock Exchange or B shares.
- **The fault.** v2.0.8 marks NOT_IN_EXCHANGE_LIST any company absent from the lists, whatever its board. So 684 listed BSE and B-share companies were marked so, and treated as delisted on an unknown date. 872 − 684 = 188 is the number of companies on the covered boards absent from the lists, as estimated in finding 71.
- **No dates for them.** The quote list was not asked, because every company on the covered boards had a date. Its board filters do not include them either. They therefore have no listing dates, and make up about 684 of the 1,029 without one.
- **The remedy.**
  - The status applies only to the boards the lists cover.
  - Listing dates for the optional boards come from the exchanges' B-share lists, and for the Beijing Stock Exchange from the quote list's BSE filter.

## 105. Eastmoney answers again

**Evidence.**
- **Quote list.** "Diagnose the quote list": five of six variants answered with 5,563 securities, and page 11 answered; only the plain-HTTP variant was refused.
- **Price histories.** The self-test's `eastmoney_daily_bars` passed (24 bars, latest 30 October).
- **Later the same day.** The self-test's quote-list check failed (finding 106).

**Assessment.** The refusal of finding 66 has lifted, at least at times. Price histories, which the backfill and "Download daily prices" use, answer. "Test price sources" will show whether Tencent answers too, so that a fallback can be chosen.

## 106. The self-test's quote-list message

**Evidence.** In the screenshot: "eastmoney_market_list FAIL HTTP 502 from http://push2.eastmoney.com/…".

**Assessment (from `selftest.check_eastmoney_list`).**
- **The fault.** When the variants fail in mixed ways (some refused, some disconnected), the check raises the last variant's error. That is the plain-HTTP one, so the message names an address the program does not normally use.
- **What happened.** All six variants failed at 15:45 UTC: Eastmoney refused requests again for a time.
- **The remedy.** The check should report every variant's result, as "Diagnose the quote list" does.

## 107. Financial extraction, six runs

**Evidence.** Six runs of `extract-financials --kind all`, each stopped by the author. They lasted 7,109, 3,708, 8,826, 7,508, 2,141 and 551 seconds, and read 859 of the 1,514 documents in all, at 30 to 98 seconds each.

**Assessment.** Finding 101 again. Resume works: each run continued with the rest. Each run took hours, because every page is read, and announcements are read as well. Targeted reading for financial extraction is now the most useful single change (plan, workstream B).

## 108. The checks after the re-reads

**Evidence.**
- **Balance sheets:** "groups_checked: 803, passed: 741, failed: 62".
- **Findings:** "2415 flag(s) EXTRACTION_DISCREPANCY: 260, PARSER_DISAGREEMENT: 1790, SEGMENT_SUM_MISMATCH: 345, OWNERSHIP_TYPE_UNKNOWN: 10, CORRECTED_REPORT: 7, ACTUAL_CONTROLLER_CHANGED: 3".

**Assessment.**
- **Balance sheets.** Failures fell from 11% (finding 87) to 7.7%, on more balance sheets.
- **Rising counts.** Discrepancies (174 to 260) and segment mismatches (248 to 345) rose, but so did what is checked: 655 documents have not yet been read by the new financial readers, and keep figures read by the old ones. A difference between an old and a new reading is counted until both are read again. Segments rose from 3,859 to 5,841 rows.
- **Read as rates.** The counts can be judged only once extraction finishes, and as rates. The findings CSV (`show-flags --export`) gives the patterns (DIGITS_GLUED, POWER_OF_TEN) and the size of each segment difference.
- **Corrected reports.** CORRECTED_REPORT (7) shows the same-day rule of finding 86 at work.

## 109. Panel rows without financial figures

**Evidence.** "5,011 of 5,181 rows have no financial figure at all", with `max_published_date: 2026-06-13`.

**Assessment.** Financial figures come from downloaded reports, and reports are downloaded for 295 companies, so 170 rows have figures. This is coverage, not a fault. A whole-market panel with figures needs the periodic reports of every company downloaded: about 5,200 companies, three or four reports a year. That is a large download (tens of gigabytes a year) and, at today's pace, weeks of extraction. Targeted reading brings the extraction to days. The panel's warning should say how many companies have figures and how many have downloaded reports.

## 110 and 111. Corporate actions and ownership

"corporate_actions_grouped: 34871": the actions read after the checks in finding 90 are now grouped. "ownership_checked: 166, ownership_failed: 2": the top-10 tables of 166 companies pass the ownership check, with two exceptions. These are not findings but lines in the output of `validate-ownership` (for example "pledged > shares"), which names the company and date.

## What to do now

1. "Test price sources", and choose a source under Settings.
2. Let "Extract figures from reports" wait for v2.0.10, which reads only the key-figure and statement pages. Or run it with "Reports: reports" now: documents already read stay read either way.
3. Run the query in finding 98 and attach two or three of the PDFs it lists. Or, after v2.0.10, run `inspect-tables` on them (plan, workstream C).
4. `show-flags --export exports/findings.csv` and attach the file, so that the differences can be measured by pattern and size.

The fixes for findings 96 to 111, with those still open from earlier, are planned in `docs/plan_v2.0.10.md`.
