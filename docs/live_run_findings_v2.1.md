# v2.1 and v2.1.1 live-run findings (findings 118 to 131)

The author sent three logs:
- **v2.1, first part.** "Update the company list", the topology view, "Read guidance" three times, the company commands for 600519, "Check balance sheets" and a catalogue run that was stopped.
- **v2.1, second part.** The same log continued: a catalogue refresh of 1 January to 31 October 2026 with downloads, and the start of a panel.
- **v2.1.1.** The company list, the calendar, CNINFO's filters, the scanned-page check, a sustainability-report download, and financial, top-10 and ESG extraction.

Each finding is marked with what was done. Every fix marked v2.1.2 is set out, with its interference check and tests, in `docs/plan_v2.1.2.md`.

## Summary

| No. | Finding | Severity | Status |
|---|---|---|---|
| 118 | The company list under v2.1 and v2.1.1 | Information | Finding 104's fix works; Beijing dates wait on Eastmoney |
| 119 | Download estimates about four times too low, without progress | Medium | Fixed in v2.1.2 |
| 120 | The download step after a ten-month refresh failed ("too many SQL variables") | High | Fixed in v2.1.2 |
| 121 | A rerun of the catalogue would not have downloaded what the failed run left | High | Fixed in v2.1.2 |
| 122 | A refresh fetched all 304 days again: 13 hours for 5% new rows | Low | Fixed in v2.1.2 |
| 123 | The guidance and sustainability-report downloads | Information | See 119 |
| 124 | About one document in 25 failed in parallel reading in the desktop program | High | Fixed in v2.1.2 |
| 125 | "Check documents for scanned pages" was slow and saved nothing when stopped | Medium | Fixed in v2.1.2 |
| 126 | Financial extraction with "kind all" read English and sustainability reports | Medium | Fixed in v2.1.2 |
| 127 | Gap messages did not say why a layer was empty | Low | Fixed in v2.1.2 |
| 128 | Garbled controller names | High | Fixed in v2.1.2 |
| 129 | Balance-sheet totals read without their first digit | High | Repaired in v2.1.2 where the document proves it; cause to be confirmed |
| 130 | The English ESG report shown as the title | Low | Fixed in v2.1.2 |
| 131 | Top-10 readings disagree often | Medium | Open |

## 118. The company list

**Evidence.**
- Shanghai and Shenzhen A and B shares are all dated: "1,700 of 1,700 … Shenzhen B shares 33 of 33".
- "226 in neither exchange's list", against 872 under v2.0.9.
- Eastmoney refused every request in both runs (HTTP 502), so "BSE 606" remain without listing dates. In v2.1.1 the B-share board's quote list was refused too, but B shares are dated from the exchanges' lists, so nothing was lost.

**Assessment.** Finding 104's fix works. The Beijing dates depend on Eastmoney answering. A second source (the Beijing exchange's own list) is a possible addition, but it needs bse.cn to be reachable from the author's network, which cannot be checked from here.

## 119 and 123. Download estimates and progress

**Evidence.**
- "Read guidance": "Downloading 5113 documents: roughly 5.0 GB and 2.1 hours". The run took 28,788 s (eight hours), almost all of it downloading: about 5.6 s a document.
- Sustainability reports: "2112 documents: roughly 6.2 GB and 0.9 hours", stopped after 3,724 s with no progress line.

**Assessment.**
- **Rate.** The estimate assumed 1.5 s a document.
- **Progress.** Progress printed only counts ("[25/5113] downloaded 25"), and the sustainability-report run printed none before it was stopped.

**Fix (v2.1.2).**
- Downloads give progress as extraction does: documents done, seconds a document, time left.
- Each download records its measured rate and the mean size by kind, and the next estimate uses them (5 s a document until then).

## 120 and 121. The download step after a catalogue refresh

**Evidence.**
- The refresh finished: "Catalogue done: 524,409 rows in 20,000 queries; 27,244 new … 304 day(s) finished, 0 failed".
- It then failed: "OperationalError: too many SQL variables … WHERE disclosures.document_url IS NOT NULL AND disclosures.id IN (?, ?, …". "Failed after 46614.9s".

**Assessment.**
- **The failure.** The catalogue passed every document to download to one `IN (...)` query; SQLite accepts a limited number of values in one statement. The catalogue was saved; nothing was downloaded.
- **The trap.** The documents to download were held only in memory. A rerun without `--refresh` skips the finished days, and so would have queued and downloaded nothing.

