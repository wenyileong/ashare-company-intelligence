'use strict';
// NVF topology viewer. Adapted from the NVF Topology Tester v0.1 (index.html, app.js, styles.css): the page layout,
// the inspector, the coverage table and the charts are kept; the data now come from the snapshot embedded in this
// file (ashare.viz.snapshot), which decides every node, line, position, value and status. The page only filters
// and draws (finding P7). Positions are fixed when the nodes are created and no force moves them (P6), and the 2D
// view uses only settings that force-graph has (P5).

let DATA = null, LAYERS = [], COLOR_BY_LAYER = {}, graph = null, revenueChart = null, profitChart = null;
let NODE_BY_ID = {};
const $ = id => document.getElementById(id);
const EDGE_STYLES = {
  DOCUMENTED_FACT: {color: '#0072B2', width: 1.8, dash: null, label: 'Documented fact (solid)'},
  OBSERVED_ASSOCIATION: {color: '#8c959f', width: 1.2, dash: [6, 4], label: 'Observed association (dashed)'},
  ESTIMATED_RELATIONSHIP: {color: '#8c959f', width: 1.2, dash: [2, 3], label: 'Estimated relationship (dotted)'},
  THEORETICAL_PROPOSITION: {color: '#b0b8c1', width: 1.0, dash: [10, 3, 2, 3], label: 'Theoretical proposition (dash-dot)'}
};
const CHART_COLOURS = ['#0072B2', '#009E73', '#CC79A7', '#E69F00', '#D55E00', '#56B4E9', '#000000'];

function escapeHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); }
function money(v, digits = 2) { return v == null ? 'Not available' : Number(v).toLocaleString('en-GB', {minimumFractionDigits: digits, maximumFractionDigits: digits}); }
function idOf(end) { return typeof end === 'object' ? end.id : end; }
function companyLabel(code) { const n = NODE_BY_ID[`company:${code}`]; return n ? n.label : code; }
function yearOf(n) { const p = n.period || (n.dates || {}).observed_date; return p ? String(p).slice(0, 4) : null; }

function formatValue(n) {
  if (n.low != null && n.high != null) {
    return n.low === n.high ? formatOne(n.low, n.unit) : `${formatOne(n.low, n.unit)} to ${formatOne(n.high, n.unit)}`;
  }
  return n.value == null ? 'Not available' : formatOne(n.value, n.unit);
}
function formatOne(v, unit) {
  if (unit === 'CNY') return `CNY ${money(v, 0)}`;
  if (unit === 'CNY_PER_SHARE') return `CNY ${money(v, 2)} per share`;
  if (unit === 'PERCENT' || unit === 'PCT') return `${money(v, 2)}%`;
  if (unit === 'PERSON') return `${money(v, 0)} people`;
  return `${money(v, 2)}${unit ? ' ' + unit : ''}`;
}

function loadData() {
  try {
    DATA = JSON.parse($('snapshot').textContent);
    if (DATA.schema_version !== 1) throw new Error(`This viewer reads snapshot schema 1; the file holds schema ${DATA.schema_version}.`);
    LAYERS = DATA.layers;
    COLOR_BY_LAYER = Object.fromEntries(LAYERS.map(l => [l.id, l.colour]));
    NODE_BY_ID = Object.fromEntries(DATA.nodes.map(n => [n.id, n]));
    const p = DATA.parameters;
    $('eyebrow').textContent = `RESEARCH VIEW · SNAPSHOT SCHEMA ${DATA.schema_version}` + (p.episode ? ` · ${String(p.episode).toUpperCase()}` : '');
    $('subtitle').textContent = `${p.companies.length} compan${p.companies.length === 1 ? 'y' : 'ies'} · fiscal years ${p.periods[0].slice(0, 4)}–${p.periods[p.periods.length - 1].slice(0, 4)} · expectations: ${p.expectations === 'MANAGEMENT_GUIDANCE' ? 'management guidance (a proxy)' : 'analyst forecasts'}`;
    $('asOfPill').textContent = `As of ${p.as_of}`;
    populateFilters(); renderKpis(); renderLegend(); renderCharts(); renderCoverage(); renderNotes(); renderGraph();
    $('footerSourceCount').textContent = `${DATA.nodes.length} nodes · ${DATA.edges.length} links · published by ${p.as_of}`;
    $('footerSoftware').textContent = `${DATA.software} · offline snapshot · libraries bundled`;
  } catch (error) {
    $('graphCanvas').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    $('graphStatus').textContent = 'Snapshot unreadable';
  }
}

