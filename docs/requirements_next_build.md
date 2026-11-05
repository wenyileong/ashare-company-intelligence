# Requirements for the next build (recorded 5 November 2026)

These are the author's requirements for the build after v2.2.0, whatever its version number (v2.2.1 or v2.3). The plan for that build must address each one and record how it was met, or why it was not.

## R1. Every graph and visualisation is scalable and interactive

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