**Fix (v2.1.2).**
- ID lists are queried 500 at a time wherever they can grow with the market (downloads, stale facts, review items, validation flags, top-10 rows, catalogue days).
- The catalogue's download step chooses from the database every wanted document of its dates not yet on disk (kinds "all" and "reports"), so a rerun downloads what an interrupted run left.
- A failed download step no longer fails the finished catalogue; it names "Download catalogued documents" as the way to resume.

**Until then (for v2.1 and v2.1.1).** "Download catalogued documents" with the kinds needed selects by kind, not by a list of IDs, and so avoids the failure.

## 122. The refresh window

**Evidence.** The refresh fetched all 304 days in 46,615 s, for 27,244 new rows of 524,409 (5%).

**Fix (v2.1.2).** `--refresh` fetches again only the finished days in the last 30 days of the period ("Days to fetch again"; 0 for every day).

## 124. About one document in 25 failed in parallel reading in the desktop program

**Evidence.**
- Every error in v2.1.1 was `AttributeError("'NoneType' object has no attribute 'write'")`:
  - 894 of 6,650 documents in financial extraction;
  - 34 in top-10;
  - 8 in ESG.
- "Read guidance" under v2.1 reported "201 document(s) could not be read" on both full runs, and 7 when only those 201 were read again.

**Assessment.**
- **The line.** An old progress line ("... 25 documents read") is written once every 25 documents.
- **Where it fails.** The main process silences it during extraction, but the worker processes of parallel reading keep their own counter, which was never silenced. In the desktop program the workers have no console, so the write failed and took that document with it.
- **The arithmetic fits.** 5,113 ÷ 25 ≈ 204, against 201; 201 ÷ 25 ≈ 8, against 7.
- **Scope.** The command-line program has a console and was not affected.
- **No data was lost.** The failed documents were never marked as read, so the next run reads them.

**Fix (v2.1.2).**
- The workers' line is silenced.
- Their missing streams are replaced by a null device.
- The line is never written where there is no console.

## 125. "Check documents for scanned pages"

**Evidence.** "... 275 documents read (0.1 per second)", stopped after 2,449 s, and again after 426 s.

**Assessment.**
- **Speed.** It read every page with the slow reader, about 10 s a document.
- **Nothing saved.** It saved its results only at the end, so both stopped runs kept nothing, although the message said otherwise.
- **Unconverted.** It was the last extractor still on the old progress line.

**Fix (v2.1.2).**
- Pages are counted from the fast page text, in worker processes.
- Each document is saved as it is checked.
- Progress lines as elsewhere.
- The classification rule is unchanged.

## 126. Financial extraction with "kind all"

**Evidence.**
- The five slowest documents were:
  - a sustainability report (603191, 634 s, 47 pages);
  - English annual reports (190 to 234 s each).
- "read_by_section: 589" of 3,988 documents read.

**Assessment.** English versions and sustainability reports give no figures to these readers. "kind reports" already leaves them out.

**Fix (v2.1.2).** With "kind all" they are left out and counted (`not_financial`).

## 127. Gap messages

**Evidence.**
- After "Read guidance" had read 9,812 observations, the topology view of 600519 still said "No management guidance read. Run 'Read guidance'".
- The company commands for 600519 said only "No R&D or workforce data", "No segment data" and "No subsidiary data".

**Assessment.** 600519 had no downloaded periodic reports and no earnings forecasts in the span: a matter of coverage, but the messages pointed to the wrong action.

**Fix (v2.1.2).**
- The topology view says, company by company, whether reports or forecasts are not catalogued, not downloaded, not read, or read with nothing in the span.
- The three company commands say the same.

## 128. Garbled controller names

**Evidence.** "Companies with the same controller" listed names such as:
- "国务院国有资产监督、张玉卓、管理委员会";
- "深圳市人民政府国有、杨军、资产监督管理委员会";
- "湖南省人民政府国有、资产监督管理委员会";
- "人/单位负";
- "/单位负责".

Central SASAC appeared under three spellings.

**Assessment.**
- **Wrapped names.** In the Shenzhen layout (a header row, then one row per controller), a name that wraps within its cell arrives on several lines. Each line's first word was taken as another controller.
- **The legal representative.** The name in the next column was taken as a controller too.
- **Headings.** Pieces of the wrapped header were taken as names.

