# Plan for v2.2: the remaining data fixes and the visualisation section

v2.2 does two things in one release:
- **Part A** fixes what the author's tests of v2.1.2 showed (findings 132 to 139; `docs/live_run_findings_v2.1.2.md`, written with the build).
- **Part B** builds the scaffolding of a new **Visualise** section, with relational maps, and three reference views.

The two parts are ordered on purpose. The relational maps draw on controller names, holdings and balance-sheet totals, so the fixes that correct those come first (section C1).

Every fix below states its cause, the change, why it cannot disturb what already works, and its tests. The rule of earlier plans stands: an existing test may change only where the change is the intended behaviour, with the reason noted beside it.

# Part A: data fixes

## Results of the author's v2.1.2 test plan

| Test | Result |
|---|---|
| Parallel reading (finding 124) | **Fixed**: 0 errors in financial (7,088 documents), top-10, control, ESG and guidance runs |
| Files page | Works; 6,650 copies exported in 173 s |
| Downloads, refresh window, scanned-page check, gap messages, ESG title | Work |
| Balance-sheet repair (finding 129) | **Not applied**: 103 failures, 86 out by a round number; document 31 still out by exactly 20 billion |
| Controller names (finding 128) | **Partly fixed**: SASAC grouped once (11 companies); four names still garbled |
| Top-10 coverage (finding 131) | **Low**: 502 of 2,199 reports gave rows |
| Side panel | Not reported (visual) |

## A1. The balance-sheet repair did not apply (finding 132; high)

**Evidence.** "Check balance sheets": 103 failed, "86 out by a single digit times a power of ten". Document 31 (000009) is still out by exactly 20,000,000,000.

**Cause.** The repair of v2.1.2 needs a second figure in the *same reading* to confirm which total lost its digit (parent plus minority equity; current plus non-current liabilities or assets). Two things can defeat that, and the logs cannot tell which:
- The failing totals may come from the key-figures reading, which reads only the three totals and so never has the confirming parts.
- The confirming parts may be cut in the same way (parent equity sits in the same narrow column and has the same number of digits).

**Change.**
1. **Confirmation across readings.** If the other reading of the same document and period has the same item equal to the read value plus the gap, the figure is restored from it. Two independent readings agreeing on the complete figure is stronger evidence than the arithmetic.
2. **Confirmation by the statement's own total.** If "负债和所有者权益总计" is read, agrees with total assets, and only one of the three totals is short of the place the digit was lost at, that total is restored.
3. **Rejoining at the source.** The author's `inspect-tables 31 --table balance_sheet` and `76` will show how the figure is split on the page. If the split is a lone digit and a separate thousands group with no note number possible between them (for example, the digit in the column of the current period and no "附注" column on that page), the reader rejoins them before any check.

Rules 1 and 2 are built in any case. Rule 3 is built only if the samples show the pattern, and only in the form they show.

**Interference.** The repair acts only on a balance sheet out by exactly a single digit times a power of ten, as before; a balance sheet that balances is never touched. Every restored figure keeps its reading in `raw_value`, notes the rule used and has lower confidence. Version financials-5.

**Tests.**
- Rule 1 with the key-figures reading short and the statement complete, and the reverse.
- Rule 2 with only equity short of the place.
- Nothing restored when two totals could be short.
- The author's two documents, rebuilt as test lines from the `inspect-tables` files.

## A2. Controller names: the legal representative glued to the wrapped name (finding 133; high)

**Evidence.** Four rows of "Companies with the same controller":
- 国务院国有资产监督、张玉卓管理委员会;
- 深圳市人民政府国有、杨军资产监督管理委员会;
- 山西省人民政府国有、洪强资产监督管理委员会;
- 代表国家履行出资人、深圳市人民政府国有、杨军资产监督管理委员会.

**Cause.** In these reports the legal representative's name is printed on the same line as the second half of the wrapped entity name, with no space ("杨军资产监督管理委员会"). v2.1.2 handled the name on a line of its own. On this layout, its rule for keeping two whole names apart split the name at the wrong place. Reproduced exactly.

