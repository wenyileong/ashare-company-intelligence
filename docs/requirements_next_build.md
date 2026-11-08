# Requirements for the next builds

## For the build after v2.3.0 (recorded 8 November 2026)

The plan for the build after v2.3.0, whatever its version number, must address R3 and record how it was met, or why it was not.

### R3. A percentage progress bar whenever the program fetches or reads data

**The author's requirement.** Fetching and downloading data shows a loading bar like the standard Windows percentage bar: it fills from left to right and shows how much is complete.

**Where things stand in v2.3.0.**
- **Desktop program.** The status bar runs an indeterminate bar (a block moving back and forth) for every action. Progress appears only as lines in the Output pane, such as "250 of 9,800 documents; 8.7 s each; about 23 hours left".
- **Check > Jobs.** The daily update and queued jobs already have a determinate bar, but nothing else does.
- **Command line.** It prints the same progress lines, every 25 items or once a minute.

**What the next build should provide.**
1. **A determinate bar for every long action that fetches or reads data.** The bar fills in proportion to the work done. It shows, beside it:
   - the percentage;
   - "1,234 of 2,370 documents" (or companies, pages or days, whichever the action counts);
   - the time left;
   - when downloading, the speed.

   This covers:
   - catalogue announcements;
   - document downloads;
   - every extractor;
   - financial figures;
   - whole-market prices;
   - the daily update;
   - GLEIF matching;
   - building a panel;
   - writing a release;
   - copying the data folder in a move.
2. **Stages.** An action with several stages shows the stage it is on ("Stage 2 of 3: downloading documents") and a bar for that stage. Where the stages can be weighed, it also shows an overall bar. The daily update is an example: catalogue, then download, then read.
3. **Unknown totals.** While the total is not yet known (the first page of a catalogue, a server that gives no size), the bar is indeterminate and says "counting…". It turns determinate as soon as the total is known. If the total grows during the run (more pages than the first page said), the bar steps back honestly, never past 100 per cent, and the count says "about".
4. **Downloads by size.** For a single large file whose size the server gives, the bar counts bytes ("12.4 of 30.5 MB"). Otherwise it counts files.
5. **Stop and resume.** Stop keeps what was fetched, as now. A resumed action starts its bar at the count already done ("resuming at 1,234 of 2,370"), not at zero.
6. **The command line.**
   - When the output is a terminal, it draws a text bar on one line, redrawn in place: `[██████████░░░░░░░░░░] 52%  1,234 of 2,370 documents; about 3 min left`.
   - When the output goes to a file or to the desktop program, it writes plain lines as now, so logs stay readable.
7. **Accuracy and cost.**
   - The figures come from the same counter the work uses, never from an estimate of time alone.
   - The bar is updated at most four times a second, so it never slows the work.
   - The time left is smoothed over the recent items, so one slow document does not throw it.
8. **Language and accessibility.**
   - The text beside the bar is translated (中文).
   - The percentage is always written as well as drawn, so it does not depend on colour.
9. **Windows taskbar (optional).**
   - The program's taskbar button may show the same progress, as Windows file copies do.
   - This is done only if it needs no new third-party library, or after that library has been reviewed (as review V11 of the v2.3 plan required for new libraries).
   - Otherwise it waits.

**How it could be built.**
- The existing counter (`extractstate.Progress`) gains a machine-readable line, written beside the human one, giving the stage, done, total, unit and bytes.
- The desktop program reads these lines from the command it runs and drives a determinate `ttk.Progressbar` in the status bar. It does not show them in the Output pane.
- Actions that do not yet count their work are given counters.
- Nothing about the work itself changes.

**Tests for that build.**
- **The counter.** It writes well-formed progress lines, at most four a second.
- **Unknown and growing totals.** The bar is indeterminate, then determinate, and never above 100 per cent.
- **The desktop program.** With a fake command that reports progress, the status bar turns determinate, shows the percentage and the counts, and resets when the action ends, fails or is stopped.
- **Resume.** A resumed job starts at its done count.
- **The command line.** It draws a bar in a terminal and writes plain lines otherwise.
- **The log.** It holds no progress control lines.
- **No slowdown.** Timed on a long extraction with the bar and without it.
- **Every switch off.** The earlier suite passes unchanged.