function populateFilters() {
  const p = DATA.parameters;
  $('companyFilter').innerHTML = '<option value="all">All companies</option>' + p.companies.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(companyLabel(c))}</option>`).join('');
  $('yearFilter').innerHTML = '<option value="all">All years</option>' + p.periods.map(x => `<option>${x.slice(0, 4)}</option>`).join('');
  $('layerFilter').innerHTML = '<option value="all">All layers</option>' + LAYERS.map(l => `<option value="${l.id}">${escapeHtml(l.label)}</option>`).join('');
  for (const id of ['viewMode', 'companyFilter', 'yearFilter', 'layerFilter', 'showOwnership', 'showGaps']) {
    const control = $(id);
    if (!control.dataset.bound) {
      control.addEventListener('change', () => { renderGraph(); if (id === 'companyFilter' || id === 'yearFilter') renderCharts(); });
      control.dataset.bound = '1';
    }
  }
  if (!$('exportBtn').dataset.bound) { $('exportBtn').addEventListener('click', exportVisible); $('exportBtn').dataset.bound = '1'; }
}

function renderKpis() {
  $('kpis').innerHTML = DATA.summary.map(k => `<div class="kpi"><div class="label">${escapeHtml(k.label)}</div><div class="value">${escapeHtml(k.value)}</div><div class="note">${escapeHtml(k.note)}</div></div>`).join('');
}

function renderLegend() {
  const gaps = new Set(DATA.coverage.filter(c => c.status === 'GAP').map(c => c.layer));
  $('layerLegend').innerHTML = LAYERS.map(l => `<span class="legend-item"><span class="swatch" style="background:${l.colour}"></span>${escapeHtml(l.label)}${gaps.has(l.id) ? ' (no data)' : ''}</span>`).join('') + '<span class="legend-empty">A grey node = no validated data in that layer</span>';
  const used = new Set(DATA.edges.map(e => e.evidence_status));
  $('edgeLegend').innerHTML = Object.entries(EDGE_STYLES).filter(([k]) => used.has(k) || k === 'DOCUMENTED_FACT').map(([k, s]) => `<span class="legend-item"><svg width="26" height="8"><line x1="1" y1="4" x2="25" y2="4" stroke="${s.color}" stroke-width="2" ${s.dash ? `stroke-dasharray="${s.dash.join(',')}"` : ''}/></svg>${escapeHtml(s.label)}</span>`).join('');
}

function renderCharts() {
  if (!window.Chart) return;
  const selected = $('companyFilter').value;
  const years = DATA.parameters.periods.map(p => p.slice(0, 4));
  const codes = DATA.parameters.companies.filter(c => selected === 'all' || c === selected);
  const dataFor = metric => {
    const s = DATA.series.find(x => x.metric === metric) || {points: []};
    return codes.map((c, i) => ({label: companyLabel(c), data: years.map(y => { const pt = s.points.find(v => v.company === c && v.period.slice(0, 4) === y); return pt ? pt.display_value : null; }),
      tension: .18, spanGaps: false, pointRadius: 3, borderWidth: 2, borderColor: CHART_COLOURS[i % CHART_COLOURS.length], backgroundColor: CHART_COLOURS[i % CHART_COLOURS.length]}));
  };
  const titles = DATA.series.map(s => s.label);
  if (titles[0]) $('chart1Title').textContent = titles[0];
  if (titles[1]) $('chart2Title').textContent = titles[1];
  const common = {responsive: true, maintainAspectRatio: true, interaction: {mode: 'index', intersect: false}, plugins: {legend: {position: 'bottom', labels: {boxWidth: 9, font: {size: 10}}}, tooltip: {callbacks: {label: ctx => `${ctx.dataset.label}: ${ctx.raw == null ? 'n/a' : Number(ctx.raw).toFixed(3)} CNY bn`}}}, scales: {x: {grid: {display: false}}, y: {grid: {color: '#edf0f4'}, ticks: {font: {size: 10}}}}};
  if (revenueChart) revenueChart.destroy(); if (profitChart) profitChart.destroy();
  revenueChart = new Chart($('revenueChart'), {type: 'line', data: {labels: years, datasets: dataFor('revenue')}, options: common});
  profitChart = new Chart($('profitChart'), {type: 'line', data: {labels: years, datasets: dataFor('net_profit_parent')}, options: common});
}

function renderCoverage() {
  const cls = {COMPLETE: 'available', PARTIAL: 'partial', GAP: 'missing'};
  const rows = DATA.coverage.map(r => `<tr><td><strong>${escapeHtml((LAYERS.find(l => l.id === r.layer) || {}).label || r.layer)}</strong></td><td><span class="status ${cls[r.status] || ''}">${escapeHtml(r.status)}</span></td><td>${r.observations}</td><td>${escapeHtml(r.note)}</td></tr>`).join('');
  $('coverageTable').innerHTML = `<div class="table-wrap"><table><thead><tr><th>NVF layer</th><th>Status</th><th>Items</th><th>Interpretation</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderNotes() {
  $('observationNotes').innerHTML = DATA.notes.map(n => `<div class="note"><strong>${escapeHtml(n.title)}.</strong> ${escapeHtml(n.text)}</div>`).join('');
}

