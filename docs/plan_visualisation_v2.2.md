# Plan for v2.2: the scaffolding of the visualisation section

## 1. Purpose and scope

v2.2 gathers every chart and map the program draws under one heading, **Visualise** (可视化), and builds the scaffolding on which further views can be added without re-engineering each one. It is a framework release: it moves what exists, sets the contract every view follows, and proves the contract with three reference views. The views of later phases (sector, NVF and relational views at market scale) are specified here, so that the scaffolding fits them, but built only when their data are in place (section 9).

The topology view (v2.1) is the model: a view is described as data (a *snapshot*), every item carries its provenance, gaps are shown and not filled, and the same snapshot can be drawn interactively or written as files. v2.2 generalises that pattern from one view to many.

Out of scope: the v2.1.3 fixes (balance-sheet repair, top-10 coverage, controller names). Section 9 notes which views depend on them.

## 2. Principles (carried over from the v2.1 plan, section 7.1)

1. **Point in time.** Every view is built "as published by" a date. Nothing published later enters it.
2. **Provenance.** Every plotted value and every link names its source: document and page, classification, price feed or import, with method and confidence.
3. **Gaps are shown.** Missing data appear as gaps with the reason (the v2.1.2 gap messages), never interpolated or silently dropped.
4. **No causal language.** A line, a link or a sequence is a documented fact or an association, not evidence of cause. Each view states its evidential status (as the topology view does).
5. **Persons and licences.** Natural persons are pseudonymised by default with the release key. Licensed data are left out unless included explicitly, and the manifest says which.
6. **Determinism.** The same parameters and the same database give the same snapshot, byte for byte.
7. **Offline and bilingual.** Interactive pages work from disk with no network. Interface text follows the glossary; data, variable names and files stay in English.
8. **Proxies are labelled.** Where a view stands in for a concept of the paper (Institutional Visibility, the Fractal Investment Clock), it says that it is a descriptive proxy, and which definition it uses (section 6).

## 3. What exists and where it goes

| Today | Where | v2.2 place |
|---|---|---|
| Topology view (`topology`) | Analyse > Topology | Visualise > Topology |
| Company charts: financials, segment mix, segment history, workforce, prices, findings (`chart`) | Datasets > Export a chart; Company pages | Visualise > Company views |
| Control chain, group tree, board interlocks (`chart`) | As above | Visualise > Relational maps (the ego map absorbs them) |
| Industry distribution, peer scatter (`chart`) | As above | Visualise > Sectors and the market |
| Panel explorer: histogram, box plot, scatter, coverage, summary (`panel-chart`) | Datasets | Visualise > Econometric charts |
| Event study (`event-study`) | Analyse | Stays under Analyse (it computes); its figure is drawn under Visualise > Econometric charts |

The commands keep their names, so `run_log.txt` and existing scripts still work. Each old page keeps a one-line pointer to the new place for one release.

## 4. Architecture

### 4.1 Package layout

```
ashare/viz/
    registry.py      the list of views; the GUI pages and the CLI are generated from it
    view.py          the View contract (4.2) and the readiness check
    data.py          point-in-time accessors shared by all views (as-of filtering, provenance rows)
    graph.py         the relational model (4.4): nodes, edges, projections, measures
    definitions.py   versioned definitions of the NVF proxies (section 6)
    snapshot.py      the topology snapshot (unchanged in behaviour; reused by the graph views)
    series.py        the series snapshot (4.3) for chart views
    export.py        files and manifest for both snapshot kinds (generalised from v2.1)
    figure.py        publication figures (4.5)
    views/           one module per view: topology, ego_map, coverage, guidance_outcome, ...
    viewer/          the interactive page shell: graph mode (from the Topology Tester) and chart mode
```

`ashare/charts/` stays as the drawing layer (SVG and Tk renderers); views produce chart specifications for it.

### 4.2 The View contract

Every view is one class registered in `registry.py`:

| Member | Meaning |
|---|---|
| `id`, `family` | e.g. `ego_map`, family `relational` (families: topology, company, relational, sector, econometric, coverage) |
| `title`, `intro` | Interface text, through the translation catalogue |
| `params` | The fields the view takes (codes or industry, span, as-of, options), declared once. The GUI form and the CLI options are generated from them. |
| `requires` | The data the view needs, as checks (e.g. "industry classification imported", "prices for the span") |
| `readiness(params)` | For each requirement: met, partly met (with counts), or missing, with the action that fills it. The GUI shows this before Run. |
| `build(params)` | Returns a snapshot (graph or series), with coverage and gap notes |
| `outputs` | Which of the outputs in 4.5 it supports |
| `evidence` | Its evidential status, for the caption: documented fact, observed association, descriptive proxy |

A view never queries the database except through `data.py`, which applies the as-of date, pseudonymisation and licence rules in one place. This is what keeps principles 1 and 5 true for views written later.

### 4.3 Two kinds of snapshot

