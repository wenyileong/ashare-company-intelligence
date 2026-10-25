# v2.0.7 live-run findings

**Source:** the author's desktop log of 24 October 2026 under v2.0.7, and a screenshot of the installer. The log has six actions:

1. "Update the company list" (42 s);
2. "Diagnose the quote list";
3. "Count by board";
4. "Read listing events from announcements";
5. "Re-catalogue busy days" (29 April, 31 min);
6. "Read top-10 shareholders from reports", which had just started when the log was copied.

**Second log (findings 76 to 81).** A later copy of the same log adds:
- "Read top-10 shareholders", stopped by the author after 8 h 7 min;
- "Read controlling shareholder and actual controller" (42 min);
- the transactions, share-capital and regulatory extractions;
- the start of "Extract segments from reports".

**Third log (findings 82 to 91).** The latest copy adds:
- "Extract segments from reports", finished (8 h 30 min);
- "Run all checks" (`validate-all`) and "Show findings" (`show-flags`, 1,778 findings);
- share-capital reconciliation and transactions again, and corporate actions from titles.

**Fourth excerpt (findings 92 to 95).** The corporate-action run that ends the third log, then "Build a panel" (`build-panel --unit year --align fiscal --start 2026-01-01 --end 2026-10-24 --universe-basis auto`), 25 October 2026.

**Status:** findings only; no code has been changed. Numbering continues from the v2.0.6 findings (`docs/live_run_findings_v2.0.6.md`, findings 58 to 69).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 70 | The exchanges' stock lists work live: 5,224 companies, all dated, in three requests; the quote list was not needed | Information (findings 58 and 66 resolved for listing dates) | Confirmed |
| 71 | About 350 companies in CNINFO's list are in neither exchange's list; most are probably delisted, but only 165 are recognised as such | Medium (status left unset for about 190 companies) | Confirmed from counts; cause inferred |
| 72 | 29 April is complete: the whole 2026 catalogue now matches CNINFO's totals | Information (findings 23, 45 and 61 closed) | Confirmed |
| 73 | Eastmoney still refuses every request from this network; the daily price snapshot depends on it | Medium (daily prices) | Confirmed |
| 74 | The installer fails with a Windows error when the earlier version is still running | Low (installation) | Confirmed |
| 75 | Listing events read from announcements: 130 listings and 1,050 delistings | Information | Confirmed |
| 76 | Reading top-10 shareholders takes about five minutes a report; the run was stopped after eight hours | **High** (the shareholder re-extraction of v2.0.7 cannot finish; other extractors are slow in the same way) | Confirmed from the log and the code |
| 77 | So the re-extraction is incomplete: reports not yet read keep their misread rows | High (wrong ownership figures remain; names are protected) | Follows from 76 |
| 78 | The actual controller's name was found in 6 of 293 reports | Medium (control data mostly without names) | Confirmed; cause to check |
| 79 | The progress counter says "0.0 per second" and counts reads, not documents | Low (misleading) | Confirmed |
| 80 | Transactions and regulatory events are read from titles only, with no counterparty or amount | Information (documents not downloaded) | Confirmed |
| 81 | Share-capital reconciliation found no data to reconcile | Information | Confirmed |
| 82 | Segment extraction finished: 600 reports in 8 h 30 min, about 51 seconds a report | Medium (slow, as in 76) | Confirmed |
| 83 | Segment totals often disagree with the reported total: 248 findings, median difference 35% | **High** (segment figures unreliable without review) | Confirmed from the findings; cause to check |
| 84 | 174 differences between two readings of the same period, 168 of them between two documents filed the same day; 100 differ by a power of ten | **High** (wrong financial figures in the database) | Confirmed; which documents, to check |
| 85 | Digits glued to or cut from figures: for example 11,791,960,892.40 against 1,791,960,892.40 | High (wrong figures) | Confirmed from the findings |
| 86 | Three differences marked "explained by a restatement" are between documents filed the same day | Low (a weak explanation shown as an explanation) | Confirmed from the code |
| 87 | The balance-sheet identity fails in 37 of 351 groups checked (11%) | Medium | Confirmed |
| 88 | The two parsers disagree on 1,345 figures (financials 486, statements 278, segments 581) | Medium (needs review, not a fault in itself) | Confirmed |
| 89 | A table heading, 与本公司的关系, read as the actual controller's name | Medium (supports 78) | Confirmed |
| 90 | Corporate actions (42,395, titles only) were read after the checks ran, so none were grouped; ownership checks covered one company | Information (order of actions) | Confirmed |
| 91 | "Show findings" prints 1,778 findings as a 10,000-line table, without the company code | Low (hard to use) | Confirmed |
| 92 | The panel ignores the 5,200 listing dates: a listing history built before they arrived takes precedence | **High** (panels fall back on report evidence for every company) | Confirmed from the code |
| 93 | A fiscal-year panel for 2026 has no annual figures, because the year has not ended | Medium (an empty panel, with no warning) | Confirmed from the code |
| 94 | 352 companies are in neither the listing record nor the report evidence | Information (consistent with 71) | Confirmed from counts |
| 95 | The corporate-action run is the one already in the third log | Information | Confirmed |