// Filtering only: which of the snapshot's nodes and lines to draw. Nothing is computed.
function buildGraphData() {
  const selectedCompany = $('companyFilter').value, selectedYear = $('yearFilter').value, selectedLayer = $('layerFilter').value;
  const showOwnership = $('showOwnership').checked, showGaps = $('showGaps').checked;
  const linkedTo = {};
  for (const e of DATA.edges) { (linkedTo[e.source] = linkedTo[e.source] || new Set()).add(e.target); (linkedTo[e.target] = linkedTo[e.target] || new Set()).add(e.source); }
  const keep = n => {
    if (n.kind === 'data_gap') return showGaps && (selectedLayer === 'all' || n.layer === selectedLayer);
    if ((n.kind === 'shareholder' || n.kind === 'controller') && !showOwnership) return false;
    if (selectedLayer !== 'all' && n.layer !== selectedLayer && !['company', 'shareholder', 'controller'].includes(n.kind)) return false;
    if (selectedYear !== 'all' && n.kind === 'observation' && yearOf(n) !== selectedYear) return false;
    if (selectedCompany !== 'all') {
      if (n.company_code) return n.company_code === selectedCompany;
      if (n.kind === 'shareholder' || n.kind === 'controller' || n.kind === 'sector') return (linkedTo[n.id] || new Set()).has(`company:${selectedCompany}`);
    }
    return true;
  };
  const nodes = DATA.nodes.filter(keep).map(n => ({...n, color: n.kind === 'data_gap' ? '#bfc5cc' : (COLOR_BY_LAYER[n.layer] || '#718096'),
    x: n.position.x, y: n.position.y, z: n.position.z, fx: n.position.x, fy: n.position.y, fz: n.position.z}));
  const ids = new Set(nodes.map(n => n.id));
  const links = DATA.edges.filter(e => ids.has(e.source) && ids.has(e.target)).map(e => ({...e}));
  return {nodes, links};
}

function nodeSize(n) { return n.kind === 'company' ? 13 : n.kind === 'sector' || n.kind === 'regulatory_event' ? 10 : n.kind === 'shareholder' || n.kind === 'controller' ? 8 : 6; }

function makeNodeThreeObject(node, THREE) {
  const group = new THREE.Group();
  const gap = node.kind === 'data_gap';
  const material = new THREE.MeshLambertMaterial({color: node.color || '#718096', transparent: gap, opacity: gap ? .45 : 1});
  group.add(new THREE.Mesh(new THREE.SphereGeometry(nodeSize(node), 12, 10), material));
  if (gap) group.add(new THREE.Mesh(new THREE.TorusGeometry(15, 1.5, 8, 30), new THREE.MeshBasicMaterial({color: '#E69F00'})));
  return group;
}

function linkStyle(l) { return EDGE_STYLES[l.evidence_status] || EDGE_STYLES.OBSERVED_ASSOCIATION; }

