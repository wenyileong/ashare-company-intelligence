# v2.0.8 live-run findings

**Source:** the author's desktop log of 30 October 2026. It includes the first table extractions under v2.0.8:
- "Update the company list" (failed three times);
- "Extract figures from reports" (`--kind all`; stopped, then running at 225 of 1,511 when the log was copied);
- "Read controlling shareholder and actual controller" (stopped once, then complete);
- "Read top-10 shareholders from reports" (complete, then rerun);
- "Extract segments from reports" (complete).

**Status:** findings only; no code has been changed since v2.0.9. Numbering continues from `docs/live_run_findings_v2.0.7.md` (findings 70 to 95).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 96 | "Update the company list" failed with a TypeError | High (no company-list updates) | Cause found and fixed in v2.0.9; to confirm on v2.0.9 |
| 97 | Top-10 shareholders: 905 reports in 25 minutes, 1.7 seconds each, against about five minutes each under v2.0.7 | Information (findings 76 and 77 answered for speed) | Confirmed |
| 98 | Top-10 shareholders: only 167 of 905 reports gave rows, 6.9 holders each on average, while the other reader found 1,684 rows the kept one did not | **High** (most reports without shareholder data) | Confirmed from counts; cause to check against reports |
| 99 | The actual controller is now named in 257 of 292 reports (6 of 293 under v2.0.7) | Information (findings 78 and 89 answered) | Confirmed |
| 100 | Segments: 600 reports in 10 minutes, 1.0 second each (51 seconds under v2.0.7); 561 with segments; 72 old rows removed | Information (finding 82 answered) | Confirmed; the sums to check with "Run all checks" |
| 101 | Financial extraction still takes about 36 seconds a document, and `--kind all` gives it 1,511 documents, most of them announcements: about 14 hours | Medium (a long run, mostly for nothing) | Confirmed |
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

## What to do now

1. If not done, install v2.0.9, then "Update the company list". If it fails, run `ashare-cli update-universe` in a command prompt and send the full error.
2. Stop "Extract figures from reports" if it is still running with "all", and run it with "Reports: reports". Documents already read stay read.
3. "Run all checks", then "Show findings", and send the summary.
4. Run the query in finding 98 and attach two or three of the PDFs it lists.

**For the next patch (proposed, v2.0.10):**
1. Targeted reading for financial extraction (finding 101).
2. The top-10 parser for the layouts the attached reports show; secondary-only rows to be kept when they pass the table checks (finding 98).
3. The full error written to the run log for every failed action, so that a failure like finding 96 can be diagnosed from the log alone.