## 70. The exchanges' stock lists work

**Evidence.** "Exchange lists: Shanghai main board 1,700 of 1,700 dated; STAR Market 618 of 618 dated; Shenzhen A shares (main board and ChiNext) 2,906 of 2,906 dated". Then: "4233 listing dates added (4,233 from the exchanges' lists, 0 from the quote list). The quote list was not needed." The action took 42 seconds.

**Assessment.** The second source of listing dates, added in v2.0.7 on the parameters the exchanges' own pages send, works live on its first run. Together with the 999 dates the quote list gave earlier, about 5,230 of the 5,577 companies in the list now have a listing date. Point-in-time panels can now use listing records instead of the report-evidence fallback (finding 41).

## 71. Companies in neither exchange's list

**Evidence.**
- **The two lists.** "Count by board" gives 1,850 Shanghai main board, 623 STAR, 1,649 Shenzhen main board and 1,455 ChiNext companies, 5,577 in all. The exchanges list 1,700, 618 and 2,906.
- **The status line.** "5225 listed, 165 delisted (by name)".

**Assessment (inferred).** CNINFO's list holds about 350 companies more than the exchanges list. Most are probably delisted companies whose short names do not mark them as delisted: only 165 are recognised by name, and the remaining 187 or so have no status. Their listing dates are missing too, so point-in-time panels leave them out as "no listing date". When the exchanges' lists are complete, a company absent from both could be marked NOT_IN_EXCHANGE_LIST. Its delisting date could then come from the delisting events read from announcements (finding 75), so that panels for earlier years still include it where it was listed. This is for a later patch, and should be checked against a few named companies first.

## 72. 29 April is complete

**Evidence.** "2026-04-29: 26,066 rows after splitting (board_disjoint+category+trade+trade_division+stock), complete", in 1,313 queries and 31 minutes. The query that held the last rows, 日常经营 in manufacturing on the Shenzhen main board (3,024), reached 2,989 by the 31 manufacturing divisions. Company batches of 10 then brought in the rest: 165 batches, sent with the companies' own exchange and no board code.

**Assessment.**
- **Batches of ten.** They work as the probe showed (finding 60), and none was larger than its parent (finding 62).
- **Divisions.** The divisions left 35 rows, more than the 15 the probe found at exchange level, since some companies are classified only at section level.
- **The catalogue.** With 9 to 12 January complete under v2.0.6 (finding 65), every day of 2026 to date now matches CNINFO's own total within the enabled boards. That completes the catalogue's aim.

The batches read all 165 groups even though only 35 rows were missing, because the engine cannot tell which companies hold them. That cost about 200 extra requests, which is acceptable for a query that occurs on a few days a year.

## 73. Eastmoney still refuses every request

**Evidence.** "Diagnose the quote list": every variant failed on page 1 again (HTTP 502, or disconnected).

**Assessment.** The refusal reported in finding 66 has lasted at least a day. Listing dates no longer depend on this service (finding 70). Two things still do:
- **The daily price snapshot** in the daily update uses the same service (`push2`). It records an error and the update carries on, but no daily prices arrive while the refusal lasts.
- **Price histories** ("Download daily prices") use another of Eastmoney's services (`push2his`), which answered in the v2.0.3 self-test. Whether it is refused too is not known.

A run of "Download daily prices" for one company would show it. If it is refused as well, prices need another public source, or licensed data imported from CSV, which the program already supports.