## For the build after v2.2.0 (recorded 5 November 2026; met in v2.3.0)

R1 and R2 below were addressed in v2.3.0; see the build record in `docs/plan_v2.3.md`.

These are the author's requirements for the build after v2.2.0, whatever its version number (v2.2.1 or v2.3). The plan for that build must address each one and record how it was met, or why it was not.

### R1. Every graph and visualisation is scalable and interactive

**The author's requirement.** All graphs and visualisations are to be scalable, with live interactive features such as zooming in to read figures more precisely.

**Where things stand in v2.2.0.**

| Output | Zoom and pan | Exact values |
|---|---|---|
| Topology view, 3D and 2D maps (`topology.html`) | Yes (scroll to zoom, drag to pan or rotate) | Yes, in the inspector |
| Ego map (`view.html`, relational maps) | Yes (scroll to zoom, drag to pan) | Yes, in the inspector |
| Charts in the topology page (revenue, profit) | No | Tooltip only |
| Series views (`view.html`: guidance scatter, error bars, panel balance) | No | Tooltip and the data table |
| Coverage heatmap (`view.html`) | No (an HTML table) | The values are in the cells |
| Dataset explorer charts | No | Tooltip only |
| Desktop chart window (Tk) | No | No |
| Publication figures (`figure_*.svg`, `figures.html`) | Vector only (browser zoom) | The CSV beside each figure |

**What the next build should provide.**

1. **Zoom and pan on every interactive chart.**
   - Scroll or pinch to zoom, and drag to pan, on both axes or on one axis at a time.
   - Box zoom: drag a rectangle to zoom to it.
   - A "Reset zoom" control, and double-click to reset.
   - The axes re-tick as the range changes, so the gridlines and labels stay legible at every scale.
   - Applies to the line, bar and scatter charts of the topology page, the series views and the dataset explorer.
2. **Precise reading of values.**
   - A crosshair or hover readout giving the exact value of the point under the pointer, in its unit, with the period, the source document and the page.
   - Typed axis ranges ("from" and "to") for exact framing.
   - Choice of scale where it helps: linear or logarithmic, and yuan, 10,000 yuan or 100 million yuan.
3. **Heatmaps** (coverage, and the sector heatmaps of v2.3) drawn as zoomable charts. Hovering a cell gives its counts (listed, with data, share). The table stays available below.
4. **Relational maps.** Zoom and pan as now, plus:
   - zoom to a selected node and its neighbours;
   - labels that stay readable at every zoom level;
   - for the larger maps of v2.3, aggregation by group when zoomed out and the full detail when zoomed in.
5. **Desktop chart window.** Zoom, pan and reset on the charts the desktop draws, or a button that opens the same chart as an interactive page in the browser.
6. **Publication figures stay static and exact.** They remain vector SVG, sized for a column or a page, with their CSV. Zooming in an interactive page never changes the figures written for publication. A figure may record the range it was cut to, if the author asks for figures to be written from a zoomed view.
7. **Offline and self-contained.** Any library added for zooming (for example the Chart.js zoom plugin) is bundled with its licence in the viewer folder and in `THIRD_PARTY_NOTICES.txt`. No page fetches anything from the network.
8. **Performance.** Zooming stays smooth on the largest views expected: about 6,000 companies for the market map, and panels of many company-years. Where a series has more points than can be drawn smoothly, it is thinned when zoomed out and shown in full when zoomed in. The page says when this happens.

**Tests for the next build.**
- In a headless browser, for each interactive page:
  - scroll and box zoom change the visible axis range;
  - reset restores it;
  - the hover readout gives the stored value exactly;
  - there are no console errors;
  - the page makes no network requests.
- The figures written for publication are byte-identical before and after interactive use.
- Each new bundled library is listed in the notices.
- The larger pages are timed.

### R2. The fixes from the v2.2.0 live run

Findings 140 to 146 in `docs/live_run_findings_v2.2.md`, with the highest priority on:
- 145, a data folder that can be moved without losing the links to the documents;
- 144, progress and resume for the whole-market price download.

The quarterly top-10 layout (finding 134) and the source rejoining of balance-sheet digits (finding 132, rule 3) still wait on the author's `inspect-tables` samples.
