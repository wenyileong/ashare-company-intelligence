# Developer guide

This guide is for those who extend or maintain A-share Company Intelligence: adding a parser, adding a source, changing the schema, testing and building releases. Section 2 of `ashare_scraper_build_plan.md` gives the architecture in more detail.

## 1. Layout of the code

| Area | Modules |
|---|---|
| Storage and schema | `models.py` (SQLAlchemy models, engine, `init_db`), `migrate.py` and `migrations/` (Alembic) |
| Acquisition | `http.py` (rate-limited client), `sources/` (adapters), `disclosures.py`, `market.py`, `pipeline.py`, `ops.py` (jobs, daily update) |
| Extraction | `parsers/` (registry, dual running), `layout.py` (table rows from character positions), one module per content type (`financials.py`, `cas.py`, `control.py`, `segments.py`, `group.py`, `management.py`, `transactions.py` and others) |
| Checking | `crossvalidation.py`, `validation.py`, `reconciliation.py`, `review.py`, `evaluation.py` (corpus scoring and calibration), `selftest.py` |
| Research outputs | `panel.py`, `stata.py`, `eventstudy.py`, `valuation.py`, `derived.py`, `security_master.py`, `charts/`, `report.py`, `research.py` |
| Visualisation (v2.1) | `nvf/layers.py` (variables to NVF layers), `viz/snapshot.py` (build and rules), `viz/schema.py`, `viz/export.py`, `viz/viewer.py` and `viz/viewer/` (the offline page and its bundled libraries), `charts/layers.py`, `expectations.py` |
| Distribution | `release.py`, `licences.py`, `quality.py`, `update.py` |
| Interfaces | `cli.py` (typer), `gui.py` and `gui_review.py` (Tkinter), `i18n/` (interface language, v2.1) |
| Speed (v2.1) | `reportreader.py` (section pages), `parallel.py` (worker processes), `extractstate.py` (progress and resume) |

The desktop application runs every action through the command line in the same process (`gui.run_command`), so each action has a command and the run log records it. A new feature therefore needs a command first, and a form in `gui.SECTIONS` second; `tests/test_gui_helpers.py` checks that every form option exists on its command.

## 2. Principles to keep

- **Source before inference.** Store the response or document as received, with its URL, time and hash, before deriving anything from it.
- **Evidence before normalisation.** Keep the raw value, page and method beside the normalised value.
- **Time before snapshots.** Record publication dates; never let a later value replace an earlier one.
- **Conflicts before overwrites.** Validation adds flags; review adds corrections in `manual_corrections`. Neither edits the observation.
- **Politeness.** All network access goes through `RateLimitedClient`, at one request per second by default. Never bypass authentication, CAPTCHAs, access controls or rate limits.

## 3. Adding a parser

1. Write a function that takes the document's pages (a list of strings, one per page) and a metadata dictionary (`title`, `announcement_date`, `fallback_period`) and returns a list of records (dictionaries).
2. Register it:

```python
from ashare.parsers import ParserSpec, register

register(ParserSpec(
    name="audit_fees",                 # family name; a layout variant would be "audit_fees@layout"
    run=_run_audit_fees,
    key=("auditor",),                  # fields that identify one record
    fields=("fee", "currency"),        # fields scored by the evaluation harness
    method="PDF_TEXT_HEURISTIC",
    description="Auditor and audit fee",
    doc_kinds=("annual_report",),
    prior=0.55,                        # confidence until calibrated
))
```

3. For a table, add the family name to `TABLE_FAMILIES`: a layout variant is then registered automatically, runs on rows rebuilt by `layout.layout_text_pages`, and the extractor can use `dual_run(family, path, meta)` (the PDF path; text pages can be passed in), which picks the better-calibrated variant and records agreement.
4. Store the records with full provenance (source document, page, raw value, method, confidence from `record_confidence`) and add any validation rule to `crossvalidation.py`.
5. Add documents to a golden corpus (`ashare-cli corpus-template --corpus CORPUS --document FILE`), verify the expected values by hand, set `"verified": true`, and evaluate (`ashare-cli evaluate-parsers --corpus CORPUS --calibrate`). With 30 or more scored values, calibration replaces the prior.
6. If the parser changes behaviour, raise `PARSER_VERSION`. Calibration stored for an older version is then ignored until the corpus is re-evaluated.
7. Extend the synthetic corpus generator (`corpus.py`) and regenerate the regression baseline:

```
ashare-cli synthetic-corpus --out build/synth
ashare-cli evaluate-parsers --corpus build/synth --write-baseline packaging/parser_baseline.json
```

The test suite fails if precision on the synthetic corpus falls by more than one percentage point against the baseline.

### Reading only the pages a parser needs (v2.0.8)

A table extractor reads a report through `ashare.reportreader.ReportReader`. Pass `reader=` and `sections=` to `parsers.dual_run`. The reader finds the sections' pages with pdfium's page text, and gives the parser pages of the document's full length, blank outside the sections, so page numbers stay right. A new extractor should name its section (heading patterns, and how many pages after the heading belong to it) in `SECTIONS`. It should run through `extractstate.run`, which counts the documents, reports progress and records each document read in `extraction_state`. `tests/test_v208.py::test_targeted_reading_matches_full_reading_on_the_synthetic_corpus` checks that targeted and full readings agree.

### Reading in worker processes (v2.1)

`extractstate.run(..., parse="module:function")` reads documents in worker processes (`ashare.parallel.imap`). The parse function takes `(job, reader)` and returns what the handler needs; it must be importable by name, touch no database and print nothing (the Windows desktop program has no standard output). The handler, in the main process, writes the result and returns the outcome; results arrive in the documents' order. A test that patches a parse function must set `ASHARE_WORKERS=1`, because a patch does not reach a spawned worker.

## 4. Adding a source

1. Write an adapter in `sources/` that uses `RateLimitedClient` (never `httpx` directly), so that pacing, retries and offline test transports apply.
2. Store raw responses in `raw_records` (or documents in the documents folder) with their hash before parsing them.
3. Give stored rows a `source` label. If the label does not start with a prefix known to `licences.py` (CNINFO, SSE, SZSE, BSE, EASTMONEY and the others listed in `_RULES`), add a rule, or the rows will be classed LICENSED and left out of releases.
4. Add a check to `selftest.py` and a canned response to `fixture_handler`, so that the offline self-test covers it and the live self-test reports when the source changes.
5. Add the source to section 1 of the methods document.

## 5. Changing the schema

The schema is versioned with Alembic. After changing a model:

1. Create a revision in `ashare/migrations/versions/`, named `NNNN_short_description.py`, with `down_revision` set to the current head (`ashare-cli db-status` shows it). The template `ashare/migrations/script.py.mako` gives the layout; with Alembic installed you can also run `alembic -c <config> revision`, but a hand-written file is simplest.
2. Use the idempotent helpers, because a database created from the current models may already have the change:

```python
from alembic import op
from ashare.migrate import add_column_if_missing, create_index_if_missing

revision = "0003_audit_fees"
down_revision = "0002_v20_licences"

def upgrade() -> None:
    conn = op.get_bind()
    add_column_if_missing(conn, "financial_facts", "auditor", "VARCHAR(200)")
    create_index_if_missing(conn, "ix_financial_facts_auditor", "financial_facts", "auditor")
```

3. A new table needs `Base.metadata.tables["name"].create(conn, checkfirst=True)` in the revision.
4. For changes SQLite cannot make in place (dropping or retyping a column), use `op.batch_alter_table`.
5. Add a test that upgrades the stored old-schema fixtures (`tests/fixtures/schema_v07.sql`, `schema_v13.sql`, `schema_v19.sql`) and checks the new column. `init_db` upgrades databases automatically and writes a backup copy of a SQLite file first.

## 6. Tests

```
python -m pytest -q                       # the whole suite, offline
ASHARE_TEST_DB_URL=postgresql+psycopg://user:pass@localhost/test python -m pytest -q   # against PostgreSQL
```

