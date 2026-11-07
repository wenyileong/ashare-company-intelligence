/* The interactive chart runtime (v2.3.0, plan section B4; the author's requirement R1).

   Every chart in the offline pages gets: wheel and pinch zoom, on both axes or one; drag to pan; shift-drag to zoom
   to a box; a reset (button or double-click); typed axis ranges; a logarithmic scale where every value is positive;
   a unit choice for money; and a readout of the exact stored value under the pointer, with its label. Long series are
   thinned for display when zoomed out and shown in full when zoomed in.

   Uses chartjs-plugin-zoom 2.2.0 and Hammer.js 2.0.8 (MIT; vendor/LICENSES.txt). Exposes window.AshareInteractive
   and records every chart in window.AshareInteractive.charts (for the tests). */
(function () {
  "use strict";
  var THIN_ABOVE = 5000, THIN_TO = 2000;
  var UNITS = {"yuan": 1, "10k yuan": 1e4, "100m yuan": 1e8};

  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = text;
    if (cls) e.className = cls; return e; }

  function exact(v) {
    if (v == null) return "–";
    if (typeof v !== "number") return String(v);
    return v.toLocaleString(undefined, {maximumFractionDigits: 6});
  }

  function zoomOptions(mode) {
    return {
      limits: {x: {minRange: 1e-9}, y: {minRange: 1e-9}},
      pan: {enabled: true, mode: mode},
      zoom: {wheel: {enabled: true}, pinch: {enabled: true},
             drag: {enabled: true, modifierKey: "shift", backgroundColor: "rgba(0,114,178,0.12)",
                    borderColor: "rgba(0,114,178,0.6)", borderWidth: 1},
             mode: mode}
    };
  }

  function countPoints(cfg) {
    return (cfg.data.datasets || []).reduce(function (n, d) { return Math.max(n, (d.data || []).length); }, 0);
  }

  function allPositive(cfg) {
    var ok = true, seen = false;
    (cfg.data.datasets || []).forEach(function (d) { (d.data || []).forEach(function (p) {
      var y = (p && typeof p === "object") ? p.y : p; if (y == null) return; seen = true; if (!(y > 0)) ok = false; }); });
    return ok && seen;
  }

  /* Add the zoom and thinning options to a Chart.js configuration, before the chart is made. */
  function prepare(cfg, info) {
    info = info || {};
    cfg.options = cfg.options || {};
    cfg.options.plugins = cfg.options.plugins || {};
    cfg.options.plugins.zoom = zoomOptions("xy");
    var many = countPoints(cfg) > THIN_ABOVE && cfg.type === "line";
    if (many) {
      cfg.options.parsing = false;
      cfg.options.plugins.decimation = {enabled: true, algorithm: "lttb", samples: THIN_TO, threshold: THIN_ABOVE};
    }
    if (info.money) {
      var y = cfg.options.scales && cfg.options.scales.y;
      if (y) { y.ticks = y.ticks || {}; var div = UNITS[info.unit || "yuan"];
        y.ticks.callback = function (v) { return (v / div).toLocaleString(undefined, {maximumFractionDigits: 2}); }; }
    }
    return many;
  }

  function readout(chart, box) {
    chart.options.onHover = function (evt, active) {
      if (!active || !active.length) return;
      var a = active[0], d = chart.data.datasets[a.datasetIndex], raw = d.data[a.index];
      var label = chart.data.labels ? chart.data.labels[a.index] : null;
      var parts = [d.label || ""];
      if (raw && typeof raw === "object") {
        if (raw.r && raw.r.label) parts.push(raw.r.label);
        parts.push("x = " + exact(raw.x), "y = " + exact(raw.y));
        if (raw.r && raw.r.disclosure_id != null) parts.push("document " + raw.r.disclosure_id + (raw.r.page != null ? ", page " + raw.r.page : ""));
      } else {
        if (label != null) parts.push(String(label));
        parts.push(exact(raw));
      }
      box.textContent = parts.filter(Boolean).join(" · ");
    };
  }

  function toolbar(chart, info, thinned) {
    var bar = el("div", null, "ai-toolbar");
    var reset = el("button", "Reset zoom"); reset.type = "button";
    reset.onclick = function () { chart.resetZoom(); };
    bar.appendChild(reset);
    var mode = el("select"); ["xy", "x", "y"].forEach(function (m) {
      var o = el("option", m === "xy" ? "zoom both axes" : "zoom " + m + " only"); o.value = m; mode.appendChild(o); });
    mode.onchange = function () { chart.options.plugins.zoom.zoom.mode = mode.value;
      chart.options.plugins.zoom.pan.mode = mode.value; chart.update("none"); };
    bar.appendChild(mode);
    var inputs = {};
    ["x", "y"].forEach(function (ax) {
      if (!chart.scales[ax] || chart.scales[ax].type === "category") return;
      ["min", "max"].forEach(function (k) { var i = el("input"); i.type = "number"; i.step = "any";
        i.placeholder = ax + " " + (k === "min" ? "from" : "to"); i.className = "ai-range"; inputs[ax + k] = i;
        bar.appendChild(i); });
    });
    if (Object.keys(inputs).length) {
      var go = el("button", "Apply range"); go.type = "button";
      go.onclick = function () {
        ["x", "y"].forEach(function (ax) {
          var lo = inputs[ax + "min"], hi = inputs[ax + "max"];
          if (!lo) return;
          var a = lo.value === "" ? null : Number(lo.value), b = hi.value === "" ? null : Number(hi.value);
          if (a != null || b != null) chart.zoomScale(ax, {min: a != null ? a : chart.scales[ax].min,
                                                          max: b != null ? b : chart.scales[ax].max}, "none");
        });
      };
      bar.appendChild(go);
    }
    if (info.positive && chart.options.scales && chart.options.scales.y) {
      var lab = el("label"), cb = el("input"); cb.type = "checkbox";
      cb.onchange = function () { chart.options.scales.y.type = cb.checked ? "logarithmic" : "linear"; chart.update(); };
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" log scale")); bar.appendChild(lab);
    }
    if (info.money) {
      var u = el("select"); Object.keys(UNITS).forEach(function (k) { var o = el("option", k); o.value = k; u.appendChild(o); });
      u.value = info.unit || "yuan";
      u.onchange = function () { var div = UNITS[u.value];
        chart.options.scales.y.ticks.callback = function (v) { return (v / div).toLocaleString(undefined, {maximumFractionDigits: 2}); };
        chart.update("none"); };
      bar.appendChild(u);
    }
    var hint = el("span", "Wheel or pinch to zoom · drag to pan · shift-drag to zoom to a box · double-click to reset"
                  + (thinned ? " · thinned for display; zoom in for every point" : ""), "ai-hint");
    bar.appendChild(hint);
    return bar;
  }

  /* Make an interactive chart in ``holder``: returns the Chart. ``info``: {money, unit}. */
  function make(holder, cfg, info) {
    info = info || {};
    info.positive = allPositive(cfg);
    var thinned = prepare(cfg, info);
    var canvas = document.createElement("canvas"); canvas.height = 320;
    var wrap = el("div", null, "ai-chart"); wrap.appendChild(canvas);
    holder.appendChild(wrap);
    var chart = new Chart(canvas, cfg);
    var box = el("div", "Point at a value to read it exactly.", "ai-readout");
    readout(chart, box);
    holder.insertBefore(toolbar(chart, info, thinned), wrap);
    holder.appendChild(box);
    canvas.addEventListener("dblclick", function () { chart.resetZoom(); });
    window.AshareInteractive.charts.push(chart);
    return chart;
  }

  /* For a chart made elsewhere (the topology page): add the zoom options to its configuration. */
  function options(opts) {
    opts = opts || {};
    opts.plugins = opts.plugins || {};
    opts.plugins.zoom = zoomOptions("xy");
    return opts;
  }

  function register() {
    if (typeof Chart === "function" && typeof ChartZoom !== "undefined") {
      try { Chart.register(ChartZoom); } catch (e) { /* registered already */ }
    }
  }
  register();
  window.AshareInteractive = {make: make, options: options, charts: [], ready: typeof ChartZoom !== "undefined"};
})();