## 74. The installer fails when the earlier version is running

**Evidence.** A screenshot: "Error opening file for writing: C:\Users\…\AppData\Local\Programs\AShareScraper\AShareScraper.exe", with Abort, Retry and Ignore.

**Assessment.** Windows locks a running program's file, so the installer cannot replace it while the earlier version is open. That includes a copy left running in the background after its window closed. The installer does not check for this first, so the user sees a generic Windows error. "Ignore" would leave the old program among the new files. A later build should check before copying and ask for the program to be closed, in plain words.

## 75. Listing events read from announcements

**Evidence.** "Read listing events from announcements": 1,379 announcements, 1,437 events, 1,337 new (130 listings, 1,050 delistings, 106 name changes, 151 legal name changes).

**Assessment.** The delisting events give dates that the status line, which recognises delisting only by name, does not use (finding 71). They feed the security history (`rebuild-security-history`), which the point-in-time universe reads.

## 76. Top-10 shareholders: about five minutes a report

**Evidence.**
- **The counter.** "Read top-10 shareholders from reports" printed its counter eight times ("... 200 documents read (0.0 per second)") and was stopped after 29,199 seconds (8 h 7 min). The counter counts each plain-text reading of a document, and the action makes two per report, so about 100 reports were read: some five minutes each.
- **The others.** "Extract segments" shows the same pace. "Read controlling shareholder and actual controller" took 42 minutes for its reports.

**Cause (from the code).**
- **Two readings.** Each report is read twice: once for the top-10 table and once for the tradable-holders table. Each reading takes the plain text and the layout text of the whole document, with no shared cache.
- **Every page.** The layout reader rebuilds the rows of every page, 200 to 300 pages for an annual report, in Python. The table sought is on two or three of them.
- **No progress or resume.** The action gives no total, no estimate and no resume, unlike financial extraction since v2.0.6. A stopped run starts again from the beginning.

**Assessment.** At this pace, re-reading every downloaded report would take days, and extraction speed is the subject of v2.1 (workstream B). This case does not need the whole of v2.1, though: the remedy is targeted reading.
- **Find the pages.** A fast plain-text pass (pdfium) finds the pages that hold the section sought, such as 前十名股东持股情况 with the page after it, or 控股股东 and 实际控制人.
- **Read only those.** The layout reader then works on those pages only.
- **Read once.** Each report is read once for all the tables sought from it.
- **Follow and resume.** Progress, an estimate and resume work as for financial extraction.

This should take each report from minutes to seconds.

## 77. The shareholder re-extraction is incomplete

**Evidence.** The run stopped after about 100 reports, and it gave no summary.

**Assessment.** For reports not yet read under v2.0.7, the misread top-10 rows of finding 68 remain in the database. Names are protected in a release by the fail-safe rule of v2.0.7, whatever the rows hold (finding 69), but their percentages may be wrong. **A release should not be made for shareholder analysis until the re-extraction has finished.** `show-ownership 000563` shows whether 陕国投A's report was among those read.

## 78. The actual controller's name in 6 of 293 reports

**Evidence.** "Read controlling shareholder and actual controller": `{'reports': 293, 'with_controller': 6, 'types': {'LOCAL_SOE': 113, 'PRIVATE': 79, 'NO_CONTROLLER': 36, 'CENTRAL_SOE': 50, 'UNKNOWN': 8, 'FOREIGN': 7}}`.

**Assessment.** The type of ownership was classified for all 293 reports, from the nature of the controller where its name was not found. But the actual controller's name was read in only six. Annual reports name the actual controller in nearly every case (36 say there is none), so the name parser probably misses the common layouts, much as the top-10 parser missed the Shenzhen layout (finding 68). This needs checking against a few reports, for example `ashare-cli control 600519` and a Shenzhen company, before it is fixed. Until then the control chain is mostly without names.

## 79. The progress counter

**Evidence.** "... 25 documents read (0.0 per second)", repeated.

**Assessment.** At several minutes a reading, the rate rounds to 0.0 per second. The counter also counts readings of a document's text, several per document, not documents. Extractions should report documents done and left, seconds per document and an estimate, as financial extraction has since v2.0.6.

## 80. Transactions and regulatory events from titles only

