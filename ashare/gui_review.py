"""Review page and chart window for the desktop application (v1.5)."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .i18n import tr

# command -> chart builder taking the card's form values
def _financial(v):
    from .charts.builders import financial_chart
    metric = (v.get("metric") or "").strip()
    return financial_chart(v["code"], [metric] if metric else None)


def _segments(v):
    from .charts.builders import segment_chart
    return segment_chart(v["code"], (v.get("dimension") or "PRODUCT") or "PRODUCT", v.get("period") or None)


def _history(v):
    from .charts.builders import history_chart
    return history_chart(v["code"], ["rd_investment"])


def _flags(v):
    from .charts.builders import flags_chart
    return flags_chart((v.get("security_code") or "").strip() or None)


CHARTS = {"show-financials": _financial, "segments": _segments, "human-capital-history": _history,
          "show-flags": _flags}


def COLUMN_LABELS() -> dict:
    return {"kind": tr("ui.win.col.kind", "Kind"), "item": tr("ui.win.col.item", "Item"),
            "field": tr("ui.win.col.field", "Field"), "value": tr("ui.win.col.value", "Value"),
            "status": tr("ui.win.col.status", "Status"), "id": tr("ui.win.col.id", "Id"),
            "done": tr("ui.win.col.done", "Done"), "failed": tr("ui.win.col.failed", "Failed"),
            "total": tr("ui.win.col.total", "Total"), "created": tr("ui.win.col.created", "Created"),
            "error": tr("ui.win.col.error", "Error")}


class ChartWindow(tk.Toplevel):
    """One reusable window that shows the chart for the last chartable action."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(tr("ui.win.chart", "Chart"))
        self.configure(bg="#ffffff")
        self.spec = None
        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        self.heading = ttk.Label(bar, text="", font=app.f_bold)
        self.heading.pack(side="left")
        ttk.Button(bar, text=tr("ui.win.close", "Close"), style="Small.TButton", command=self.withdraw).pack(side="right", padx=(6, 0))
        from .charts import mpl
        if mpl.available():
            ttk.Button(bar, text=tr("ui.win.save_png", "Save PNG…"), style="Small.TButton", command=self._png).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=tr("ui.win.save_data_csv", "Save data (CSV)…"), style="Small.TButton", command=self._csv).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=tr("ui.win.save_svg", "Save SVG…"), style="Small.TButton", command=self._svg).pack(side="right", padx=(6, 0))
        ttk.Label(self, text=tr("ui.win.chart_hint", "Hover over a point or bar to see its source; click it to "
                                                     "show the full trace in the output panel."), style="Muted.TLabel").pack(side="bottom", anchor="w", padx=12,
                                                                             pady=(4, 10))
        # v2.1: a chart taller than the screen (the layered view of many companies) scrolls
        self.scroll = ttk.Scrollbar(self, orient="vertical")
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#ffffff", yscrollcommand=self.scroll.set)
        self.scroll.configure(command=self.canvas.yview)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def show(self, spec):
        from .charts.tk import render_tk
        self.spec = spec
        self.heading.configure(text=spec.title)
        render_tk(self.canvas, spec, on_click=self._clicked)
        self.canvas.configure(scrollregion=(0, 0, spec.width, spec.height))
        room = max(300, self.winfo_screenheight() - 160)
        if spec.height + 90 > room:
            self.scroll.pack(side="right", fill="y")
        else:
            self.scroll.pack_forget()
        self.canvas.yview_moveto(0)
        self.geometry(f"{spec.width + 40}x{min(spec.height + 90, room)}")
        self.deiconify()
        self.lift()

    def _clicked(self, meta):
        table, row_id = meta.get("table"), meta.get("row_id")
        if table and row_id:
            self.app.run_quiet(["trace", str(table), str(row_id)], f"Trace of {table} row {row_id}")

    def _save(self, ext, writer):
        if not self.spec:
            return
        p = filedialog.asksaveasfilename(defaultextension=ext, initialdir=str(self.app.folder),
                                         filetypes=[(ext.upper().strip("."), "*" + ext)])
        if p:
            try:
                writer(p)
            except Exception as exc:
                messagebox.showwarning(tr("ui.win.chart", "Chart"), str(exc))
                return
            self.app._log(f"Chart saved: {p}\n", "muted")

    def _svg(self):
        from .charts.svg import render_svg
        self._save(".svg", lambda p: Path(p).write_text(render_svg(self.spec), encoding="utf-8"))

    def _csv(self):
        from .charts.builders import export_chart
        import tempfile
        import shutil

        def write(p):
            with tempfile.TemporaryDirectory() as d:
                files = export_chart(self.spec, str(Path(d) / "chart"))
                shutil.copyfile(next(f for f in files if f.endswith(".csv")), p)
        self._save(".csv", write)

    def _png(self):
        from .charts.mpl import render_png
        self._save(".png", lambda p: render_png(self.spec, p))


