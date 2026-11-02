# Plan for v2.1.2

This release fixes what the v2.1 and v2.1.1 live runs showed (`docs/live_run_findings_v2.1.md`, findings 118 to 131), and adds three things the author asked for: a scrollable side panel, a Files page, and the paper the software accompanies. Each fix below states its cause, the change, why it cannot disturb what already works, and its tests.

The rule for every change: an existing test may be changed only where the change is the intended behaviour (a new message, a new version), and the reason is noted beside it.

## 1. The missing console in the reading processes (finding 124; high)

**Cause.**
- An old progress line ("... 25 documents read") is written to the console by `document_heartbeat` once every 25 documents.
- The main process silences it during extraction (`quiet_heartbeat`). The worker processes of parallel reading have their own copy of the counter, which is never silenced.
- In the desktop program, the workers have no console (`sys.stdout` is None), so the write raises `AttributeError: 'NoneType' object has no attribute 'write'` and that document fails.
- The arithmetic fits:
  - "Read guidance": 5,113 documents ÷ 25 ≈ 204, against 201 failures; its small rerun of 201 ÷ 25 ≈ 8, against 7.
  - Financial extraction failed 894 of 6,650 documents (several readings per document); top-10 failed 34 and ESG 8.

**Change.**
- The workers' heartbeat is silenced when they start.
- Their missing console and error streams are replaced by a null device, so that no library can fail on them either.
- `document_heartbeat` never writes when there is no console.

**Interference.** The heartbeat still answers Stop, so cancellation is unchanged. The main process's output is unchanged. Failed documents were never marked as read, so the next run reads them.

**Tests.**
- A worker with no console reads 30 documents with the heartbeat on, without error.
- The worker initialiser replaces missing streams.
- The heartbeat with no console does nothing.

## 2. The download step after a catalogue (findings 120 and 121; high)

**Cause.**
- The catalogue passes every new document's ID to `download_pending` in one `IN (...)` query.
- A ten-month refresh queued more IDs than SQLite allows in one statement, so it failed after thirteen hours, with nothing downloaded.
- The IDs were held only in memory, so a rerun without `--refresh` skipped the finished days and downloaded nothing.

**Change.**
- `ids_in_chunks` (new, `ashare/dbutil.py`) runs `IN` queries 500 values at a time. It is used by `download_pending` and the other places where an ID list can grow with the market:
  - removing stale facts;
  - the review queue;
  - regenerating validation flags;
  - removing stale top-10 rows.
- After the catalogue, the documents to download are chosen as "wanted and not on disk" within the catalogue's dates, read from the database. A rerun therefore downloads what an interrupted one left.
- A failed download step no longer turns a finished catalogue into a failed action. The catalogue result is kept, the error is reported, and "Download catalogued documents" is named as the way to resume.

**Interference.**
- The selection rule ("wanted" by the same `_wanted` test) is unchanged.
- The only new effect: documents of the same dates that an earlier run catalogued without downloading are now downloaded too. That is what downloading a catalogued period means.
- Batching returns the same rows in the same order (ordered after the batches are merged).

**Tests.**
- `download_pending` with 40,000 IDs.
- The catalogue's download step picks up documents an earlier, stopped run left.
- A failing download step keeps the catalogue's result.

## 3. Download progress and estimates (findings 119 and 123; medium)

**Cause.**
- The estimate assumed 1.5 s a document. The guidance download took about 5.6 s, and the sustainability-report download estimated 0.9 hours for what took several.
- Progress printed only counts.

**Change.**
- Progress lines as in extraction: documents done, seconds a document, time left.
- The rate and the size per document of each run are recorded in `download_rates.json` beside the database. The next estimate uses them, falling back to 5 s and the typical sizes.

**Interference.** Downloading itself is unchanged; only messages and a small file are added.

**Tests.**
- Progress lines appear.
- The estimate uses a recorded rate.
- A damaged rates file is ignored.

## 4. Financial extraction reads documents that cannot give figures (finding 126; medium)

**Cause.** With "kind all", English annual reports and sustainability reports were read: 190 to 634 s each, and no figures.

**Change.** With "kind all", financial extraction leaves out:
- English versions (`*_english`, or titles without Chinese characters);
- sustainability reports.

It says how many were left out (`not_financial`). Summaries stay, as before.

**Interference.**
- "kind reports" (the default) already excludes them, so it is unchanged.
- The financial extractor version becomes financials-4 (section 6), so every report is read once more in any case.

**Test.** With "kind all", an English report and a sustainability report are counted as left out and not read.