**Evidence.**
- **Transactions.** 41,388 events from 40,927 announcements. `transactions 600519` shows three rows with no counterparty, amount or approval.
- **Regulatory events.** 21,963 events, all "title_only".

**Assessment.** The details are read from the documents, which were not downloaded (the catalogue ran with `--no-download-documents`). The titles give the type and date of each event. The details need the documents, which for 40,000 announcements is a large download, best limited to the companies or event types under study.

## 81. Share-capital reconciliation found nothing to reconcile

**Evidence.** "Reconcile share capital": 0 companies.

**Assessment.** The reconciliation compares share-capital observations, imported or read from reports, with corporate actions. None have been imported or extracted yet, so there is nothing to compare. This is not a fault.

## 82. Segment extraction: 600 reports in eight and a half hours

**Evidence.** "Extract segments from reports" counted 1,200 readings and finished after 30,588 seconds: `{'reports': 600, 'segments': 3859, ... 'dual_run': {'agree': 2979, 'disagree': 581, 'single': 299, 'secondary_only': 1799}, 'scanned_documents': [405]}`. The PDF reader noted damaged cross-references (repaired) and fonts without a standard encoding in two documents.

**Assessment.** About 51 seconds a report, two readings each: faster than top-10 shareholders (finding 76), but still eight hours for 600 reports. The same remedy applies (targeted pages, one reading per report, progress and resume). One document (disclosure 405) is a scan without a text layer, so nothing was read from it. The 1,799 segments found only by the second (plain-text) parser are kept as that parser's reading, so they lack the cross-check the other 2,979 have.

## 83. Segment totals often disagree with the reported total

**Evidence.** 248 `SEGMENT_SUM_MISMATCH` findings: by product 102, by industry 88, by region 42, by sales model 11, reportable segments 5. Most compare the sum of the segments with the table's own total (217); the rest with the revenue figure (31). The absolute differences have a median of 35%; 69 are within 10%, and 65 are 90% or more. Four exceed a billion per cent, which can only be a unit or digit fault. 56 sums are larger than the total, 192 smaller.

**Assessment (cause to check).** A difference of a few per cent can be genuine (rounding, an "other" line not read, inter-segment eliminations). Differences of a third or more, and sums under half the total, point to rows missed when a table runs over a page or wraps, or to a subtotal row read as a segment. Until this is checked against a few reports, segment figures should be used only where the sum agrees with the total. A `segments` call for a flagged company with the report open beside it would show the pattern.

## 84. Two readings of the same period disagree

**Evidence.** 174 `EXTRACTION_DISCREPANCY` findings (plus the 3 of finding 86), from 77 pairs of documents:
- **Same day.** In 168 of the 174, the two documents were filed on the same day and have consecutive record numbers (for example disclosures 9 and 10, 57 and 58).
- **Powers of ten.** In 100, the two values differ by exactly 1,000, 10,000, a million or a hundred million: one reading applied the wrong unit (元, 千元, 万元 or 亿元).
- **Other.** Two differ only in sign (operating profit −12,513,029,670 against +12,513,029,670); the other 72 by no simple factor (inventory 373,738,098,100 against 2,664,000), which means a different figure was read.
- **Metrics.** Revenue (64), parent net profit (34), operating cash flow (32) and net profit after non-recurring items (28): the headline figures.

**Cause (from the code; the documents still to check).** Two things combine.
- **Two documents.** Financial extraction reads documents classed as annual, interim or quarterly reports. A summary (摘要) or English version is classed apart, so these pairs are probably a report together with another document whose title also contains 年度报告 (a corrected version, or a notice about the report), or documents read under "All downloaded documents" before v2.0.6. This needs the two titles; the query below gives them.
- **The unit.** The text reader takes the first figure after a label, and the unit from the nearest "单位：" line before it. Where no such line precedes the figure on that page or earlier, but one exists elsewhere in the document, it assumes 元. A key-figures table near the front of a report, or a summary document, often declares its unit only in the table heading or not at all, so the same figure is read once in 元 and once in 万元.

In each pair at most one value is right, and the database does not yet say which. Panels should not use the periods of these 77 pairs until it is fixed.

**Check.** `ashare-cli query "SELECT id, announcement_date, kind, title_cn FROM disclosures WHERE id IN (9,10,57,58,126,128,129,255,256)"` shows what the pairs are.

