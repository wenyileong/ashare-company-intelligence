# v2.0.10 patch plan: the remaining live-run faults, cumulatively

**Status:** plan, 30 October 2026. Nothing in it is built yet.

**Basis:**
- the v2.0.8 and v2.0.9 live runs (findings 96 to 111, `docs/live_run_findings_v2.0.8.md`);
- the findings still open from the register (`docs/plan_v2.0.8_and_visualisation.md`, section 2);
- the author's screenshot of the live self-test of 30 October.

**Aim:** one patch that closes every fault the live runs have shown and the code can fix now, in order of effect on the data:
1. Beijing and B-share companies treated as delisted (finding 104);
2. financial extraction, still hours a run (findings 101 and 107);
3. top-10 shareholder coverage (finding 98);
4. what failures and checks report (findings 96, 106, 108 and 109).

No visualisation work belongs here; V0 and V1 follow, beside v2.1, as decided on 29 October.

## 1. Where things stand

**Confirmed fixed in the live runs:**

| Area | Findings | Evidence |
|---|---|---|
| Panels use the listing dates | 92 | 5,162 of 5,181 rows from the listing record |
| The company-list update | 96 | v2.0.9 runs in 307 seconds and rebuilds 5,230 histories |
| Table extraction speed | 76 and 82 | Top-10: 1.7 s a report, against about 300 s. Segments: 1.0 s, against 51 s |
| Progress and resume | 79 | Every table extractor; reruns skip what was read |
| Actual controller | 78 and 89 | Named in 257 of 292 reports, against 6 of 293 |
| Corporate actions grouped | 90 | 34,871 |
| Balance sheets | 87 | Failures down from 11% to 7.7%; re-reads unfinished |
| Eastmoney | 73 | Answers again, at times (finding 105) |

**Open, and in this plan:**

| # | Finding | Severity | Workstream |
|---|---|---|---|
| 104 | Beijing and B-share companies marked "in neither exchange's list", and without listing dates | **High** | A |
| 101, 107 | Financial extraction reads every page, and with "all" every announcement too: about 35 s a document | **High** | B |
| 98 | Top-10 rows from only 167 of 905 reports | **High** | C |
| 96 | A failed action leaves only a one-line error, so a fault cannot be diagnosed from the log | Medium | D |
| 106 | The self-test reports only the last variant's error | Low | D |
| 108 | Discrepancy and segment counts cannot be read as rates | Medium | D |
| 109 | The panel does not say why rows have no figures | Low | D |

**Open, and not in this plan:**
- **Waiting on the author's PDFs or findings CSV.** Finding 98 (the parser itself, beyond C) and finding 108 (the segment and discrepancy patterns).
- **Planned for v2.1 (workstream C).** Findings 7 to 10 and 16 to 18.
- **Monitored.** Findings 1 and 19.

## 2. Workstream A: the optional boards (finding 104)

**The fault.** The exchanges' lists read since v2.0.7 cover the Shanghai main board and STAR, and Shenzhen's A shares. v2.0.8 marks NOT_IN_EXCHANGE_LIST any company absent from them, whatever its board. With the Beijing Stock Exchange and B shares enabled, 684 listed companies were marked so. They were treated as delisted on an unknown date, and have no listing dates either.

**The fix.**
1. **Status.** NOT_IN_EXCHANGE_LIST applies only to the boards the lists that were read cover. A company on another board keeps LISTED, unless its name or a delisting event says otherwise.
2. **Repair.** Companies on the optional boards marked NOT_IN_EXCHANGE_LIST by v2.0.8 or v2.0.9 are set back on the next "Update the company list". Their history is rebuilt.
3. **Listing dates for B shares.** The exchanges' own B-share lists are read when B shares are enabled, with the same requests as their A-share lists:
   - Shanghai's list with `STOCK_TYPE=2`;
   - Shenzhen's list with `TABKEY=tab2`.
   
   Two requests in all, kept in the raw archive like the others.
4. **Listing dates for the Beijing Stock Exchange.** When it is enabled, the quote list is asked for that board alone (filter `m:0+t:81+s:2048`): about seven requests for 608 companies. It answers again (finding 105), and the three-refusal rule stops it if not.
5. **Output.** The update reports each list, as now. Companies still without a listing date are counted by board, so that a missing optional-board list shows at once.

**Not verified offline.** The request parameters for the B-share lists and the BSE filter follow the exchanges' and Eastmoney's own pages. The build environment cannot reach them, so "Update the company list" is their live test. Each is reported, and a failed list leaves the others' dates in place.

**Accepted when:**
- on the author's database, the BSE and B-share companies are LISTED;
- most of them have a listing date;
- NOT_IN_EXCHANGE_LIST counts about 188, the covered boards' companies absent from the lists.

## 3. Workstream B: financial extraction reads only its pages (findings 101 and 107)

**The fault.** Financial extraction is the one document extractor still reading every page: the plain text and the layout of all 200 to 300 pages, for figures that sit on a dozen of them. With "all", it also reads every downloaded announcement whole, though most carry no statements.

**The fix.**
1. **Sections.** Five sections are added to the report reader:
   - the key figures (主要会计数据和财务指标), with the page after;
   - the consolidated balance sheet, income statement and cash-flow statement (合并资产负债表, 合并利润表, 合并现金流量表), with three pages after each;
   - the employees and R&D pages already found for R&D and workforce (for the headline employees and R&D figures).