The `db` fixture gives each test its own database and folders; with `ASHARE_TEST_DB_URL` it recreates the PostgreSQL schema instead. Network access in tests goes through `httpx.MockTransport`, installed with `ashare.http.set_default_transport`. PDFs for tests are made with reportlab (`tests/helpers.make_pdf`). Live-source checks are not part of the suite: they are the self-test, run on a networked machine.

### Interface text (v2.1)

Every text the desktop shows is written in English where it is used, with a stable key:
- the pages, actions and fields of `gui.SECTIONS` take their keys from their identifiers (`section.<id>.title`, `action.<page>.<command>.label`, `….field.<key>.hint`);
- any other text is `tr("ui.<name>", "English text")`, with literal strings (use `.format()` on the result for values).

After changing or adding text, run `python packaging/i18n_catalogue.py`. It rewrites `ashare/i18n/en.json` from the code and `zh_CN.json` from `packaging/i18n/zh_CN_source.json`, and `--todo` lists texts that have no Chinese yet. Add their renderings to the source file under the glossary (`docs/glossary_zh_CN.md`), adding new terms to its part 11 for review. The tests fail if `en.json` differs from the code, a key lacks Chinese, a translation is stale, placeholders differ, a glossary term is rendered otherwise, or a casual term is used.

Command output stays English and must never depend on the language, nor may any file a command writes.

## 7. Building the Windows programs

On Windows with Python 3.10 to 3.13, run `build_windows.bat`. It creates a build environment, runs the tests, builds both executables with PyInstaller (`packaging/ashare.spec`), builds the documentation (`packaging/build_docs.py`), signs the executables if a certificate is configured (`packaging/sign.bat`), builds the installer with NSIS if it is installed (`packaging/installer.nsi`), and writes a portable zip.

- **Signing.** Set `ASHARE_SIGN_CERT` (a `.pfx` file) and, if needed, `ASHARE_SIGN_PASSWORD`, or set `ASHARE_SIGN_COMMAND` for a hardware token or cloud signing service. Without these the build continues unsigned. On Linux, `packaging/sign.sh` does the same with osslsigncode.
- **Installer.** `makensis /DVERSION=X.Y.Z packaging\installer.nsi`, with the version being built. The installer is per-user and includes both programs and the documentation.
- **Documentation.** `python packaging/build_docs.py --codebook` regenerates `docs/codebook.md` from the variable registry and converts every `docs/*.md` to HTML.
- **Update check.** Publish a JSON file (`{"version", "url", "sha256", "notes"}`) at an HTTPS address and give users that address; the program never contacts it unless configured.

PyInstaller does not cross-compile: build the Windows programs on Windows (a Wine environment also works for testing). `build_unix.sh` builds a native binary for macOS or Linux.

## 8. Releasing a new version

1. Raise `__version__` in `ashare/__init__.py` (the default user agent follows it), the version in `packaging/installer.nsi` and the first line of `packaging/READ_ME_FIRST.txt`.
2. Add a migration if the schema changed, and a test.
3. If the financial extraction changed, raise `EXTRACTOR_VERSION` in `ashare/financials.py` (v2.0.6), so that documents read by the earlier version are read again; otherwise a rerun skips them. For the table extractors (top-10 holders, control, segments, R&D and workforce, subsidiaries, roster), raise their entry in `VERSIONS` in `ashare/extractstate.py` (v2.0.8). If you add a section to `SECTIONS` in `ashare/reportreader.py`, raise `INDEX_VERSION` there, so that the cached section indexes are rebuilt.
4. Update `README.md`, `CHANGELOG.md`, the build plan's status and `CITATION.cff`, and run `packaging/i18n_catalogue.py` if any interface text changed.
5. Run the tests on SQLite and PostgreSQL, and the offline self-test.
6. Build and sign the installer and the portable zips, and write `SHA256SUMS.txt` for the downloads.
7. Create the GitHub release for the tag `vX.Y.Z`, attach the downloads, `LICENSE.md`, `THIRD_PARTY_NOTICES.txt` and `SHA256SUMS.txt`, and publish the update JSON if one is used.