class ReviewPage:
    """Queue on the left; the selected item, its source page and the actions on the right."""

    def __init__(self, app, parent):
        self.app = app
        self.items: dict[str, dict] = {}
        self.current = None
        self.photo = None
        P = app_palette()
        top = ttk.Frame(parent, padding=(28, 22, 28, 8))
        top.pack(fill="x")
        ttk.Label(top, text=tr("ui.win.review", "Review"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text=tr("ui.win.review_intro",
                               "Values that need a person's check: validation findings, disagreements between the "
                               "two text extractors, and low-confidence values, most material first. Decisions are "
                               "stored separately; the original values are never changed."),
                  style="Muted.TLabel", wraplength=860, justify="left").pack(anchor="w", pady=(4, 8))
        bar = ttk.Frame(top)
        bar.pack(fill="x")
        ttk.Label(bar, text=tr("ui.win.security_code", "Security code")).pack(side="left")
        self.code = tk.StringVar()
        ttk.Entry(bar, textvariable=self.code, width=10).pack(side="left", padx=(6, 14))
        ttk.Label(bar, text=tr("ui.win.show", "Show")).pack(side="left")
        self.status = tk.StringVar(value="OPEN")
        ttk.Combobox(bar, textvariable=self.status, state="readonly", width=11,
                     values=["OPEN", "DEFERRED", "CORRECTED", "ACCEPTED", "REJECTED", "ALL"]).pack(side="left", padx=6)
        ttk.Label(bar, text=tr("ui.win.confidence_below", "Confidence below")).pack(side="left", padx=(14, 0))
        self.below = tk.StringVar(value="0.6")
        ttk.Entry(bar, textvariable=self.below, width=5).pack(side="left", padx=6)
        ttk.Button(bar, text=tr("ui.win.update_queue", "Update queue"), style="Accent.TButton", command=self.rebuild).pack(side="left", padx=(14, 6))
        ttk.Button(bar, text=tr("ui.win.refresh_list", "Refresh list"), style="Small.TButton", command=self.reload).pack(side="left")
        self.count = ttk.Label(bar, text="", style="Muted.TLabel")
        self.count.pack(side="left", padx=12)

        panes = ttk.PanedWindow(parent, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=28, pady=(4, 12))
        left = ttk.Frame(panes)
        cols = ("kind", "item", "field", "value", "status")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=14, selectmode="browse")
        for c, w in zip(cols, (105, 170, 60, 90, 70)):
            self.tree.heading(c, text=COLUMN_LABELS().get(c, c.capitalize()))
            self.tree.column(c, width=w, stretch=c == "item")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        panes.add(left, weight=1)

        right = ttk.Frame(panes, padding=(12, 0, 0, 0))
        panes.add(right, weight=2)
        self.summary = tk.Text(right, height=6, wrap="word", font=app.f_small, relief="flat", bg=P["out_bg"],
                               highlightthickness=1, highlightbackground=P["line"], padx=8, pady=6)
        self.summary.pack(fill="x")
        act = ttk.Frame(right, padding=(0, 8, 0, 0))
        act.pack(fill="x")
        ttk.Label(act, text=tr("ui.win.correct_value", "Correct value")).grid(row=0, column=0, sticky="w")
        self.value = tk.StringVar()
        ttk.Entry(act, textvariable=self.value, width=18).grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Label(act, text=tr("ui.win.reason_needed_to_correct", "Reason (needed to correct or reject)")).grid(row=0, column=1, sticky="w")
        self.reason = tk.StringVar()
        ttk.Entry(act, textvariable=self.reason, width=30).grid(row=1, column=1, sticky="we", padx=(0, 10))
        act.columnconfigure(1, weight=1)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(6, 0))
        for text, a, style in (("Accept", "accept", "Accent.TButton"), ("Correct", "correct", "Small.TButton"),
                               ("Not disclosed", "reject", "Small.TButton"), ("Defer", "defer", "Small.TButton")):
            ttk.Button(buttons, text=text, style=style, command=lambda a=a: self.decide(a)).pack(side="left", padx=(0, 6))
        ttk.Label(right, text=tr("ui.win.review_buttons",
                                 "Accept = the value is right. Correct = enter the right value. Not disclosed = the "
                                 "report does not give this value. Defer = decide later."),
                  style="Muted.TLabel", wraplength=400, justify="left").pack(anchor="w", pady=(4, 2))
        nav = ttk.Frame(right)
        nav.pack(fill="x", pady=(6, 2))
        self.page_label = ttk.Label(nav, text=tr("ui.win.source_page", "Source page"), style="Muted.TLabel")
        self.page_label.pack(side="left")
        ttk.Button(nav, text=tr("ui.win.next_page", "Next page"), style="Small.TButton", command=lambda: self.turn(1)).pack(side="right")
        ttk.Button(nav, text=tr("ui.win.previous_page", "Previous page"), style="Small.TButton", command=lambda: self.turn(-1)).pack(side="right",
                                                                                                        padx=4)
        holder = ttk.Frame(right)
        holder.pack(fill="both", expand=True)
        self.page = tk.Canvas(holder, bg="#eeeeef", highlightthickness=0, height=300)
        vs = ttk.Scrollbar(holder, orient="vertical", command=self.page.yview)
        hs = ttk.Scrollbar(holder, orient="horizontal", command=self.page.xview)
        self.page.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.page.pack(side="left", fill="both", expand=True)

        self.page_no = None
        self.doc_path = None
        self.highlight = None

    # -- data ---------------------------------------------------------------------
    def rebuild(self):
        from .review import build_review_queue
        try:
            try:
                below = float(self.below.get())
            except ValueError:
                below = 0.6
            r = build_review_queue(self.code.get().strip() or None, below)
            self.app._log(f"Review queue updated: {r}\n", "muted")
        except Exception as exc:
            messagebox.showerror(tr("ui.win.review", "Review"), str(exc))
        self.reload()

    def reload(self):
        from .review import review_queue
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        try:
            rows = review_queue(self.code.get().strip() or None, self.status.get(), limit=500)
        except Exception as exc:
            messagebox.showerror(tr("ui.win.review", "Review"), str(exc))
            return
        for r in rows:
            kind = r["rule"] or {"LOW_CONFIDENCE": "Low confidence", "DISAGREEMENT": "Disagreement"}.get(
                r["kind"], r["kind"])
            iid = self.tree.insert("", "end", values=(kind, f"{r['code']} {r['item']}", r["field"] or "",
                                                      r["value"] or "", r["status"]))
            self.items[iid] = r
        self.count.configure(text=tr("ui.win.items", "{n} item(s)").format(n=len(rows)))

    def select(self):
        from .review import review_item
        sel = self.tree.selection()
        if not sel:
            return
        r = self.items[sel[0]]
        try:
            detail = review_item(r["id"])
        except Exception as exc:
            messagebox.showerror(tr("ui.win.review", "Review"), str(exc))
            return
        self.current = detail
        tr = detail.get("trace") or {}
        doc = tr.get("document") or {}
        loc = tr.get("location") or {}
        lines = [f"{detail['label']}  ·  {detail['field']} = {detail['value']}",
                 f"{detail['kind']}{' / ' + detail['rule'] if detail['rule'] else ''}  ·  confidence "
                 f"{detail['confidence']}  ·  status {detail['status']}",
                 f"Document: {doc.get('title') or doc.get('source_document') or 'n/a'} "
                 f"({doc.get('published') or ''})  page {loc.get('source_page') or 'n/a'}",
                 f"Raw text: {tr.get('raw_value') or 'n/a'}",
                 f"Method: {tr.get('extraction_method')}  {json.dumps(tr.get('extraction_note'), ensure_ascii=False) if tr.get('extraction_note') else ''}"]
        flag = detail.get("details", {}).get("flag")
        if flag:
            lines.append("Finding: " + json.dumps(flag, ensure_ascii=False, default=str)[:400])
        for c in detail["corrections"]:
            if not c["superseded"]:
                lines.append(f"Decision: {c['action']} {c['corrected'] or ''} by {c['reviewer']} at {c['at']} "
                             f"({c['reason'] or ''})")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.value.set(detail["value"] or "")
        self.reason.set("")
        self.doc_path = doc.get("local_path")
        self.page_no = loc.get("source_page") or 1
        self.highlight = tr.get("raw_value") or ""
        self.draw_page()

    def draw_page(self):
        from .pagerender import available, render_page, png_base64
        self.page.delete("all")
        if not self.doc_path or not Path(self.doc_path).exists():
            self.page_label.configure(text=tr("ui.win.source_page_document_not", "Source page: document not downloaded"))
            return
        if not str(self.doc_path).lower().endswith(".pdf") or not available():
            self.page_label.configure(text=tr("ui.win.source_page_preview_needs", "Source page: preview needs a PDF and the pypdfium2 package"))
            return
        try:
            r = render_page(self.doc_path, self.page_no, self.highlight)
        except Exception as exc:
            self.page_label.configure(text=tr("ui.win.cannot_render", "Source page: cannot render ({error})").format(
                error=exc))
            return
        self.page_no = r["page"]
        self.photo = tk.PhotoImage(data=png_base64(r["png"]))
        self.page.create_image(0, 0, image=self.photo, anchor="nw")
        for x0, y0, x1, y1 in r["boxes"]:
            self.page.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, outline="#d00000", width=2)
        self.page.configure(scrollregion=(0, 0, r["width"], r["height"]))
        if r["boxes"]:
            frac = max(0.0, (r["boxes"][0][1] - 40) / r["height"])
            self.page.after(60, lambda: self.page.yview_moveto(frac))
        found = tr("ui.win.match", ", match highlighted") if r["boxes"] else tr("ui.win.no_match",
                                                                                 ", match not found on this page")
        self.page_label.configure(text=tr("ui.win.page_of", "Source page {page} of {pages}").format(
            page=r["page"], pages=r["pages"]) + found)

    def turn(self, step):
        if self.page_no:
            self.page_no = max(1, self.page_no + step)
            self.draw_page()

    def decide(self, action):
        from .review import resolve
        if not self.current:
            return
        try:
            value = self.value.get().strip() if action == "correct" else None
            resolve(self.current["id"], action, value, self.reason.get().strip() or None)
        except Exception as exc:
            messagebox.showwarning(tr("ui.win.review", "Review"), str(exc))
            return
        self.app._log(f"Review item {self.current['id']}: {action}\n", "muted")
        self.reload()
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])


