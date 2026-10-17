# Font check for v2.0.3 (finding 1)

**Question.** The v2.0.2 live run logged 2,428 warnings of the form "fontTools is required to fully parse the encoding of a CFF Type1 font". The Windows build does not include fontTools. Are figures in financial tables lost or garbled as a result?

**Answer.** No, for the fonts in the live run. fontTools is therefore not bundled. The program now counts the one kind of font that could be affected and lists its documents (see "What v2.0.3 does").

## What the warning means

pypdf (version 6.19 in the Windows build; the logic is the same in 6.21) issues the warning in one situation only, for a font with all three of these properties:

- it is a simple Type1 font;
- its program is embedded as a compact font (`/FontFile3`, subtype `Type1C`);
- it has **no** `/ToUnicode` map.

For such a font, pypdf would normally read the font program's own ("built-in") encoding. Without fontTools it skips that step and decodes the text through the encoding the font dictionary declares in `/Encoding`.

The PDF specification (ISO 32000-1, section 9.6.6) provides that a named base encoding such as `/WinAnsiEncoding` replaces the built-in encoding of a non-symbolic font. When `/Encoding` names a standard encoding, the built-in encoding therefore does not decide any character. The digits, comma, full stop, minus sign, brackets and per cent sign occupy the same codes (0x30 to 0x39 and so on) in the WinAnsi, Standard and MacRoman encodings.

## The fonts in the live run

| `/Encoding` in the font dictionary | Warnings | Fonts |
|---|---:|---|
| `/WinAnsiEncoding` | 2,408 | HelveticaNeueLTPro-Lt and -Bd (2,356), MyriadPro-Regular and -Bold, AvenirLTStd-Roman |
| An encoding dictionary (indirect object) | 20 | AvenirLTPro-Light (12), AvenirLTPro-Roman (8) |
| Total | 2,428 | |

The 20 fonts with an encoding dictionary cover character codes 24 to 31 only (`/FirstChar` 24 or 26, `/LastChar` 31). Those are below the digit codes (48 to 57), so they cannot carry figures. They are most likely ligatures or symbols that the typesetter re-encoded into unused codes.

## The experiment

`tests/test_v203.py::test_font_check_figures_survive_without_fonttools` builds a one-page PDF and extracts its text with pypdf with fontTools switched off. The PDF has:

- a real embedded CFF font (built with fontTools, which is needed only to build it);
- the font name HelveticaNeueLTPro-Lt;
- no ToUnicode map;
- a figure such as `1,234,567.89`.

A standalone version of the experiment (kept outside the repository) also compared pdfium, with these results.

| Case | Expected | pypdf without fontTools | pypdf with fontTools | pdfium |
|---|---|---|---|---|
| `/Encoding /WinAnsiEncoding`, standard built-in encoding (the live case) | `Revenue 1,234,567.89 (12.5%) -2025` | identical | identical | identical |
| No `/Encoding`, standard built-in encoding | as above | identical | identical | identical |
| No `/Encoding`, built-in encoding that places the digits at the codes of A to J | `1234567` | `BCDEFGH` (lost) | `1234567` | `BCDEFGH` (lost) |

The warning was raised in all three cases. Figures are lost only in the third case: a font with a non-standard built-in encoding and no declared encoding. None of the fonts in the live run is of that kind. pdfium also fails in that case, so switching to pdfium would not help either.

## What v2.0.3 does

- fontTools is not bundled.
- pypdf's messages are collected rather than printed, and summarised in one line at the end of each command (finding 5).
- Font notices are counted in two kinds:
  - fonts that declare a standard encoding (text unaffected);
  - fonts that do not, whose documents are listed first in `logs/pdf_warnings_*.txt` so that figures from them can be checked.

If a later run shows many notices of the second kind, bundling fontTools (about 4 MB) is the remedy. pypdf would then read the built-in encoding, which recovers the figures, as the third row of the table shows.