## 85. Digits glued to or cut from figures

**Evidence.** One company's documents of 31 March (disclosures 128 and 129) and a later document (126, 13 June):
- equity 11,791,960,892.40 against 1,791,960,892.40;
- other equity instrument investments 452,156,535.48 against 2,156,535.48;
- taxes and surcharges 227,102,914.31 against 7,102,914.31;
- non-current assets due within a year 22,103,629.82 against 22,103;
- revenue 1,355.2 against 143,751,044,503.13.

**Assessment.** The digits beyond the shared ending (1, 45, 22) look like a note reference (附注 number) glued to the figure in one reading, or digits lost in the other; "22,103" and "1,355.2" are figures cut at a separator or a line break. Either way, one reading of each is wrong. These come from both readers, the text heuristic and the statement-table reader. The number check (`_WELL_FORMED`) added for the top-10 parser in v2.0.7 rejects such numbers there, and the financial readers need the same check, with the note column kept apart.

## 86. "Explained by a restatement" for documents filed the same day

**Evidence.** Three `RESTATEMENT_EXPLAINED` findings compare disclosures 57 and 58, both of 29 April: revenue 9,835,474,916.50 against 2,544,411,519.38, parent net profit −12,582,399,856.80 against +94,810,677.19.

**Assessment (from `crossvalidation.py`).** A difference is "explained" whenever a restatement announcement falls between the two documents' dates. When both are filed on the same day, any restatement filed that day explains it, so this says little. These are probably the same fault as finding 84. A difference between documents of the same day should be explained only by a restatement that names the document (a corrected report, 更正后).

## 87. The balance-sheet identity

**Evidence.** "Balance sheet identity: groups_checked: 351, passed: 314, failed: 37, insufficient: 228".

**Assessment.** Total assets equal total liabilities and equity in 314 of 351 balance sheets read whole (89%). The 37 failures are probably the faults of findings 84 and 85; 228 balance sheets lacked one of the three totals.

## 88. The two parsers disagree on 1,345 figures

**Evidence.** 1,345 `PARSER_DISAGREEMENT` findings: segments 581, financials 486, statements 278. In each the layout reading was kept.

**Assessment.** This is the dual run doing its job: it shows where a figure needs a look. It is not a fault in itself. But at this number it needs the review queue (`build-review-queue`) rather than reading the findings one by one, and the parsers' evaluation (`evaluate-parsers`) on a few hand-checked reports would show which reader is more often right.

## 89. A table heading read as the actual controller

**Evidence.** Among the eight `OWNERSHIP_TYPE_UNKNOWN` findings: `"controller": "与本公司的关系"` ("relationship with the company", a column heading); three with an empty name and the nature 境内其他机构; four with no controller found.

**Assessment.** This supports finding 78: the controller parser reads the table's layout wrongly in some reports, as the top-10 parser did before v2.0.7. A heading should never be taken as a name.

## 90. The order of the actions

**Evidence.** "Run all checks" reported `corporate_actions_grouped: 0` and `ownership_checked: 1`. Corporate actions were read from titles afterwards: 42,395 actions, all "title_only".

**Assessment.** Not a fault. The checks ran before the corporate actions existed, so none were grouped, and only one company has ownership data that the check can test (from an imported or extracted shareholding total). Running "Link events" and "Run all checks" again now groups the corporate actions.

## 91. "Show findings" is hard to use at this size

**Evidence.** 1,778 findings printed as a table of about 10,000 lines, with the JSON details wrapped in a narrow column and no company code.

**Assessment.** The command can filter (`--security-code`, `--severity`, `--rule`), but the desktop action shows everything. A count by rule and company first, the company code in each row, and an export to CSV would make it usable.

## 92. The panel ignores the new listing dates

**Evidence.** `{'rows': 5225, ... 'dropped': {'included_by_report_evidence': 5223, 'excluded_no_listing_date': 5575}}`. Only 2 of 5,225 rows come from the listing record, although "Update the company list" had given about 5,230 companies a listing date (finding 70).

**Cause (from `security_master.universe_at`).** The point-in-time universe reads the listing history (`security_history`) where a company has one, and the company record's listing date only where it has none. The history was built ("Build listing history") before the exchanges' lists filled in the listing dates, so its derived periods for nearly every company have no start date. Such a company is then counted as "no listing date", and the listing date now on its company record is never consulted. Step 2 of "What to do now", rebuilding the history, had not yet been run.