**Change.**
- A token that begins with a two- or three-character personal name followed by the rest of a wrapped name (资产…, 管理委员会, 有限公司, and the other continuations) loses the personal name and joins the piece before it.
- Where a table row yields a whole entity name, pieces that do not end as an entity name ends are dropped (for example 代表国家履行出资人, the start of "代表国家履行出资人职责的…").
- The grouping key treats 省政府 and 省人民政府 before 国有资产监督管理委员会 as the same.
- Version control-4.

**Interference.** The cases fixed in v2.1.2, the Shanghai label-and-value layout and several persons acting together all keep their tests. A personal name is stripped only when what follows it reads as the rest of a wrapped name.

**Tests.** The four forms above, exactly as in the log; the author's `inspect-tables --code 000019 --year 2025 --table control` if sent.

## A3. Top-10 tables of quarterly reports (finding 134; medium)

**Evidence.** 2,199 reports read (mostly third-quarter reports downloaded in October), 502 with rows. "dual_run: agree 278, disagree 243, single 1903, secondary_only 898".

**Assessment.** Quarterly reports carry a top-10 table ("前十名股东持股情况") in a shorter layout than annual reports: fewer columns, often with the tradable-holder table immediately after. The section index finds the heading, so the cause is likely the parser's column expectations. It cannot be fixed safely without the author's `inspect-tables --table top10` samples.

**Change (once the samples arrive).**
- The quarterly layout is recognised.
- The checks (ten rows at most, percentages between 0 and 100, total no more than 100) are kept.
- The coverage is reported by report kind, so a gap in quarterly reports shows as such.

**Interference.** Annual and interim tables keep their tests; a quarterly table must pass the same checks. Version top10-4.

## A4. Smaller fixes

- **A4.1 Download estimates (finding 135).** The rate recorded by a run of a few documents (the 15-second guidance run: 4.2 s) or of a different kind (forecasts, 5.2 s, against 2.7 s for reports) misled the next estimate.
  - Rates are now kept by kind, as a running mean over the last downloads of at least 25 documents.
  - Shorter runs are not recorded.
- **A4.2 Stop message during downloads (finding 136).** Stopping the download step of a catalogue said "resumes with the first unfinished day" when every day was finished. It now says that the catalogue is complete and that running it again downloads the rest.
- **A4.3 ESG counts (finding 137).** Every run reported 2,112 "updated" for sustainability-report titles that had not changed. A title row is now written only when something differs; the count says "unchanged" otherwise.
- **A4.4 Short documents marked PARTIAL (finding 138).** One- and two-page announcements with a signature or seal page count as partly scanned under the 80% rule. A document of three pages or fewer is now FULL when every page but the last has text, and the rule is stated in the output. The data were not affected: these documents are read normally.
- **A4.5 Slow controller read (finding 139; information).** One half-year report (000756, 140 pages) took 138 s. It is named in `slowest` as designed; it is to be looked at only if it recurs.

## A5. What the author needs to send

| For | Command (from the data folder) |
|---|---|
| A1 | `ashare-cli inspect-tables 31 --table balance_sheet` and `ashare-cli inspect-tables 76 --table balance_sheet` |
| A3 | `ashare-cli inspect-tables ID --table top10` for two or three quarterly reports without rows |
| A2 (optional) | `ashare-cli inspect-tables --code 000019 --year 2025 --table control` |

Parts B and C, A2, A4 and rules 1 and 2 of A1 do not wait for these. A1 rule 3 and A3 do.

# Part B: the visualisation section

## B1. Purpose and scope

v2.2 gathers every chart and map the program draws under one heading, **Visualise** (可视化), and builds the scaffolding on which further views can be added without re-engineering each one. It is a framework release: it moves what exists, sets the contract every view follows, and proves the contract with three reference views. The views of later phases (sector, NVF and relational views at market scale) are specified here, so that the scaffolding fits them, but built only when their data are in place (section B9).