def app_palette():
    from .gui import PALETTE
    return PALETTE


def _event_study(v):
    """Chart of the CAAR written by an event-study run."""
    import csv as _csv
    from pathlib import Path as _P
    from .charts.spec import ChartSpec, Series, Point
    p = _P(v.get("out") or "event_studies") / f"{v.get('name') or 'event_study'}_caar.csv"
    rows = list(_csv.DictReader(open(p, encoding="utf-8-sig")))
    f = lambda x: float(x) if x not in (None, "") else None  # noqa: E731
    pts = [Point(r["day"], f(r["caar"])) for r in rows]
    band = [(f(r["low"]), f(r["high"])) if r["low"] else None for r in rows]
    return ChartSpec("line", "Cumulative average abnormal return", [Series("CAAR", pts, band=band)],
                     unit="RATIO", x_label="trading days relative to the event", subtitle="shaded: 95% band")


def _price(v):
    from .charts.builders import price_chart
    return price_chart(v["code"])


def _control(v):
    from .charts.builders import control_chart
    return control_chart(v["code"], (v.get("as_of") or "").strip() or None)


def _interlocks(v):
    from .charts.builders import interlock_chart
    return interlock_chart((v.get("code") or "").strip() or None, (v.get("as_of") or "").strip() or None)


def _group_tree(v):
    from .charts.builders import group_tree_chart
    return group_tree_chart(v["code"], (v.get("date") or "").strip() or None)


