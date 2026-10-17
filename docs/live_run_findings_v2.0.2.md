# A-share Company Intelligence v2.0.2: findings from the live runs

**Sources.**
- Log A, supplied 10 October 2026: 2,990 lines, 30 actions.
- Log B, supplied 11 October 2026 in two copies, each continuing log A. The pasted copy (3,273 lines, 49 actions) contains everything in the attached copy (3,211 lines, 44 actions), so the pasted copy was analysed.

Findings 1 to 12 come from log A, with figures updated from log B where it adds evidence; findings 13 to 18 are new in log B.
**Status:** recorded for future builds. Nothing has been changed in the code.
**Legend:** *Confirmed* = shown directly by the log. *Inferred* = the most likely explanation, to be verified before fixing.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | PDF font warnings: text in some fonts may be extracted incompletely (fontTools not bundled) | High (silent data quality) | Confirmed warning; effect inferred |
| 2 | Extraction runs at about 10 to 20 seconds per document | High (whole market would take days) | Confirmed (both logs) |
| 3 | The market-wide catalogue ignores the exchange column, so every query runs twice | High for kind "all" (doubles a run of a day or more) | Confirmed |
| 4 | The Eastmoney quote list fails (502), so no listing dates are stored and every panel has 0 rows | High (empty dataset) | Confirmed twice; now looks persistent, not transient |
| 5 | Warning text floods the output and run log (2.1 MB of 2.2 MB) | Medium | Confirmed |
| 6 | Days with more than 3,000 announcements: results beyond 3,000 appear unreachable, and paging runs on to 2,000 pages | **Critical** (missing data on the busiest disclosure days; hours of wasted requests) | Triggered in log B; strongly supported by the counts, to be confirmed with one test |
| 7 | Parquet is offered in the desktop build, which has no pyarrow; the failure leaves partial panel files | Low | Confirmed |
| 8 | Empty results give no reason (compare, transactions, regulatory events, calendar) | Low (usability) | Confirmed |
| 9 | Code 201872 not recognised | Low | Confirmed |
| 10 | Optional-board settings can be changed while an action is running | Low | Confirmed |
| 11 | The progress rate display is too coarse ("0.0 per second") | Low | Confirmed |
| 12 | Status line "0 listed" is misleading when the quote list failed | Low | Confirmed |
| 13 | "Running it again resumes" is not true for the catalogue: every run restarts at the start date | High (hours repeated per restart) | Confirmed |
| 14 | An error inside a split window abandons the rest of the month, and the error report hides what was done | High (silent gaps) | Confirmed |
| 15 | No progress within a window: a busy day can run for over an hour with no output | Medium (looks stuck) | Confirmed |
| 16 | Intermittent DNS failures on the user's connection ("getaddrinfo failed") | Medium (environmental) | Confirmed |
| 17 | The dataset explorer opens on an empty panel with blank output | Low | Confirmed |
| 18 | `show-market` prints nothing at all when there are no prices | Low | Confirmed |
| 19 | The layout extractor depends on the computer's CJK fonts when a PDF's fonts are not embedded | Medium (results can differ between machines) | Confirmed in GitHub CI and reproduced locally |

## 1. Font warnings during PDF text extraction (possible silent loss of text)

**Evidence.**
- 2,428 lines of the form `fontTools is required to fully parse the encoding of a CFF Type1 font in font dictionary {...}`.
- The fonts involved are mainly HelveticaNeueLTPro-Lt and -Bd (about 2,350 lines), with some MyriadPro-Regular.

**Why it matters.** pypdf needs the optional `fontTools` package to decode the character encoding of these embedded fonts, and the Windows build does not include it. Text set in these fonts may therefore come out wrong or empty. In Chinese reports, Latin fonts such as Helvetica Neue are often used for figures, dates and English terms. If figures in the financial tables are set in them, numbers could be missed or garbled with no error raised.

**Inferred, not yet verified.** Whether figures are actually lost has not been checked. To verify:
1. take one affected report;
2. compare pypdf text with pdfium text (pypdfium2 is already bundled and does not need fontTools);
3. compare both with the values in the PDF.

