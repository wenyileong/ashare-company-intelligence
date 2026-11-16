"""A rehearsal of a live run, offline (v2.4.1).

It seeds a small data folder from the synthetic corpus, then drives the command line through the steps of the author's
live-run checklist: diagnostics, the rule packs, timeliness, share-dealing flags, a panel, the views, the outputs
register, moving the data folder, and using a folder restored elsewhere. It checks that every step ends cleanly (no
traceback) and that every document is still found after each move.

It does not replace a live run: nothing is fetched, the documents are synthetic, and the desktop window is not opened.

    python packaging/rehearsal.py                       # with the source tree
    python packaging/rehearsal.py --cli dist/AShareScraper/ashare-cli.exe
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SEED = r'''
import hashlib, json, sys
from datetime import date, timedelta
from pathlib import Path
from ashare.models import init_db, SessionLocal, Company, Disclosure, TradingDay
from ashare.models_v23 import InsiderDealing
from ashare.storage import upsert_ashares
from ashare.corpus import build_synthetic_corpus
from ashare.storepaths import to_stored

root = Path(sys.argv[1])
init_db()
codes = [f"60{1000 + i}" for i in range(6)]
upsert_ashares([{"code": c, "exchange": "SSE", "legal_name_cn": f"示例{i:02d}科技股份有限公司",
                 "short_name_cn": f"示例{i:02d}", "org_id": f"gssh0{c}"} for i, c in enumerate(codes, 1)])
build_synthetic_corpus(str(root / "corpus_tmp"), 6, 2, 20260101, "pdf")
man = json.loads((root / "corpus_tmp" / "manifest.json").read_text(encoding="utf-8"))
s = SessionLocal()
comp = {c.security_code: c for c in s.query(Company)}
dest = root / "disclosures" / "annual_report"
dest.mkdir(parents=True, exist_ok=True)
n = 0
for doc, code in zip([d for d in man["documents"] if d["id"].startswith("ar")], codes):
    src = root / "corpus_tmp" / doc["file"]
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    p = dest / f"{sha}.pdf"
    p.write_bytes(src.read_bytes())
    late = n == 0                                        # the first report is published after its deadline
    s.add(Disclosure(company_id=comp[code].id, announcement_id=f"rehearsal-{n}", sec_code=code,
                     announcement_date="2025-05-20" if late else "2025-04-2%d" % n, title_cn=f"示例{n + 1:02d}科技股份有限公司2024年年度报告",
                     kind="annual_report", document_url=f"https://example.invalid/{sha}.pdf", local_path=to_stored(p),
                     sha256=sha, file_size=p.stat().st_size, content_type="application/pdf", source="REHEARSAL"))
    n += 1
d0 = date(2024, 11, 1)
for i in range(260):
    x = d0 + timedelta(days=i)
    s.add(TradingDay(exchange="SSE", trade_date=x.isoformat(), is_open=int(x.weekday() < 5), source="rehearsal"))
c1 = comp[codes[1]]
s.add(Disclosure(company_id=c1.id, announcement_id="rehearsal-plan", sec_code=codes[1], announcement_date="2025-03-03",
                 title_cn="关于董事减持股份计划的预披露公告", kind="other", source="REHEARSAL"))
s.add_all([InsiderDealing(company_id=c1.id, person_name="张三", role="董事", deal_date="2025-03-10", direction="SELL",
                          shares=10000, published_date="2025-03-17", method="AUCTION"),
           InsiderDealing(company_id=c1.id, person_name="李四", role="监事", deal_date="2025-04-18", direction="SELL",
                          shares=5000, published_date="2025-04-21", method="BLOCK")])
s.commit(); s.close()
shutil = __import__("shutil"); shutil.rmtree(root / "corpus_tmp")
print("seeded", n, "documents")
'''

CHECK = r'''
import json, sys
from ashare.datafolder import paths_report
r = paths_report()
f = r["tables"]["documents"]["files"]
print(json.dumps({"root": r["data_root"], **f}))
sys.exit(0 if f.get("missing", 0) == 0 and f.get("present", 0) + f.get("recoverable", 0) >= 6 else 3)
'''


class Run:
    def __init__(self, cli: list[str], keep: bool):
        self.cli, self.keep = cli, keep
        self.base = Path(tempfile.mkdtemp(prefix="ashare_rehearsal_"))
        self.failures: list[str] = []
        self.steps = 0

    def env(self, home: Path) -> dict:
        e = dict(os.environ)
        e.update({"ASHARE_HOME": str(home), "ASHARE_DB": str(home / "ashare.db"), "PYTHONIOENCODING": "utf-8",
                  "PYTHONUTF8": "1", "APPDATA": str(self.base / "appdata"), "ASHARE_PROGRESS": "off",
                  "PYTHONPATH": str(ROOT) + os.pathsep + e.get("PYTHONPATH", ""), "COLUMNS": "200",
                  "ASHARE_FEATURES": "insider=on"})
        e.pop("ASHARE_RAW_DIR", None)
        return e

    def _go(self, name: str, argv: list[str], home: Path, expect: str | None, ok=(0,)) -> str:
        self.steps += 1
        p = subprocess.run(argv, cwd=home, env=self.env(home), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        out = (p.stdout or "") + (p.stderr or "")
        bad = None
        if "Traceback (most recent call last)" in out:
            bad = "a traceback"
        elif p.returncode not in ok:
            bad = f"exit code {p.returncode}"
        elif expect and expect not in out:
            bad = f"'{expect}' not in the output"
        print(f"{'FAIL' if bad else 'ok  '}  {name}" + (f": {bad}" if bad else ""))
        if bad:
            self.failures.append(f"{name}: {bad}\n" + out[-1500:])
        return out

    def cmd(self, name, args, home, expect=None, ok=(0,)):
        return self._go(name, self.cli + args, home, expect, ok)

    def py(self, name, code, home, args=(), expect=None):
        return self._go(name, [sys.executable, "-c", code, *args], home, expect)

    def main(self) -> int:
        a, b, c = self.base / "data", self.base / "moved", self.base / "restored"
        a.mkdir()
        self.py("seed a data folder from the synthetic corpus", SEED, a, [str(a)], "seeded 6 documents")
        self.cmd("version", ["version"], a)
        self.cmd("diagnostics", ["diagnostics"], a, "Rule packs")
        self.cmd("rule packs: list", ["rules-list"], a, "insider")
        for p in ("insider", "deadlines", "nominees"):
            self.cmd(f"rule packs: check {p}", ["rules-check", p], a, "valid")
        self.cmd("rule packs: export, compare, reset", ["rules-export", "insider"], a, "Written")
        self.cmd("rule packs: compare", ["rules-diff", "insider"], a, "No difference")
        self.cmd("rule packs: reset", ["rules-reset", "insider", "--apply"], a, "bundled")
        self.cmd("rule packs: confirmation sheet", ["rules-sheet", "--out", "sheet.md"], a, "Written")
        self.cmd("paths: every document found", ["paths-report"], a)
        self.py("paths: checked in numbers", CHECK, a)
        self.cmd("timeliness", ["timeliness", "--out", "exports/timeliness.csv"], a, "late")
        out = self.cmd("share-dealing flags", ["insider-flags"], a, "provisional rule")
        if "trading days before the sale" not in " ".join(out.split()):
            self.failures.append("share-dealing flags: the late reduction plan was not flagged\n" + out[-800:])
            print("FAIL  share-dealing flags: the late reduction plan was not flagged")
        self.cmd("share-dealing flags, confirmed rules only", ["insider-flags", "--confirmed-only"], a, "No rule")
        self.cmd("a panel", ["build-panel", "--codes", "601000,601001", "--start", "2024-01-01", "--end",
                             "2025-06-30", "--name", "rehearsal", "--variables",
                             "report_delay_days,report_late,insider_net_buy_12m"], a, ok=(0, 1))
        for view, extra in (("viz-coverage", ["--start", "2024", "--end", "2024"]),
                            ("viz-timeliness", ["--start", "2024", "--end", "2024"]),
                            ("viz-sectors", ["--start", "2024", "--end", "2024"]),
                            ("viz-market-map", []), ("viz-common-ownership", ["--codes", "601000,601001"])):
            self.cmd(f"view: {view}", [view, *extra, "--out", f"visualise/{view}"], a, ok=(0, 1))
        cov = a / "visualise" / "viz-coverage" / "view.html"
        if not cov.exists() or "chartjs-plugin-zoom" not in cov.read_text(encoding="utf-8", errors="replace"):
            self.failures.append("view: the coverage page or its zoom runtime is missing")
            print("FAIL  view: the coverage page or its zoom runtime is missing")
        self.cmd("outputs: find earlier outputs", ["outputs-scan", "--apply"], a)
        self.cmd("outputs: list", ["outputs"], a)
        self.cmd("documents not read", ["not-read"], a, ok=(0, 1))
        self.cmd("move: dry run", ["move-data-folder", str(b)], a)
        self.cmd("move: apply", ["move-data-folder", str(b), "--apply"], a)
        self.py("move: every document found in the new folder", CHECK, b)
        self.cmd("move: timeliness still works there", ["timeliness", "--out", "exports/t2.csv"], b, "late")
        for src in b.rglob("*"):                                # as if restored from a backup after reinstalling
            dst = c / src.relative_to(b)
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
        shutil.rmtree(b)
        self.cmd("restored folder: check", ["adopt-data-folder", str(c)], c)
        self.cmd("restored folder: use it", ["adopt-data-folder", str(c), "--apply"], c)
        self.py("restored folder: every document found", CHECK, c)
        self.cmd("restored folder: flags still work", ["insider-flags"], c, "provisional rule")
        print(f"\n{self.steps} steps; {len(self.failures)} failed")
        for f in self.failures:
            print("\n--- " + f)
        if not self.keep:
            shutil.rmtree(self.base, ignore_errors=True)
        else:
            print(f"kept: {self.base}")
        return 1 if self.failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cli", help="The packaged ashare-cli program; blank: the source tree")
    ap.add_argument("--keep", action="store_true", help="Keep the folders for inspection")
    ns = ap.parse_args()
    cli = [str(Path(ns.cli).resolve())] if ns.cli else [sys.executable, "-m", "ashare.cli"]
    sys.exit(Run(cli, ns.keep).main())