function renderGraph() {
  if (!DATA) return;
  const graphEl = $('graphCanvas'); graphEl.innerHTML = '';
  if (graph && graph._destructor) { try { graph._destructor(); } catch (e) { /* the previous view is gone anyway */ } }
  const mode = $('viewMode').value;
  const data = buildGraphData();
  $('axisNote').innerHTML = mode === '3d' ? '<b>3D encoding:</b> X = NVF layer · Y = company lane · Z = year. Positions are fixed by the snapshot, not by a simulation.'
    : '<b>2D slice:</b> X = NVF layer · Y = company lane, with the years set apart within it. Choose a fiscal year to see one year at a time.';
  if (mode === '3d') {
    if (!window.ForceGraph3D) { graphEl.innerHTML = '<div class="error">The 3D graph library is missing from this file. Use the 2D slice, or the tables and charts below.</div>'; return; }
    const THREE = window.THREE;
    graph = ForceGraph3D()(graphEl).backgroundColor('#f0f4f8').showNavInfo(false)
      .nodeColor(n => n.color).nodeVal(n => nodeSize(n)).nodeLabel(n => `${n.label}${n.masked ? ' (pseudonym)' : ''}`)
      .linkColor(l => linkStyle(l).color).linkOpacity(.65).linkWidth(l => linkStyle(l).width)
      .linkLabel(l => `${l.label || l.relation} (${l.evidence_status.replace(/_/g, ' ').toLowerCase()})`)
      .onNodeClick(showDetails).onLinkClick(showLinkDetails)
      .width(graphEl.clientWidth).height(graphEl.clientHeight)
      .warmupTicks(0).cooldownTicks(2).d3Force('charge', null).d3Force('center', null);
    if (THREE) graph.nodeThreeObject(n => makeNodeThreeObject(n, THREE));
    graph.d3Force('link').strength(0);           // kept only to join the lines to their nodes; it pulls nothing
    // two ticks with no forces: the lines are laid along the fixed nodes, then the camera frames them
    const g3 = graph;
    g3.onEngineStop(() => { if (!g3._framed) { g3._framed = true; g3.zoomToFit(400, 40); } });
    graph.graphData(data);
  } else {
    if (!window.ForceGraph) { graphEl.innerHTML = '<div class="error">The 2D graph library is missing from this file. Use the 3D view, or the tables and charts below.</div>'; return; }
    graph = ForceGraph()(graphEl).backgroundColor('#f0f4f8')
      .nodeColor(n => n.color).nodeVal(n => nodeSize(n)).nodeLabel(n => `${n.label}${n.masked ? ' (pseudonym)' : ''}`)
      .linkColor(l => linkStyle(l).color).linkWidth(l => linkStyle(l).width).linkLineDash(l => linkStyle(l).dash)
      .linkLabel(l => `${l.label || l.relation} (${l.evidence_status.replace(/_/g, ' ').toLowerCase()})`)
      .onNodeClick(showDetails).onLinkClick(showLinkDetails)
      .width(graphEl.clientWidth).height(graphEl.clientHeight)
      .warmupTicks(0).cooldownTicks(2).d3Force('charge', null).d3Force('center', null)
      .nodeCanvasObject((node, ctx, globalScale) => {
        const r = nodeSize(node) / 2;
        ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false); ctx.fillStyle = node.color; ctx.fill();
        if (node.kind === 'data_gap') { ctx.strokeStyle = '#E69F00'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI); ctx.stroke(); }
        if (globalScale > 1.15 || node.kind === 'company') { ctx.font = `${Math.max(8, 10 / globalScale)}px sans-serif`; ctx.fillStyle = '#273444'; ctx.fillText(node.label, node.x + r + 2, node.y + 3); }
      })
      .nodePointerAreaPaint((node, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(node.x, node.y, nodeSize(node) / 2 + 2, 0, 2 * Math.PI); ctx.fill(); });
    graph.d3Force('link').strength(0);
    const g2 = graph;
    g2.onEngineStop(() => { if (!g2._framed) { g2._framed = true; g2.zoomToFit(300, 30); } });
    graph.graphData({nodes: data.nodes.map(n => ({...n, y: n.position.y2, fy: n.position.y2, fz: undefined, z: undefined})), links: data.links});
  }
  $('graphStatus').textContent = `${data.nodes.length} nodes · ${data.links.length} links`;
}

function provenanceBlock(p) {
  if (!p) return '';
  const rows = [];
  const add = (k, v) => { if (v != null && v !== '') rows.push(`<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`); };
  add('Document', p.document_title); add('Document ID', p.disclosure_id); add('Page', p.page); add('Method', p.method);
  add('Confidence', p.confidence_class); add('Review', p.review); add('Validation', p.validation); add('Source', p.source);
  add('Trading day', p.trade_date); add('Issuer', p.issuer); add('Licence', p.licence); add('Legal character', p.legal_classification);
  add('Authority', p.authority); add('Statements', p.revisions > 1 ? `${p.revisions} for this period` : null);
  add('Document hash', p.document_hash ? String(p.document_hash).slice(0, 16) + '…' : null);
  const link = p.source_url ? `<a class="source-link" href="${escapeHtml(p.source_url)}" target="_blank" rel="noopener noreferrer">Open the source document ↗</a>` : '';
  return `<dl class="detail-list">${rows.join('')}</dl>${link}`;
}