def _topology(v):
    """v2.1: the layered chart of the snapshot just written."""
    from .charts.layers import layers_chart
    snap = json.loads((Path(v.get("out") or "topology") / "snapshot.json").read_text(encoding="utf-8"))
    return layers_chart(snap)


CHARTS["topology"] = _topology
CHARTS.update({"event-study": _event_study, "price-chart": _price, "control": _control, "interlocks": _interlocks,
               "subsidiaries": _group_tree})


def empty_panel_reason(path) -> str:
    """Why a panel is empty, from its manifest when there is one (v2.1, finding 17)."""
    p = Path(path)
    manifest = p.with_name(p.stem + "_manifest.json")
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ("Its manifest was not found. Build the panel again (Research: 'Build a panel'); a panel without "
                "rows is not written, and the output says why.")
    params = m.get("parameters") or {}
    return (f"It was built for {params.get('start')} to {params.get('end')} ({params.get('unit')}). Usually the "
            "company list has no listing dates or statuses for that span: run 'Update the company list', then build "
            "the panel again.")


class ExplorerWindow(tk.Toplevel):
    """Dataset explorer: summaries, distributions, scatter plots and coverage of a panel CSV."""

    def __init__(self, app, path=None):
        super().__init__(app)
        self.app = app
        self.title(tr("ui.win.dataset_explorer", "Dataset explorer"))
        self.configure(bg="#ffffff")
        self.rows = []
        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text=tr("ui.win.open_panel", "Open panel…"), style="Small.TButton", command=self.choose).pack(side="left")
        self.file_label = ttk.Label(bar, text=tr("ui.win.no_panel_loaded", "No panel loaded"), style="Muted.TLabel")
        self.file_label.pack(side="left", padx=10)
        ctl = ttk.Frame(self, padding=(12, 0))
        ctl.pack(fill="x")
        ttk.Label(ctl, text=tr("ui.win.variable", "Variable")).pack(side="left")
        self.x = tk.StringVar()
        self.xbox = ttk.Combobox(ctl, textvariable=self.x, state="readonly", width=24)
        self.xbox.pack(side="left", padx=(6, 14))
        ttk.Label(ctl, text=tr("ui.win.second_variable_scatter", "Second variable (scatter)")).pack(side="left")
        self.y = tk.StringVar()
        self.ybox = ttk.Combobox(ctl, textvariable=self.y, state="readonly", width=24)
        self.ybox.pack(side="left", padx=6)
        btns = ttk.Frame(self, padding=(12, 8))
        btns.pack(fill="x")
        for label, kind in (("Summary", "summary"), ("Histogram", "hist"), ("By year", "box"),
                            ("Scatter with fit", "scatter"), ("Coverage", "coverage"), ("Correlations", "corr")):
            ttk.Button(btns, text=label, style="Small.TButton", command=lambda k=kind: self.show(k)).pack(
                side="left", padx=(0, 6))
        ttk.Button(btns, text=tr("ui.win.save_chart_svg", "Save chart (SVG)…"), style="Small.TButton", command=self.save).pack(side="right")
        self.canvas = tk.Canvas(self, bg="#ffffff", highlightthickness=0, width=780, height=420)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.spec = None
        self.geometry("900x580")
        if path:
            self.load(path)

    def choose(self):
        p = filedialog.askopenfilename(initialdir=str(self.app.folder), filetypes=[("Panel CSV", "*.csv")])
        if p:
            self.load(p)

    def load(self, path):
        from .explorer import load_panel, numeric_columns
        try:
            self.rows = load_panel(path)
        except Exception as exc:
            messagebox.showerror(tr("ui.win.dataset_explorer", "Dataset explorer"), str(exc))
            return
        if not self.rows:                                   # v2.1 (finding 17): say why, not a blank view
            reason = empty_panel_reason(path)
            self.file_label.configure(text=f"{Path(path).name}: " + tr("ui.win.no_rows", "no rows"))
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", width=820, fill="#57606a", font=("Segoe UI", 11),
                                    text=tr("ui.win.empty_panel", "The panel has no rows, so there is nothing "
                                                                  "to explore.") + "\n\n" + reason)
            self.app._log(f"\n› Dataset explorer: {Path(path).name} has no rows. {reason}\n", "cmd")
            return
        cols = numeric_columns(self.rows)
        self.xbox.configure(values=cols)
        self.ybox.configure(values=cols)
        if cols:
            self.x.set(cols[0])
            self.y.set(cols[1] if len(cols) > 1 else cols[0])
        self.file_label.configure(text=f"{Path(path).name}: " + tr(
            "ui.win.rows_vars", "{rows} rows, {cols} numeric variables").format(rows=len(self.rows), cols=len(cols)))
        self.show("coverage")

    def show(self, kind):
        from .explorer import summary, correlations, chart_for
        from .charts.tk import render_tk
        if not self.rows:
            self.app._log("\n› Dataset explorer: no panel with rows is open. Choose 'Open panel…', or build one "
                          "(Research: 'Build a panel').\n", "cmd")
            return
        if kind in ("summary", "corr"):
            rows = summary(self.rows) if kind == "summary" else correlations(self.rows)
            self.app._log(f"\n› Dataset explorer: {kind}\n", "cmd")
            cols = list(rows[0].keys()) if rows else []
            fmt = lambda v: f"{v:,.4g}" if isinstance(v, float) else ("" if v is None else str(v))  # noqa: E731
            widths = [max(len(c), *(len(fmt(r.get(c))) for r in rows)) for c in cols]
            self.app._log("  ".join(c.ljust(w) for c, w in zip(cols, widths)) + "\n")
            for r in rows:
                self.app._log("  ".join(fmt(r.get(c)).ljust(w) for c, w in zip(cols, widths)) + "\n")
            return
        try:
            self.spec = chart_for(self.rows, kind, self.x.get(), self.y.get())
        except Exception as exc:
            messagebox.showwarning(tr("ui.win.dataset_explorer", "Dataset explorer"), str(exc))
            return
        render_tk(self.canvas, self.spec)

    def save(self):
        from .charts.svg import render_svg
        if not self.spec:
            return
        p = filedialog.asksaveasfilename(defaultextension=".svg", initialdir=str(self.app.folder))
        if p:
            Path(p).write_text(render_svg(self.spec), encoding="utf-8")


