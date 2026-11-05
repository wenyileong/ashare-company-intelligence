# v2.2.0 live-run findings (findings 140 to 148)

The author sent one v2.2.0 log (5 November 2026). It covered:
- the Visualise section (two ego maps, guidance against outcome, data coverage, three topology views);
- the company charts in their new place;
- a catalogue of every kind of announcement from 2020;
- the price-source test and a whole-market price download.

The reports had not yet been read again under v2.2 (financials-5, control-4). The topology view says "Reports are downloaded … but not yet read". So the balance-sheet and controller fixes are not yet tested; that is the next step of the test plan.

## Summary

| No. | Finding | Severity | Status |
|---|---|---|---|
| 140 | Ego map: regulatory events without a named authority are left out, and the note says there are none | Medium | To fix in v2.2.1 |
| 141 | Guidance against outcome: 105 of 2,208 paired, without saying why the rest are not | Low | To fix in v2.2.1 (the reasons); the count should rise after the re-read |
| 142 | Topology view: a code given twice is counted twice in the heading | Low | To fix in v2.2.1 |
| 143 | The catalogue stopped after three 504 Gateway Time-out errors in a row (33 days failed) | Medium | To fix in v2.2.1 |
| 144 | The whole-market price download shows no progress and does not resume | High | To fix in v2.2.1 |
| 145 | Moving the data folder breaks the links to the downloaded documents | High | To fix in v2.2.1 |
| 146 | Small wording ("1 announcements", "2020-12-30 to 2020-12-30", the failed days listed twice) | Low | To fix in v2.2.1 |
| 147 | Data coverage, the company charts and the views' files | Information | Work as designed |
| 148 | The pace of a full "kind all" catalogue | Information | About 7.5 hours a year of announcements |

## 140. Ego map: events without a named authority

**Evidence.**
- **600519:** readiness reports "regulatory events: ready (2 rows for 1 company)", but the map says "regulators NONE … no regulatory event published by then".
- **600400:** 5 rows, but the map shows "4 event(s) from 2 authorities".

**Cause.** The map draws an event only under the authority that issued it. An event read from an announcement's title often names no authority, and such events were dropped without a word. The note then wrongly said that none had been published.

**Fix.**
- Events without a named authority are drawn under one node, "authority not named", with their count.
- The note gives events shown, events without an authority, and events published after the date.

## 141. Guidance against outcome: why most guidance is unpaired

**Evidence.** "Guidance with a later report: 105 of 2,208". Within the range: 44%; median absolute error: 7.0%.

**Assessment.** Most guidance has no periodic-report figure to compare with yet, for three reasons:
- the reports have not been read again since the upgrade;
- quarterly and half-year guidance needs those reports' figures, and few have been read;
- guidance for 2026 periods has no report yet.

**Fix.** The notes and the summary split the unpaired guidance by reason:
- the period has not ended, or its report is not yet due;
- the report is not catalogued;
- the report is catalogued but not downloaded;
- the report is downloaded but not read;
- the report was read without net profit attributable.

The count should be checked again after "Extract figures from reports".

## 142. Topology view: a duplicated code

**Evidence.** The codes given included 688012 twice. The heading said "15 companies", the layers "4 of 14 companies".

**Fix.** Codes are de-duplicated before they are counted, and the heading notes any duplicate dropped.

## 143. The catalogue stopped on gateway time-outs

**Evidence.** After 7.5 hours, three windows in a row (30 December 2020 to January 2021) failed with "504 Gateway Time-out". The run stopped, leaving 33 failed days to retry. Running it again retries only those days, as designed.

**Cause.** A server error is retried three times within about three seconds. A gateway time-out at CNINFO usually lasts minutes.

**Fix.**
- Server errors (502, 503, 504) are retried with growing pauses, up to five minutes, before a window counts as failed.
- The pauses can be stopped like the run itself.
- Progress says "CNINFO is not answering (504); waiting".

## 144. The whole-market price download

**Evidence.** `acquire-market --start 2020-01-01 --end 2026-11-05` printed nothing for 85 minutes, until the author stopped it.

**Cause.**
- The download reports nothing until every company is done.
- A rerun starts again from the first company and fetches the prices already stored.

**Fix.**
- Progress by company: count, seconds each and the time left.
- A rerun skips companies whose stored prices already cover the period (from the same source and adjustment), unless "fetch again" is ticked.
- The result is shown when the run is stopped.
- The errors are listed by company.

## 145. Moving the data folder

**Evidence.** The author asked whether moving the program's files out of `C:\Users\User` would break anything.

**Cause.** The database stores the full path of each downloaded document (`disclosures.local_path`) and of each archived source response (`raw_records.payload_path`), for example `C:\Users\User\…\disclosures\600519\<hash>.pdf`. After a move:
- those files are treated as not downloaded;
- reading again (financials-5, control-4) skips them;
- downloads fetch them again from CNINFO.

The scheduled daily update, if one was set up under Operations, also names the old folder.

**Fix.**
- **Paths relative to the data folder.** Paths are stored relative to the data folder. Existing absolute paths are read through a fallback: when a stored path is missing, the file is looked for at the same place under the current folder. The documents are named by their SHA-256 under `disclosures\<code>\`, so the match is exact, and the hash is checked.
- **"Move data folder"** (Settings): it moves the folder or adopts one already moved, rewrites the stored paths, re-creates the scheduled update and records the move in the run log.
- **Files check.** "Check files" reports stored paths outside the data folder.

Until then, see the advice given with this record (move nothing yet, or move and rewrite the paths).

## 146. Wording

- "2020-04-05 to 2020-04-06: 1 announcements" should read "1 announcement".
- A single day is shown as "2020-12-30 to 2020-12-30".
- The failed days are listed twice at the end of a catalogue run.

## 147. What worked

- The Visualise views ran and wrote every file:
  - the ego map, 0.2 to 0.5 s;
  - guidance against outcome, 2.6 s;
  - data coverage over 5,209 companies listed at the end of 2025, 4.0 s.
- The readiness notes matched the data: no controllers, holders, subsidiaries or rosters read yet; no industry classification imported, so coverage grouped by board.
- "Export a chart" and "Price chart with events" work in their new place.
- Both price sources answer (Eastmoney and Tencent, 600519 closing at 1,452.00 on 5 November 2026).

## 148. The pace of a full catalogue

The catalogue of every kind for 2020 took 7.5 hours for 364 days: 534,105 announcements in 19,813 queries. Busy days near the reporting deadlines are split by board, category and manufacturing division, as designed. The remaining 2021 to 2026 will take about 45 hours at this pace. It resumes by day, so it can be run in parts.
