# Text-layer comparison for v2.1 (plan workstream B2)

**Question.** Should pdfium replace pypdf as the plain-text layer of the "text" variant of each parser?

**Rule set in the plan (section B2).** Switch only if neither precision nor recall falls for any parser on the golden corpus.

**Decision.** **Not switched.** pypdf stays the default text layer in v2.1.

- **Why.** The subsidiaries parser's precision falls from 82.4% to 77.8% (seven more spurious rows) under pdfium.
- **What follows.** No extractor version is raised for the text layer, and the calibration is not rebuilt.
- **Kept as an option.** The pdfium layer stays available for further comparison with `ASHARE_TEXT_LAYER=pdfium`. It is not a user setting.

## Method

- **Corpus.** The synthetic golden corpus (`synthetic-corpus --fmt pdf`, the corpus used by the CI accuracy gate):
  - 8 periodic reports;
  - 4 announcements for the pledge, corporate-action and regulatory parsers.
- **Runs.** `evaluate-parsers --corpus ... --report ...`, once with each layer:
  - `ASHARE_TEXT_LAYER=pypdf` (the default);
  - `ASHARE_TEXT_LAYER=pdfium`.
- **What changes between runs.** Only the text variant of each parser; the layout variants are the same in both runs.
- **Date.** Run on 30 October 2026, in the build environment (Python 3.12).

## Results: text variants

Counts are rows (correct, wrong, missed, spurious); precision and recall are percentages.

| Parser | pypdf: C / W / M / S | pypdf: P, R | pdfium: C / W / M / S | pdfium: P, R | Change |
|---|---|---|---|---|---|
| financials | 91 / 0 / 21 / 0 | 100.0, 81.2 | 96 / 0 / 16 / 0 | 100.0, 85.7 | Better |
| statements | 80 / 0 / 0 / 0 | 100.0, 100.0 | 80 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| top10 | 146 / 0 / 43 / 0 | 100.0, 77.2 | 167 / 0 / 22 / 0 | 100.0, 88.4 | Better |
| top10_tradable | 37 / 0 / 7 / 4 | 90.2, 84.1 | 37 / 0 / 7 / 4 | 90.2, 84.1 | Same |
| control | 24 / 0 / 0 / 0 | 100.0, 100.0 | 24 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| pledges | 24 / 0 / 0 / 0 | 100.0, 100.0 | 24 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| segments | 124 / 0 / 55 / 4 | 96.9, 69.3 | 179 / 0 / 0 / 0 | 100.0, 100.0 | Better |
| subsidiaries | 98 / 0 / 147 / 21 | 82.4, 40.0 | 98 / 0 / 147 / 28 | 77.8, 40.0 | **Precision falls** |
| human_capital | 152 / 0 / 0 / 0 | 100.0, 100.0 | 152 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| roster | 300 / 0 / 20 / 0 | 100.0, 93.8 | 300 / 0 / 20 / 0 | 100.0, 93.8 | Same |
| esg | 21 / 0 / 0 / 0 | 100.0, 100.0 | 21 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| corporate_actions | 28 / 0 / 0 / 0 | 100.0, 100.0 | 28 / 0 / 0 / 0 | 100.0, 100.0 | Same |
| regulatory | 24 / 0 / 0 / 0 | 100.0, 100.0 | 24 / 0 / 0 / 0 | 100.0, 100.0 | Same |

**The layout variants** are unchanged: 100% precision, and 99.1% to 100% recall.

## Speed

- **Synthetic reports.** The two layers took the same time on a 253-page report (0.31 s and 0.32 s for all pages).
- **Real reports.** The case for pdfium was speed on real reports, whose embedded fonts pypdf decodes slowly. That cannot be measured here, because the build environment has no real reports.
- **Why it matters less now.** With targeted reading (B1), plain text is read only on a report's section pages, so the text layer's speed counts for a dozen pages, not two hundred.
- **What is measured instead.** The profiling run on the author's reports (B4) measures the page-text pass. If it shows pypdf as the bottleneck, the comparison is repeated on real reports.

## Revisiting

The question is reopened if:
- the subsidiaries text variant is improved, so that pdfium no longer lowers its precision; or
- the author's profiling run (B4) shows the page-text pass as the bottleneck; or
- a real-report corpus becomes available, on which the same comparison can be run.

If pdfium is then adopted:
- every extractor version is raised;
- the calibration is rebuilt;
- all documents are read again once.
