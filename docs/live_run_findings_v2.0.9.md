# v2.0.9 live-run findings, second part (findings 112 to 117)

The author's log of v2.0.9 runs from "Update the company list" to "Extract R&D and workforce from reports". Its first part, up to the panel, is recorded as findings 103 to 111 in `docs/live_run_findings_v2.0.8.md`. This document records the rest: two more financial runs, which finished the extraction, ESG extraction, and R&D and workforce extraction. It also records two things in the first part that were not recorded then (the slow documents and the trading calendar).

Each finding is marked with what has been done about it:
- **closed by v2.1.0**: the fault was already fixed in v2.1.0, released the same day;
- **fixed in v2.1.1**: fixed now;
- **open**: needs material from a live run before it can be fixed;
- **information**: no fault.

## Summary

| No. | Finding | Severity | Status |
|---|---|---|---|
| 112 | Financial extraction finished: all 1,514 documents read | Information | v2.1.0 makes the next run several times faster |
| 113 | A few documents took up to an hour and a half each | Medium | Fixed in v2.1.1 |
| 114 | ESG extraction read whole documents, without resume or progress | Medium | Fixed in v2.1.1 |
| 115 | The trading calendar was built for Shenzhen only | Medium | Fixed in v2.1.1 |
| 116 | R&D and workforce: 600 reports at 2.2 s each | Information | None needed |
| 117 | ESG extraction found 77 values in 304 documents | Low | Open |

Several lines of the log repeat findings already closed by v2.1.0; they are listed at the end.

## 112. Financial extraction finished

**Evidence.** Eight runs of "Extract figures from reports" (kind all), each stopped by the author and resumed, read every document. The last two were:
- "638 document(s) to read from 122 companies; 876 already read", stopped at 375 after 14,030 s (37.3 s each);
- "263 document(s) to read from 52 companies; 1,251 already read", which finished: "documents: 262, facts_inserted: 12399, skipped: 1, errors: []" after 9,482 s.

**Assessment.** Resume worked across all eight runs: no document was read twice and none failed. At 33 to 58 s a document, whole reading took about 15 hours for 1,514 documents. v2.1.0 reads only the key-figure and statement pages and reads several documents at once (findings 101 and 107). On the synthetic long reports this takes a fraction of the whole-reading time. The new extractor version (financials-3) reads every document once more, so the next run gives a direct measure of the gain.

## 113. A few documents took up to an hour and a half each

**Evidence.**
- In the third run, the mean time rose from 33.2 s at document 80 to 97.9 s at document 83 (of 1,035): documents 81 to 83 took about 5,470 s together, about an hour and a half.
- In the last run, the mean rose from 44.9 s at document 6 to 90.4 s at document 9: about nine minutes for three documents.
- The first document of a run often took more than 100 s ("1 of 638 documents; 102.6 s each"; "1 of 263 documents; 113.4 s each"). Part of that is opening the PDF library and the first index, and part is the document.

**Assessment.** A serial run loses only the time of the slow document. In v2.1.0's parallel reading, results were written in one global order, so one slow document held back every later result. Once the window of queued documents filled, the other workers stood idle until it finished. An hour-and-a-half document would have stopped the whole run for an hour and a half.

**Fix (v2.1.1).**
- Results are kept in order only within a company. A company's later report may supersede an earlier one, so its reports are still written in their date order, as in a serial run. Other companies' reports are written as soon as they are read.
- Only documents still being read count against the window, so the other workers keep working.
- Each result records how long its document took and how many pages it has. A run's summary names its five slowest documents when they took more than two minutes (`slowest`: disclosure id, seconds, pages, title).

Run the slowest of them through `inspect-tables` (or send the report) if they recur under v2.1.1: a report that takes an hour in targeted reading is a fault in itself.

**Tests.** `test_v211.py`: a slow document holds back only its own company; each result gives its time; the slowest documents are named only when they are slow; and extraction totals name them.

## 114. ESG extraction read whole documents, without resume or progress

**Evidence.**
- "... 25 documents read (0.1 per second)" up to "... 300 documents read (0.0 per second)", the progress lines of v2.0.7 and earlier.
- "documents: 304, sustainability_reports: 2062, values: 77, inserted: 2139" after 6,939.5 s, about 23 s a document.

**Assessment.**
- **Not converted.** Findings 76, 77 and 79 (v2.0.8) gave the table extractors targeted reading, progress and resume, but ESG extraction was not converted with them. It read every page of every annual report with the slow reader. Stopped, it started again from the beginning.
- **Title rows.** The 2,062 sustainability reports are recorded from their titles (`sustainability_report_published`), which needs no download. Most of them are catalogued (kind all) but not downloaded, which is why only 304 documents were read.