The topology view (v2.1) is the model: a view is described as data (a *snapshot*), every item carries its provenance, gaps are shown and not filled, and the same snapshot can be drawn interactively or written as files. v2.2 generalises that pattern from one view to many.

The data fixes are in Part A; sections B9 and C1 say which views depend on them.

## B2. Principles (carried over from the v2.1 plan, section 7.1)

1. **Point in time.** Every view is built "as published by" a date. Nothing published later enters it.
2. **Provenance.** Every plotted value and every link names its source: document and page, classification, price feed or import, with method and confidence.
3. **Gaps are shown.** Missing data appear as gaps with the reason (the v2.1.2 gap messages), never interpolated or silently dropped.
4. **No causal language.** A line, a link or a sequence is a documented fact or an association, not evidence of cause. Each view states its evidential status (as the topology view does).
5. **Persons and licences.** Natural persons are pseudonymised by default with the release key. Licensed data are left out unless included explicitly, and the manifest says which.
6. **Determinism.** The same parameters and the same database give the same snapshot, byte for byte.
7. **Offline and bilingual.** Interactive pages work from disk with no network. Interface text follows the glossary; data, variable names and files stay in English.
8. **Proxies are labelled.** Where a view stands in for a concept of the paper (Institutional Visibility, the Fractal Investment Clock), it says that it is a descriptive proxy, and which definition it uses (section B6).

## B3. What exists and where it goes

| Today | Where | v2.2 place |
|---|---|---|
| Topology view (`topology`) | Analyse > Topology | Visualise > Topology |
| Company charts: financials, segment mix, segment history, workforce, prices, findings (`chart`) | Datasets > Export a chart; Company pages | Visualise > Company views |
| Control chain, group tree, board interlocks (`chart`) | As above | Visualise > Relational maps (the ego map absorbs them) |
| Industry distribution, peer scatter (`chart`) | As above | Visualise > Sectors and the market |
| Panel explorer: histogram, box plot, scatter, coverage, summary (`panel-chart`) | Datasets | Visualise > Econometric charts |
| Event study (`event-study`) | Analyse | Stays under Analyse (it computes); its figure is drawn under Visualise > Econometric charts |

The commands keep their names, so `run_log.txt` and existing scripts still work. Each old page keeps a one-line pointer to the new place for one release.

## B4. Architecture

### B4.1 Package layout

```
ashare/viz/
    registry.py      the list of views; the GUI pages and the CLI are generated from it
    view.py          the View contract (B4.2) and the readiness check
    data.py          point-in-time accessors shared by all views (as-of filtering, provenance rows)
    graph.py         the relational model (B4.4): nodes, edges, projections, measures
    definitions.py   versioned definitions of the NVF proxies (section B6)
    snapshot.py      the topology snapshot (unchanged in behaviour; reused by the graph views)
    series.py        the series snapshot (B4.3) for chart views
    export.py        files and manifest for both snapshot kinds (generalised from v2.1)
    figure.py        publication figures (B4.5)
    views/           one module per view: topology, ego_map, coverage, guidance_outcome, ...
    viewer/          the interactive page shell: graph mode (from the Topology Tester) and chart mode
```

`ashare/charts/` stays as the drawing layer (SVG and Tk renderers); views produce chart specifications for it.

### B4.2 The View contract

Every view is one class registered in `registry.py`:

| Member | Meaning |
|---|---|
| `id`, `family` | e.g. `ego_map`, family `relational` (families: topology, company, relational, sector, econometric, coverage) |
| `title`, `intro` | Interface text, through the translation catalogue |
| `params` | The fields the view takes (codes or industry, span, as-of, options), declared once. The GUI form and the CLI options are generated from them. |
| `requires` | The data the view needs, as checks (e.g. "industry classification imported", "prices for the span") |
| `readiness(params)` | For each requirement: met, partly met (with counts), or missing, with the action that fills it. The GUI shows this before Run. |
| `build(params)` | Returns a snapshot (graph or series), with coverage and gap notes |
| `outputs` | Which of the outputs in B4.5 it supports |
| `evidence` | Its evidential status, for the caption: documented fact, observed association, descriptive proxy |