2. **Units still found.** The unit rule of v2.0.8 (a figure's own page, or the page before) still applies. The page before a section heading is included when it ends with a unit declaration.
3. **Announcements.** An announcement with none of these headings is skipped in under a second and marked read. Only periodic reports without the headings are read whole, as before.
4. **The same facts.** On the synthetic corpus, targeted and whole reading must give the same facts. So `EXTRACTOR_VERSION` stays "financials-2", and the 859 documents already read are not read again.
5. **The desktop.**
   - The form's default stays "Reports: reports".
   - Choosing "all" shows how many announcements it adds.
   - Under v2.0.10, "all" costs little, so the warning is a count, not a refusal.

**Expected effect.** From about 35 seconds a document to a few seconds, as for the other extractors (finding 97: 300 s to 1.7 s). The author's 655 unread documents would take under an hour, not about six.

**Accepted when:**
- targeted and whole reading give the same facts on the synthetic corpus;
- a generated 251-page report is read in under a tenth of the time of v2.0.9;
- an announcement without statements is skipped without its pages being laid out.

## 4. Workstream C: top-10 coverage (finding 98)

**The fault (as far as can be told without the reports).** 167 of 905 reports gave rows. The reading kept from each table found 1,145 rows, while the other reading found 1,684 rows under other names. The dual run drops such rows as fragments of broken rows. At this scale they are probably real rows that the kept reading missed, or rows it read under a different name.

**The fix, in two parts.**
1. **A diagnostic the author can send instead of PDFs.**
   - **The command.** `inspect-tables DISCLOSURE_ID --table top10` writes a small text file. It holds the pages of the section, in both readings, and the parser's decision on each line: header, row read, row rejected (with the check that failed), or ignored.
   - **Privacy.** Shareholder names appear in the file as they do in the report: these are disclosed data, but the file is the author's to share or not.
   - **What it gives.** It shows the layouts the parser misses without the PDF itself leaving the author's machine.
2. **Rows only one reading found.** These are kept when they pass the table checks of v2.0.7:
   - rank 1 to 10;
   - a percentage between 0 and 100;
   - the table's percentages adding up to no more than 100;
   - no more than ten rows.
   
   They are marked SINGLE, with lower confidence, and listed in the review queue. Rows that fail stay dropped, as now. The extractor's version becomes "top10-3", so the next run re-reads all 905 reports (about 25 minutes).

The parser itself is changed for new layouts only once the diagnostic output or the PDFs show them.

**Accepted when:**
- the share of reports with rows rises well above 18%, on the author's run;
- no row is kept that fails the checks;
- a test reproduces both readings finding different rows of one table.

## 5. Workstream D: what failures and checks report (findings 96, 106, 108 and 109)

1. **Errors in full (finding 96).** Every failed action writes its full error, with the traceback, to `run_log.txt` and to a file in `logs/`. The output panel keeps the plain one-line message, with the file's name. A failure like finding 96 can then be diagnosed from the run log alone.
2. **The self-test (finding 106).** The quote-list check reports every variant's result, and names the one that answered, as "Diagnose the quote list" does.
3. **Findings as rates (finding 108).** "Show findings" adds, for each rule, the number of observations checked: segment tables compared, document pairs compared, balance sheets checked. Each rule then reads as a rate. For segment mismatches it also gives how many are within 10%, within 50%, or beyond, and for discrepancies, how many fall under each pattern (DIGITS_GLUED, POWER_OF_TEN, SIGN, OTHER).
4. **Panel coverage (finding 109).** The panel's warning names how many companies have financial figures for the period, and how many have downloaded reports. For example: "Financial figures exist for 170 of 5,181 companies; reports are downloaded for 295. Download periodic reports ('Download documents', kind reports) to cover more."

## 6. Tests

Each fault gets a test that fails on v2.0.9:
- a BSE and a B-share company with only A-share lists read, and with the B-share lists read;
- the BSE quote-list filter, against a mock list;
- targeted financial reading giving the same facts as whole reading on the synthetic corpus;
- an announcement without statements skipped without layout;
- two readings of one top-10 table finding different rows, and the checks deciding which are kept;
- `inspect-tables` output for a known table;
- a failed action leaving its traceback in the run log;
- the self-test's message listing every variant;
- the findings summary with rates;
- the panel's coverage line.

The full matrix as before:
- Linux Python 3.12 and 3.13;
- PostgreSQL 16;
- Windows Python under Wine, with the installer;
- GitHub CI.

## 7. Order of work

| Step | Content | Depends on |
|---|---|---|
| 1 | Workstream B (financial extraction) and A (optional boards) | Nothing |
| 2 | Workstream C, part 1 (`inspect-tables`) and part 2 (single-reading rows) | Nothing; the parser changes wait on the author's output |
| 3 | Workstream D | Nothing |
| 4 | Release v2.0.10. The author runs, in order: "Update the company list", "Extract figures from reports" (reports), "Read top-10 shareholders", "Run all checks", and `show-flags --export` | Steps 1 to 3 |
| 5 | A parser fix for the top-10 layouts shown (v2.0.11, if needed) | The author's `inspect-tables` output or PDFs |
| 6 | v2.1, with visualisation V0 and V1 beside it | v2.0.10 live |

## 8. After v2.0.10 (author)

1. "Update the company list". Expect the BSE and B-share companies LISTED and dated, and about 188 in neither list.
2. "Test price sources", then choose under Settings.
3. "Extract figures from reports" with "Reports: reports". It should finish the remaining reports in under an hour.
4. "Read top-10 shareholders" (re-reads all reports once, about 25 minutes).
5. "Run all checks", then "Show findings" (now with rates), and `show-flags --export exports/findings.csv`.
6. For two or three reports still without top-10 rows: `inspect-tables ID --table top10`, and attach the files.
