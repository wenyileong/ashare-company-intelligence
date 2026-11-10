# Plan for v2.4.0 (11 November 2026)

## Scope

v2.4.0 builds what is available without the author's samples or a live run of v2.3.0:

1. **Swappable rule packs** (the author's instruction of 11 November 2026). The legal rules the program applies are kept as packs that can be updated without a new version of the program. Each pack and each rule is marked with its status. The packs are:
   - the share-dealing rules;
   - the disclosure deadlines;
   - the list of nominee accounts.
2. **Share-dealing flags on the provisional rules.** The current rules are applied, and every flag they raise is marked *provisional* until the author confirms the rule. This also adds:
   - the third rule (a sale without an earlier announced plan);
   - the two panel variables that waited on the rules.
3. **R3, a percentage progress bar** (`docs/requirements_next_build.md`) whenever the program fetches or reads data.
4. **Two loose ends from v2.3.0:**
   - GLEIF parent companies drawn as their own relation on the ego map;
   - the readiness check for regulatory events counting only the events published by the view's date.

**Not in this build:**
- the fixes from a live run of v2.3.0 (none reported yet);
- findings 134 and 132 rule 3 (they wait on the `inspect-tables` samples);
- email and Windows notifications, trusted timestamps and the Windows taskbar progress (each waits on a review of a new library, review V11 of the v2.3 plan).

## Review of this plan against the code (11 November 2026)

| # | Finding | Response |
|---|---|---|
| W1 | **Where the rules are read.** Three modules read the rule files directly from the program folder (`insider.py`, `timeliness.py`, `network_measures.py`), each with its own `lru_cache`, so an updated file is not seen until the program restarts. | One loader (`rulepacks.py`) for all three. Its cache is keyed by the file's modification time, so an imported pack applies from the next action. |
| W2 | **The program folder is not writable.** An installed program cannot be updated in place: Program Files is read-only, and a reinstall would overwrite an edited file. | Updated packs live in the data folder (`rules/`), beside `features.json`. The bundled pack is the fallback and is never edited. |
| W3 | **A bad pack.** A malformed or mistyped pack must not stop the program, and must not be applied silently. | Every pack is validated on import and on load. An override that fails is not used. The bundled pack is used instead, and Diagnostics and every result that relies on the pack say so. |
| W4 | **What 'verified' means.** In v2.3 a rule's `verified` field does two jobs: it says how the rule was checked, and it decides whether the rule is applied. The deadline rules are applied with a note that the author must confirm them. The share-dealing rules are not applied at all. | Each rule gets one explicit `status`: `provisional` (applied; every result marked provisional) or `confirmed` (applied as it is). `verified` becomes a free-text record of the check. A rule can also be withdrawn (`withdrawn`), so that it is not applied. Results stay comparable across versions because each records the pack version it used. |
| W5 | **Provisional flags in outputs.** A provisional flag must not read as a finding. | Each flag carries "(provisional rule)", the note names the unconfirmed rules, and the panel variables' codebook entries say which pack and status produced them. "A flag is a fact to examine, not a finding of breach" stays. |
| W6 | **Progress through the desktop program.** The progress lines are ordinary text in the Output pane, so the desktop program cannot read a percentage from them. | The desktop program runs commands in its own process (`run_command`), so the counter passes its numbers straight to the desktop program, which drives a determinate bar. Nothing is added to the Output pane or the run log. A terminal gets a bar redrawn on one line. Another program can ask for machine-readable lines (`ASHARE_PROGRESS=machine`). Output to a file is unchanged. |
| W7 | **Actions that do not count their work.** Some long actions count nothing before they start (the catalogue pages, the market download by day). | Each is given a counter. Where the total is unknown, the bar is indeterminate ("counting…") until it is known. |
| W8 | **Interference.** New rule-pack code sits under three v2.3 features, and the progress protocol under every long action. | The rule loader returns exactly the bundled data when no override exists (a test compares them). Progress numbers reach the desktop program directly, and machine-readable lines are written only when asked for (`ASHARE_PROGRESS=machine`), so command-line output and logs are unchanged. Two new switches: `rules.overrides` and `progress.bar`. |

## Scaffolding first

1. **Switches.** `rules.overrides` (on) and `progress.bar` (on). Off means the bundled packs only, and the indeterminate bar of v2.3.
2. **The rule-pack loader,** with validation and status, returning the bundled data unchanged. The three modules read through it.
3. **The pack commands.** `rules-list`, `rules-show`, `rules-export`, `rules-check`, `rules-import` and `rules-reset`. Importing always validates first, keeps the replaced pack, and records the change.
4. **The progress protocol:** the writer in `extractstate.Progress` and the reader in the desktop program, before any action is given a counter.
5. **Then the features:** the flags, the panel variables, the counters, the GLEIF relation and the readiness check.

## Part A. Swappable rule packs

### The packs

| Pack | File | Used by |
|---|---|---|
| `insider` | `insider_rules.json` | share-dealing flags and panel variables |
| `deadlines` | `disclosure_deadlines.json` | timeliness, its panel variables and views |
| `nominees` | `nominee_holders.json` | ownership network measures |

**What each pack carries.**
- `pack`, `version` and `schema` (1).
- `swappable: true`.
- `status`: `provisional` or `confirmed`, the lowest status of its rules.
- `updated`, and a note saying how to update the pack.

**What each rule carries.**
- `status` and `verified` (how it was checked);
- `source`, with its article, and `effective_from` / `effective_to`.

### Updating a pack

- **Export.** `rules-export insider` copies the pack in use to `rules/insider_rules.json` in the data folder, for editing.
- **Check.** `rules-check insider` validates the pack in use, or a file.
- **Import.** `rules-import insider FILE` validates and installs a file. The pack it replaces is kept in `rules/_replaced/` with a timestamp.
- **Reset.** `rules-reset insider` returns to the bundled pack, also keeping the replaced pack.
- **Desktop.** All of these are under **Check > Rules**.

### Validation

**What every rule must have.**
- an id the code knows;
- whole positive numbers of days or months;
- dates in ISO form;
- a status of provisional, confirmed or withdrawn;
- a source.

**Unknown fields** are kept, and listed as warnings.

**When validation fails,** the override is not used. The bundled pack is used, and:
- Diagnostics shows the error;
- every result from that pack says that the bundled pack was used and why.

## Part B. Share-dealing flags

1. **Which rules are applied.** The `provisional` and `confirmed` rules. Each flag names its rule and, when the rule is provisional, says so. `--confirmed-only` applies only the confirmed rules.
2. **Rule 3, a sale without an announced plan.** For each sale by auction, the program looks for an announcement of a reduction plan by the same company, found by title, published at least the rule's number of trading days before the sale. When there is none, the sale is flagged. Without the trading calendar, no flag is raised and the note says why. A sale whose method is unknown counts as an auction sale, and this is marked on the flag.
3. **Panel variables.** Group "insider"; both use the dealings published by the row's date:
   - `insider_net_buy_12m`: shares bought less shares sold in the twelve months to the row's date;
   - `insider_window_sales_12m`: sales within a blackout window in the same twelve months.

   Their confidence is LOW (experimental reader; provisional rules), and they are blank when the insider switch is off.

## Part C. R3, the progress bar

1. **The protocol.**
   - **The desktop program** runs each command in its own process, so it receives the numbers directly: it installs a receiver for the length of the action.
   - **Another program** can set `ASHARE_PROGRESS=machine` and read lines of the form `@@ashare-progress {"stage":…,"stages":…,"done":…,"total":…,"unit":…,"bytes":…,"bytes_total":…,"left":…}`.
   - Reports are sent at most four times a second, and always on the first and last item.
2. **The desktop program.**
   - It hides these lines from the Output pane and drives a determinate bar in the status bar, with the percentage, "done of total unit", the stage and the time left.
   - With no total, or before the first line arrives, the bar is indeterminate and says "counting…".
   - It resets when the action ends, fails or is stopped.
3. **The terminal.** When the output is a terminal (and `ASHARE_PROGRESS` is not `off`), the command line redraws one line with a text bar.
4. **The time left** is smoothed: the mean over the last 50 items, weighted with the mean over the whole run.
5. **Resume.** `Progress(start=n)` begins the bar at the items already done.
6. **Counters for every long action:**
   - catalogue (by page, with the total from the first page);
   - document downloads;
   - each extractor (already counted);
   - financials;
   - market download (by company, already counted);
   - the daily update (by stage);
   - GLEIF matching;
   - building a panel (by company);
   - writing a release (by table);
   - copying the data folder (by bytes).

## Part D. Loose ends

1. **GLEIF parents.** When the `gleif` switch is on and a parent was recorded, the ego map adds a node for the direct and ultimate parents, with a "GLEIF parent" relation. The relation is labelled with GLEIF as source and the record's date.
2. **Regulatory readiness by date.** The readiness check for regulatory events counts only events published by the view's date. The view's own result is unchanged.

## Part E. Tests and release

- `tests/test_v24.py`:
  - **The loader:**
    - with no override, it returns the bundled data;
    - an override is applied and seen without a restart;
    - an invalid override falls back with a message;
    - import keeps the replaced pack, and reset restores the bundled one.
  - **The flags:** provisional and confirmed rules; withdrawn rules skipped; `--confirmed-only`; rule 3 with and without the calendar.
  - **The panel variables.**
  - **The progress protocol:**
    - the writer's rate, and its first and last lines;
    - unknown and growing totals;
    - terminal versus file;
    - the desktop program's parser and bar with a fake command;
    - resume.
  - **The GLEIF relation.**
  - **Readiness by date.**
- **Every switch off:** the earlier suite passes unchanged.
- **Other environments:**
  - Python 3.13, PostgreSQL;
  - the Windows build and tests on GitHub;
  - a smoke test of the packaged program under Wine.
- **Release outputs:** the installer, the portable zip and the command-line add-on, with checksums. Also the installer inside a zip, because the chat does not deliver `.exe` files.

# Build record (v2.4.0, 11 November 2026)

Built scaffolding first, as planned:
1. the two switches;
2. the rule-pack loader, returning the bundled data unchanged;
3. the pack commands;
4. the progress protocol;
5. then the features.

No migration was needed: no table changed.

**Built as planned.**
- Part A: the three packs marked as swappable; validation, import, export, check and reset; the change log; Check > Rules; the packs in Diagnostics.
- Part B: provisional and confirmed flags; `--confirmed-only`; rule 3; effective dates; both panel variables.
- Part C: the determinate bar, stages, the job bar with the action within it, resume, the terminal bar and machine-readable lines.
- Part D: GLEIF parents on the ego map; regulatory readiness by date.

**Differences from the plan, and why.**
- **Part C, the protocol.** The plan had the desktop program read progress lines from the command's output. It runs commands in its own process, so the counter passes its numbers straight to it, and nothing is added to the Output pane or the run log (review W6). The machine-readable lines use the plain marker `@@ashare-progress`, because the record separator first proposed counts as a line break in Python's `splitlines`.
- **Part C, downloads by size.** A single large download is not yet counted in bytes: documents and files are counted one by one. The counter accepts bytes (`Counter.bytes`) for when a download reports its size.
- **Part C, data-folder copy.** It is counted by files, not bytes.
- **Part B, rule 3.** A reduction plan is matched to a sale by company and by title, within 200 days, not by person. A sale whose method is not given is treated as a sale by auction, and its flag says so.
- **Part B, effective dates.** The bundled rules have none yet. A rule then applies to every dealing, and its flags are provisional.
- **The deadline rules** were already applied in v2.3 with a note. They are now marked provisional, and every result names the pack and its status. No figure changed.

**Interference.**
- **Every switch off.** The suite of v2.3 and earlier passes unchanged (`ASHARE_FEATURES=all=off`: 456 passed, 4 skipped, as in v2.3).
- **Extractors.** No extractor version changed, so nothing is read again.
- **The loader.** With no override, it returns exactly the bundled data (tested).

**Tests.**
- `tests/test_v24.py`: 21 tests.
- `tests/test_v23.py`: the share-dealing test was updated to the provisional rules, keeping the v2.3 assertion under `--confirmed-only`.

| Environment | Passed | Skipped |
|---|---|---|
| Linux, Python 3.12 | 528 | 4 |
| Python 3.13 | 490 | 40 |
| PostgreSQL 16 | 521 | 11 |

- **Python 3.13:** the skips are the tests that need Tk.
- **PostgreSQL 16:** run before two small changes (a table's columns and a test's terminal width), both covered by the 3.12 run.

**Windows.**
- The programs were built under Wine with the Windows Python.
- The packaged command line:
  - lists, checks, exports and resets the rule packs;
  - shows them in Diagnostics;
  - writes an interactive page with the zoom runtime.
- The installer installs silently, and the installed program reports 2.4.0.
- GitHub's Windows runner built and tested the release commit: 516 passed and 16 skipped, and the smoke test of the packaged program (now including the rule packs) passed.
