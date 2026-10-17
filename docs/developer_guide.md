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
| Distribution | `release.py`, `licences.py`, `quality.py`, `update.py` |
| Interfaces | `cli.py` (typer), `gui.py` and `gui_review.py` (Tkinter) |

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

The `db` fixture gives each test its own database and folders; with `ASHARE_TEST_DB_URL` it recreates the PostgreSQL schema instead. Network access in tests goes through `httpx.MockTransport`, installed with `ashare.http.set_default_transport`. PDFs for tests are made with reportlab (`tests/helpers.make_pdf`). Live-source checks are not part of the suite: they are the self-test, run by the user.

## 7. Building the Windows programs

On Windows with Python 3.10 to 3.13, run `build_windows.bat`. It creates a build environment, runs the tests, builds both executables with PyInstaller (`packaging/ashare.spec`), builds the documentation (`packaging/build_docs.py`), signs the executables if a certificate is configured (`packaging/sign.bat`), builds the installer with NSIS if it is installed (`packaging/installer.nsi`), and writes a portable zip.

- **Signing.** Set `ASHARE_SIGN_CERT` (a `.pfx` file) and, if needed, `ASHARE_SIGN_PASSWORD`, or set `ASHARE_SIGN_COMMAND` for a hardware token or cloud signing service. Without these the build continues unsigned. On Linux, `packaging/sign.sh` does the same with osslsigncode.
- **Installer.** `makensis /DVERSION=2.0.2 packaging\installer.nsi`. The installer is per-user and includes both programs and the documentation.
- **Documentation.** `python packaging/build_docs.py --codebook` regenerates `docs/codebook.md` from the variable registry and converts every `docs/*.md` to HTML.
- **Update check.** Publish a JSON file (`{"version", "url", "sha256", "notes"}`) at an HTTPS address and give users that address; the program never contacts it unless configured.

PyInstaller does not cross-compile: build the Windows programs on Windows (a Wine environment also works for testing). `build_unix.sh` builds a native binary for macOS or Linux.

## 8. Releasing a new version

1. Raise `__version__` in `ashare/__init__.py`, the user agent in `config.py` and the first line of `packaging/READ_ME_FIRST.txt`.
2. Add a migration if the schema changed, and a test.
3. Update `README.md`, the build plan's status and `CITATION.cff`.
4. Run the tests on SQLite and PostgreSQL, and the offline self-test.
5. Build, sign, and publish the installer, its SHA-256 hash and the update JSON.