A view never queries the database except through `data.py`, which applies the as-of date, pseudonymisation and licence rules in one place. This is what keeps principles 1 and 5 true for views written later.

### B4.3 Two kinds of snapshot

- **Graph snapshot**: nodes and edges, as in the topology view.
  - The schema goes to version 2, which adds the node kinds of the relational maps (entity, person, authority, sector, group) and their relations (B4.4).
  - Version 1 snapshots stay readable, and a topology view built with v2.2 produces the same nodes and edges as with v2.1.2, apart from controller names corrected by A2 (tested; sections B10 and C2).
- **Series snapshot**: rows for charts, each with its provenance columns (the `observations.csv` columns of v2.1), plus axes, units and gap notes.

Both are written as JSON with a JSON Schema, a CSV of exactly what is plotted, and a manifest. The manifest records the parameters, the database fingerprint, the software version, the definition version (section B6) and a SHA-256 for every file.

### B4.4 The relational model (`graph.py`)

**Nodes.**

| Kind | Identity | Source |
|---|---|---|
| Company | security code | `Company` |
| Entity (legal person: holder, controller, subsidiary, counterparty) | `Entity` (credit code where known), else the normalised name | `Entity`, `EntityAlias`, resolution |
| Person | `Person` (pseudonymised by default) | `Person`, `PersonRole` |
| Authority | regulator name, normalised | `RegulatoryEvent` |
| Sector | CSRC code | `IndustryClassification` |
| Group | the ultimate controller | derived from control |

**Edges**, each with the published date, the observed date, the source document and page, method and confidence:

| Relation | From | To | Source |
|---|---|---|---|
| CONTROLS | entity or person | company or entity | `ControlObservation`, `ControlEdge` |
| HOLDS (with %) | holder | company | `OwnershipObservation` (top-10) |
| SUBSIDIARY_OF (with stake, direct or indirect) | entity | company | `SubsidiaryObservation` |
| SERVES_ON (role) | person | company | `PersonRole` |
| TRANSACTS_WITH, GUARANTEES, PLEDGES | company | entity | `TransactionEvent`, `PledgeEvent` |
| ACTS_ON (penalty, enquiry, measure) | authority | company | `RegulatoryEvent` |
| IN_SECTOR | company | sector | `IndustryClassification` |

**Identity rules.**
- A name that cannot be resolved to an entity stays its own node, flagged `UNRESOLVED`, and is never merged by guesswork.
- The controller grouping key of v2.1.2 is used for controllers.
- The resolution rate is shown in the coverage panel of every relational view.

**Operations.**
- **As-of slicing.** The links valid on a date are the latest observation published by then for each pair.
- **Projections.** From two-sided to one-sided: shareholders × companies → companies sharing holders; persons × companies → interlocks.
- **Measures**, in pure Python, with no new dependency for the Windows build:
  - degree;
  - components;
  - distance to the ultimate controller;
  - group size;
  - the common-ownership measure (MHHI delta) by sector.
  Betweenness and similar measures are computed only below a size limit, and say so above it.
- **Panel variables.** The measures become dated variables in `build-panel`, with codebook entries, so that they can enter regressions (section B7).

### B4.5 Outputs

| Output | For | How |
|---|---|---|
| In the window | Looking | Tk renderer of `charts` (existing) |
| Interactive page | Exploring, sharing | One offline HTML file. Graph mode is the Topology Tester shell, generalised to the v2 schema (filters by relation, as-of slider, inspector). Chart mode uses the bundled Chart.js. |
| Publication figure | Papers | SVG from the `charts` renderer in a journal style: single column (85 mm) or full width (175 mm), greyscale-safe markers and line styles, a caption with the evidential status, source and as-of date. A print-ready HTML page gives a PDF through the browser's print dialogue. PNG and PDF directly when matplotlib is installed (source installations; it is not in the Windows build). |
| Data | Re-drawing in Stata or R | The snapshot's CSV, and a labelled Stata file (`.dta`), written as panels are |

