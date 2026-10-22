# v2.1 build plan

**Status:** planned, 18 October 2026. The glossary is approved (section 3.4). The v2.0.3 live checks are done (section 1), and their remaining catalogue gaps go to the v2.0.4 patch (`docs/plan_v2.0.4.md`), which is built first.
**Theme:** a Chinese-language desktop interface, faster extraction, and the remaining polish from the v2.0.2 live run.

## Contents

1. Before the build: confirm v2.0.3 live
2. Scope
3. Workstream A: interface language toggle (desktop only)
4. Workstream B: extraction speed (finding 2)
5. Workstream C: polish (findings 7 to 11 and 16 to 18)
6. Workstream D: publication readiness (proposed)
7. Testing and release
8. Order of work
9. Decisions needed
10. Deferred to later versions

---

## 1. Before the build: confirm v2.0.3 live

v2.0.3 was verified against a simulated CNINFO only. Three checks on a networked machine come first, because their results may change the order of this plan.

**Results, 18 October 2026** (`docs/live_run_findings_v2.0.3.md`): the paging limit is confirmed and the quote list answers. Twelve days are still short of CNINFO's total, so the busy-day row below is not met. Its fix is the v2.0.4 patch, built before v2.1.

| Check | Command | Expected | Result |
|---|---|---|---|
| Paging limit | `ashare-cli probe-cninfo-paging --day 2026-04-24` | `LIMIT_CONFIRMED` | **Met**: LIMIT_CONFIRMED in the live self-test (finding 33) |
| Quote list | `ashare-cli diagnose-quote-list` | At least one variant answers | **Met**: the self-test lists 5,562 securities (finding 33). Listing dates still need fetching ("Update the company list") |
| Busy days | `ashare-cli recatalogue-busy-days --kind all`, then `ashare-cli catalogue-days --kind all --problems` | No SHORTFALL days; 24 April stored 15,382 | **Not met**: 12 days short; 24 April stored 14,399 (findings 22 to 25). Fixed by v2.0.4 |

## 2. Scope

**In scope**

- An English / Simplified Chinese (简体中文) toggle for the **desktop application only**.
- Extraction speed and the progress display.
- The polish items deferred from v2.0.3.
- Publication readiness, if confirmed (section 6).

**Out of scope for v2.1**

- **Translation of the command line's output.** It stays in English, including the lines the command line writes into the desktop's output panel. Later versions may add it (section 10).
- **Any change to dataset contents.** Variable names, column names, codebook identifiers, file names and manifest fields are unaffected by the language setting.
- **A Chinese user guide**, and Chinese chart captions.

## 3. Workstream A: interface language toggle (desktop only)

### 3.1 What is translated

The text the desktop application itself shows:

- the sidebar groups and the 23 page titles and introductions;
- the labels and notes of the 110 actions;
- the labels and hints of the 125 form fields, and the options of choice fields;
- buttons, menus, dialogs, confirmation messages (for example the whole-market download warning) and the status bar;
- the Getting started page and Settings;
- the windows for review, the dataset explorer and charts, wherever their text is the application's own;
- error explanations produced for the desktop (`friendly_error`), and the desktop's own summary lines (for example "Last action failed (see output)").

There are roughly 700 to 900 strings, to be counted exactly at the start of the build.

### 3.2 What stays in English in both modes

| Item | Reason |
|---|---|
| Command names and the command recorded in `run_log.txt` | The log must stay reproducible and readable in bug reports |
| The output of each command, as shown in the output panel | Command-line translation is deferred; showing it unchanged avoids two versions of the same message |
| Variable and column names, codebook identifiers, file names, manifest and release metadata | A panel built in Chinese mode must be byte-for-byte identical to one built in English mode, so that the interface language never becomes a hidden variable in research data |
| Source data (company names, announcement titles) | Already in Chinese from the source; unaffected |

