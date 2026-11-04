/* The relational map (v2.2): the snapshot drawn with the 2D force layout. Every link opens its document and page in
   the inspector; natural persons appear under pseudonyms, as in the snapshot. */
(function () {
  "use strict";
  var snap = JSON.parse(document.getElementById("snapshot").textContent);
  var COLOURS = {company: "#0072B2", entity: "#56B4E9", person: "#CC79A7", authority: "#D55E00",
                 sector: "#009E73", group: "#E69F00"};
  var side = document.getElementById("side"), inspector = document.getElementById("inspector");
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = text;
    if (cls) e.className = cls; return e; }
  var p = snap.parameters || {};
  side.appendChild(el("h1", p.title || "Relational map"));
  side.appendChild(el("div", "As published by " + p.as_of + " · " + snap.software, "muted"));
  side.appendChild(el("h2", "Kinds"));
  Object.keys(COLOURS).forEach(function (k) {
    if (!snap.nodes.some(function (n) { return n.kind === k; })) return;
    var d = el("div"); var c = el("span", null, "chip"); c.style.background = COLOURS[k]; d.appendChild(c);
    d.appendChild(document.createTextNode(k)); side.appendChild(d);
  });
  side.appendChild(el("h2", "Relations shown"));
  var rels = {}; snap.edges.forEach(function (e) { rels[e.relation] = true; });
  var shown = {};
  Object.keys(rels).sort().forEach(function (r) {
    shown[r] = true;
    var lab = el("label"); var box = document.createElement("input"); box.type = "checkbox"; box.checked = true;
    box.setAttribute("data-relation", r);
    box.addEventListener("change", function () { shown[r] = box.checked; redraw(); });
    lab.appendChild(box); lab.appendChild(document.createTextNode(" " + r.toLowerCase().replace(/_/g, " ")
      + " (" + snap.edges.filter(function (e) { return e.relation === r; }).length + ")"));
    side.appendChild(lab);
  });
  if ((snap.coverage || []).length) {
    side.appendChild(el("h2", "Coverage"));
    snap.coverage.forEach(function (c) { side.appendChild(el("div", c.item + ": " + c.status + (c.note ? " · " + c.note : ""), "note")); });
  }
  side.appendChild(el("h2", "Notes"));
  (snap.notes || []).forEach(function (n) { side.appendChild(el("div", n, "note")); });

  var byId = {}; snap.nodes.forEach(function (n) { byId[n.id] = n; });
  function data() {
    var links = snap.edges.filter(function (e) { return shown[e.relation]; })
      .map(function (e) { return {source: e.source, target: e.target, edge: e}; });
    var keep = {}; links.forEach(function (l) { keep[l.source] = keep[l.target] = true; });
    var nodes = snap.nodes.filter(function (n) { return keep[n.id] || n.centre; }).map(function (n) {
      var o = {id: n.id, node: n}; if (n.centre) { o.fx = 0; o.fy = 0; } return o; });
    return {nodes: nodes, links: links};
  }
  function row(t, k, v) { if (v == null || v === "") return; var tr = el("tr"); tr.appendChild(el("td", k));
    tr.appendChild(el("td", String(v))); t.appendChild(tr); }
  function show(n, e) {
    inspector.innerHTML = ""; inspector.style.display = "block";
    var close = el("div", "×"); close.style.cssText = "float:right;cursor:pointer;font-size:16px";
    close.onclick = function () { inspector.style.display = "none"; }; inspector.appendChild(close);
    var t = el("table");
    if (n) {
      inspector.appendChild(el("b", n.label));
      row(t, "kind", n.kind); row(t, "code", n.code); row(t, "flags", (n.flags || []).join(", "));
      row(t, "degree", n.degree); if (n.masked) row(t, "note", "a natural person, shown under a pseudonym");
      snap.edges.filter(function (x) { return x.source === n.id || x.target === n.id; }).forEach(function (x) {
        var other = byId[x.source === n.id ? x.target : x.source];
        row(t, x.relation.toLowerCase(), (other ? other.label : "") + (x.label ? " · " + x.label : "")
          + (x.basis && x.basis.disclosure_id ? " · document " + x.basis.disclosure_id + (x.basis.page ? " p. " + x.basis.page : "") : ""));
      });
    } else if (e) {
      inspector.appendChild(el("b", (byId[e.source] || {}).label + " → " + (byId[e.target] || {}).label));
      row(t, "relation", e.relation); row(t, "detail", e.label); row(t, "value", e.value);
      row(t, "evidence", e.evidence_status); var b = e.basis || {}, d = e.dates || {};
      row(t, "document", b.disclosure_id); row(t, "page", b.page); row(t, "method", b.method);
      row(t, "source", b.source); row(t, "published", d.published_date); row(t, "observed", d.observed_date);
    }
    inspector.appendChild(t);
  }
  var holder = document.getElementById("graph");
  var main = document.getElementById("main");
  var graph = null;
  if (typeof ForceGraph === "function") {
    graph = ForceGraph()(holder).width(main.clientWidth).height(main.clientHeight)
      .nodeId("id").nodeLabel(function (o) { return o.node.label; })
      .nodeColor(function (o) { return COLOURS[o.node.kind] || "#8c959f"; })
      .nodeVal(function (o) { return o.node.centre ? 6 : 2; })
      .linkLabel(function (l) { return l.edge.relation.toLowerCase() + (l.edge.label ? ": " + l.edge.label : ""); })
      .linkDirectionalArrowLength(4).linkDirectionalArrowRelPos(1)
      .nodeCanvasObjectMode(function () { return "after"; })
      .nodeCanvasObject(function (o, ctx, scale) {
        if (scale < 1.2 && !o.node.centre) return;
        ctx.font = (o.node.centre ? 5 : 3.5) + "px sans-serif"; ctx.fillStyle = "#1f2328"; ctx.textAlign = "center";
        ctx.fillText(o.node.label, o.x, o.y + 7);
      })
      .onNodeClick(function (o) { show(o.node, null); })
      .onLinkClick(function (l) { show(null, l.edge); });
    window.addEventListener("resize", function () { graph.width(main.clientWidth).height(main.clientHeight); });
  } else {
    holder.appendChild(el("p", "The graph library could not start; the data are listed below.", "panel"));
  }
  function redraw() { if (graph) graph.graphData(data()); }
  redraw();
  window.__relmap = {nodes: function () { return data().nodes.length; }, links: function () { return data().links.length; },
                     show: show};
})();