### B4.6 Command line

- `ashare-cli viz list`: the views, their families and whether their data are ready.
- `ashare-cli viz check VIEW [params]`: the readiness report.
- `ashare-cli viz build VIEW [params] --out FOLDER --formats html,svg,csv`.
- `topology`, `chart` and `panel-chart` stay, as aliases of `viz build`.

### B4.7 The desktop

A new group in the side panel, **Visualise** (可视化), between Analyse and Check, with six pages generated from the registry:
- Topology;
- Relational maps (关系图);
- Company views;
- Sectors and the market;
- Econometric charts;
- Data coverage (数据覆盖).

Each view's card shows its readiness (met, partly, missing, with the action to run) above its form. The scrollable side panel of v2.1.2 already accommodates the longer list.

## B5. The reference views built in v2.2

Three views, one of each snapshot shape, chosen because their data are already in the database:

1. **Data coverage** (series; family coverage).
   - A heatmap of companies with data by layer × sector × year, using CSRC sectors once imported and boards until then.
   - The confidence distribution, finding rates from the last checks, and panel balance (entries and exits, with reasons).
   - This is the figure a methods section needs, and it also guides what to collect next.
2. **Ego map** (graph; family relational).
   - One company at the centre, with its controller chain upward, subsidiaries downward, its top-10 holders, board members (pseudonymised), interlocked companies and regulators acting on it, as of a date.
   - It absorbs the control-chain, group-tree and interlock charts.
   - Parameters: depth (1 or 2 steps), relations shown, as-of date.
3. **Guidance against outcome** (series; family econometric).
   - Each earnings forecast's range against the profit later reported.
   - The distribution of the differences, by year and by forecast type (预增, 预减 and so on).
   - Evidential status: observed association. It tests the proxy the topology view relies on.

## B6. Definitions of the NVF proxies

Views that stand in for the paper's concepts read their definitions from `definitions.py`. Each definition is versioned (for example `ivt-0` for the transmission timeline, `fic-0` for the phase plot), and every snapshot records the version it used.

- **v2.2 defaults** are labelled "descriptive proxy, provisional".
  - Capability: R&D expense and capital expenditure, each over revenue.
  - Fundamentals: revenue and net profit attributable.
  - Expectations: management guidance.
  - Valuation: year-end market value.
  - Growth: year on year.
- When the paper's operational definitions are settled, they become version 1. Figures already made keep their version in their manifest, so a figure can always be traced to the definition behind it.

This answers the open question of waiting for the definitions or proceeding with proxies: the scaffolding proceeds, and nothing built on a proxy can be mistaken for the definitive measure.

## B7. Relational measures in the panels

`build-panel` gains optional relational variables, each dated by publication:
- `ctrl_distance` (steps to the ultimate controller);
- `ctrl_group` (group identifier, for fixed effects or clustering);
- `ctrl_type` (central SOE, local SOE, private, foreign, none);
- `holder_overlap_n` (companies sharing a top-10 holder);
- `mhhi_delta` (common ownership, by sector);
- `interlock_n` (boards sharing a director);
- `reg_actions_12m` (regulatory actions in the past twelve months).

The codebook entry of each states its source, its date rule and its limits:
- Top-10 truncation makes the ownership measures lower bounds.
- Network observations are not independent: use clustered or network-robust standard errors.

## B8. Cautions, and where each is shown

| Caution | Shown in |
|---|---|
| Top-10 tables list ten holders only | Ownership and common-ownership views; codebook |
| Names not resolved to entities | Coverage panel of each relational view; `UNRESOLVED` nodes |
| Natural persons are personal data | Pseudonyms by default; manifest |
| Proxies, not the paper's measures | Caption and manifest (definition version) |
| No causal reading | Caption (evidential status) of every view |
| Licensed data | Excluded unless included; manifest |

## B9. Phases