## 5. "Check documents for scanned pages" (finding 125; medium)

**Cause.**
- It read every page of each document with the slow reader, at about 10 s a document.
- It saved nothing until it finished, so the two stopped runs in the log kept nothing, although the message said "everything saved so far is kept".
- It used the old progress line.

**Change.**
- Pages are counted from the fast page text (pdfium), in worker processes when there are enough documents.
- Each document is saved as it is checked.
- Progress lines as in extraction.
- The old reader is used only where pdfium is not available.

**Interference.**
- The classification rule is unchanged: at least 20 characters makes a page with text; all pages FULL, under 80% PARTIAL, none NONE.
- The stored field (`text_layer`) is unchanged, and documents already checked are still skipped unless `--recheck`.

**Tests.**
- A scanned page and a text page are classified as before.
- A run stopped half-way keeps the documents it checked.
- The rerun checks only the rest.

## 6. A leading digit dropped from a balance-sheet total (finding 129; high)

**Cause.**
- 108 of about 120 failed balance sheets were out by an exact 10, 20 or 30 billion yuan: a total of eleven digits read without its first digit.
- The likeliest cause is the text layer splitting a long figure in a narrow column ("1 3,212,752,903.71"). A text-level rejoining rule would be unsafe, because a note number before an amount ("七、31 3,212,…") looks the same.

**Change.**
- A repair from the balance identity, when the document's own figures prove it. Suppose assets minus liabilities minus equity is exactly *d* × 10^*k* (*d* from 1 to 9), and the short figure is below 10^*k*. The short figure is restored only when a second identity confirms which figure it is:
  - equity: equity attributable to the parent plus minority interests;
  - liabilities: current plus non-current liabilities;
  - assets: current plus non-current assets.
- A restored figure keeps the reading in `raw_value`, is noted `LEADING_DIGIT_RESTORED`, and has its confidence lowered. When no second identity decides, nothing is changed, and the balance check still fails, as it should.
- `inspect-tables --table balance_sheet` writes the statement's lines with the numbers each line yields, so the real cause can be seen in the author's reports.
- "Check balance sheets" prints a summary (round-number differences, other differences) and writes the rows to `exports/balance_check.csv`, instead of printing every row.
- Version financials-4.

**Interference.**
- Only facts that fail the identity by a single digit times a power of ten, and are confirmed by a second identity, are touched; every passing balance sheet is untouched.
- `validate_financials` still never overwrites values.

**Tests.**
- An equity short by 10 billion is restored when parent plus minority equity confirms it.
- It is left alone when nothing confirms it.
- Liabilities are restored when current plus non-current confirms them.
- A balance sheet that balances is untouched.
- The CSV is written.

## 7. Controller names (finding 128; high)

**Cause.**
- In tables headed by a header row (Shenzhen layout), a name that wraps within its cell arrives on several lines. Each line's first word was taken as another controller, and the words were joined with "、".
- The legal representative's name, in the next column, was taken as a controller too ("国务院国有资产监督、张玉卓、管理委员会"). Fragments of the wrapped header itself were taken as names ("人/单位负").

**Change.**
- Under a header row naming entities (名称, with a legal-representative column), fragments are joined until they end as an entity name ends (委员会, 公司, 集团, 政府, 局, 厅, 中心, 银行, 合伙企业 and similar). A personal name standing between them is dropped as the legal representative.
- Fragments of headings, and anything with "/", are never names.
- Under a header row naming persons (姓名), several persons are kept as before ("王传福、吕向阳").
- Grouping by controller normalises the known forms of the SASAC names.
- Version control-3.

**Interference.**
- The label-and-value layout (Shanghai) is unchanged.
- The person case is unchanged.
- The existing control tests must all pass unchanged.

**Tests.** The three garbled forms in the log, rebuilt as report lines, give the right names; two persons acting together stay two persons.

## 8. Why a layer is empty (finding 127; low)

**Change.**
- The topology view's gap notes say why for each empty layer:
  - no periodic report downloaded for these companies;
  - reports downloaded but not yet read;
  - read, with nothing for these years;
  - no forecast catalogued, or read with none in the span.
- "R&D and workforce", "Business segments" and "Group structure" say the same when empty.

**Interference.** Only messages change. The coverage status (COMPLETE, PARTIAL, GAP) is computed as before.

**Tests.**
- No reports downloaded gives that message.
- A forecast read outside the span gives "none in the span".

## 9. Smaller fixes