The output panel will therefore show Chinese interface text above English command output. This mix is accepted for v2.1, and the user guide says so.

### 3.3 Behaviour

- **Toggle:** a compact "EN | 中文" switch in the window header, mirrored in Settings.
- **Persistence:** saved in the existing `settings.json` (`"language": "en"` or `"zh_CN"`).
- **First start:** follows the Windows display language (Chinese for any `zh` locale, otherwise English).
- **Switching:** immediate, without a restart. Every page is built from one specification (`SECTIONS`), so the window rebuilds its pages in the new language. Form values already typed are kept.
- **During an action:** the toggle is disabled while an action is running, consistent with the settings lock (finding 10).
- **Fonts:** in Chinese mode, Microsoft YaHei UI is the primary interface font (it is already the second fallback). Line wrapping and field widths are checked on screen at 100% and 150% scaling.
- **Dates and numbers:** unchanged (ISO dates, Western digits) in both modes, because they are also inputs to commands.

### 3.4 Terminology and the glossary

The interface uses official disclosure and regulatory terms only, as used by the China Securities Regulatory Commission (CSRC), the exchanges, CNINFO and the reports themselves. It never uses the casual terms of financial portals and trading apps (for example 年报 for 年度报告, or 分红 used loosely where the report says 利润分配 or 现金红利).

Process:

1. The glossary (`docs/glossary_zh_CN.md`) lists every recurring term with its rendering and authority.
2. **Done, 18 October 2026:** the author approved every proposed rendering, including the interface's own terms (part 10). Two facts are still to be confirmed during the build: the supervisory-board transition date, and the successor to the 2012 industry classification. The settled labels stand meanwhile.
3. All interface strings are then translated from the settled glossary. A term outside the glossary is added to it, and reviewed, rather than translated ad hoc.
4. The author reviews the full Chinese interface in a pre-release build (screenshots of every page, plus the build itself).

### 3.5 Implementation

- **Catalogues:** `ashare/i18n/en.json` and `ashare/i18n/zh_CN.json`, keyed by stable identifiers (for example `action.update_universe.label`, `field.since.hint`). English is the source and the fallback, so a missing translation shows English and never a blank.
- **Lookup:** a small `t(key)` function. `SECTIONS`, `A()` and `F()` carry keys rather than literal text; the English strings move into `en.json` unchanged.
- **Stale translations:** each Chinese entry records a hash of the English text it was translated from. If the English text changes later, the entry is flagged as stale.
- **Packaging:** the catalogues are bundled with the executables.

### 3.6 Tests

- Every key in `en.json` exists in `zh_CN.json`, and no entry is empty.
- No stale entries (English changed since translation).
- Every glossary term that appears in an English string is rendered with its glossary translation in the Chinese string.
- Placeholders such as `{n:,}` match between languages.
- A panel built after switching to Chinese is byte-for-byte identical to one built in English (same CSV, DTA and manifest except the timestamp).
- The run log records identical commands in both modes.
- The desktop opens and switches language under Wine on Windows; screenshots of every page in both languages are produced for review.

### 3.7 Acceptance

- Every page, action, field, dialog and status message appears in Chinese when 中文 is selected, with no English left except command output and the items listed in section 3.2.
- The author has approved the glossary and the screenshots.
- The data-identity test passes.

## 4. Workstream B: extraction speed (finding 2)

**Problem.** Extraction takes about 10 to 20 seconds per document, so the whole market would take days.

**Target.** A median of 2 seconds or less per document on the author's machine, with no loss of parser accuracy. This target is still to be verified; it is not a measured result.

**Measures:**