**For a future build.**
- Bundle `fontTools` (pypdf's optional dependency) and confirm the warnings disappear.
- Count, per document, the fonts pypdf could not decode, and lower the confidence of values from such documents.
- Consider pdfium text as the primary text layer, since it handles these fonts without extra packages.

## 2. Extraction is very slow

**Evidence.**
- `extract-financials --kind reports` read 525 documents in 11,324.8 s, about 21.6 s per document, before it was stopped.
- A second run (`--kind all`) read 1,475 documents in 17,985.6 s before it was stopped (log B), about 12.2 s per document.

**Why it matters.** The whole market has about 22,000 periodic reports a year. At 10 to 20 s each, one extraction pass takes three to five days. Each extractor (financials, top-10 holders, segments, subsidiaries and the others) reads the same PDFs again.

**Likely causes (inferred, to profile).**
- pypdf text extraction of 200 to 300 page annual reports.
- The layout variant (pdfium character boxes for every page) runs as well, because table parsers are dual-run.
- Each font warning in finding 1 formats a large dictionary as text, thousands of times.
- Extracted text is not cached across extractors or runs.

**For a future build.**
- Profile one annual report end to end.
- Cache page text per document hash, in the existing `document_pages` table or a sidecar file, and share it across all extractors.
- Read only the pages the parser needs (find the section first, then extract those pages).
- Run the layout variant only on candidate table pages.
- Process documents in parallel (worker processes), keeping database writes in the main process.
- Show seconds per document and an estimated time to finish (see finding 11).

## 3. Market-wide catalogue: every query runs twice

**Evidence.**
- Every monthly or split window shows identical totals for SSE and SZSE: for example, 2,931 announcements for 27 to 28 August on both.
- Each pass totals 28,382, and the run fetched 56,764 = 2 × 28,382 in 1,934 queries (2,952.8 s).
- "25,036 new, 28,034 already known" is consistent with the second pass re-reading everything the first pass had stored.

**Cause (confirmed by the data).** When the stock field is empty, CNINFO ignores the `column` parameter and returns the whole market for either value.

**Effect.**
- About half the queries and half the time are wasted: around 25 minutes for kind "reports". For kind "all" the SSE pass alone had not finished after several runs totalling over 20 hours (log B), so the duplicate SZSE pass would cost as much again.
- About 28,000 rows are rewritten for nothing.
- The per-exchange progress lines are misleading.

**What went right.** Paging was complete: the totals reported by CNINFO match what was stored, so nothing was truncated.

**For a future build.**
- Query the market once per window (one column), and assign the exchange from the security code.
- Have the self-test check whether the two columns return identical totals.
- The daily update (`catalogue_market_day`) uses the same pattern and probably has the same duplication.

## 4. A transient Eastmoney error empties the panel

**Evidence.**
- `update-universe` reported: `listing dates not fetched: HTTPStatusError: Server error '502 Bad Gateway' ... clist/get?pn=5`. The error came on page 5, after four pages had already been read.
- "Status: 0 listed, 164 delisted (by name), 0 not in the quote list; 0 listing dates added."
- `build-panel` then returned `{'rows': 0, ... 'dropped': {'excluded_no_listing_date': 5576}}` and reported "Done", writing empty panel files.

**Why it matters.** One failed page (after retries) discards the pages already fetched. Because v2.0.2 leaves out companies with no listing date, the next panel silently contains nothing. A temporary server fault therefore becomes an empty dataset that looks like a successful run.

**Log B.** "Update the company list" was run again and failed the same way, this time on the very first page (`pn=1`), and two further panels again had 0 rows with all 5,576 companies excluded. A failure on every attempt, while the price-history service on another Eastmoney host (`push2his`) works, suggests a persistent problem rather than a passing fault. Possible causes, all inferred:
- the quote-list service now refuses requests without browser-like headers (for example a Referer);
- the access token parameter (`ut`) or the field list has changed;
- the host is blocked or throttled from the user's network.

The self-test's quote-list check should show which.

**For a future build.**
- Diagnose the 502 first: compare the request with what Eastmoney's own web page sends, and try the alternative quote hosts.
- Keep the pages already fetched.
- Retry with a longer back-off.
- Make the listing-date step resumable, or let it run again on its own (separate command, or part of the daily update).
- `build-panel` should fail, or at least warn prominently, when the universe filter removes most companies, and should name the fix.
- For fiscal-aligned panels, consider falling back to evidence of listing (for example a periodic report published for the period), flagged as such, rather than excluding everything.

## 5. Warning text floods the output and run log

**Evidence.** Of the 2.2 MB log:
- 2,428 fontTools warnings, each several hundred characters of font dictionary;
- 260 "Ignoring wrong pointing object" messages (malformed cross-reference tables in some PDFs, usually harmless);
- 79 progress lines;
- only about 250 lines of real output.

**Effect.**
- The desktop output and `run_log.txt` become hard to read and grow quickly.
- Real errors are easy to miss.
- Formatting the messages costs time (see finding 2).

**For a future build.**
- Route pypdf's logger to a per-document counter.
- Report a one-line summary, such as "38 documents had font-decoding warnings; 12 had damaged cross-references", with the list saved to a file.

## 6. Days with more than 3,000 announcements (now critical)

**Log A.** With kind "reports" no single day exceeded 3,000 (busiest: 2,693), and the totals stored matched CNINFO's totals exactly. That run was complete.

**Log B (kind "all").** Many single days exceed 3,000 announcements:

| Date | Announcements |
|---|---:|
| 27 March | 4,660 |
| 28 March | 7,154 |
| 31 March | 12,213 |
| 21 April | 8,367 |
| 23 April | 13,196 |
| 24 April | 15,382 |
| 25 April | 13,724 |

These cannot be split further, because the smallest window is one day.

**What the counts show.** The last run, which began on 24 April, reported:
- 2,705 queries and 81,060 announcements, which is 30 announcements on every page;
- but only 2,756 of them were new and 77,305 "already known";
- yet the only windows it reached were 24 April (15,382) and part of 25 April (13,724). Together these need about 970 pages.

The arithmetic fits one explanation:
- **24 April** ran to the code's limit of 2,000 pages;
- **25 April** ran about 700 pages before the network failed;
- **every page was full**, even far beyond the last real page;
- **almost every result was a repeat.**

That is consistent with CNINFO serving at most 100 pages (3,000 results) for one query, then repeating content on later pages while still reporting more to come.

**Consequences.**
- **Data.** On every day with more than 3,000 announcements, everything beyond the first 3,000 is probably missing. These are the busiest days of the annual-report season, so the gap falls exactly where the most material disclosures are. The runs did not report this as an error.
- **Time.** Each such day costs up to 2,000 requests (over an hour at the polite rate) instead of about 100. This explains most of the very long runs in log B: 7,436 s, 9,349 s, 14,112 s, 20,564 s and 28,779 s.

**To confirm before fixing.** Fetch pages 100, 101 and 150 for 24 April and compare the announcement IDs. If page 101 repeats earlier IDs, the cap is confirmed.

**For a future build.**
- Stop paging when a page brings no new announcement IDs, or once the total has been reached.
- Split a day over 3,000 into smaller queries until each is under 3,000. Options:
  - by announcement category (the category codes are already in the program);
  - by exchange plate, if the plate filter works when the stock field is empty;
  - by company groups, as a last resort.
- After each window, compare the unique announcements stored with CNINFO's total, and record any shortfall as an error the user can see.
- Re-catalogue the affected days (27 to 31 March, and most of April and late August, for kind "all") once fixed.

## 7. Parquet offered without pyarrow; partial panel files on failure

**Evidence.** `build-panel ... --formats csv,dta,parquet` failed with "Parquet output needs the optional pyarrow package" after 2.2 s.

**Problems.**
- The desktop build offers the Parquet option although pyarrow is not bundled.
- The code writes CSV and DTA before reaching Parquet, so the failed run leaves new CSV and DTA files beside an older manifest, or without one. The folder is then internally inconsistent.

**For a future build.**
- Hide Parquet in the desktop build when pyarrow is absent, or bundle it (size impact to assess).
- Check that every requested format can be written before writing any file, or write to a temporary folder and move it into place at the end.

## 8. Empty results without a reason

**Evidence.**
- `compare --codes 600519,000858 ...` printed a table of blanks.
- `financial-series 600519` printed "(no rows)".
- `extract-transactions` returned 0 announcements, and `extract-regulatory-events --titles-only` scanned 26,550 disclosures and found 0 events. The catalogue had been built with kind "reports" only, so this is expected, but nothing said so.
- `build-calendar` returned no exchanges. At that point there were no prices; it needs prices for at least two securities a day.

**For a future build.** Print the reason and the next step whenever a result is empty, for example:
- "No financial values for 600519: download its reports and run Extract figures."
- "No announcements of these types in the catalogue: catalogue with kind 'all'."
- "The calendar needs daily prices for at least two securities: run the daily update or Download daily prices."

## 9. Code 201872 not recognised

**Evidence.** "1 code range not recognised: 201872".

**Inferred.** Probably a Shenzhen B share in the 201 range (B-share codes are 200xxx). To confirm against CNINFO's entry for this code, then add the prefix to the B-share map (off by default).

## 10. Settings changed while an action was running

**Evidence.** "Optional boards: BSE", "BSE, B_SHARE", "BSE", "none" appear in the middle of the extraction output: the optional boards were switched while it ran.

**Why it matters.** Extraction is unaffected. But changing optional boards during "Update the company list" or a catalogue run would change behaviour halfway through, because the setting is read from an environment variable on each use.

**For a future build.**
- Disable the optional-board switches while an action is running, or apply changes only to the next action.

## 11. Progress rate too coarse

**Evidence.** "... 25 documents read (0.0 per second)" for documents taking 10 to 20 s each.

**For a future build.** Show seconds per document, the number still to read and an estimated time to finish, for example "525 of 22,000 documents; 21.6 s each; about 5 days left".

## 12. "0 listed" when the quote list failed

**Evidence.** "Status: 0 listed, 164 delisted (by name), 0 not in the quote list". The 0 reflects the failed quote list (finding 4), not the market.

**For a future build.** When the quote list fails, say that status could not be determined, instead of printing zero counts.

## 13. "Running it again resumes" does not hold for the catalogue

**Evidence (log B).** Each catalogue run started again from its start date and re-read days already stored. Three runs from 1 January repeated January to March each time. The user then worked round this by hand, moving the start date to 28 March, 11 April, 15 April and 24 April. The last run reported 77,305 of 81,060 announcements as "already known".

**Why it matters.**
- Records are not duplicated, which is what the message promised.
- But each restart repeats hours of requests.
- The Stop message ("running it again resumes") sets the wrong expectation for this action.

**For a future build.**
- Record each completed day (per kind) as a high-water mark, and skip completed days on the next run unless the user asks for a full refresh.
- Run long catalogues as resumable jobs (the job system already exists for the daily update).
- Word the Stop message for what each action actually does.

## 14. An error inside a split window abandons the rest of the month

**Evidence (log B).**
- In one run, the window 1 to 4 February completed, then a network error was reported as "SSE 2026-02-01 to 2026-02-28: error", and the run moved on to March. The rest of February was skipped.
- In the last run, 24 and 25 April completed (25 April only partly), then "SSE 2026-04-24 to 2026-04-30: error".

**Why it matters.**
- When a month is split into smaller windows, an error in one of them ends the whole month.
- The error is recorded for the whole month, so it hides which parts completed and which did not.
- The user cannot tell what is missing without re-reading the log.
- In the first case a later run happened to fill February. In the second, 26 to 30 April are still missing (as are May onwards, where the run stopped).

**For a future build.**
- Handle errors at the smallest window, carry on with the next window, and list the exact days that failed.
- Combined with finding 13, a rerun then fetches only the failed days.

## 15. No progress within a window

**Evidence (log B).** The catalogue prints one line per window, after that window's first page. A day such as 24 April (15,382 announcements, and up to 2,000 pages because of finding 6) then runs for over an hour with no further output. This is the same "looks stuck" problem that v2.0.2 fixed for the per-company catalogue.

**For a future build.** Print a progress line every 50 pages or so, with the number fetched against the total and an estimated time left.

## 16. Intermittent DNS failures on the user's connection

**Evidence (log B).** "ConnectError('[Errno 11001] getaddrinfo failed')" in two runs. That is the Windows error for a failed name lookup, raised before any request reaches CNINFO.

**Assessment.** Environmental (the user's network or DNS), not a program fault. The program behaved as designed: three failed windows in a row stopped the run with a plain message. With finding 14, though, each failure also abandoned the rest of its month.

**For a future build.** For name-lookup failures, wait and retry for longer (for example up to five minutes) before counting the window as failed, since such outages are often brief.

## 17. Dataset explorer on an empty panel

**Evidence (log B).** "Open the dataset explorer" ran the placeholder command `ashare-cli version` and then "Dataset explorer: summary" printed two blank lines. The panel had 0 rows (finding 4).

**For a future build.**
- Say "The panel has no rows" and give the reason from the panel manifest.
- Do not show the placeholder `version` command as if it were the action.

## 18. `show-market` prints nothing when there are no prices

**Evidence (log B).** `show-market 600519` printed nothing at all, not even "(no rows)" as other commands do.

**For a future build.** Print "(no rows)" and the next step (Download daily prices, or the daily update).

## 19. Layout extractor depends on installed CJK fonts

**Source.** First GitHub CI run, 17 October 2026 (not the live logs).

**Evidence.**
- `test_synthetic_corpus_evaluation_and_gate` failed on GitHub's Ubuntu runner: `subsidiaries@layout` recall was 0.71 against the required 0.95.
- The same test passed on every machine used for building, because each had CJK fonts installed.
- Hiding all system fonts locally reproduced the failure exactly (0.714). Restoring one CJK font (WenQuanYi Zen Hei) made it pass.

**Cause.** The synthetic test PDFs use a standard CJK font (STSong-Light) that is referenced but not embedded. Without a CJK font on the system, pdfium substitutes one with different character widths. The character boxes the layout extractor relies on then change, and rows with wrapped cells are rebuilt wrongly.

**Why it matters.**
- **Real reports.** CNINFO reports usually embed their fonts, but not always. For a report without embedded fonts, results could differ between a Windows desktop (which has CJK fonts) and a bare server or a reviewer's machine.
- **Tests.** The test corpus is not self-contained, so the regression gate is not independent of the machine it runs on.

**Interim fix (applied to CI only).** The GitHub test workflow now installs a CJK font, so CI matches a typical desktop. The program itself is unchanged.

**For a future build.**
- Embed a freely licensed CJK font in the synthetic corpus, so the tests are self-contained.
- When reading a real PDF whose CJK fonts are not embedded and no system CJK font is available, record this per document and lower confidence in layout-extracted values.
- Bundle a CJK font with the program for pdfium to use as the substitute.

## Worked as intended

- The market-wide catalogue completed: 56,764 announcements, with no errors and complete paging.
- The universe update recognised 302132 and 689xxx, summarised exclusions by reason (605 Beijing Stock Exchange, 78 B shares), and found 164 delisted companies by name.
- Stop worked three times; each time the action ended cleanly with the "everything saved so far is kept" message.
- `acquire-market` for 000001 stored 183 daily bars for 1 January to 9 October 2026.
- Log B: the three-failures early stop worked as designed during the DNS outage, with a plain explanation.
- Log B: company reports for 000001, 000002, 000009 and 600519 were written; a short code (00009) was padded correctly to 000009.
- Reports, SQL queries and Stata output worked.

## Suggested order for the next build

1. **Finding 6.** Confirm the 3,000-result cap; stop runaway paging; split busy days; report shortfalls. Then re-catalogue the affected days.
2. **Findings 3, 13 and 14.** One market-wide query per window; resume by completed day; handle errors per day.
3. **Finding 4.** Diagnose the Eastmoney 502; make listing dates resumable; no silently empty panels.
4. **Finding 1.** Verify the effect of the font warnings on figures; bundle fontTools.
5. **Finding 2.** Text cache and extraction performance.
6. **Findings 5, 7, 8 and 15.** Clean output, progress within windows, safe multi-format writes, reasons for empty results.
7. **Findings 9 to 12 and 16 to 19.**