| Phase | Views | Needs |
|---|---|---|
| **v2.2 (this plan, with Part A)** | Scaffolding; reorganised section; data coverage, ego map, guidance against outcome | Data in hand |
| v2.3 | Market map (controllers as hubs), common-ownership map, sector-by-quarter heatmap, sector phase plot (`fic-0`) | The CSRC classification import (by the author); A2 (controller names); A3 (top-10 coverage) |
| v2.4 | Transmission timeline (`ivt-0`), valuation decomposition, event-study figures around policy events, the layered (multiplex) map with the as-of slider | Prices across exchanges; policy events (V3) |

Semiconductors (CSRC C39) remain the first worked episode in v2.3, as in the topology view.

## B10. Tests, and the check that nothing existing changes

- **The contract, for every registered view:**
  - its snapshot validates against its schema;
  - two builds with the same parameters are byte-identical;
  - a document published after the as-of date never enters it;
  - natural persons are pseudonymised by default;
  - licensed rows are excluded by default;
  - a view with missing data returns gaps with reasons, not an error.
- **Readiness:** each requirement reports met, partly met and missing correctly on a seeded database.
- **Relational model:**
  - as-of slicing;
  - projections;
  - each measure, on a small hand-built graph with known answers;
  - `UNRESOLVED` names are never merged.
- **Interference:**
  - The topology view gives the same nodes, edges and coverage under v2.2 as under v2.1.2 for the test database (compared as data).
  - `topology`, `chart` and `panel-chart` give the same files as before.
  - Existing panels without the new variables are byte-identical.
- **Desktop:** every registry view has a page, a form and a readiness note in both languages; the side panel scrolls to the new group.
- **Interactive pages:** open offline in a headless browser (as in v2.1), filters and slider work, and the 2D fallback appears without WebGL.
- **Scale:** a market map of 6,000 companies and their controllers builds in under a minute and opens in the browser. Above a set size, the page aggregates by group instead of drawing every node, and says so.
- **Matrix:** Python 3.12 and 3.13, PostgreSQL, and Windows Python under Wine, as for every release.

## B11. Interface terms to approve (glossary part 13, proposed)

| English | Chinese |
|---|---|
| Visualise (the group) | 可视化 |
| Relational maps | 关系图 |
| Ego map (one company at the centre) | 公司关系图 |
| Market map | 市场关系图 |
| Common ownership | 共同持股 |
| Board interlocks | 董事交叉任职 |
| Data coverage | 数据覆盖 |
| Readiness | 数据就绪情况 |
| Descriptive proxy | 描述性代理指标 |
| Publication figure | 出版用图 |

## B12. Decisions for the author (Part B)

1. **The first output.** Default: both interactive and publication outputs for the three reference views, since the renderers exist. Alternatively, publication figures first.
2. **The proxy definitions.** Default: proceed with labelled, versioned proxies (section B6), to be replaced by the paper's definitions.
3. **First case.** Default: the ego map first (case-study pictures), with the market map in v2.3 after the industry import and controller fix.
4. **Old locations.** Default: a pointer for one release, then removed.

# Part C: order, tests and release

## C1. Order of the build

1. **A2 and A4.** Controller names; download rates; stop message; ESG counts; short documents. None needs samples.
2. **A1, rules 1 and 2.** The balance-sheet repair across readings and by the statement's total.
3. **B4.** The scaffolding: registry, View contract, data layer, graph model, series snapshot, exports, CLI, the Visualise group in the desktop.
4. **B5.** The three reference views: data coverage, ego map, guidance against outcome. The ego map comes after A2, because it draws controller names.
5. **A1 rule 3 and A3**, when the author's samples arrive. If they arrive after the rest is ready, v2.2 is released without them, and they follow in v2.2.1.

## C2. Tests

- **Part A:** the tests listed under each fix.
- **Part B:** section B10.
- **Interference across the parts:**
  - The topology view built after the controller fix differs from v2.1.2 only where a controller's name changed. The difference is listed in the build record.
  - Panels without the new relational variables are byte-identical.
