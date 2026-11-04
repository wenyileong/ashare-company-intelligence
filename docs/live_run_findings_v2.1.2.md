# v2.1.2 live-run findings (findings 132 to 139)

The author ran the v2.1.2 test plan and sent the logs. They covered:
- the parallel reading of financial figures, top-10 tables, controllers, ESG and guidance;
- the Files page;
- downloads, the refresh window and the scanned-page check;
- "Check balance sheets" and "Companies with the same controller".

Each finding is marked with what was done. The fixes are set out, with their interference checks and tests, in Part A of `docs/plan_v2.2.md`.

## Summary

| No. | Finding | Severity | Status |
|---|---|---|---|
| 132 | The balance-sheet repair of v2.1.2 did not apply | High | Fixed in v2.2 (rules 1 and 2); rule 3 waits on samples (v2.2.1) |
| 133 | Four controller names still garbled | High | Fixed in v2.2 |
| 134 | Top-10 tables of quarterly reports: 502 of 2,199 reports gave rows | Medium | Open; waits on samples (v2.2.1) |
| 135 | Download estimates misled by short runs and by other kinds of document | Low | Fixed in v2.2 |
| 136 | The stop message of the download step spoke of unfinished days | Low | Fixed in v2.2 |
| 137 | ESG runs reported 2,112 "updated" titles that had not changed | Low | Fixed in v2.2 |
| 138 | One- to three-page announcements marked PARTIAL by the scanned-page check | Low | Fixed in v2.2 |
| 139 | One half-year report took 138 s in the controller read | Information | Named in `slowest`; to be looked at if it recurs |

The result of finding 124 (parallel reading in the desktop program) is confirmed: 0 errors over 7,088 financial documents and in the top-10, control, ESG and guidance runs.

## 132. The balance-sheet repair did not apply

"Check balance sheets" reported 103 failures, 86 of them "out by a single digit times a power of ten". Document 31 (000009) was still out by exactly 20,000,000,000.

The v2.1.2 repair needs a second figure in the same reading to confirm which total lost its first digit. Two things can defeat that:
- the failing totals may come from the key-figures reading, which reads only the three totals;
- the confirming parts (parent equity, for example) may be cut in the same way.

**Fix (v2.2, financials-5).**
- **Across readings.** When the other reading of the same document and period has the same item equal to the read value plus the gap, and not equal to the read value, the figure is restored from it. The note records "other reading (method)".
- **By the statement's own total.** When "负债和所有者权益总计" is read and only one total can be short, the total that the grand total confirms is restored.
- Nothing is restored when two totals could be short. Every restored figure keeps its reading in `raw_value`, records the rule in its note and has its confidence lowered by a fifth.

**Waiting on samples.** Rejoining a lone digit to its thousands group at the source (plan A1, rule 3) needs `inspect-tables 31 --table balance_sheet` and `inspect-tables 76 --table balance_sheet`.

## 133. Controller names still garbled

Four rows of "Companies with the same controller":
- 国务院国有资产监督、张玉卓管理委员会;
- 深圳市人民政府国有、杨军资产监督管理委员会;
- 山西省人民政府国有、洪强资产监督管理委员会;
- 代表国家履行出资人、深圳市人民政府国有、杨军资产监督管理委员会.

In these reports the legal representative's name is printed on the same line as the second half of the wrapped entity name, with no space between them.

**Fix (v2.2, control-4).**
- A token that begins with a two- or three-character personal name followed by a continuation that cannot begin a name (资产…, 监督管理…, 管理委员会, 有限公司 and the like) loses the personal name. A place name (ending in 省, 市, 县, 区, 州, 盟 or 旗) is never taken for a personal name.
- Where the row yields a whole entity name, pieces of a phrase (代表, 履行, 出资人, 职责, 作为, 通过) that do not end as an entity name are dropped.
- The grouping key treats 省政府 and 省人民政府 before 国有资产监督管理委员会 as one.

All four forms are tests, with the cases fixed in v2.1.2 kept.

## 134. Top-10 tables of quarterly reports

Of 2,199 reports read, mostly third-quarter reports, 502 gave rows ("dual_run: agree 278, disagree 243, single 1903, secondary_only 898"). Quarterly reports carry the table in a shorter layout. The fix needs `inspect-tables ID --table top10` for two or three quarterly reports without rows, and follows in v2.2.1.

## 135. Download estimates

A guidance run of a few documents recorded 4.2 s a document, and forecasts (5.2 s) differ from reports (2.7 s). Rates are now kept by kind of document, as a running mean, and a run of fewer than 25 documents is not recorded. A kind not yet measured takes the mean of the kinds measured, or 5 s.

## 136. The stop message of the download step

Stopping the download step of a catalogue said that a rerun "resumes with the first unfinished day" when every day was finished. The note now says that a rerun resumes with the first unfinished day or, when every day is finished, downloads the documents still missing. Notes were added for "Extract ESG", "Read guidance" and "Check documents for scanned pages".

## 137. ESG counts

A sustainability-report title row is written only when its value, text, source, page, reading, method or confidence differs; otherwise it is counted as "unchanged".

## 138. Short documents marked PARTIAL

A document of two or three pages in which every page but the last has text is FULL. The last page of such a document is usually a signature or seal. The data were not affected.

## 139. A slow controller read

One half-year report (000756, 140 pages) took 138 s. It is named in `slowest`, as designed.