**Assessment.** The remedy for the author is to run "Build listing history" (`rebuild-security-history`), then build the panel again; the history then starts from the IPO event or the listing date. In the code, two things are wrong and belong in v2.0.8:
- a derived history without a start date should give way to the company record's listing date, not exclude the company;
- "Update the company list" should rebuild the derived history for the companies whose listing dates it changed, or at least say that it needs rebuilding.

## 93. A fiscal-year panel for a year that has not ended

**Evidence.** `--unit year --align fiscal --start 2026-01-01 --end 2026-10-24` gave one row per company for the fiscal year ending 31 December 2026, and `max_published_date: None`: no value in the panel has a publication date.

**Assessment (from `panel._rows_spec`).** A fiscal-year row takes figures for the year ending 31 December, so the 2026 row looks for 2026 annual reports, which will be published from January 2027. The financial variables are therefore empty in every row. The report evidence, by contrast, counts 2026 interim and quarterly reports, so the rows exist. The panel the author probably wants is fiscal year 2025 (`--start 2025-01-01 --end 2025-12-31`, using the annual reports published in 2026), or quarterly rows for 2026 (`--unit quarter`). The program should warn when a fiscal-year row's year has not ended, and say how many rows have no financial figures at all.

## 94. Companies outside the panel

**Evidence.** 5,225 rows from 5,577 companies.

**Assessment.** The other 352 have neither a usable listing record nor a periodic report for 2026. This matches the roughly 350 companies in CNINFO's list but in neither exchange's list (finding 71), most probably delisted before 2026. Leaving them out of a 2026 panel is right; for earlier years they need delisting dates (finding 71).

## 95. Corporate actions from titles

**Evidence.** 42,395 actions from 472,613 announcements, all "title_only", after 131.7 seconds.

**Assessment.** The figures and the time are identical to the last action of the third log, so this is the same run, not a second one (finding 90). The titles give the type and date of each action; ratios and record dates need the documents.

## What to do now

1. Let "Read top-10 shareholders from reports" finish, then check 陕国投A: `ashare-cli show-ownership 000563` should show its real percentages (26.80, 16.76 …) and names without the nature glued on.
2. "Resolve entities", then `rebuild-security-history`, so that the listing and delisting events reach the point-in-time universe.
3. Make the release again, then rebuild a panel. Most rows should now be included by listing record, not report evidence.
4. Optionally, "Download daily prices" for one company, to see whether Eastmoney's price history still answers (finding 73).
5. Run the query in finding 84 and send the output, so that the document pairs can be identified before the fix.
6. "Link events", then "Run all checks" again, so that the corporate actions are grouped (finding 90).
7. "Build listing history", then build the panel again, for fiscal year 2025 (`--start 2025-01-01 --end 2025-12-31`). Expect most rows with `universe_basis = LISTING_RECORD` (findings 92 and 93).
8. Until v2.0.8, do not use segment figures whose sum disagrees with the total, or financial figures for the company-periods flagged in findings 84 and 85.

**For the next patch (v2.0.8, proposed):**
1. Targeted reading for the document extractors: find the pages first, read the layout of those pages only, and read each report once for all its tables. Add progress, an estimate and resume (findings 76, 77 and 79).
2. The actual controller's name, after checking a few reports (finding 78).
3. The installer's check for a running copy (finding 74).
4. The NOT_IN_EXCHANGE_LIST status, with delisting dates from the listing events (findings 71 and 75).
5. A second price source, if finding 73 shows that price histories are refused too.
6. Financial figures: the unit taken from the table that holds the figure, the number check of v2.0.7 for the financial readers, and the note column kept apart; documents that are not the report itself left out (findings 84, 85 and 87).
7. Segments: rows over page breaks and subtotal rows, checked against the flagged reports (finding 83).
8. Restatements: a same-day difference explained only by a corrected report (finding 86).
9. "Show findings": a summary by rule and company, the company code and a CSV export (finding 91).
10. The listing history: the company record's listing date used where the derived history has no start, and the history rebuilt when listing dates change (finding 92).
11. Panels: a warning for fiscal years not yet ended, and a count of rows without financial figures (finding 93).