1. **Text cache.** Extracted text is stored once per document (keyed by its SHA-256 hash), so every later extractor and every rerun reads the cache instead of the PDF.
2. **pdfium as the primary text layer.** pypdfium2 is already bundled and is generally much faster than pypdf. pypdf stays as a fallback and for the comparison. Before switching, both are run over the golden corpus; the switch is made only if precision and recall do not fall (`evaluate-parsers`), and the comparison is recorded.
3. **Parallel extraction.** Several documents are read at once, one per processor core (configurable; default: cores minus one). Network politeness is unaffected, because extraction does not use the network.
4. **One pass per document.** The page text is read once and shared by all extractors run in the same action.
5. **Profiling first.** One run over 200 real reports is profiled before and after, and the results are recorded in the change log.

**Progress display (finding 11).** It shows seconds per document, documents remaining and an estimated time to finish, for example "525 of 22,000 documents; 1.8 s each; about 11 hours left", instead of "0.0 per second".

## 5. Workstream C: polish (findings 7 to 11 and 16 to 18)

| Finding | Change |
|---|---|
| 7 | Parquet is offered only when pyarrow is available. A failed write removes the partial files, so a panel is written in all requested formats or not at all |
| 8 | Empty results give a reason and a next step (compare, transactions, regulatory events, calendar), as panels now do |
| 9 | Code 201872 is investigated and its range recognised, or reported with a clear reason |
| 10 | Settings, including the language toggle, are locked while an action is running |
| 11 | Progress with time per document and an estimated finish (section 4) |
| 16 | Name-lookup (DNS) failures are retried for longer (up to about five minutes) before a period counts as failed |
| 17 | The dataset explorer explains an empty or missing panel instead of opening blank |
| 18 | `show-market` says when there are no prices and how to fetch them |

## 6. Workstream D: publication readiness (proposed; confirm)

This workstream was offered after the question about publishing the dataset. It is included only if confirmed.

- `release --zenodo` writes `.zenodo.json` (title, creators with ORCID, licence, keywords, related identifiers for the software) beside the release.
- A "publish-ready" report lists:
  - the licence classes included and excluded;
  - whether personal names are pseudonymised;
  - that no document text or PDFs are included;
  - that a data licence is set;
  - the dataset and software citations.
- Prerequisite decisions for the author: a licence for the code and one for the data (CC BY 4.0 is the usual choice for data).

## 7. Testing and release

- All existing tests, plus the new ones above, pass on:
  - Linux Python 3.12 and 3.13;
  - PostgreSQL 16;
  - Windows CPython 3.12 under Wine;
  - GitHub CI.
- The parser accuracy report (golden corpus) is unchanged or better after the pdfium switch.
- Windows build: executables, installer and portable zips (each under 30 MB), installed and uninstalled under Wine.
- Version 2.1.0 everywhere it appears, CHANGELOG.md with changes and findings, and the user guide updated (language toggle, faster extraction).
- Commits in the author's name only, with no assistant attribution (Claude is credited in the README acknowledgements).

## 8. Order of work

1. The v2.0.4 patch (`docs/plan_v2.0.4.md`) and its live acceptance.
2. Glossary review: done.
3. Workstream B (speed): profiling, text cache, pdfium comparison, parallel extraction.
4. Workstream A (language): catalogue extraction from the existing interface, then translation from the settled glossary, then tests and screenshots for review.
5. Workstream C (polish).
6. Workstream D, if confirmed.
7. Full test matrix, Windows build, change log, push.

## 9. Decisions needed

| # | Decision | Owner | Default if not decided |
|---|---|---|---|
| 1 | Settle the glossary | User | **Done**, 18 October 2026: all proposals adopted |
| 2 | Confirm Workstream D (publication readiness) | User | Left out of v2.1 |
| 3 | Licences for the code and the data | User | Repository stays private, unlicensed |
| 4 | Speed target (median 2 s or less per document) acceptable | User | Kept as the target |

## 10. Deferred to later versions

- Translation of the command line's output, so that the output panel is fully Chinese in Chinese mode. This needs message keys throughout the command line and its own tests.
- A Chinese user guide and Chinese chart captions.
- Traditional Chinese, only if there is demand.