**Fix (v2.1.1).**
- ESG extraction uses the same progress, resume and parallel reading as the other extractors (`esg-2`). Progress is given as documents done, seconds a document and time left, and a stopped run continues with the next document. "Read reports again" (`--again`) reads everything.
- An annual report is read on the pages of its environmental and social sections only: 环境和社会责任, 环境信息情况, 重点排污单位, 排污信息, 社会责任情况, 乡村振兴, 脱贫攻坚, 对外捐赠, 温室气体, 碳排放, with the three pages after each heading. When none is found the whole report is read, as before.
- A sustainability, CSR or ESG report is about nothing else, so it is still read whole.
- The title rows are written before the reading, for every sustainability report, downloaded or not.

The cached section indexes are rebuilt once (index version 3), which takes a few seconds a report.

**Tests.** `test_v211.py`:
- the environmental section is read and the run resumes;
- a figure mentioned outside the section is not taken;
- a sustainability report is read whole and dated without its file;
- parallel and serial runs give the same values.

## 115. The trading calendar was built for Shenzhen only

**Evidence.** "Build the trading calendar": "{'exchanges': ['SZSE'], 'days_added': 188}".

**Assessment.** The calendar is derived from stored daily prices. Each exchange's days came only from its own companies' prices, and prices were stored only for Shenzhen companies. The suspension check of a Shanghai or Beijing company looks up its own exchange's days. It would have found none and reported no suspensions, however long the company had not traded. The three mainland exchanges keep one calendar (the same holidays and make-up working days).

**Fix (v2.1.1).** Prices from the three exchanges are pooled, and each day found is written for SSE, SZSE and BSE. The output names the exchanges whose prices were used ("bars_from"). An imported calendar is still kept, and still overrides a derived day.

**Test.** `test_v211.py`: a calendar from Shenzhen prices serves a Shanghai company's suspensions, and a second run adds nothing.

## 116. R&D and workforce: 600 reports at 2.2 s each

**Evidence.** "600 document(s) to read from 295 companies" in 1,300 s. "values: 5378, dual_run: agree 5040, disagree 49, single 289, secondary_only 55, read_whole: 16, scanned_documents: [405]".

**Assessment.**
- **Speed.** Targeted reading works as intended: 2.2 s a report, against 23 s for whole reading in finding 114.
- **Agreement.** The two readings agree on 93.7% of values and disagree on 0.9%. The disagreements are recorded as PARSER_DISAGREEMENT and appear in "Show findings".
- **Whole reading.** Sixteen reports had none of the section headings and were read whole.
- **Scanned report.** Document 405 is a scanned report with no text layer; no reader can take figures from it without OCR, which the system does not do.

Nothing to fix.

## 117. ESG extraction found 77 values in 304 documents

**Evidence.** "documents: 304, values: 77".

**Assessment.** About one value in four documents. Some annual reports state only "详见社会责任报告" (see the sustainability report), and many companies are not key pollutant-discharge units, which disclose the most. Even so, the yield suggests that the parser misses figures set out in tables, for example emissions by pollutant in columns, which the line-by-line patterns do not read. This cannot be judged without examples.

**Open.** After running "Extract ESG from reports" under v2.1.1, send two or three annual reports of key pollutant-discharge units (重点排污单位) for which `esg CODE` shows no emissions. Their 环境和社会责任 pages are enough.

## Repeated in this log, closed by v2.1.0

- **Unrecognised code 201872.** It is China Merchants Port's B share, recognised by v2.1.0 (finding 9, with finding 104).
- **"872 in neither exchange's list".** These, and the 1,029 companies without listing dates in "Check the company list", are Beijing and B-share companies whose boards the exchanges' A-share lists do not cover. v2.1.0 applies the status only where the company's own board's list was read, and dates them from their own lists (finding 104).
- **eastmoney_market_list FAIL in the self-test,** while "Diagnose the quote list" showed push2 answering. Eastmoney answers intermittently. v2.1.0's self-test passes on the first variant that answers and lists every variant tried (finding 106).
- **"5,011 of 5,181 rows have no financial figure at all".** This is coverage, not a fault: reports are downloaded for 295 companies. v2.1.0's panel says how many companies have figures and reports (finding 109).
- **Top-10 holders and control read 0 documents.** Every report had been read by those versions. v2.1.0's new top-10 version (top10-3) reads them all once more.

## What to do now

1. Install v2.1.1.
2. Follow the steps after upgrading in `CHANGELOG.md` (v2.1.0): "Update the company list", "Extract figures from reports" (kind reports), "Read top-10 shareholders from reports", "Run all checks", "Show findings".
3. Then "Build the trading calendar" and "Extract ESG from reports". Both are quick now.
4. Send the summaries. If any shows `slowest`, add the titles it names.
5. For finding 117, send the reports it asks for.
