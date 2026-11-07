/* The chart view (v2.2): each table of the snapshot drawn as its "chart" says (heatmap, scatter with ranges,
   histogram or bars), with the data table beneath. Missing values are gaps, never interpolated. */
(function () {
  "use strict";
  var snap = JSON.parse(document.getElementById("snapshot").textContent);
  var side = document.getElementById("side"), main = document.getElementById("charts");
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = text;
    if (cls) e.className = cls; return e; }
  var p = snap.parameters || {};
  side.appendChild(el("h1", p.title || snap.view));
  side.appendChild(el("div", "As published by " + p.as_of + " · " + snap.software, "muted"));
  side.appendChild(el("h2", "Evidence"));
  side.appendChild(el("div", snap.evidence.toLowerCase().replace(/_/g, " ") + " · definitions " + snap.definitions, "note"));
  if ((snap.summary || []).length) {
    side.appendChild(el("h2", "Summary"));
    snap.summary.forEach(function (s) { side.appendChild(el("div", s.label + ": " + s.value, "note")); });
  }
  side.appendChild(el("h2", "Notes"));
  (snap.notes || []).forEach(function (n) { side.appendChild(el("div", n, "note")); });
  function fmt(v) { if (v == null || v === "") return "–"; if (typeof v === "number") {
      return Math.abs(v) >= 1e8 ? (v / 1e8).toFixed(2) + " 亿" : (Math.abs(v) < 1 && v !== 0 ? v.toFixed(3) : v.toLocaleString()); }
    return String(v); }
  function table(t, limit) {
    var tb = el("table", null, "data"), head = el("tr");
    t.columns.forEach(function (c) { head.appendChild(el("th", c)); }); tb.appendChild(head);
    t.rows.slice(0, limit).forEach(function (r) { var tr = el("tr");
      t.columns.forEach(function (c) { tr.appendChild(el("td", fmt(r[c]))); }); tb.appendChild(tr); });
    return tb;
  }
  function heat(t, c) {
    var rows = [], cols = [], cells = {};
    t.rows.forEach(function (r) { var a = r[c.row], b = r[c.col];
      if (rows.indexOf(a) < 0) rows.push(a); if (cols.indexOf(b) < 0) cols.push(b); cells[a + "\u0001" + b] = r; });
    var tb = el("table", null, "data"), head = el("tr"); head.appendChild(el("th", c.row_label || c.row));
    cols.forEach(function (b) { head.appendChild(el("th", b)); }); tb.appendChild(head);
    rows.forEach(function (a) { var tr = el("tr"); tr.appendChild(el("td", a));
      cols.forEach(function (b) { var r = cells[a + "\u0001" + b], v = r ? r[c.value] : null, td = el("td");
        if (v == null) { td.textContent = "–"; } else {
          var x = Math.max(0, Math.min(1, v)); td.textContent = Math.round(x * 100) + "%";
          td.style.background = "rgb(" + Math.round(255 - 255 * x) + "," + Math.round(255 - (255 - 114) * x) + ","
            + Math.round(255 - (255 - 178) * x) + ")"; if (x > 0.55) td.style.color = "#fff"; }
        if (r && c.tip) td.title = r[c.tip] || ""; tr.appendChild(td); });
      tb.appendChild(tr); });
    return tb;
  }
  function chart(t, c) {
    var canvas = document.createElement("canvas"); canvas.height = 320;
    if (typeof Chart !== "function") return el("p", "The chart library could not start; see the table.");
    var cfg;
    if (c.type === "scatter") {
      var pts = t.rows.filter(function (r) { return r[c.x] != null && r[c.y] != null; });
      var ranges = []; pts.forEach(function (r) { if (r[c.low] != null && r[c.high] != null) {
        ranges.push({x: r[c.x], y: r[c.low]}, {x: r[c.x], y: r[c.high]}, {x: null, y: null}); } });
      var xs = pts.map(function (r) { return r[c.x]; }), lo = Math.min.apply(null, xs.concat([0])),
          hi = Math.max.apply(null, xs.concat([0]));
      cfg = {type: "scatter", data: {datasets: [
        {label: c.y_label || c.y, data: pts.map(function (r) { return {x: r[c.x], y: r[c.y], r: r}; }),
         backgroundColor: "#0072B2", pointRadius: 3},
        {label: c.range_label || "range", type: "line", data: ranges, borderColor: "rgba(0,114,178,.35)",
         pointRadius: 0, spanGaps: false, showLine: true},
        {label: "equal", type: "line", data: [{x: lo, y: lo}, {x: hi, y: hi}], borderColor: "#8c959f",
         borderDash: [6, 3], pointRadius: 0}]},
        options: {animation: false, parsing: false, scales: {x: {title: {display: true, text: c.x_label || c.x}},
          y: {title: {display: true, text: c.y_label || c.y}}},
          plugins: {tooltip: {callbacks: {label: function (ctx) { var r = ctx.raw && ctx.raw.r;
            return r ? (r[c.tip] || "") + ": " + fmt(ctx.raw.y) + " against " + fmt(ctx.raw.x) : ""; }}}}}};
    } else {
      cfg = {type: "bar", data: {labels: t.rows.map(function (r) { return r[c.x]; }), datasets: [
        {label: c.y_label || c.y, data: t.rows.map(function (r) { return r[c.y]; }), backgroundColor: "#0072B2"}]},
        options: {animation: false, scales: {x: {title: {display: true, text: c.x_label || c.x}},
          y: {title: {display: true, text: c.y_label || c.y}}}}};
    }
    var holder = el("div");
    if (window.AshareInteractive) { window.AshareInteractive.make(holder, cfg, {money: !!c.money}); return holder; }
    new Chart(canvas, cfg);
    return canvas;
  }
  /* v2.3.0 (B4): a heatmap as a zoomable matrix chart, with the table beneath it. */
  function matrix(t, c) {
    var holder = el("div");
    if (!window.AshareInteractive || typeof Chart !== "function") return holder;
    var rows = [], cols = [];
    t.rows.forEach(function (r) { if (rows.indexOf(r[c.row]) < 0) rows.push(r[c.row]);
      if (cols.indexOf(r[c.col]) < 0) cols.push(r[c.col]); });
    var data = t.rows.filter(function (r) { return r[c.value] != null; })
      .map(function (r) { return {x: String(r[c.col]), y: String(r[c.row]), v: r[c.value], r: r}; });
    var cfg = {type: "matrix", data: {datasets: [{label: t.title, data: data,
      backgroundColor: function (ctx) { var v = (ctx.raw && ctx.raw.v) || 0, x = Math.max(0, Math.min(1, v));
        return "rgba(0,114,178," + (0.08 + 0.92 * x).toFixed(3) + ")"; },
      width: function (ctx) { var a = ctx.chart.chartArea || {width: 0}; return Math.max(2, a.width / Math.max(1, cols.length) - 2); },
      height: function (ctx) { var a = ctx.chart.chartArea || {height: 0}; return Math.max(2, a.height / Math.max(1, rows.length) - 2); }}]},
      options: {animation: false, scales: {x: {type: "category", labels: cols.map(String), offset: true, grid: {display: false}},
        y: {type: "category", labels: rows.map(String), offset: true, grid: {display: false}}},
        plugins: {legend: {display: false}, tooltip: {callbacks: {title: function () { return ""; },
          label: function (ctx) { var r = ctx.raw.r; return [c.row_label || c.row] + " " + ctx.raw.y + ", " + ctx.raw.x + ": "
            + (Math.round(ctx.raw.v * 1000) / 10) + "%" + (c.tip && r[c.tip] ? " (" + r[c.tip] + ")" : ""); }}}}}};
    window.AshareInteractive.make(holder, cfg, {});
    return holder;
  }
  Object.keys(snap.tables).sort().forEach(function (name) {
    var t = snap.tables[name], c = t.chart || {type: "table"};
    main.appendChild(el("h2", t.title));
    if (c.type === "heatmap") { main.appendChild(matrix(t, c)); main.appendChild(heat(t, c)); }
    else if (c.type === "scatter" || c.type === "bars") main.appendChild(chart(t, c));
    var details = el("details"); details.appendChild(el("summary", "Data (" + t.rows.length + (t.rows.length === 1 ? " row" : " rows") +
      (t.rows.length > 500 ? "; the first 500 shown, all in the CSV" : "") + ")"));
    details.appendChild(table(t, 500)); main.appendChild(details);
  });
  window.__chartview = {tables: Object.keys(snap.tables).length,
                        interactive: !!(window.AshareInteractive && window.AshareInteractive.ready)};
})();
