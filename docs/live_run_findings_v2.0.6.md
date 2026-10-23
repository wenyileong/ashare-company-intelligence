# v2.0.6 live-run findings

**Source:** the author's desktop log of 23 October 2026 under v2.0.6. It has four actions:

1. "Update the company list" (49 min 27 s);
2. `probe-cninfo-filters --day 2026-04-29`, run twice (199 requests each);
3. "Re-catalogue busy days" (9 to 12 January and 29 April), still running when the log was copied.

**Second log (findings 65 to 67).** A later copy of the same log adds three things: the re-catalogue, stopped by the author after 41 min 40 s during 29 April; "Which days are catalogued"; and "Diagnose the quote list".

**Release review (findings 68 and 69).** The author passed on a review of a live dataset release (made by the scraper's `release` command, pseudonymised), carried out in another project that reads the release. The review reported two faults, which were then confirmed against the scraper's code. Both are fixed in v2.0.7.

**Status:** findings 58 to 67 are findings only; findings 68 and 69 are fixed in v2.0.7. Numbering continues from the v2.0.5 findings (`docs/live_run_findings_v2.0.5.md`, findings 35 to 57).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 58 | The quote list refused every request after page 10, including the board-by-board reading; no listing dates were added, and the run took 49 minutes | High (finding 57 not resolved) | Confirmed; cause revised |
| 59 | The note does not show the boards that failed before their first page | Low (reporting) | Confirmed from the code |
| 60 | Company queries work for up to 10 companies, and manufacturing divisions almost partition | Information (finding 54 resolved) | Confirmed |
| 61 | A batch of 150 companies is not applied: each batch reports 8,871 rows for a query of 3,024 | High (about 3,000 wasted requests; 29 April not closed) | Confirmed |
| 62 | A split whose part exceeds its parent is treated as complete coverage | High (the cause of finding 61's waste) | Confirmed from the code |
| 63 | 9 to 12 January was read again day by day | Information | Probably closed; to confirm |
| 64 | The default order is unstable on every reading of the January window | Information (finding 56 confirmed) | Confirmed |
| 65 | 9 to 12 January is complete; only 29 April remains short (20 rows) | Information (findings 39 and 63 closed) | Confirmed |
| 66 | Eastmoney refuses every request from this network, page 1 included | High (finding 58: the cause is a refusal, not a row limit) | Confirmed |
| 67 | The Stop message and the window rows work as designed | Information (findings 40, 43 and 51 closed) | Confirmed |
| 68 | Top-10 shareholder rows are misread when the shareholder nature follows the name: the nature is glued to the name and every figure shifts one column | **Critical** (wrong ownership figures in released data) | Confirmed in the code; fixed in v2.0.7 |
| 69 | A natural person's name, glued to its nature, was not masked in a pseudonymised release | **Critical** (personal data in a release marked pseudonymised) | Confirmed in the code; fixed in v2.0.7 |

## 58. The quote list refused everything after page 10

**Evidence.** "0 listing dates added. Note: quote list incomplete: 1,000 companies fetched (whole list: page 11: every variant failed: ... push2 page 11: HTTP 502; ... 82.push2+referer page 11: RemoteProtocolError: Server disconnected without sending a response ...)". The action took 2,967 seconds. Pages 1 to 10 came from the day's cache, so the first request of the run was page 11.

**Assessment (revised).** Finding 57 inferred a limit of 1,000 rows per query, and v2.0.6 reads the list board by board on that basis. The boards did not answer either. Their page 1 is within any such limit, and none of their rows reached the note (finding 59). The likelier cause is that Eastmoney refuses this network after about ten requests, with HTTP 502, for some hours: finding 4 (v2.0.2) recorded the same refusals, which later passed. The 49 minutes are the program's pauses and retries for each of the eight board readings (30 seconds and two minutes each, after six variants with two attempts). Neither cause can be confirmed from this log. `diagnose-quote-list` (eight requests) shows whether page 1 answers now: if it does not, the network is being refused.

**Consequences for the next patch:**
- **Stop on refusal.** When the first page of a board is refused as well, every request is being refused. The reading should stop at once and say so, instead of pausing for each board.
- **Another source of listing dates.** Eastmoney is a convenience feed and refuses automated reading for hours at a time. The exchanges publish their own stock lists with listing dates, and so do CNINFO's company profiles. These are more authoritative and should be considered, but each needs its own live check before it is used. Meanwhile, listing dates can be imported from a file: `import-listing-events-csv` with the columns `security_code,event_type,event_date,old_value,new_value` and rows such as `600519,IPO,2001-08-27,,`, followed by `rebuild-security-history`. The exchanges' websites offer their stock lists, with listing dates, for download.

## 59. Boards that fail before their first page are not shown

**Evidence.** The note ends after the whole list's error. It has no "by board" part, although the boards were read.

**Assessment.** The note lists only boards for which a total or some rows arrived. A board refused on its first page is left out, so the reason the reading failed is hidden. The note should list every board read, with its error.

## 60. Company queries work, for up to 10 companies; divisions almost partition

**Evidence.**
- **Companies.** "company_batches: WORKS; one by one 4 (1, 2, 1); two together 3; three together 4; 10 together 47 (one by one 47); sent with the company's exchange, without a board code". The same result came in both runs.
- **Divisions.** "manufacturing_divisions: PARTIAL; divisions add up to 5,993 of 6,008 (manufacturing); largest part 1,155". The second run gave 5,990 of 6,008.

**Assessment.** Finding 54 is resolved: company queries work when sent with the company's own exchange and no board code. Up to ten companies at once give exactly the sum of the companies one by one. (The two-company figure, 3 against 1 and 2, matches, since it covers the first two companies only.) The manufacturing divisions cover all but about 15 of 6,008 announcements, probably those of companies classified only at section level. Divisions are therefore a useful split but leave a small remainder, which the company queries can cover.

## 61. A batch of 150 companies is not applied

**Evidence.** On 29 April the engine split 日常经营 in manufacturing on the Shenzhen main board (3,024 rows) by company batches. Each batch, "rcjy/制造业/150 companies", reported 8,871 rows, nearly three times the query it was meant to split. Each was then read in full, 100 pages, followed by 100 pages newest first and 100 oldest first.

**Assessment.** CNINFO applies the company field to 10 companies (finding 60) but not to 150. It probably ignores the field beyond some number of companies, or beyond some length, and returns all 日常经营 announcements of the exchange (8,871 is close to the 8,772 on Shenzhen and the Beijing board's share). The probe tested 10, the engine used 150 (`BATCH_SIZE`). Each batch costs about 300 requests, so the ten or so batches for the Shenzhen main board cost about 3,000 requests (more than an hour) and bring no new row of the query being split. No data are wrong: the rows are real announcements of the day, and the day's completeness is checked against its own total. But 29 April cannot be closed this way.

**Remedy:**
- batches no larger than the size the probe confirms (10);
- the probe testing larger batches (for example 25 and 50), to find the largest that works;
- the check of finding 62.

## 62. A split whose part exceeds its parent is taken as coverage

**Evidence.** The code accepts a split when its parts add up to at least the parent's total. Here the parts added up to about ten times 8,871 for a parent of 3,024. A part larger than its parent can only mean that the filter was not applied, yet the engine counted it as coverage and read every part.

**Assessment.** A split with any part larger than its parent should be treated as a filter that is not applied: not used, and not used again for that kind of query. The completeness checks themselves stay sound, because rows are keyed and counted against the day's own total, so this costs requests but loses nothing.

## 63. 9 to 12 January was read again day by day

**Evidence.** The window (2,954) was read in full (2,378 rows after 80 pages), then by day: 9 January 1,171 of 1,171, and 10 January 1,240 (1,200 after 40 of 42 pages). The run then moved to 29 April without a SHORTFALL line for the window. The engine prints a line only for a short or split unit.

**Assessment.** The split by day (v2.0.6, finding 39) worked as designed, and the window was probably complete. "Which days are catalogued" will confirm it.

## 64. The default order is unstable on every reading

**Evidence.** The probe's single reading of the January window brought 2,914 of 2,952 in the first run and 2,926 of 2,954 in the second. The re-catalogue's reading brought 2,378 rows after 80 pages, 22 short of 2,400.

**Assessment.** This confirms finding 56: one reading of a quiet window loses 1% or so of its rows, by a different amount each time. Splitting by day is the right remedy.

## 65. 9 to 12 January is complete

**Evidence.** "Which days are catalogued", problems only: "Status: DONE 288, OPEN 1, SHORTFALL 1 (296 days; a window of quiet days counts once)". The only short day is 29 April (26,046 of 26,066, 20 within the enabled boards). Its record is still the one written by v2.0.5, since the v2.0.6 re-catalogue was stopped during that day before recording it. The partition note shows this: "stock: filter ignored by CNINFO", from the earlier run.

**Assessment.** The split of short windows by day (finding 39) closed the January window: 13 rows that two earlier versions could not reach. The whole 2026 catalogue now lacks 20 rows on one day, in one query (finding 61).

## 66. Eastmoney refuses every request from this network

**Evidence.** "Diagnose the quote list": every variant failed on page 1, five with HTTP 502 and one disconnected ("No variant answered").

**Assessment.** This settles finding 58. The quote list now refuses even its first page, so the failure at page 11 was the start of a refusal, not a limit of 1,000 rows per query. Reading board by board cannot help while the refusal lasts. The same refusals were seen in the v2.0.2 runs (finding 4), and the quote list answered again by the v2.0.3 self-test (finding 33). The refusal therefore seems to come and go, perhaps after a burst of requests. Two consequences:
- **Stop on refusal.** When page 1 of a part fails as well, the program should stop at once and say that the source is refusing requests (finding 58).
- **Another source.** Listing dates should not depend on this feed alone. A second source (the exchanges' stock lists or CNINFO's company profiles) should be added after a live check. Until then, the import route in finding 58 is available.

The 1,000-row reading added in v2.0.6 does no harm and stays useful if such a limit exists, but it is not shown to be needed.

## 67. The Stop message and the window rows work

**Evidence.** "Stopped: stopped by the user; everything saved so far is kept; running it again resumes with the first unfinished day", and the status line counting a window once.

**Assessment.** Findings 40, 43 and 51 are closed as far as this log shows. Extraction's progress and resume have not yet been seen live.

## 68. Top-10 shareholder rows misread when the nature follows the name

**Evidence (release review).** A live release held 16 top-10 shareholder rows, all for 陕国投A (000563).
- The shareholder nature was glued to the end of the name, for example "…有限责任公司国有法人".
- The real percentage stood in `change_shares` (26.8, 16.76 …).
- `ownership_pct` held stray figures (0.0, 46.0, −519.0).

**Cause (confirmed in the code).** `parse_top10_pages` read every row in the column order of the older template: name, change in the period, shares held, percentage, restricted shares, pledge state, and the nature at the end. The Shenzhen templates put the nature straight after the name, then the percentage, the shares held, the change, and restricted and unrestricted shares. In that layout:
- the nature was read as part of the name;
- the percentage was read as the change;
- the change, or a share count, was read as the percentage.

The only check was that the percentage did not exceed 100, which 0, 46 and −519 all pass. The synthetic test corpus generated only the older layout, so the parser accuracy gate could not catch it.

**Fix (v2.0.7).**
- **Both layouts read.** The layout is taken from the header, or from where the nature stands. The figures after the shares are placed by checking that restricted and unrestricted shares add up to the shares held.
- **Checks.** A nature glued to a name is taken off. A row whose percentage is outside 0 to 100 is left out, and a table whose percentages add up to more than 100 is rejected. A number that is really two cells run together ("833,820,000200,000") is not read.
- **Wrapped names.** A name wrapped onto two lines is joined, in both tables.
- **Old rows removed.** Rows an earlier parser read from a document, and the current one does not, are removed when the document is read again, with their review items. `resolve-entities` removes entities left only by such rows.
- **Corpus.** Half the reports in the synthetic corpus now use the other layout, a quarter with the nature glued to the name. On that corpus the text reader's precision for the top-10 table is 100% (82.1% before, on the older corpus), and the layout reader's stays at 100%.

## 69. A natural person's name unmasked in a pseudonymised release

**Evidence (release review).** Because the nature was glued to the name (finding 68), one natural-person shareholder was not recognised, and that person's real name appeared unmasked in a release marked "pseudonymised".

**Cause (confirmed in the code).** `is_natural_person` treated a name as a person's only if it looked like a two-to-five-character Chinese name, or if its nature said so. "张三境内自然人" (seven characters) failed the first test, and its nature, misread, did not pass the second. A person's name written in Latin letters ("JOHN SMITH") without a nature would also have been released unmasked. Masking failed open: anything unrecognised was released as it stood.

**Fix (v2.0.7).**
- **Fail-safe rule.** A name is now masked unless a legal-person nature, or a word only organisations use (公司, 基金, 银行, LIMITED, BANK, AUTHORITY ...), shows it to be an organisation's. A nature glued to a name is taken off first, and the bare name receives the same identifier, so it is also replaced where it occurs in free text.
- **Cost.** Masking an organisation by mistake loses a little information. Leaving a person unmasked is a privacy failure.
- **The manifest.** Each release now records the rule in `manifest.json` (`pseudonymisation.rule`), so a release made under the earlier rule can be recognised.
- **Existing releases.** Releases made before v2.0.7 should not be shared. After upgrading:
  1. run `extract-top-holders` (which also removes the misread rows);
  2. run `resolve-entities`;
  3. make the release again.

## What to do now

- **The running re-catalogue.** It can be left to finish or stopped. Stopping loses nothing, since everything saved is kept. 29 April will probably stay about 20 rows short under v2.0.6 (finding 61). The January window has probably been recorded already.
- **Then:**
  - "Which days are catalogued", problems only, to confirm January;
  - "Diagnose the quote list", to see whether Eastmoney answers at all from this network.
- **The next patch (v2.0.7):**
  - company batches of at most 10, larger sizes tested by the probe, and parts larger than their parent rejected (findings 61 and 62);
  - the quote list stopping at once when everything is refused, and listing every board in its note (findings 58 and 59);
  - a second source of listing dates, after a live check.