class OperationsPage:
    """Daily update, resumable jobs with progress and cancel, scheduling and storage (v1.9)."""

    def __init__(self, app, parent):
        import threading
        self.app = app
        self.threading = threading
        self.running = None
        P = app_palette()
        top = ttk.Frame(parent, padding=(28, 22, 28, 8))
        top.pack(fill="x")
        ttk.Label(top, text=tr("ui.win.operations", "Operations"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text=tr("ui.win.ops_intro",
                               "Keep the database up to date. The daily update fetches only what is new: "
                               "announcements since the last run (market-wide, one query per exchange and day), "
                               "today's prices for all companies, and extraction for companies with new documents. "
                               "Jobs can be cancelled and resumed; nothing is duplicated."), style="Muted.TLabel", wraplength=860,
                  justify="left").pack(anchor="w", pady=(4, 10))
        bar = ttk.Frame(top)
        bar.pack(fill="x")
        ttk.Button(bar, text=tr("ui.win.run_daily_update", "Run daily update"), style="Accent.TButton", command=self.daily).pack(side="left")
        ttk.Button(bar, text=tr("ui.win.resume_selected_job", "Resume selected job"), style="Small.TButton", command=self.resume).pack(side="left", padx=8)
        self.cancel_btn = ttk.Button(bar, text=tr("ui.win.cancel", "Cancel"), style="Small.TButton", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left")
        ttk.Button(bar, text=tr("ui.win.refresh", "Refresh"), style="Small.TButton", command=self.refresh).pack(side="left", padx=8)
        prog = ttk.Frame(top)
        prog.pack(fill="x", pady=(10, 0))
        self.pvar = tk.DoubleVar(value=0)
        ttk.Progressbar(prog, variable=self.pvar, maximum=100, length=420).pack(side="left")
        self.plabel = ttk.Label(prog, text=tr("ui.win.idle", "Idle"), style="Muted.TLabel")
        self.plabel.pack(side="left", padx=10)
        body = ttk.Frame(parent, padding=(28, 4, 28, 8))
        body.pack(fill="both", expand=True)
        cols = ("id", "kind", "status", "done", "failed", "total", "created", "error")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=8, selectmode="browse")
        for c, w in zip(cols, (50, 110, 90, 60, 60, 60, 130, 260)):
            self.tree.heading(c, text=COLUMN_LABELS().get(c, c.capitalize()))
            self.tree.column(c, width=w, stretch=c == "error")
        self.tree.pack(fill="both", expand=True)
        low = ttk.Frame(parent, padding=(28, 0, 28, 16))
        low.pack(fill="x")
        ttk.Label(low, text=tr("ui.win.run_automatically_on_weekdays", "Run automatically on weekdays at")).pack(side="left")
        self.at = tk.StringVar(value="18:30")
        ttk.Entry(low, textvariable=self.at, width=6).pack(side="left", padx=6)
        ttk.Button(low, text=tr("ui.win.schedule", "Schedule"), style="Small.TButton", command=lambda: self.schedule(True)).pack(side="left")
        ttk.Button(low, text=tr("ui.win.remove_schedule", "Remove schedule"), style="Small.TButton",
                   command=lambda: self.schedule(False)).pack(side="left", padx=6)
        ttk.Button(low, text=tr("ui.win.storage", "Storage"), style="Small.TButton", command=self.storage).pack(side="right")
        self.refresh()

    def refresh(self):
        from .ops import list_jobs
        self.tree.delete(*self.tree.get_children())
        try:
            for j in list_jobs(30):
                self.tree.insert("", "end", iid=str(j["id"]), values=[j[c] for c in ("id", "kind", "status", "done", "failed",
                                                                                     "total", "created", "error")])
        except Exception as exc:
            self.app._log(f"Jobs: {exc}\n", "muted")

    def _progress(self, done, total, key, status):
        def ui():
            self.pvar.set(100.0 * done / total if total else 0)
            self.plabel.configure(text=f"{done} of {total} · {key} {status}")
        self.app.after(0, ui)

    def _start(self, fn, label):
        if self.running:
            return
        self.cancel_btn.state(["!disabled"])
        self.plabel.configure(text=f"{label}…")

        def work():
            try:
                r = fn()
                self.app._log(f"\n› {label}\n{json.dumps(r, ensure_ascii=False, default=str)[:2000]}\n")
            except Exception as exc:
                self.app._log(f"\n› {label} failed: {exc}\n")
            finally:
                self.running = None
                self.app.after(0, lambda: (self.cancel_btn.state(["disabled"]), self.plabel.configure(text=tr("ui.win.idle", "Idle")),
                                           self.refresh()))
        self.running = self.threading.Thread(target=work, daemon=True)
        self.running.start()

    def daily(self):
        from .ops import daily_update
        self._start(lambda: daily_update(progress=self._progress), "Daily update")
        self.app.after(1500, self.refresh)

    def resume(self):
        from .ops import run_job
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(tr("ui.win.operations", "Operations"), tr("ui.win.select_job", "Select a job in the list first."))
            return
        jid = int(sel[0])
        self._start(lambda: run_job(jid, self._progress), f"Job {jid}")

    def cancel(self):
        from .ops import request_cancel, list_jobs
        for j in list_jobs(30):
            if j["status"] == "RUNNING":
                request_cancel(j["id"])
        self.plabel.configure(text=tr("ui.win.cancelling_after_the_current", "Cancelling after the current item…"))

    def schedule(self, enable):
        from .ops import schedule
        try:
            r = schedule(enable, self.at.get().strip() or "18:30")
        except Exception as exc:
            messagebox.showerror(tr("ui.win.schedule", "Schedule"), str(exc))
            return
        self.app._log(f"\n› Schedule\n{json.dumps(r, ensure_ascii=False)}\n")

    def storage(self):
        from .ops import storage_stats
        r = storage_stats()
        self.app._log("\n› Storage\n" + json.dumps(r, ensure_ascii=False, indent=1) + "\n"
                      "Use 'ashare-cli prune-documents' to remove documents you no longer need (they can be fetched "
                      "again).\n")