function showDetails(n) {
  const layer = (LAYERS.find(l => l.id === n.layer) || {}).label || 'No layer';
  const d = n.dates || {};
  const dates = [['Event', d.event_date], ['Published', d.published_date], ['Observed', d.observed_date], ['Valid from', d.valid_from]].filter(x => x[1]).map(x => `${x[0]} ${x[1]}`).join(' · ') || 'Not specified';
  const flags = (n.flags || []).length ? `<dt>Findings</dt><dd>${escapeHtml(n.flags.join(', '))}</dd>` : '';
  $('detailContent').innerHTML = `<div class="detail-title">${escapeHtml(n.label)}</div><span class="tag">${escapeHtml(layer)}</span><span class="tag ${n.kind === 'data_gap' ? 'missing' : ''}">${escapeHtml(n.kind.replace(/_/g, ' '))}</span>${n.masked ? '<span class="tag">pseudonym</span>' : ''}${n.restated ? '<span class="tag missing">restated</span>' : ''}`
    + `<dl class="detail-list"><dt>Dates</dt><dd>${escapeHtml(dates)}</dd>${n.kind === 'observation' ? `<dt>Value</dt><dd>${escapeHtml(formatValue(n))}</dd>` : ''}`
    + `<dt>Explanation</dt><dd>${escapeHtml(n.description || '')}</dd>${n.company_code ? `<dt>Company</dt><dd>${escapeHtml(companyLabel(n.company_code))}</dd>` : ''}${flags}</dl>`
    + provenanceBlock(n.provenance)
    + '<p class="detail-caveat">The evidential status records what the source supports. It does not, by itself, support causation.</p>';
}

function showLinkDetails(l) {
  const s = NODE_BY_ID[idOf(l.source)] || {}, t = NODE_BY_ID[idOf(l.target)] || {};
  const b = l.basis || {}, d = l.dates || {};
  const basis = Object.entries(b).filter(([k, v]) => v != null && v !== '').map(([k, v]) => `<dt>${escapeHtml(k.replace(/_/g, ' '))}</dt><dd>${escapeHtml(v)}</dd>`).join('');
  const dates = Object.entries(d).filter(([k, v]) => v).map(([k, v]) => `${k.replace(/_date$/, '').replace(/_/g, ' ')} ${v}`).join(' · ');
  $('detailContent').innerHTML = `<div class="detail-title">${escapeHtml(s.label || '')} → ${escapeHtml(t.label || '')}</div><span class="tag">${escapeHtml(l.relation.replace(/_/g, ' ').toLowerCase())}</span><span class="tag">${escapeHtml(l.evidence_status.replace(/_/g, ' ').toLowerCase())}</span>`
    + `<dl class="detail-list"><dt>Stated as</dt><dd>${escapeHtml(l.label || l.relation)}</dd><dt>Dates</dt><dd>${escapeHtml(dates || 'Not specified')}</dd>${basis}</dl>`
    + '<p class="detail-caveat">A documented fact is what the named document, classification or feed states. Proximity in the map is not evidence of control or effect.</p>';
}

function exportVisible() {
  const data = buildGraphData();
  const cols = ['id', 'company_code', 'layer', 'metric', 'period', 'value', 'low', 'high', 'unit', 'published_date', 'disclosure_id', 'page', 'method', 'label'];
  const cell = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const rows = data.nodes.filter(n => n.kind === 'observation').map(n => [n.id, n.company_code, n.layer, n.metric, n.period, n.value, n.low, n.high, n.unit, (n.dates || {}).published_date, (n.provenance || {}).disclosure_id, (n.provenance || {}).page, (n.provenance || {}).method, n.label].map(cell).join(','));
  const blob = new Blob(['﻿' + [cols.join(',')].concat(rows).join('\n')], {type: 'text/csv;charset=utf-8'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'topology_visible_observations.csv';
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

// The canvas takes the size of its panel, not of the window (the prototype's graph sat off centre).
window.addEventListener('resize', () => { if (graph) { const el = $('graphCanvas'); graph.width(el.clientWidth).height(el.clientHeight); } });

loadData();