**Fix (v2.1.2).**
- Under a header naming entities, pieces are joined until they end as an entity name ends, and a personal name between them is dropped as the legal representative.
- Pieces of headings are never names.
- Several persons acting together are kept as before.
- Grouping by controller counts the forms of a commission's name as one.
- Version control-3 reads every report again.

## 129. Balance-sheet totals read without their first digit

**Evidence.**
- "Check balance sheets": "groups_checked: 1410, passed: 1309, failed: 101".
- Of about 120 failures printed, 108 were out by an exact round number: 53 by 10 billion and 23 by 20 billion yuan, then 30, 40 and 150 billion. For example: "equity: 3212752903.71, residual: 20000000000.0".
- Most were 2026 first-quarter and half-year reports.

**Assessment.**
- **The likeliest cause.** An eleven-digit total read without its first digit, because the text layer splits a long figure in a narrow column ("1 3,212,752,903.71").
- **No text-level fix.** A rule rejoining a lone digit to the number after it would be unsafe: a note number before an amount looks the same.

**Fix (v2.1.2).**
- **Repair.** When assets minus liabilities minus equity is exactly a single digit times a power of ten, the short figure is restored only if a second identity in the same document confirms which figure it is: parent plus minority equity, or current plus non-current liabilities or assets. The reading stays in `raw_value`, the note records the repair, and the confidence is lowered. Otherwise nothing changes, and the check still fails.
- **Diagnosis.** `inspect-tables --table balance_sheet` shows, for each line of the balance sheet, the numbers the reader finds in it, so the cause can be confirmed on the author's reports.
- **Output.** "Check balance sheets" gives a summary by pattern and writes every row to `exports/balance_check.csv`.
- **Version.** financials-4: every report is read again (about three hours for the documents in the v2.1.1 run).

**Still to do.** Run `inspect-tables --table balance_sheet` on two of the documents still failing after v2.1.2, for example 31, 297 or 327, and send the files.

## 130. The ESG report title

**Evidence.** "sustainability_report_title: '贵州茅台2025年环境、社会及治理（ESG）报告（英文版）'".

**Fix (v2.1.2).** When a year has both, the Chinese report is the title shown.

## 131. Top-10 readings disagree often (open)

**Evidence.**
- "reports: 358, holders: 2676 … single_added: 1567".
- "dual_run: agree 145, disagree 150, single 814, secondary_only 1669".
- 907 reports were read.

**Assessment.**
- **Coverage.** Under four in ten reports gave rows. Some of the 34 failures of finding 124 belong here.
- **Agreement.** The two readings disagree about as often as they agree, and most rows come from the second reading alone. That may be right (finding 98 found the first reading missing rows), but it cannot be judged without examples.

**To do.** After v2.1.2, run "Read top-10 shareholders" again. For two or three reports where the readings disagree, send `inspect-tables --table top10`.

## Also noted

- **Empty guidance documents.** 1,344 earnings-forecast documents (26%) gave no figure. Many are probably corrections or notices without figures; a sample would show.
- **ESG yield (finding 117).** 76 values from 303 documents; still open.
- **Index constituents.** None are imported ("no membership data for SSE 180, STAR 50, SZSE 100 or ChiNext Index imported"), so the sustainability-reporting mandate cannot be checked.
- **Speed (v2.1.1).** Financial extraction ran at 1.6 to 1.7 s a document (36 s under v2.0.9), top-10 at 0.4 s and ESG at 0.7 s. The calendar is written for all three exchanges (finding 115). The slowest-document list works (finding 113).

## What to do after installing v2.1.2

1. **Re-read the reports.**
   - "Extract figures from reports" (kind reports): every report is read once more (financials-4), and the 894 documents that failed are read.
   - Then "Read top-10 shareholders", "Read controlling shareholder and actual controller" (control-3) and "Read guidance".
2. **Run the checks.** "Run all checks", then "Check balance sheets"; send `exports/balance_check.csv` if many rows remain.
3. **Downloads.** For the documents of the October refresh, run "Catalogue announcements" again with downloading ticked: the finished days are skipped and the documents left are downloaded. Or use "Download catalogued documents".
4. **Samples for findings 129 and 131.** `inspect-tables --table balance_sheet` for two documents still failing, and `inspect-tables --table top10` for two or three reports.