- **Graph snapshot**: nodes and edges, as in the topology view.
  - The schema goes to version 2, which adds the node kinds of the relational maps (entity, person, authority, sector, group) and their relations (4.4).
  - Version 1 snapshots stay readable, and a topology view built with v2.2 produces the same nodes and edges as with v2.1 (tested; section 10).
- **Series snapshot**: rows for charts, each with its provenance columns (the `observations.csv` columns of v2.1), plus axes, units and gap notes.

Both are written as JSON with a JSON Schema, a CSV of exactly what is plotted, and a manifest. The manifest records the parameters, the database fingerprint, the software version, the definition version (section 6) and a SHA-256 for every file.

### 4.4 The relational model (`graph.py`)

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
- **Panel variables.** The measures become dated variables in `build-panel`, with codebook entries, so that they can enter regressions (section 7).

### 4.5 Outputs

| Output | For | How |
|---|---|---|
| In the window | Looking | Tk renderer of `charts` (existing) |
| Interactive page | Exploring, sharing | One offline HTML file. Graph mode is the Topology Tester shell, generalised to the v2 schema (filters by relation, as-of slider, inspector). Chart mode uses the bundled Chart.js. |
| Publication figure | Papers | SVG from the `charts` renderer in a journal style: single column (85 mm) or full width (175 mm), greyscale-safe markers and line styles, a caption with the evidential status, source and as-of date. A print-ready HTML page gives a PDF through the browser's print dialogue. PNG and PDF directly when matplotlib is installed (source installations; it is not in the Windows build). |
| Data | Re-drawing in Stata or R | The snapshot's CSV, and a labelled Stata file (`.dta`), written as panels are |

### 4.6 Command line

- `ashare-cli viz list`: the views, their families and whether their data are ready.
- `ashare-cli viz check VIEW [params]`: the readiness report.
- `ashare-cli viz build VIEW [params] --out FOLDER --formats html,svg,csv`.
- `topology`, `chart` and `panel-chart` stay, as aliases of `viz build`.

### 4.7 The desktop

A new group in the side panel, **Visualise** (可视化), between Analyse and Check, with six pages generated from the registry:
- Topology;
- Relational maps (关系图);
- Company views;
- Sectors and the market;
- Econometric charts;
- Data coverage (数据覆盖).

Each view's card shows its readiness (met, partly, missing, with the action to run) above its form. The scrollable side panel of v2.1.2 already accommodates the longer list.

## 5. The reference views built in v2.2

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

## 6. Definitions of the NVF proxies

Views that stand in for the paper's concepts read their definitions from `definitions.py`. Each definition is versioned (for example `ivt-0` for the transmission timeline, `fic-0` for the phase plot), and every snapshot records the version it used.

- **v2.2 defaults** are labelled "descriptive proxy, provisional".
  - Capability: R&D expense and capital expenditure, each over revenue.
  - Fundamentals: revenue and net profit attributable.
  - Expectations: management guidance.
  - Valuation: year-end market value.
  - Growth: year on year.
- When the paper's operational definitions are settled, they become version 1. Figures already made keep their version in their manifest, so a figure can always be traced to the definition behind it.

This answers the open question of waiting for the definitions or proceeding with proxies: the scaffolding proceeds, and nothing built on a proxy can be mistaken for the definitive measure.

## 7. Relational measures in the panels

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

## 8. Cautions, and where each is shown

| Caution | Shown in |
|---|---|
| Top-10 tables list ten holders only | Ownership and common-ownership views; codebook |
| Names not resolved to entities | Coverage panel of each relational view; `UNRESOLVED` nodes |
| Natural persons are personal data | Pseudonyms by default; manifest |
| Proxies, not the paper's measures | Caption and manifest (definition version) |
| No causal reading | Caption (evidential status) of every view |
| Licensed data | Excluded unless included; manifest |

## 9. Phases

| Phase | Views | Needs |
|---|---|---|
| **v2.2 (this plan)** | Scaffolding; reorganised section; data coverage, ego map, guidance against outcome | Data in hand |
| v2.3 | Market map (controllers as hubs), common-ownership map, sector-by-quarter heatmap, sector phase plot (`fic-0`) | The CSRC classification import; the v2.1.3 controller fix; better top-10 coverage (finding 131) |
| v2.4 | Transmission timeline (`ivt-0`), valuation decomposition, event-study figures around policy events, the layered (multiplex) map with the as-of slider | Prices across exchanges; policy events (V3) |

Semiconductors (CSRC C39) remain the first worked episode in v2.3, as in the topology view.

## 10. Tests, and the check that nothing existing changes

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

## 11. Interface terms to approve (glossary part 13, proposed)

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

## 12. Decisions for the author

1. **The first output.** Default: both interactive and publication outputs for the three reference views, since the renderers exist. Alternatively, publication figures first.
2. **The proxy definitions.** Default: proceed with labelled, versioned proxies (section 6), to be replaced by the paper's definitions.
3. **First case.** Default: the ego map first (case-study pictures), with the market map in v2.3 after the industry import and controller fix.
4. **Old locations.** Default: a pointer for one release, then removed.