- **Matrix:** Python 3.12 and 3.13, PostgreSQL, Windows Python under Wine; the Windows build, with the command-line program run under Wine; GitHub's checks.

## C3. After installing v2.2

1. "Extract figures from reports" (financials-5) and "Read controlling shareholder and actual controller" (control-4): every report is read again.
2. "Check balance sheets": the round-number failures should fall; the rest are listed in `exports/balance_check.csv`.
3. "Companies with the same controller": the four garbled names should be gone.
4. **Visualise > Data coverage**, then **Relational maps > Ego map** for a company with reports read (for example 000009 or 000021).

## C4. Release

- **Documents.** Version 2.2.0, with the CHANGELOG, `docs/live_run_findings_v2.1.2.md` (findings 132 to 139), the user guide (the Visualise section) and the build plan.
- **Chinese interface.** The glossary part 13 terms (section B11).
- **Commit.** In the author's name only.

# Build record (v2.2.0, 4 November 2026)

Built with the defaults of section B12: interactive and publication outputs for the three reference views; labelled, versioned proxies (`nvf-0`); the ego map first; a pointer at each old location for one release.

**Built as planned.**
- A1 rules 1 and 2 (financials-5), A2 (control-4), A4.1 to A4.4.
- The scaffolding of B4: `ashare/viz/view.py`, `registry.py`, `definitions.py`, `data.py`, `graph.py` (schema version 2), `series.py`, `schema.py`, `publish.py`, `pages.py`, and the viewer pages `relmap.html` and `chart.html`.
- The three views of B5: the ego map, data coverage and guidance against outcome, each with its readiness checks.
- The Visualise group in the desktop, with a readiness note on each view's page, and the terms of B11 in Chinese (glossary part 13).

**Differences from the plan.**
- **Commands.** Each view has its own command (`viz-ego-map`, `viz-coverage`, `viz-guidance-outcome`) with typed options, in place of one `viz build VIEW`; `viz-list` and `viz-check VIEW` are as planned. The topology view keeps its command (`topology`).
- **Panel variables (B7).** `ctrl_group`, `ctrl_distance` and `reg_actions_12m` are built. `ctrl_type` exists already as `ownership_type`. `holder_overlap_n`, `mhhi_delta` and `interlock_n` follow with the common-ownership and market maps in v2.3, which compute them.
- **Steps to the ultimate controller.** The ego map counts them on the control chain where one reaching the company was read, and otherwise counts the direct controller link as one step. The same rule gives `ctrl_distance`, which uses the longest path in the chain.
- **Not built, waiting on the author's samples (v2.2.1).** A1 rule 3 (rejoining a lone digit at the source) and A3 (the quarterly top-10 layout).
- **Scale test of B10.** It belongs with the market map (v2.3); the ego map draws at most 40 subsidiaries and 60 second-ring companies.

**Interference.**
- The topology view's code, snapshot (schema version 1) and viewer are unchanged; it is registered in the Visualise group only.
- The new panel variables are not among the defaults, so panels built without them are unchanged.
- "Export a chart", "Price chart with events" and the dataset explorer keep their commands; only their place in the side panel changed.

**Tests.** `tests/test_v22.py` (31 tests): the Part A fixes; the ego map on a seeded database (each relation; a controller published after the date left out; persons pseudonymised; `UNRESOLVED` holders; depth 2 through a shared holder and a shared director; determinism; the relation filter); the files and manifest a view writes; coverage as of two dates; guidance paired only with the later periodic report; the registry, `viz-list`, `viz-check` and `viz-ego-map`; the relational panel variables; both interactive pages in a headless browser with no console errors; and the Visualise pages of the desktop.

**Matrix.** Linux Python 3.12: 458 passed, 1 skipped (DuckDB not installed). Python 3.13: 430 passed, 28 skipped (no Tk or browser tests). PostgreSQL 16: 455 passed, 4 skipped. Windows CPython 3.12 under Wine: 452 passed, 7 skipped. The Windows build's command-line program lists the views and writes a coverage view under Wine.
