# v2.0.7 live-run findings

**Source:** the author's desktop log of 24 October 2026 under v2.0.7, and a screenshot of the installer. The log has six actions:

1. "Update the company list" (42 s);
2. "Diagnose the quote list";
3. "Count by board";
4. "Read listing events from announcements";
5. "Re-catalogue busy days" (29 April, 31 min);
6. "Read top-10 shareholders from reports", which had just started when the log was copied.

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

## What to do now

1. Let "Read top-10 shareholders from reports" finish, then check 陕国投A: `ashare-cli show-ownership 000563` should show its real percentages (26.80, 16.76 …) and names without the nature glued on.
2. "Resolve entities", then `rebuild-security-history`, so that the listing and delisting events reach the point-in-time universe.
3. Make the release again, then rebuild a panel. Most rows should now be included by listing record, not report evidence.
4. Optionally, "Download daily prices" for one company, to see whether Eastmoney's price history still answers (finding 73).

**For a later patch:**
- the installer's check for a running copy (finding 74);
- the NOT_IN_EXCHANGE_LIST status with delisting dates (finding 71);
- a second price source, if finding 73 shows that price histories are refused too.