- **Refresh window (finding 122).** `--refresh` fetches again only the last 30 days of the period by default (`--refresh-days`, 0 for every day). Without `--refresh`, nothing changes. The library function keeps its old default (every day), so other callers are unchanged.
- **ESG report title (finding 130).** When a year has both, the Chinese sustainability report is preferred over the English version as the title shown.

## 10. A scrollable side panel (author's request)

**Change.**
- The panel's contents (name, language switch, sections, Settings) sit in a scrolling area, with a thin scrollbar shown only when they do not fit.
- The mouse wheel scrolls the panel when the pointer is over it, and the page otherwise.
- The selected section is scrolled into view.
- The version and data-folder line stays fixed at the foot.

**Interference.** Navigation, the language switch and the page scrolling are unchanged; the page's wheel binding is set only while the pointer is over the page.

**Tests (Tk, at 1100 × 420 and full height).**
- Settings can be reached by scrolling at the short height.
- No scrollbar shows at full height.
- Selecting Settings brings it into view.
- The language switch keeps working.

## 11. The Files page (author's request)

Downloaded documents are stored as `disclosures/<code>/<hash>.pdf`, the paths the database and the provenance records hold. They are not renamed; the page works around them.

**Actions** (CLI `files-*`, and a Files page under Check):
- **Files summary.** Documents on disk by kind and by year, with their size. Also price files and exports.
- **List files.** For one company, or a kind and year: readable name, date, size, path, and the extractors that read it.
- **Export readable copies.** A chosen set copied into `exports/files/<code> <name>/<year>/`, named `<code> <date> <title>.pdf`, with an index (CSV and HTML) giving each copy's source address and database record. Copies, not links: links need administrator rights on Windows.
- **Check files.**
  - Files on disk that no record names.
  - Records whose file is missing.
  - The same file under two records.
  - Summaries and English versions downloaded by earlier versions.
- **Tidy files.**
  - Removes a chosen class (files no record names; summaries and English versions; documents of one kind).
  - It previews by default, and acts only when "Apply" is ticked.
  - Removing a file clears its path in the database, so a later run downloads it again if needed.
  - Every removal is written to `logs/tidy_<time>.csv`.

**Interference.** Read-only unless "Apply" is ticked. Nothing touches a file that a record names, except a removal the author chose. Exports go under `exports/`.

**Tests.**
- The summary counts.
- An export's index gives the source of each copy, and the original is untouched.
- The check finds an unnamed file and a missing one.
- Tidy previews by default.
- Applied, it clears the path and writes the log.

## 12. The paper (author's request)

**Change.**
- A README section, "The paper this software accompanies":
  - the citation (OSCOLA), SSRN's suggested citation, the DOI and the licence;
  - what the paper does, in its own words;
  - what the software does in relation to it, and what it does not claim;
  - the research it supports.
- `CITATION.cff` gains the paper under `references`. The software keeps its own citation.

**Interference.** Documentation only. The CITATION file is checked with `cffconvert` if available, otherwise parsed as YAML.

## 13. Release

- **Version and files.** Version 2.1.2, with the CHANGELOG and the findings document (`docs/live_run_findings_v2.1.md`).
- **Chinese interface.** The glossary terms for the new interface text are added to the Chinese catalogue (Files page, side panel), using the approved terms where the glossary has them.
- **Tests.**
  - The full suite on Python 3.12 and 3.13, on PostgreSQL, and on Windows Python under Wine.
  - The Windows build, with the command-line program run under Wine.
- **Commit.** In the author's name only.

## 14. Build record

- **Implemented** as planned, sections 1 to 12.
- **Testing found, and fixed:**
  - The refresh window fetched one day too many (the window now covers exactly the last *N* days).
  - The side panel did not scroll the selected section into view right after a language switch (it is tried again once the panel is laid out).
  - Two whole entity names were joined when the first lacked a usual ending ("中国移动" + "甲公司"); a following piece is now joined only when it reads as the rest of a wrapped name.
  - The document-folder scan would have counted the program's cached section indexes as stray files when the data folder's own path has a part beginning with a dot; only paths within the folder are now considered.
  - **Under Windows Python (Wine):** an export to a drive that cannot hold Chinese names now falls back to the code, date and record ID (the index still gives the title). Copies are made with `copyfile` and `copystat`, because `copy2` uses `CopyFile2`, which some Windows environments lack.
- **Not changed:** the licence identifier in `CITATION.cff` (`PolyForm-Strict-1.0.0`) is not in the SPDX list the CFF schema checks against, so `cffconvert --validate` reports it; the rest of the file, including the new reference, validates.
