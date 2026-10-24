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

## What to do now

1. Let "Read top-10 shareholders from reports" finish, then check 陕国投A: `ashare-cli show-ownership 000563` should show its real percentages (26.80, 16.76 …) and names without the nature glued on.
2. "Resolve entities", then `rebuild-security-history`, so that the listing and delisting events reach the point-in-time universe.
3. Make the release again, then rebuild a panel. Most rows should now be included by listing record, not report evidence.
4. Optionally, "Download daily prices" for one company, to see whether Eastmoney's price history still answers (finding 73).

**For the next patch (v2.0.8, proposed):**
1. Targeted reading for the document extractors: find the pages first, read the layout of those pages only, and read each report once for all its tables. Add progress, an estimate and resume (findings 76, 77 and 79).
2. The actual controller's name, after checking a few reports (finding 78).
3. The installer's check for a running copy (finding 74).
4. The NOT_IN_EXCHANGE_LIST status, with delisting dates from the listing events (findings 71 and 75).
5. A second price source, if finding 73 shows that price histories are refused too.
