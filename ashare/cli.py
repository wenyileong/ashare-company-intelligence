import typer
from rich import print
from .models import init_db, SessionLocal, Company, FinancialFact
from .pipeline import update_universe
from .disclosure_pipeline import catalogue_disclosures
from .validation import validate_database
from .financials import extract_financials, validate_financials
from .market import acquire_market_data, import_bars_csv, show_market
from .ownership import import_ownership_csv, import_capital_csv, catalogue_ownership_disclosures, show_ownership, show_capital, validate_ownership
from .corporate_actions import extract_corporate_actions, import_corporate_actions_csv, show_actions, capital_effective_date
from .reconciliation import reconcile_capital
from .regulatory import (extract_regulatory_events, import_regulatory_document, import_regulatory_csv,
                         show_events, regulatory_status)
from .export import export_table, TABLES
from .crossvalidation import validate_all, cross_validate, show_flags
from .linking import link_all
from .intelligence import company_profile, financial_series, compare, market_stats, timeline
from .report import write_profile_report
from .research import (search_disclosures, index_documents, search_documents, inspect_document, trace,
                       run_query, release_dataset)
from .industry import (import_industry_csv, industry_history, peers, industry_stats, industry_summary)
from .management import (extract_management_events, extract_rosters, import_management_csv,
                         import_management_events_csv, roster_at, governance, show_management_events)
from .segments import extract_segments, import_segments_csv, segments as segments_view, segment_history
from .group import extract_subsidiaries, import_subsidiaries_csv, subsidiaries as subsidiaries_view, scope_changes
from .human_capital import (extract_human_capital, import_human_capital_csv, human_capital, human_capital_history,
                            ITEMS as HC_ITEMS)
from .esg import extract_esg, import_esg_csv, import_esg_ratings_csv, esg_profile, ITEMS as ESG_ITEMS
from . import __version__
from rich.console import Console
from rich.table import Table


def _console():
    import os
    return Console(width=int(os.environ.get("COLUMNS", "140")), highlight=False, soft_wrap=False)


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.4f}" if abs(v) < 100 else f"{v:,.0f}"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items() if x not in (None, "", [], {}))
    if isinstance(v, list):
        return "; ".join(_fmt(x) for x in v)
    return str(v)


def _table(rows, columns=None, title=None):
    """Print a list of dicts as an aligned table."""
    con = _console()
    if not rows:
        con.print("[dim](no rows)[/dim]")
        return
    columns = columns or list(rows[0].keys())
    if title:
        con.print(f"[bold]{title}[/bold]")
    t = Table(show_lines=False, header_style="bold", box=None, pad_edge=False)
    for c in columns:
        t.add_column(c, overflow="fold", max_width=60)
    for r in rows:
        t.add_row(*[_fmt(r.get(c)) for c in columns])
    con.print(t)
    con.print(f"[dim]{len(rows)} row(s)[/dim]")

app = typer.Typer(help="China A-share company research data collector", pretty_exceptions_enable=False)

# Commands that work on the company list and do nothing useful without it.
_NEEDS_UNIVERSE = {
    "catalogue-disclosures", "recatalogue-busy-days", "download-documents", "acquire-market", "daily-update", "job-create", "extract-financials",
    "extract-corporate-actions", "extract-regulatory-events", "extract-management", "extract-segments",
    "extract-subsidiaries", "extract-human-capital", "extract-esg", "extract-top-holders", "extract-control",
    "extract-pledges", "extract-transactions", "extract-listing-events", "build-panel", "market-snapshots",
    "universe-at", "security-history", "suspensions", "build-calendar", "show-company", "show-financials",
    "show-market", "profile", "report", "roster", "segments", "subsidiaries", "governance", "control",
    "esg", "peers", "industry-stats", "valuation", "event-study", "universe-stats", "validate-universe",
}


def _progress(text: str) -> None:
    """Progress lines, flushed at once so the desktop output shows them live."""
    import sys
    sys.stdout.write(text + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


@app.callback()
def _before(ctx: typer.Context):
    """China A-share company research data collector."""
    from . import pdfwarnings                     # v2.0.3: one summary line instead of a flood (finding 5)
    pdfwarnings.install()
    ctx.call_on_close(lambda: pdfwarnings.finish(ctx.invoked_subcommand or "", _progress))
    if ctx.invoked_subcommand in _NEEDS_UNIVERSE:
        try:
            from sqlalchemy import func
            init_db()
            s = SessionLocal()
            try:
                n = s.query(func.count(Company.id)).scalar()
            finally:
                s.close()
        except Exception:
            return
        if not n:
            print("[yellow]The company list is empty, so there is nothing to work on yet. Run 'Update the company "
                  "list' (ashare-cli update-universe) first; if that fails, run the Self-test.[/yellow]")

@app.command("init-db")
def init_database():
    """Create the database, or upgrade it to the current schema."""
    init_db()
    print("[green]Database initialised.[/green]")

@app.command("update-universe")
def update_universe_cmd(
    source: str = typer.Option("cninfo", help="Universe source"),
    listing_dates: bool = typer.Option(True, "--listing-dates/--no-listing-dates",
                                       help="Also fetch listing dates: the exchanges' stock lists (3 requests), "
                                            "then the public quote list for any still missing (~60 requests)"),
):
    """Download the list of listed companies from CNINFO, with listing dates (the exchanges' stock lists first,
    v2.0.7) and status."""
    init_db()
    print(f"[cyan]Updating A-share universe from {source}...[/cyan]")
    result = update_universe(source, listing_dates=listing_dates)
    print({"observations": result["observations"], "inserted": result["inserted"],
           "updated": result["updated"], "not_collected": result["rejected"]})
    if result["errors"]:
        from collections import Counter
        from .universe import rejection_reason
        reasons = Counter(rejection_reason(code) for code, _ in result["errors"])
        print("Not collected:")
        for reason, n in reasons.most_common():
            print(f"  {n:5d}  {reason}")
        odd = [code for code, _ in result["errors"] if rejection_reason(code) == "code range not recognised"]
        if odd:
            print(f"  unrecognised codes: {', '.join(odd[:20])}")
    st = result.get("status") or {}
    if st.get("exchange_lists"):                      # v2.0.7: the exchanges' own stock lists
        print("Exchange lists: " + st["exchange_lists"])
    if st and not st.get("LISTED") and not st.get("quote_list_complete", True):    # finding 12
        print(f"Status: could not be determined from the exchanges' lists or the quote list "
              f"({st.get('DELISTED', 0)} delisted, recognised by name). " + (f"Note: {st['note']}" if st.get("note") else ""))
        return
    by = st.get("listing_dates_by_source") or {}
    src = (f" ({by.get('exchanges', 0):,} from the exchanges' lists, {by.get('quote_list', 0):,} from the quote list)"
           if by else "")
    print(f"Status: {st.get('LISTED', 0)} listed, {st.get('DELISTED', 0)} delisted (by name), "
          f"{st.get('NOT_IN_QUOTE_LIST', 0)} not in the quote list; {st.get('listing_dates_added', 0)} listing dates "
          f"added{src}." + (" The quote list was not needed." if st.get("exchange_lists_complete")
                             and not st.get("quote_list_used") else "")
          + (f" Note: {st['note']}" if st.get("note") else ""))


@app.command("validate-universe")
def validate_universe():
    """Check that each company's exchange and board match its security code."""
    init_db()
    problems = validate_database()
    s = SessionLocal()
    try:
        n = s.query(Company).count()
    finally:
        s.close()
    if not n:
        print("No companies to check.")
        return
    if not problems:
        print(f"[green]Exchange and board match the code for all {n} companies.[/green]")
    else:
        print(f"[red]{len(problems)} validation problems found.[/red]")
        for p in problems[:30]:
            print(p)
    s = SessionLocal()
    try:
        from sqlalchemy import func
        no_ld = s.query(Company).filter((Company.listing_date.is_(None)) | (Company.listing_date == "")).count()
        no_legal = s.query(Company).filter(Company.legal_name_cn.is_(None)).count()
        by_status = dict(s.query(func.coalesce(Company.status, "UNKNOWN"), func.count()).group_by(Company.status))
    finally:
        s.close()
    print(f"Status: {by_status}")
    if no_ld:
        print(f"[yellow]{no_ld} companies have no listing date. Point-in-time lists (universe-at, panels) leave them "
              "out until it is known: 'Update the company list' fetches dates for listed companies; for delisted "
              "ones, catalogue announcements with kind 'all' and run 'Read listing events', or import them "
              "(import-listing-events-csv).[/yellow]")
    if no_legal:
        print(f"{no_legal} companies have only a short name (CNINFO's list has no full legal names); this does "
              "not affect collection.")

@app.command("universe-stats")
def universe_stats():
    """Number of companies by exchange, board and status."""
    init_db()
    session = SessionLocal()
    try:
        rows = (
            session.query(Company.exchange, Company.board)
            .all()
        )
        counts = {}
        for exchange, board in rows:
            key = (exchange, board or "UNKNOWN")
            counts[key] = counts.get(key, 0) + 1
        for (exchange, board), count in sorted(counts.items()):
            print({
                "exchange": exchange,
                "board": board,
                "count": count,
            })
        print({"total": len(rows)})
    finally:
        session.close()

@app.command("catalogue-disclosures")
def catalogue_disclosures_cmd(
    since: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    until: str = typer.Option(..., help="End date YYYY-MM-DD"),
    kind: str = typer.Option("reports", help="annual, interim, quarterly (Q3), q1, reports, earnings_forecast, distributions, corporate_actions, regulatory, or all"),
    security_code: str = typer.Option(None, help="Optional six-digit code; omit for the whole universe"),
    download_documents: bool = typer.Option(False, "--download-documents/--no-download-documents"),
    max_pages: int = typer.Option(10000, help="Maximum pages per company"),
    per_company: bool = typer.Option(False, "--per-company", help="Whole market: query each company "
                                                                  "separately (slow; the v2.0 method)"),
    refresh: bool = typer.Option(False, "--refresh", help="Whole market: fetch again days already finished "
                                                          "(by default a rerun carries on where the last one stopped)"),
    retry_shortfalls: bool = typer.Option(False, "--retry-shortfalls",
                                          help="Whole market: fetch again days recorded as short of CNINFO's total"),
):
    """Catalogue announcements from CNINFO for one company or the whole market, optionally downloading documents.

    Whole market (v2.0.3): one market-wide query per window; busy days are split so that every announcement
    arrives; each day's count is checked against CNINFO's total; finished days are remembered, so running the
    same action again carries on from the first unfinished day."""
    init_db()
    print(f"[cyan]Cataloguing CNINFO disclosures: {since} to {until}, kind={kind}...[/cyan]")
    result = catalogue_disclosures(
        since=since, until=until, kind=kind, security_code=security_code,
        download_documents=download_documents, max_pages=max_pages, progress=_progress,
        mode="company" if per_company else "auto", refresh=refresh, retry_shortfalls=retry_shortfalls,
    )
    _report_catalogue(result)


def _report_catalogue(result: dict) -> None:
    """Print a catalogue result. Exit codes: 0 complete; 3 finished with gaps (v2.0.4: a completed run with
    days short of CNINFO's total is not a failure); 1 failed days or a stopped run."""
    errors = result.pop("errors", [])
    shortfalls = result.pop("days_shortfall", [])
    outside = result.pop("days_gap_outside", [])
    failed = result.pop("days_failed", [])
    held = result.pop("held", [])
    print(result)
    if outside:
        print(f"{len(outside)} day(s) are complete within the enabled boards but CNINFO also lists announcements "
              "outside them that were not reached (for example the Beijing Stock Exchange when it is off):")
        for s in outside[:15]:
            print(f"  {s['day']}: {s['gap_out_scope']:,} outside the enabled boards")
    if shortfalls:
        print(f"[red]{len(shortfalls)} day(s) have a gap within the enabled boards (recorded as SHORTFALL):[/red]")
        for s in shortfalls[:30]:
            extra = f", {s['gap_out_scope']:,} outside them" if s.get("gap_out_scope") else ""
            print(f"  {s['day']}: {s['stored']:,} of {s['expected']:,} rows; "
                  f"{s.get('gap_in_scope', s['expected'] - s['stored']):,} missing within the enabled boards{extra}")
        print("'Which days are catalogued' (catalogue-days --problems) shows the cause recorded for each day. "
              "Re-cataloguing only helps after a change of method; if a gap remains, please report it with "
              "the output of probe-cninfo-filters.")
    if failed:
        print(f"[red]{len(failed)} day(s) failed: {', '.join(failed[:40])}{' ...' if len(failed) > 40 else ''}[/red]")
        print("Run the same action again to retry only these days.")
    elif errors:
        print(f"[yellow]Errors: {len(errors)} (run the same action again to retry)[/yellow]")
        for error in errors[:20]:
            print(error)
    if failed or result.get("stopped_early"):
        raise typer.Exit(code=1)
    if shortfalls:
        print(f"Finished with gaps: {len(shortfalls)} day(s) short within the enabled boards.")
        raise typer.Exit(code=3)


@app.command("diagnose-quote-list")
def diagnose_quote_list_cmd():
    """Why the public quote list (listing dates, daily snapshot) refuses requests: tries each request variant once,
    then page 11 of the whole list and of one board (about eight requests), and reports what each returned
    (findings 4 and 57)."""
    from .quotelist import diagnose
    r = diagnose()
    for e in r["results"]:
        if e.get("ok") and e.get("deep"):
            print(f"  [green]{e['variant']}: answered[/green], {e['rows']} rows; e.g. {e['sample']}")
        elif e.get("ok"):
            print(f"  [green]{e['variant']}: answered[/green], {e['total']:,} securities; e.g. {e['sample']}")
        else:
            print(f"  [red]{e['variant']}: {e['error']}[/red]")
    print(r["verdict"])
    if not r["working"]:
        raise typer.Exit(code=1)


@app.command("recatalogue-busy-days")
def recatalogue_busy_days_cmd(
    kind: str = typer.Option("all", help="Kind of announcement, as in catalogue-disclosures"),
    since: str = typer.Option(None, help="Only days from this date (YYYY-MM-DD)"),
    until: str = typer.Option(None, help="Only days up to this date (YYYY-MM-DD)"),
    threshold: int = typer.Option(2500, help="Days catalogued before v2.0.3 with at least this many stored "
                                             "announcements count as busy"),
    list_only: bool = typer.Option(False, "--list", help="Only list the days, do not fetch"),
    include_current: bool = typer.Option(False, "--include-current",
                                         help="Also fetch again days whose gap recurred under the current method"),
):
    """Fetch again the busy days that earlier versions cut short (findings 6 and 26).

    Busy days are failed days, days short of CNINFO's total under an earlier method (v2.0.3 or before), and
    days catalogued before v2.0.3 whose stored announcements reach the threshold. Days whose gap recurred under
    the current method are not fetched again unless --include-current is given, because repeating the same
    queries cannot close a gap caused by a limit of CNINFO's search."""
    from .market_catalogue import busy_days, recatalogue_busy_days
    init_db()
    if list_only:
        days = busy_days(kind, since, until, threshold, include_current)
        print(f"{len(days)} busy day(s): {', '.join(days) if days else 'none'}")
        return
    _report_catalogue(recatalogue_busy_days(kind, since, until, threshold, progress=_progress,
                                            include_current=include_current))


@app.command("catalogue-days")
def catalogue_days_cmd(kind: str = typer.Option("all"), since: str = typer.Option(None),
                       until: str = typer.Option(None),
                       problems: bool = typer.Option(False, "--problems", help="Only days not complete"),
                       by_day: bool = typer.Option(False, "--by-day", help="One row per day, also for windows "
                                                                           "of quiet days")):
    """Which days the market-wide catalogue has finished, with stored and expected counts. v2.0.6: the days of a
    window of quiet days, read as one query, are shown as one row with the window's total and gap."""
    from collections import Counter
    from .market_catalogue import day_status, units
    init_db()
    rows = day_status(kind, since, until)
    shown = rows if by_day else units(rows)
    counts = Counter(r["status"] for r in shown)
    print("Status: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "no days recorded yet")
          + ("" if by_day or len(shown) == len(rows) else
             f" ({len(rows):,} days; a window of quiet days counts once)"))
    if problems:
        shown = [r for r in shown if r["status"] not in ("DONE",)]
    _table(shown, ["day", "status", "expected", "stored", "gap_in_scope", "gap_out_scope", "rows_multi", "method",
                   "partition", "error"])


@app.command("probe-cninfo-filters")
def probe_cninfo_filters_cmd(day: str = typer.Option("2026-04-29", help="A very busy day"),
                             quiet_window: str = typer.Option("2026-01-09~2026-01-12",
                                                              help="A quiet window with repeated rows")):
    """Check which CNINFO search filters work for whole-market queries: board codes, industry, manufacturing
    divisions, company queries (up to 50 at once) and sort orders, and why rows repeat (about 200 to 270 requests;
    v2.0.4, company test and divisions v2.0.6, larger batches v2.0.7)."""
    from .market_catalogue import probe_filters
    r = probe_filters(day, quiet_window=quiet_window)
    print(f"{r['day']}: CNINFO reports {r.get('total', 0):,} announcements. Requests: {r.get('requests', 0)}.")
    if r.get("largest"):
        lg = r["largest"]
        print(f"Largest category and board: {lg['category'].rstrip(';')} on {lg['plate']}: {lg['total']:,}")
    for t in r["tests"]:
        print(f"  [bold]{t['test']}[/bold]: {t['verdict']}; {t['detail']}")
        if t.get("parts"):
            print("      " + ", ".join(f"{k} {v:,}" for k, v in t["parts"].items()))
    print("Keep this output with the run log; the catalogue checks the same things as it runs and uses only the "
          "filters that work.")


@app.command("probe-cninfo-paging")
def probe_cninfo_paging_cmd(day: str = typer.Option("2026-04-24", help="A busy day (more than 3,000 "
                                                                       "announcements)")):
    """Check whether one CNINFO query stops at 3,000 results (4 requests; finding 6)."""
    from .market_catalogue import probe_paging
    r = probe_paging(day)
    print(f"{r['day']}: CNINFO reports {r['total']:,} announcements.")
    for p, i in r["pages"].items():
        print(f"  page {p}: {i['items']} items, more to come: {i['has_more']}")
    for k in ("overlap_101_with_100", "new_on_101", "new_on_150"):
        if k in r:
            print(f"  {k.replace('_', ' ')}: {r[k]}")
    print(f"[bold]{r['verdict']}[/bold]: {r['explanation']}")


@app.command("download-documents")
def download_documents_cmd(kinds: str = typer.Option("annual_report", help="Comma-separated kinds, e.g. "
                                                     "annual_report,interim_report,quarterly_report"),
                           security_code: str = typer.Option(None)):
    """Download catalogued documents that are not yet on disk (resumable)."""
    from .disclosure_pipeline import download_pending
    ids = None
    if security_code:
        s = SessionLocal()
        try:
            from .models import Disclosure
            c = s.query(Company).filter_by(security_code=security_code.zfill(6)).first()
            ids = [d.id for d in s.query(Disclosure).filter_by(company_id=c.id)] if c else []
        finally:
            s.close()
    print(download_pending(ids, tuple(k.strip() for k in kinds.split(",") if k.strip()), progress=_progress))


@app.command("extract-financials")
def extract_financials_cmd(
    security_code: str = typer.Option(None, help="Optional six-digit code; omit for the whole universe"),
    kind: str = typer.Option("reports", help="reports, annual, interim, quarterly, or all"),
    limit: int = typer.Option(None, help="Optional maximum documents per company"),
    again: bool = typer.Option(False, "--again", help="Read every document again, including those already read "
                                                      "by this extractor version"),
):
    """Read headline figures and statements from downloaded periodic reports. v2.0.6: shows progress, and a
    stopped run continues with the next document when run again."""
    init_db()
    print(f"[cyan]Extracting financial facts: security={security_code or 'ALL'}, kind={kind}...[/cyan]")
    result = extract_financials(security_code=security_code, kind=kind, limit=limit, again=again,
                                progress=lambda m: print(m))
    print(result)
    if result["errors"]:
        print(f"[yellow]Errors: {len(result['errors'])}[/yellow]")
        for error in result["errors"][:20]:
            print(error)

@app.command("validate-financials")
def validate_financials_cmd(
    security_code: str = typer.Option(None, help="Optional six-digit code; omit for the whole database"),
):
    """Internal accounting checks on extracted financial values (flags only)."""
    init_db()
    result = validate_financials(security_code=security_code)
    print(result)
    if result["errors"]:
        print(f"[yellow]Balance-sheet exceptions: {len(result['errors'])}[/yellow]")
        for error in result["errors"][:20]:
            print(error)

@app.command("show-financials")
def show_financials(
    security_code: str,
    metric: str = typer.Option(None, help="Canonical metric such as revenue, net_profit, total_assets"),
    period: str = typer.Option(None, help="Reporting period YYYY-MM-DD"),
):
    """Extracted financial values of one company."""
    init_db()
    session = SessionLocal()
    try:
        company = session.query(Company).filter_by(security_code=security_code.zfill(6)).first()
        if not company:
            print("[yellow]No company found.[/yellow]")
            return
        q = session.query(FinancialFact).filter(FinancialFact.company_id == company.id)
        if metric:
            q = q.filter(FinancialFact.metric == metric)
        if period:
            q = q.filter(FinancialFact.reporting_period == period)
        for row in q.order_by(FinancialFact.reporting_period, FinancialFact.metric).all():
            print({
                "code": company.security_code,
                "period": row.reporting_period,
                "period_type": row.period_type,
                "metric": row.metric,
                "metric_cn": row.metric_cn,
                "value": row.value,
                "raw_value": row.raw_value,
                "unit": row.unit,
                "method": row.extraction_method,
                "confidence": row.confidence,
                "source_page": row.source_page,
                "source_xbrl_tag": row.source_xbrl_tag,
                "validation": row.validation_status,
            })
    finally:
        session.close()

@app.command("acquire-market")
def acquire_market_cmd(
    start: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end: str = typer.Option(..., help="End date YYYY-MM-DD"),
    security_code: str = typer.Option(None, help="Optional six-digit code; omit for the whole universe"),
    provider: str = typer.Option("eastmoney", help="Market provider: eastmoney"),
    adjust: str = typer.Option("none", help="none, forward, or backward"),
):
    """Download daily prices for one company (or all) from the public price feed."""
    init_db()
    print(f"[cyan]Acquiring market data: {start} to {end}, provider={provider}, adjustment={adjust}...[/cyan]")
    result = acquire_market_data(security_code, start, end, provider, adjust)
    print(result)

@app.command("import-market-csv")
def import_market_csv_cmd(
    path: str,
    security_code: str = typer.Option(None, help="Optional code when the CSV contains one security"),
    source: str = typer.Option("CSV_IMPORT", help="Provenance label for the imported dataset"),
):
    """Import daily prices from a CSV file (e.g. a licensed vendor export)."""
    init_db()
    print(import_bars_csv(path, security_code=security_code, source=source))

@app.command("show-market")
def show_market_cmd(
    security_code: str,
    start: str = typer.Option(None, help="Optional start date YYYY-MM-DD"),
    end: str = typer.Option(None, help="Optional end date YYYY-MM-DD"),
):
    """Stored daily prices of one company."""
    init_db()
    for row in show_market(security_code, start, end):
        print({
            "code": security_code.zfill(6), "date": row.trade_date,
            "open": row.open, "high": row.high, "low": row.low, "close": row.close,
            "prev_close": row.prev_close, "volume": row.volume, "amount": row.amount,
            "pct_change": row.pct_change, "turnover_rate": row.turnover_rate,
            "adjustment": row.adjustment, "source": row.source,
        })

@app.command("import-ownership-csv")
def import_ownership_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import shareholder observations from a CSV file."""
    init_db(); print(import_ownership_csv(path, source=source))

@app.command("import-capital-csv")
def import_capital_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import share-capital observations from a CSV file."""
    init_db(); print(import_capital_csv(path, source=source))

@app.command("ownership-disclosures")
def ownership_disclosures_cmd(security_code: str = typer.Option(None)):
    """List catalogued announcements about shareholding and capital changes (one company or all)."""
    init_db(); rows=catalogue_ownership_disclosures(security_code); print({"count":len(rows)}); [print(r) for r in rows[:100]]

@app.command("show-ownership")
def show_ownership_cmd(security_code: str, shareholder: str = typer.Option(None)):
    """Shareholders of one company."""
    init_db(); rows=show_ownership(security_code, shareholder); [print({"date":r.observation_date,"rank":r.rank,"shareholder":r.shareholder_name,"shares":r.shares,"ownership_pct":r.ownership_pct,"pledged":r.pledged_shares,"restricted":r.restricted_shares,"control":r.is_controlling_shareholder,"actual_controller":r.is_actual_controller,"source":r.source}) for r in rows]

@app.command("show-capital")
def show_capital_cmd(security_code: str):
    """Share-capital observations of one company."""
    init_db(); rows=show_capital(security_code); [print({"date":r.observation_date,"total_shares":r.total_shares,"tradable":r.tradable_shares,"restricted":r.restricted_shares,"A":r.a_shares,"B":r.b_shares,"H":r.h_shares,"treasury":r.treasury_shares,"source":r.source}) for r in rows]


@app.command("validate-ownership")
def validate_ownership_cmd(security_code: str = typer.Option(None)):
    """Internal checks on ownership and capital observations (flags only)."""
    result = validate_ownership(security_code)
    print({k: v for k, v in result.items() if k != "errors"})
    for e in result["errors"][:30]:
        print(e)


@app.command("extract-corporate-actions")
def extract_corporate_actions_cmd(
    security_code: str = typer.Option(None, help="Optional six-digit code; omit for all catalogued disclosures"),
    use_documents: bool = typer.Option(True, "--use-documents/--titles-only", help="Parse downloaded documents where available"),
):
    """Classify catalogued disclosures and extract corporate-action observations."""
    init_db()
    result = extract_corporate_actions(security_code, use_documents=use_documents)
    print(result)


@app.command("import-corporate-actions-csv")
def import_corporate_actions_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import structured corporate actions from an authorised dataset."""
    init_db()
    print(import_corporate_actions_csv(path, source=source))


@app.command("show-actions")
def show_actions_cmd(security_code: str, action_type: str = typer.Option(None)):
    """Corporate actions of one company."""
    for r in show_actions(security_code, action_type):
        print({
            "id": r.id, "type": r.action_type, "status": r.status,
            "announced": r.announcement_date, "record": r.record_date, "ex": r.ex_date,
            "pay": r.payment_date, "listing": r.listing_date, "capital_date": capital_effective_date(r),
            "ratio": r.ratio, "cash_per_share": r.cash_amount, "share_delta": r.share_delta,
            "shares_affected": r.shares_affected, "old_total": r.old_share_count, "new_total": r.new_share_count,
            "price": r.issue_price or r.subscription_price, "method": r.extraction_method,
            "confidence": r.confidence, "validation": r.validation_status, "source": r.source,
            "page": r.source_page,
        })


@app.command("reconcile-capital")
def reconcile_capital_cmd(
    security_code: str = typer.Option(None),
    capital_source: str = typer.Option(None, help="Restrict to one capital-structure source"),
    relative_tolerance: float = typer.Option(1e-5),
    absolute_tolerance: float = typer.Option(10.0),
):
    """Check capital(t0) + corporate actions = capital(t1); flags, never overwrites."""
    result = reconcile_capital(security_code, capital_source, relative_tolerance, absolute_tolerance)
    print({k: v for k, v in result.items() if k != "results"})
    for r in result["results"][:50]:
        print(r)



@app.command("extract-regulatory-events")
def extract_regulatory_events_cmd(
    security_code: str = typer.Option(None, help="Optional six-digit code"),
    use_documents: bool = typer.Option(True, "--use-documents/--titles-only"),
):
    """Classify catalogued announcements into regulatory and legal events."""
    init_db()
    print(extract_regulatory_events(security_code, use_documents=use_documents))


@app.command("import-regulatory-document")
def import_regulatory_document_cmd(
    path_or_url: str,
    security_code: str = typer.Option(None, help="Company the document concerns (else detected from text)"),
    source: str = typer.Option(None, help="Provenance label (default: detected authority)"),
):
    """Import one CSRC/exchange decision from a local file or a URL you supply."""
    init_db()
    print(import_regulatory_document(path_or_url, security_code, source))


@app.command("import-regulatory-csv")
def import_regulatory_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import regulatory and legal events from a CSV file."""
    init_db()
    print(import_regulatory_csv(path, source=source))


@app.command("show-events")
def show_events_cmd(security_code: str, classification: str = typer.Option(None)):
    """Regulatory and legal events of one company."""
    for e in show_events(security_code, classification):
        print({
            "id": e.id, "date": e.event_date, "type": e.event_type, "subtype": e.event_subtype,
            "classification": e.legal_classification, "status": e.status,
            "authority": e.authority_name or e.authority, "document_number": e.document_number,
            "case_number": e.case_number, "fine_total": e.fine_amount_total,
            "fine_company": e.fine_amount_company, "amount_in_dispute": e.amount_in_dispute,
            "role": e.company_role, "violations": e.violation_categories,
            "method": e.extraction_method, "confidence": e.confidence, "title": e.title_cn,
        })


@app.command("regulatory-status")
def regulatory_status_cmd(security_code: str, as_of: str = typer.Option(None, help="Point-in-time date YYYY-MM-DD")):
    """Point-in-time regulatory profile, with the events each state rests on."""
    print(regulatory_status(security_code, as_of))


@app.command("export")
def export_cmd(
    table: str = typer.Argument(..., help="Table name, or 'all'"),
    out_dir: str = typer.Option("exports", help="Output folder"),
    security_code: str = typer.Option(None, help="Restrict to one company"),
):
    """Export tables to UTF-8 CSV (opens correctly in Excel)."""
    init_db()
    for path, n in export_table(table, out_dir, security_code):
        print(f"{path}: {n} rows")


# ---------------------------------------------------------------------------
# v1.0 integrated intelligence
# ---------------------------------------------------------------------------

@app.command("link-events")
def link_events_cmd(security_code: str = typer.Option(None)):
    """Link related regulatory events and group corporate-action lifecycles."""
    print(link_all(security_code))


@app.command("validate-all")
def validate_all_cmd(security_code: str = typer.Option(None)):
    """Run every validation stage (schema, internal, cross-document, cross-source)."""
    r = validate_all(security_code)
    cross = r["stage3_4_cross_validation"]
    rows = [
        {"stage": "1 Schema", "check": "Universe codes, exchanges, boards", "result": f"{r['stage1_universe_problems']} problem(s)"},
        {"stage": "-", "check": "Event linking", "result": r["event_linking"]},
        {"stage": "2 Internal", "check": "Balance sheet identity", "result": r["stage2_financial_balance"]},
        {"stage": "2 Internal", "check": "Ownership and capital", "result": r["stage2_ownership"]},
        {"stage": "2 Internal", "check": "Capital reconciliation", "result": r["stage2_capital_reconciliation"]},
        {"stage": "3-4 Cross", "check": "Restatements, interim vs annual, sources",
         "result": f"{cross['total_flags']} flag(s) " + (_fmt(cross["flags"]) if cross["flags"] else "")},
    ]
    _table(rows, ["stage", "check", "result"], title="Validation summary")
    print("Details: show-flags (findings never change the data).")


@app.command("show-flags")
def show_flags_cmd(security_code: str = typer.Option(None), severity: str = typer.Option(None),
                   rule: str = typer.Option(None)):
    """Validation flags, optionally for one company."""
    rows = [{"id": f.id, "severity": f.severity, "rule": f.rule, "layer": f.layer, "table": f.table_name,
             "rows": f.row_ids, "details": f.details} for f in show_flags(security_code, severity, rule)]
    _table(rows, title="Validation flags")


@app.command("profile")
def profile_cmd(security_code: str, as_of: str = typer.Option(None, help="Use only information published by this date")):
    """Integrated company profile (point in time)."""
    print(company_profile(security_code, as_of))


@app.command("financial-series")
def financial_series_cmd(
    security_code: str, metric: str = typer.Option("revenue"),
    period_type: str = typer.Option(None, help="FY, H1, Q1 or Q3"),
    as_of: str = typer.Option(None), vintage: str = typer.Option("latest", help="latest or original"),
):
    """Point-in-time series of one metric, with vintages and restatement marks."""
    _table(financial_series(security_code, metric, as_of, period_type, vintage),
           ["period", "period_type", "value", "unit", "published", "method", "confidence_class", "vintages", "restated"],
           title=f"{security_code} {metric}")


@app.command("compare")
def compare_cmd(
    codes: str = typer.Option(..., help="Comma-separated codes, e.g. 600519,000858"),
    metrics: str = typer.Option("revenue,net_profit,total_assets,total_liabilities"),
    period: str = typer.Option(None, help="Reporting period YYYY-MM-DD (default: latest per company)"),
    period_type: str = typer.Option("FY"), as_of: str = typer.Option(None),
):
    """Cross-company comparison with derived ratios."""
    res = compare([c.strip() for c in codes.split(",") if c.strip()], [m.strip() for m in metrics.split(",")],
                  period, period_type, as_of)
    cols = ["code"] + [m for m in res["metrics"]] + [c for c in ("net_margin", "liabilities_to_assets", "rd_intensity")
                                                    if any(c in r for r in res["rows"])]
    _table(res["rows"], cols, title="Comparison")


@app.command("market-stats")
def market_stats_cmd(security_code: str, start: str = typer.Option(None), end: str = typer.Option(None),
                     adjustment: str = typer.Option("none"), source: str = typer.Option(None)):
    """Return, volatility, drawdown and liquidity for one price series."""
    print(market_stats(security_code, start, end, adjustment, source))


@app.command("timeline")
def timeline_cmd(security_code: str, since: str = typer.Option(None), until: str = typer.Option(None)):
    """Chronology across corporate actions, regulatory events, capital and reports."""
    _table(timeline(security_code, since, until), ["date", "layer", "type", "status", "detail"], title="Timeline")


@app.command("report")
def report_cmd(security_code: str, as_of: str = typer.Option(None), out: str = typer.Option(None)):
    """Write a self-contained HTML company report."""
    print(f"Report written: {write_profile_report(security_code, out, as_of)}")


@app.command("search-disclosures")
def search_disclosures_cmd(query: str = typer.Argument(""), security_code: str = typer.Option(None),
                           since: str = typer.Option(None), until: str = typer.Option(None),
                           kind: str = typer.Option(None), limit: int = typer.Option(200)):
    """Search announcement titles (all words must appear)."""
    _table(search_disclosures(query, security_code, since, until, kind, limit),
           ["disclosure_id", "code", "date", "kind", "title", "downloaded"], title="Disclosures")


@app.command("index-documents")
def index_documents_cmd(security_code: str = typer.Option(None), reindex: bool = typer.Option(False)):
    """Extract text of downloaded documents for full-text search."""
    print(index_documents(security_code, reindex))


@app.command("search-documents")
def search_documents_cmd(query: str, security_code: str = typer.Option(None), limit: int = typer.Option(50)):
    """Full-text search inside downloaded documents."""
    _table(search_documents(query, security_code, limit), ["code", "date", "disclosure_id", "page", "title", "snippet"],
           title=f"Documents containing '{query}'")


@app.command("inspect-document")
def inspect_document_cmd(disclosure_id: int, page: int = typer.Option(None)):
    """Show a source document's metadata, hash check and page text."""
    print(inspect_document(disclosure_id, page))


@app.command("trace")
def trace_cmd(table: str, row_id: int):
    """Full provenance chain of one observation, with document hash check."""
    print(trace(table, row_id))


@app.command("query")
def query_cmd(sql: str, out: str = typer.Option(None, help="Write results to this file"),
              name: str = typer.Option(None, help="Name to record in the query log"),
              fmt: str = typer.Option("csv", help="csv or parquet")):
    """Run a logged, read-only SQL query against the database."""
    res = run_query(sql, out, name, fmt)
    rows = [dict(zip(res["columns"], r)) for r in res["rows"][:200]]
    _table(rows, res["columns"], title=f"Query #{res['log_id']} ({res['row_count']} rows)")
    if res["output"]:
        print(f"Saved {res['output']} (sha256 {res['output_sha256'][:16]}…)")


@app.command("release")
def release_cmd(out_dir: str = typer.Option("releases"), name: str = typer.Option(None),
                security_code: str = typer.Option(None),
                formats: str = typer.Option("csv,sqlite", help="Any of csv, sqlite, parquet"),
                include_licensed: bool = typer.Option(False, "--include-licensed",
                                                      help="Keep LICENSED rows (for private use only)"),
                exclude: str = typer.Option("", help="Further licence classes to leave out, e.g. PUBLIC_FEED"),
                pseudonymise: bool = typer.Option(False, "--pseudonymise",
                                                  help="Replace natural persons' names with keyed identifiers"),
                key_file: str = typer.Option(None, help="Pseudonymisation key (default: pseudonym.key in the "
                                                        "data folder, created on first use)"),
                coarsen: bool = typer.Option(False, "--coarsen", help="With --pseudonymise: ages and birth "
                                                                       "years in five-year bands"),
                drop_free_text: bool = typer.Option(False, "--drop-free-text",
                                                    help="With --pseudonymise: drop titles and other free text"),
                author: str = typer.Option(None, help="Author name for CITATION.cff")):
    """Write a versioned dataset release: licence-aware, with a quality report and citation (v2.0)."""
    from .release import build_release
    r = build_release(out_dir, name, security_code, tuple(f.strip() for f in formats.split(",") if f.strip()),
                      include_licensed=include_licensed,
                      exclude=tuple(x.strip() for x in exclude.split(",") if x.strip()),
                      pseudonymise=pseudonymise, key_file=key_file, coarsen=coarsen,
                      drop_free_text=drop_free_text, author=author)
    print(r)


# ---------------------------------------------------------------------------
# v2.0 schema, licences, quality, updates
# ---------------------------------------------------------------------------

@app.command("db-status")
def db_status_cmd():
    """Schema revision of the database and the migration history."""
    from .migrate import status
    st = status()
    print({"current": st["current"], "head": st["head"], "up_to_date": st["up_to_date"]})
    _table(st["history"], ["revision", "down_revision", "message"], title="Migrations")


@app.command("db-upgrade")
def db_upgrade_cmd(no_backup: bool = typer.Option(False, "--no-backup", help="Skip the backup copy (SQLite)")):
    """Upgrade the database to the current schema (done automatically on start)."""
    from .migrate import upgrade
    print(upgrade(backup=not no_backup))


@app.command("licences")
def licences_cmd():
    """Rows per table by licence class and source label."""
    from .licences import licence_summary, DESCRIPTIONS
    _table([{"class": k, "meaning": v} for k, v in DESCRIPTIONS.items()], title="Licence classes")
    _table(licence_summary(), ["table", "licence", "source", "rows"], title="Rows by licence")


@app.command("set-licence")
def set_licence_cmd(source: str, licence: str = typer.Argument(..., help="PUBLIC_DISCLOSURE, PUBLIC_FEED, "
                                                                          "DERIVED, MANUAL or LICENSED")):
    """Tag a source label (e.g. an import label) with a licence class."""
    from .licences import set_licence
    print(set_licence(source, licence))


@app.command("quality-report")
def quality_report_cmd(out_dir: str = typer.Option("reports/quality")):
    """Write the data-quality report for the working database."""
    from .quality import write_quality_report
    r = write_quality_report(out_dir)
    print({"folder": out_dir, "files": r["files"], **r["summary"]})


@app.command("check-update")
def check_update_cmd(url: str = typer.Option(None, help="Update information URL (HTTPS)")):
    """Check whether a newer version is published (only if an update URL is configured)."""
    from .update import check_for_update
    print(check_for_update(url))


# ---------------------------------------------------------------------------
# v1.1 industry classification and management
# ---------------------------------------------------------------------------

@app.command("import-industry-csv")
def import_industry_csv_cmd(path: str, scheme: str = typer.Option(..., help="CSRC_2012, SW_2021, CNINFO, CSRC_OTHER or CUSTOM"),
                            source: str = typer.Option("CSV_IMPORT"),
                            effective_date: str = typer.Option(None, help="Date for files without a date column")):
    """Import industry classifications (English or Chinese column headers)."""
    print(import_industry_csv(path, scheme, source, effective_date))


@app.command("show-industry")
def show_industry_cmd(security_code: str):
    """Industry classifications of one company over time."""
    rows = [{"scheme": r.scheme, "since": r.effective_date, "level1": f"{r.level1_code or ''} {r.level1_name or ''}",
             "level2": f"{r.level2_code or ''} {r.level2_name or ''}", "source": r.source,
             "check": r.validation_status} for r in industry_history(security_code)]
    _table(rows, title=f"{security_code} industry classification history")


@app.command("peers")
def peers_cmd(security_code: str, scheme: str = typer.Option("CSRC_2012"), level: int = typer.Option(2),
              as_of: str = typer.Option(None)):
    """Companies in the same industry at a date."""
    r = peers(security_code, scheme, level, as_of)
    if "error" in r:
        print(r["error"]); return
    _table(r["peers"], ["code", "name", "board", "since"],
           title=f"{r['industry_code'] or ''} {r['industry_name'] or ''} ({scheme}, level {level})")


@app.command("industry-stats")
def industry_stats_cmd(security_code: str, metric: str = typer.Option("revenue", help="A metric, or a ratio: "
                       "net_margin, liabilities_to_assets, rd_intensity, roa, roe"),
                       scheme: str = typer.Option("CSRC_2012"), level: int = typer.Option(2),
                       period: str = typer.Option(None), as_of: str = typer.Option(None),
                       min_class: str = typer.Option("LOW", help="Exclude values below HIGH, MEDIUM or LOW confidence")):
    """Industry distribution of a metric and the company's percentile."""
    r = industry_stats(security_code, metric, scheme, level, period, "FY", as_of, min_class)
    r.pop("values", None)
    print(r)


@app.command("industry-summary")
def industry_summary_cmd(scheme: str = typer.Option("CSRC_2012"), level: int = typer.Option(1), as_of: str = typer.Option(None)):
    """Number of companies per industry."""
    _table(industry_summary(scheme, level, as_of), ["code", "name", "companies"], title=f"{scheme} level {level}")


@app.command("extract-management")
def extract_management_cmd(security_code: str = typer.Option(None),
                           use_documents: bool = typer.Option(True, "--use-documents/--titles-only")):
    """Appointments and resignations from announcements, and officer tables from annual reports."""
    print({"events": extract_management_events(security_code, use_documents),
           "annual_report_rosters": extract_rosters(security_code) if use_documents else "skipped"})


@app.command("import-management-csv")
def import_management_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import roster observations (one row per person and date)."""
    print(import_management_csv(path, source))


@app.command("import-management-events-csv")
def import_management_events_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import appointment and resignation events from a CSV file."""
    print(import_management_events_csv(path, source))


@app.command("roster")
def roster_cmd(security_code: str, as_of: str = typer.Option(None)):
    """Directors, supervisors and executives in office at a date."""
    r = roster_at(security_code, as_of)
    if "error" in r:
        print(r["error"]); return
    _table(r["members"], ["role", "role_cn", "person", "gender", "age", "tenure_start", "remuneration", "basis"],
           title=f"{r['code']} roster as of {as_of or 'latest'} (base roster {r['base_roster_date']})")
    if r["pending_resignations"]:
        _table(r["pending_resignations"], title="Resignations not yet effective")


@app.command("show-management-events")
def show_management_events_cmd(security_code: str):
    """Appointments and resignations of one company."""
    rows = [{"date": e.event_date, "type": e.event_type, "person": e.person_name, "role": e.role,
             "effective": e.effective_date, "reason": e.reason, "stays": e.remains_with_company,
             "method": e.extraction_method} for e in show_management_events(security_code)]
    _table(rows, title=f"{security_code} management events")


@app.command("governance")
def governance_cmd(security_code: str, as_of: str = typer.Option(None)):
    """Board size and independence, CEO duality, turnover, and legal reference checks."""
    print(governance(security_code, as_of))


# ---------------------------------------------------------------------------
# v1.2 segments and group structure
# ---------------------------------------------------------------------------

@app.command("extract-segments")
def extract_segments_cmd(security_code: str = typer.Option(None)):
    """Read revenue-composition and segment-margin tables from downloaded annual and interim reports."""
    print(extract_segments(security_code))


@app.command("import-segments-csv")
def import_segments_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import segment observations from a CSV file."""
    print(import_segments_csv(path, source))


@app.command("segments")
def segments_cmd(security_code: str, period: str = typer.Option(None), dimension: str = typer.Option(None,
                 help="INDUSTRY, PRODUCT, REGION, SALES_MODEL or REPORTABLE_SEGMENT"), as_of: str = typer.Option(None)):
    """Segments for one period with shares, growth, margins, overseas share and concentration."""
    r = segments_view(security_code, period, dimension, as_of)
    if "error" in r:
        print(r["error"]); return
    if not r["dimensions"]:
        print("No segment data."); return
    for dim, v in r["dimensions"].items():
        extra = f", overseas share {v['regional']['overseas_share']:.1%}" if v.get("regional") else ""
        hhi = f"HHI {v['hhi']:.3f}, effective segments {v['effective_segments']:.1f}" if v.get("hhi") else ""
        _table(v["segments"], ["name", "revenue", "share", "yoy", "gross_margin", "region", "page"],
               title=f"{r['code']} {r['period']} {dim}  ({hhi}{extra})")
    print(r["note"])


@app.command("segment-history")
def segment_history_cmd(security_code: str, dimension: str = typer.Option("PRODUCT")):
    """Each segment's revenue across reporting periods."""
    _table(segment_history(security_code, dimension), title=f"{security_code} {dimension} revenue by period")


@app.command("extract-subsidiaries")
def extract_subsidiaries_cmd(security_code: str = typer.Option(None)):
    """Read the group-composition and major-subsidiary tables from downloaded reports."""
    print(extract_subsidiaries(security_code))


@app.command("import-subsidiaries-csv")
def import_subsidiaries_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Import subsidiary observations from a CSV file."""
    print(import_subsidiaries_csv(path, source))


@app.command("subsidiaries")
def subsidiaries_cmd(security_code: str, as_of: str = typer.Option(None), date: str = typer.Option(None)):
    """Group structure: subsidiaries, associates, stakes, jurisdictions, offshore entities."""
    r = subsidiaries_view(security_code, as_of, date)
    if "error" in r:
        print(r["error"]); return
    if not r["entities"]:
        print("No subsidiary data."); return
    _table(r["entities"], ["name", "relationship", "pct", "direct", "indirect", "jurisdiction", "registered",
                           "business", "acquired_by"], title=f"{r['code']} group structure at {r['date']}")
    print(r["summary"])
    print(r["notes"][0])


@app.command("scope-changes")
def scope_changes_cmd(security_code: str, date_from: str = typer.Option(None, "--from"),
                      date_to: str = typer.Option(None, "--to")):
    """Entities added to or removed from the group between two reporting dates."""
    r = scope_changes(security_code, date_from, date_to)
    if "error" in r:
        print(r["error"]); return
    print(f"{r['code']}: {r['from']} -> {r['to']}")
    _table(r["added"], title="Added")
    _table(r["removed"], title="Removed")
    _table(r["stake_or_status_changed"], title="Stake or status changed")
    print(r["note"])


# ---------------------------------------------------------------------------
# v1.3 R&D, human capital and ESG
# ---------------------------------------------------------------------------

@app.command("extract-human-capital")
def extract_human_capital_cmd(security_code: str = typer.Option(None)):
    """Read the R&D table, workforce composition, education and patents from downloaded reports."""
    print(extract_human_capital(security_code))


@app.command("import-human-capital-csv")
def import_human_capital_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Long format: security_code, reporting_period, item, value. Items: see 'human-capital-items'."""
    print(import_human_capital_csv(path, source))


@app.command("human-capital-items")
def human_capital_items_cmd():
    """R&D and workforce items that can be extracted or imported."""
    _table([{"item": k, "category": v[0], "unit": v[1], "label": v[2]} for k, v in HC_ITEMS.items()])


@app.command("human-capital")
def human_capital_cmd(security_code: str, period: str = typer.Option(None), as_of: str = typer.Option(None)):
    """R&D and workforce for one period, with derived ratios."""
    r = human_capital(security_code, period, as_of)
    if "error" in r:
        print(r["error"]); return
    if not r["values"]:
        print("No R&D or workforce data."); return
    _table([{"item": k, "label": HC_ITEMS[k][2], "value": x, "unit": HC_ITEMS[k][1],
             "page": r["provenance"].get(k, {}).get("page"), "method": r["provenance"].get(k, {}).get("method")}
            for k, x in r["values"].items()], title=f"{r['code']} {r['period']}")
    _table([{"measure": k, "value": x} for k, x in r["derived"].items()], title="Derived")


@app.command("human-capital-history")
def human_capital_history_cmd(security_code: str):
    """R&D investment, intensity, staff, employees and patents across periods."""
    _table(human_capital_history(security_code), title=f"{security_code} R&D and workforce by period")


@app.command("extract-esg")
def extract_esg_cmd(security_code: str = typer.Option(None)):
    """Read environmental and social data from annual and sustainability reports."""
    print(extract_esg(security_code))


@app.command("import-esg-csv")
def import_esg_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Long format: security_code, reporting_period, item, value. Items: see 'esg-items'."""
    print(import_esg_csv(path, source))


@app.command("esg-items")
def esg_items_cmd():
    """ESG items that can be extracted or imported."""
    _table([{"item": k, "pillar": v[0], "unit": v[1], "label": v[2]} for k, v in ESG_ITEMS.items()])


@app.command("import-esg-ratings-csv")
def import_esg_ratings_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Third-party ESG ratings: security_code, provider, rating_date, rating, score, pillar_e/s/g."""
    print(import_esg_ratings_csv(path, source))


@app.command("esg")
def esg_cmd(security_code: str, year: int = typer.Option(None), as_of: str = typer.Option(None)):
    """ESG profile for one fiscal year: disclosed E and S data, governance, regulatory actions, ratings."""
    print(esg_profile(security_code, year, as_of))

# --- v1.4: live verification and parser evaluation ------------------------------

@app.command("self-test")
def self_test_cmd(out: str = typer.Option("selftest", help="Folder for selftest_report.json and .html"),
                  offline: bool = typer.Option(False, "--offline", help="Use built-in canned responses (no network)")):
    """Check that each public source still answers in the expected shape."""
    from .selftest import run_selftest
    r = run_selftest(out, offline=offline)
    colours = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "NETWORK_UNREACHABLE": "dim"}
    con = _console()
    for row in r["results"]:
        c = colours[row["status"]]
        con.print(f"[{c}]{row['status']:<20}[/{c}] {row['check']:<34} {row['detail']}")
    s = r["summary"]
    con.print(f"[bold]Verdict: {r['verdict']}[/bold]  ({s['PASS']} pass, {s['WARN']} warn, {s['FAIL']} fail, "
              f"{s['NETWORK_UNREACHABLE']} unreachable; mode {r['mode']})")
    for f in r.get("files", []):
        con.print(f"Report: {f}")


@app.command("synthetic-corpus")
def synthetic_corpus_cmd(out: str = typer.Option("corpus_synthetic", help="Folder to create"),
                         reports: int = typer.Option(8, help="Number of annual-report documents"),
                         notices: int = typer.Option(4, help="Number of each announcement type"),
                         seed: int = typer.Option(20260101, help="Random seed"),
                         fmt: str = typer.Option("auto", help="pdf, txt or auto")):
    """Write a synthetic golden corpus (regression checks only, never calibration)."""
    from .corpus import build_synthetic_corpus
    print(build_synthetic_corpus(out, reports, notices, seed, fmt))


@app.command("corpus-template")
def corpus_template_cmd(corpus: str = typer.Option(..., help="Corpus folder (created if missing)"),
                        document: str = typer.Option(..., help="PDF path, or a disclosure id from the database"),
                        doc_id: str = typer.Option(None, help="Identifier for the document"),
                        title: str = typer.Option(None, help="Announcement title (used to pick parsers)"),
                        date: str = typer.Option(None, help="Announcement date YYYY-MM-DD"),
                        parsers: str = typer.Option(None, help="Comma-separated parser names (default: by document type)")):
    """Add a document to a golden corpus with a draft expected file to verify by hand."""
    from .evaluation import corpus_template
    init_db()
    r = corpus_template(corpus, document, doc_id, title, date, None,
                        [p.strip() for p in parsers.split(",")] if parsers else None)
    print(r)
    print("[yellow]Open the expected file, check every value against the document, then set "
          "\"verified\": true.[/yellow]")


@app.command("evaluate-parsers")
def evaluate_parsers_cmd(corpus: str = typer.Option(..., help="Corpus folder with manifest.json"),
                         parsers: str = typer.Option(None, help="Comma-separated parser names (default: all)"),
                         baseline: str = typer.Option(None, help="Baseline JSON to compare against"),
                         max_drop: float = typer.Option(1.0, help="Fail if precision falls more than this many points"),
                         write_baseline: str = typer.Option(None, help="Write this run as a baseline JSON"),
                         calibrate: bool = typer.Option(False, "--calibrate",
                                                        help="Store results as confidence calibration (verified real corpora)"),
                         include_unverified: bool = typer.Option(False, "--include-unverified"),
                         report: str = typer.Option(None, help="Write the full result (with every error) as JSON"),
                         errors: int = typer.Option(10, help="Number of error examples to print")):
    """Measure parser precision, recall and abstention on a golden corpus."""
    import json as _json
    from .evaluation import evaluate_corpus, gate, baseline_from, save_calibration
    r = evaluate_corpus(corpus, [p.strip() for p in parsers.split(",")] if parsers else None, include_unverified)
    rows = [{"parser": p, "docs": m["documents"], "expected": m["expected"], "correct": m["correct"],
             "wrong": m["wrong"], "missed": m["missed"], "spurious": m["spurious"],
             "precision": None if m["precision"] is None else f"{m['precision']:.1%}",
             "recall": None if m["recall"] is None else f"{m['recall']:.1%}",
             "abstention": None if m["abstention"] is None else f"{m['abstention']:.1%}"}
            for p, m in r["parsers"].items()]
    _table(rows, title=f"Parser evaluation: {r['corpus']}" + (" (synthetic)" if r["synthetic"] else ""))
    if r["skipped"]:
        print(f"[yellow]Skipped {len(r['skipped'])} document(s): "
              + ", ".join(f"{s['id']} ({s['reason']})" for s in r["skipped"][:5]) + "[/yellow]")
    if errors and r["errors"]:
        _table([{k: e.get(k) for k in ("document", "parser", "key", "field", "outcome", "expected", "predicted")}
                for e in r["errors"][:errors]], title="Examples of errors")
    if report:
        open(report, "w", encoding="utf-8").write(_json.dumps(r, ensure_ascii=False, indent=2, default=str))
        print(f"Full result: {report}")
    if write_baseline:
        open(write_baseline, "w", encoding="utf-8").write(_json.dumps(baseline_from(r), ensure_ascii=False, indent=2))
        print(f"Baseline written: {write_baseline}")
    if calibrate:
        init_db()
        n = save_calibration(r)
        note = " (synthetic: stored for reference, not used for confidence)" if r["synthetic"] else ""
        print(f"[green]Calibration stored for {n} parser/field rows{note}.[/green]")
    if baseline:
        g = gate(r, _json.loads(open(baseline, encoding="utf-8").read()), max_drop)
        for w in g["warnings"]:
            print(f"[yellow]{w}[/yellow]")
        if not g["passed"]:
            for f in g["failures"]:
                print(f"[red]{f}[/red]")
            raise typer.Exit(code=1)
        print(f"[green]Gate passed (precision drop within {max_drop} points).[/green]")


@app.command("calibration")
def calibration_cmd():
    """Show stored parser calibration and whether it is in use."""
    from .evaluation import calibration_table
    rows = [r for r in calibration_table() if r["field"] == "*"]
    for r in rows:
        r["precision"] = None if r["precision"] is None else f"{r['precision']:.1%}"
        r["precision_lower"] = None if r["precision_lower"] is None else f"{r['precision_lower']:.1%}"
        r["recall"] = None if r["recall"] is None else f"{r['recall']:.1%}"
    _table(rows, ["parser", "synthetic", "version", "predicted", "precision", "precision_lower", "recall", "in_use",
                  "corpus"], title="Parser calibration")


@app.command("parsers")
def parsers_cmd():
    """List the document parsers that the evaluation harness knows."""
    from .evaluation import PARSERS
    _table([{"parser": s.name, "version": s.version, "method": s.method, "documents": ", ".join(s.doc_kinds),
             "key": ", ".join(s.key), "description": s.description} for s in PARSERS.values()])


# --- v1.5: review workflow, document checks and charts ---------------------------

@app.command("scan-documents")
def scan_documents_cmd(code: str = typer.Option(None, "--security-code", "--code", help="One company (default: all)"),
                       recheck: bool = typer.Option(False, "--recheck", help="Check again documents already checked")):
    """Find downloaded PDFs without a text layer (scanned), which no parser can read."""
    from .layout import scan_documents
    r = scan_documents(code, recheck)
    print({k: v for k, v in r.items() if k != "scanned"})
    if r["scanned"]:
        _table(r["scanned"], title="Scanned or partly scanned documents (enter values manually or import them)")


@app.command("build-review-queue")
def build_review_queue_cmd(code: str = typer.Option(None, "--security-code", "--code", help="One company (default: all)"),
                           below: float = typer.Option(0.6, help="Queue values with confidence below this")):
    """Collect flags, parser disagreements and low-confidence values for review."""
    from .review import build_review_queue
    print(build_review_queue(code, below))


@app.command("review-queue")
def review_queue_cmd(code: str = typer.Option(None, "--security-code", "--code"),
                     status: str = typer.Option("OPEN", help="OPEN, DEFERRED, ACCEPTED, CORRECTED, REJECTED, OBSOLETE or ALL"),
                     limit: int = typer.Option(50)):
    """List review items, most material first."""
    from .review import review_queue
    _table(review_queue(code, status, limit), ["id", "code", "kind", "rule", "severity", "item", "field", "value",
                                               "confidence", "materiality", "status"])


@app.command("review-show")
def review_show_cmd(item_id: int):
    """Show one review item with its provenance trace and earlier decisions."""
    import json as _json
    from .review import review_item
    print(_json.dumps(review_item(item_id), ensure_ascii=False, indent=2, default=str))


@app.command("review")
def review_cmd(item_id: int,
               action: str = typer.Option(..., help="accept, correct, reject (not disclosed) or defer"),
               value: str = typer.Option(None, help="Corrected value (for correct)"),
               reason: str = typer.Option(None, help="Why (required for correct and reject)"),
               field: str = typer.Option(None, help="Field to correct (default: the item's field)"),
               reviewer: str = typer.Option(None, help="Your name or initials (default: login name)")):
    """Record a decision on a review item. The original value is kept."""
    from .review import resolve
    print(resolve(item_id, action, value, reason, reviewer, field))


@app.command("correct")
def correct_cmd(table: str = typer.Option(..., help="Table of the observation"),
                row_id: int = typer.Option(..., help="Row id (from lists, exports or trace)"),
                value: str = typer.Option(None, help="Corrected value"),
                reason: str = typer.Option(..., help="Why"),
                field: str = typer.Option(None, help="Field (default: the table's main value)"),
                reject: bool = typer.Option(False, "--reject", help="Mark the value as not disclosed instead")):
    """Correct one value directly, without a review item."""
    from .review import correct_value
    print(correct_value(table, row_id, value, reason, field, action="reject" if reject else "correct"))


@app.command("review-stats")
def review_stats_cmd():
    """Review outcomes by table and extraction method."""
    from .review import review_stats
    _table(review_stats(), ["table", "method", "reviewed", "accepted", "corrected", "rejected", "accept_rate"])
    print("[dim]Reviewed items are mostly flagged or low-confidence values, so these rates understate accuracy; "
          "use evaluate-parsers on a golden corpus for calibration.[/dim]")


@app.command("chart")
def chart_cmd(kind: str = typer.Argument(..., help="financials, segments, history, flags, price, segment-mix, "
                                                    "workforce, industry, peers, control, group-tree or interlocks"),
              code: str = typer.Option(None, "--code"),
              metrics: str = typer.Option("revenue,net_profit_parent", help="financials: comma-separated metrics"),
              dimension: str = typer.Option("PRODUCT", help="segments: PRODUCT, INDUSTRY, REGION …"),
              items: str = typer.Option("rd_investment", help="history: comma-separated items"),
              as_of: str = typer.Option(None, "--as-of", help="financials: only what was published by this date"),
              out: str = typer.Option("charts/chart", help="Output name without extension")):
    """Export a chart as SVG plus the CSV of exactly the plotted data (PNG too if matplotlib is installed)."""
    from .charts.builders import financial_chart, segment_chart, history_chart, flags_chart, export_chart
    init_db()
    if kind not in ("flags", "interlocks") and not code:
        raise typer.BadParameter("--code is required for this chart")
    if kind == "financials":
        spec = financial_chart(code, [m.strip() for m in metrics.split(",")], as_of=as_of)
    elif kind == "segments":
        spec = segment_chart(code, dimension)
    elif kind == "history":
        spec = history_chart(code, [i.strip() for i in items.split(",")])
    elif kind == "flags":
        spec = flags_chart(code)
    elif kind == "price":
        from .charts.builders import price_chart
        spec = price_chart(code, None, None, "backward")
    elif kind == "segment-mix":
        from .charts.builders import segment_mix_chart
        spec = segment_mix_chart(code, dimension)
    elif kind == "workforce":
        from .charts.builders import workforce_chart
        spec = workforce_chart(code)
    elif kind == "industry":
        from .charts.builders import industry_distribution_chart
        spec = industry_distribution_chart(code, metrics.split(",")[0].strip())
    elif kind == "control":
        from .charts.builders import control_chart
        spec = control_chart(code)
    elif kind == "group-tree":
        from .charts.builders import group_tree_chart
        spec = group_tree_chart(code)
    elif kind == "interlocks":
        from .charts.builders import interlock_chart
        spec = interlock_chart(code)
    elif kind == "peers":
        from .charts.builders import peer_scatter_chart
        ms = [m.strip() for m in metrics.split(",")] + ["net_margin"]
        spec = peer_scatter_chart(code, ms[0], ms[1])
    else:
        raise typer.BadParameter("unknown chart kind")
    for f in export_chart(spec, out):
        print(f"Written: {f}")


@app.command("render-page")
def render_page_cmd(disclosure_id: int, page: int = typer.Option(1), out: str = typer.Option("page.png"),
                    highlight: str = typer.Option(None, help="Text to highlight")):
    """Save one page of a downloaded document as PNG, optionally highlighting text."""
    from .models import Disclosure
    from .pagerender import render_page
    init_db()
    s = SessionLocal()
    try:
        d = s.get(Disclosure, disclosure_id)
        path = d.local_path if d else None
    finally:
        s.close()
    if not path:
        raise typer.BadParameter("no downloaded document for that disclosure")
    r = render_page(path, page, highlight)
    open(out, "wb").write(r["png"])
    print(f"Written: {out} (page {r['page']} of {r['pages']}, {len(r['boxes'])} highlight box(es))")


# --- v1.6: point-in-time security master -----------------------------------------

@app.command("extract-listing-events")
def extract_listing_events_cmd(security_code: str = typer.Option(None, "--security-code", "--code"),
                               use_documents: bool = typer.Option(True, "--use-documents/--titles-only")):
    """Read IPOs, delistings and name, code and board changes from announcements."""
    from .security_master import extract_listing_events
    print(extract_listing_events(security_code, use_documents))


@app.command("import-listing-events-csv")
def import_listing_events_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Columns: security_code, event_type, event_date, old_value, new_value, [exchange]."""
    from .security_master import import_listing_events_csv
    print(import_listing_events_csv(path, source))


@app.command("import-security-history-csv")
def import_security_history_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Columns: security_code, valid_from, valid_to, short_name_cn, [legal_name_cn, exchange, board,
    listing_status, risk_warning]. Imported periods take precedence over derived ones."""
    from .security_master import import_security_history_csv
    print(import_security_history_csv(path, source))


@app.command("rebuild-security-history")
def rebuild_security_history_cmd(security_code: str = typer.Option(None, "--security-code", "--code")):
    """Turn listing events and risk warnings into dated name, board and status periods."""
    from .security_master import rebuild_security_history
    print(rebuild_security_history(security_code))


@app.command("security-history")
def security_history_cmd(code: str):
    """Names, boards and listing status of one company over time, with the events behind them."""
    from .security_master import security_history
    r = security_history(code)
    if "error" in r:
        print(r)
        return
    _table(r["history"], title=f"{r['code']} identity periods")
    _table(r["events"], title="Listing events")


@app.command("universe-at")
def universe_at_cmd(on: str = typer.Argument(..., help="Date YYYY-MM-DD"),
                    boards: str = typer.Option(None, help="Comma-separated boards, e.g. SSE_MAIN,STAR"),
                    out: str = typer.Option(None, help="Save as CSV")):
    """Companies listed on a date, with the name and board they had then (no survivorship bias)."""
    from .security_master import universe_at
    rep: dict = {}
    rows = universe_at(on, [b.strip().upper() for b in boards.split(",")] if boards else None, report=rep)
    if out:
        import csv as _csv
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=["code", "current_code", "name", "board", "risk_warning", "basis"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} companies written to {out}")
    else:
        _table(rows[:200], title=f"Listed on {on}: {len(rows)} companies" + (" (first 200)" if len(rows) > 200 else ""))
    fallback = sum(1 for r in rows if r["basis"].startswith("COMPANY_RECORD"))
    if fallback:
        print(f"[yellow]{fallback} companies have no history yet (run rebuild-security-history); "
              f"their listing date was used.[/yellow]")
    if rep.get("excluded_no_listing_date") or rep.get("excluded_delisting_date_unknown"):
        print(f"[yellow]Left out because the dates are unknown: {rep['excluded_no_listing_date']} with no listing "
              f"date, {rep['excluded_delisting_date_unknown']} delisted on an unknown date. 'Update the company "
              "list' adds listing dates for listed companies; for delisted ones, catalogue announcements with kind "
              "'all' and run 'Read listing events', or import the dates.[/yellow]")


@app.command("import-index-csv")
def import_index_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Index membership: periods (index_code, security_code, valid_from, valid_to) or
    adjustments (index_code, security_code, effective_date, action ADD/REMOVE)."""
    from .security_master import import_index_csv
    print(import_index_csv(path, source))


@app.command("index-members")
def index_members_cmd(index_code: str, on: str = typer.Argument(..., help="Date YYYY-MM-DD")):
    """Constituents of an index on a date (e.g. 000300 for CSI 300)."""
    from .security_master import index_members
    _table(index_members(index_code, on), title=f"{index_code} on {on}")


@app.command("company-indices")
def company_indices_cmd(code: str, on: str = typer.Option(None, help="Date (default today)")):
    """Indices a company belonged to on a date, and the sustainability-report mandate for recent years."""
    from datetime import date as _date
    from .security_master import company_indices, sustainability_mandate, MANDATE_FIRST_YEAR
    d = on or _date.today().isoformat()
    _table(company_indices(code, d), title=f"{code} index membership on {d}")
    for fy in range(MANDATE_FIRST_YEAR, int(d[:4]) + 1):
        print(f"Fiscal {fy}: sustainability report {sustainability_mandate(code, fy)}")


@app.command("build-calendar")
def build_calendar_cmd(min_share: float = typer.Option(0.5, help="Share of securities that must have traded")):
    """Derive exchange trading days from stored daily prices."""
    from .security_master import build_trading_calendar
    print(build_trading_calendar(min_share))


@app.command("import-calendar-csv")
def import_calendar_csv_cmd(path: str, exchange: str = typer.Option("SSE"), source: str = typer.Option("CSV_IMPORT")):
    """Columns: trade_date, [is_open]. An official calendar replaces the derived one."""
    from .security_master import import_calendar_csv
    print(import_calendar_csv(path, exchange, source))


@app.command("suspensions")
def suspensions_cmd(code: str, start: str = typer.Option(..., "--start"), end: str = typer.Option(..., "--end")):
    """Spells of open trading days without trading, next to suspension announcements."""
    from .security_master import suspensions
    r = suspensions(code, start, end)
    if "error" in r:
        print(r)
        return
    print({k: v for k, v in r.items() if k not in ("spells", "suspension_announcements")})
    _table(r["spells"], title="Spells without trading")
    _table(r["suspension_announcements"], title="Suspension announcements")


@app.command("boards")
def boards_cmd():
    """Show which boards are collected. BSE and B-shares are optional and off by default."""
    from .universe import BOARD_MAP, OPTIONAL_BOARD_MAP, enabled_optional_boards
    on = enabled_optional_boards()
    rows = [{"board": b, "exchange": ex, "code prefixes": ", ".join(p for p, bb in m.items() if bb == b),
             "status": "always on"} for ex, m in BOARD_MAP.items() for b in sorted(set(m.values()))]
    for name, exs in OPTIONAL_BOARD_MAP.items():
        for ex, m in exs.items():
            for b in sorted(set(m.values())):
                rows.append({"board": b, "exchange": ex, "code prefixes": ", ".join(p for p, bb in m.items() if bb == b),
                             "status": "enabled" if name in on else f"off (set ASHARE_OPTIONAL_BOARDS={name})"})
    _table(rows)


# --- v1.7: research datasets ---------------------------------------------------------

@app.command("quarterly")
def quarterly_cmd(code: str, metric: str = typer.Argument("revenue"), as_of: str = typer.Option(None, "--as-of")):
    """Single-quarter values of a flow item (quarter-end values for balance items)."""
    from .derived import quarterly_series
    _table(quarterly_series(code, metric, as_of), ["quarter", "value", "published", "confidence_class", "formula"])


@app.command("ttm")
def ttm_cmd(code: str, metric: str = typer.Argument("revenue"), as_of: str = typer.Option(None, "--as-of")):
    """Trailing-twelve-month values of a flow item at each quarter end."""
    from .derived import ttm_series
    _table(ttm_series(code, metric, as_of), ["period", "value", "published", "confidence_class", "formula"])


@app.command("non-recurring")
def non_recurring_cmd(code: str):
    """Non-recurring items: net profit to the parent minus the same excluding them."""
    from .derived import non_recurring_series
    _table(non_recurring_series(code), ["period", "value", "share_of_net_profit", "published", "confidence_class"])


@app.command("chart-of-accounts")
def chart_of_accounts_cmd(statement: str = typer.Option(None, help="BS, IS or CF")):
    """The standard CAS line items read from consolidated statements, and their labels."""
    from .cas import CHART, CHART_VERSION
    rows = [{"code": k, "statement": v["statement"], "labels": " / ".join(v["labels"])} for k, v in CHART.items()
            if not statement or v["statement"] == statement.upper()]
    _table(rows, title=f"Chart {CHART_VERSION}: {len(rows)} items")


@app.command("adjustment-factors")
def adjustment_factors_cmd(security_code: str = typer.Option(None, "--security-code", "--code"),
                           compare: bool = typer.Option(True, "--compare/--no-compare",
                                                        help="Compare with provider-adjusted closes")):
    """Compute price-adjustment factors from recorded corporate actions."""
    from .valuation import compute_adjustment_factors, compare_adjustments
    print(compute_adjustment_factors(security_code))
    if compare:
        rows = compare_adjustments(security_code)
        if rows:
            _table([{k: v for k, v in r.items() if k != "worst_days"} for r in rows],
                   title="Own forward-adjusted closes against the provider's (tolerance 0.5%)")
        else:
            print("[dim]No provider-adjusted closes to compare with (download prices with --adjust forward).[/dim]")


@app.command("market-snapshots")
def market_snapshots_cmd(security_code: str = typer.Option(None, "--security-code", "--code"),
                         frequency: str = typer.Option("month", help="month or day")):
    """Market cap and point-in-time P/E, P/B, P/S and EV (needs prices and share capital)."""
    from .valuation import build_market_snapshots
    print(build_market_snapshots(security_code, frequency))


@app.command("valuation")
def valuation_cmd(code: str, on: str = typer.Option(None, help="Date (default today)")):
    """Valuation on one date, from information published by then."""
    from datetime import date as _date
    from .valuation import valuation_at
    r = valuation_at(code, on or _date.today().isoformat())
    inputs = r.pop("inputs", {})
    print(r)
    _table([{"input": k, **v} for k, v in inputs.items()], title="Financial inputs used")


@app.command("panel-variables")
def panel_variables_cmd(group: str = typer.Option(None, help="financial, derived, ratio, market, governance, ...")):
    """Variables available to build-panel."""
    from .panel import variables
    _table([{"name": v.name, "group": v.group, "unit": v.unit, "label": v.label} for v in variables().values()
            if not group or v.group == group])


@app.command("build-panel")
def build_panel_cmd(variables: str = typer.Option(None, help="Comma-separated (default: a standard set)"),
                    unit: str = typer.Option("year", help="year, quarter or month"),
                    start: str = typer.Option("2015-01-01"), end: str = typer.Option(None),
                    align: str = typer.Option("fiscal", help="fiscal or pit"),
                    pit_day: str = typer.Option("04-30", help="pit, yearly rows: MM-DD"),
                    lag_days: int = typer.Option(0, help="pit: reporting lag in days"),
                    as_of: str = typer.Option(None, "--as-of", help="Use only information published by this date"),
                    codes: str = typer.Option(None, help="Comma-separated codes (default: all listed)"),
                    index: str = typer.Option(None, help="Restrict to an index's constituents, e.g. 000300"),
                    boards: str = typer.Option(None, help="Comma-separated boards"),
                    exclude_financials: bool = typer.Option(False, "--exclude-financials"),
                    min_class: str = typer.Option(None, help="HIGH, MEDIUM or LOW"),
                    reviewed_only: bool = typer.Option(False, "--reviewed-only"),
                    winsor: float = typer.Option(None, help="Winsorise at this percentile each period, e.g. 1"),
                    lags: str = typer.Option(None, help="e.g. roa:1,ret:-1 (negative = lead)"),
                    with_dates: bool = typer.Option(False, "--with-dates", help="Add publication-date columns"),
                    formats: str = typer.Option("csv,dta", help="csv, dta, parquet"),
                    universe_basis: str = typer.Option("auto", help="auto, listing or report-evidence: which "
                                                       "companies a row covers (see the user guide)"),
                    out: str = typer.Option("panels", help="Output folder"), name: str = typer.Option("panel")):
    """Build a research panel with a codebook and manifest.

    A panel with no rows is not written: the command says why and what to do, and exits with an error."""
    from .panel import build_panel, write_panel, EmptyPanel
    init_db()
    r = build_panel([v.strip() for v in variables.split(",")] if variables else None, unit, start, end, align,
                    pit_day, lag_days, as_of, [c.strip().zfill(6) for c in codes.split(",")] if codes else None,
                    index, [b.strip().upper() for b in boards.split(",")] if boards else None, exclude_financials,
                    min_class, reviewed_only, winsor,
                    {k: int(v) for k, v in (x.split(":") for x in lags.split(","))} if lags else None, with_dates,
                    universe_basis)
    try:
        w = write_panel(r, out, name, tuple(f.strip() for f in formats.split(",")))
    except EmptyPanel as exc:
        print(f"[red]Not written: the panel has no rows, because {exc}[/red]")
        print({"dropped": r["dropped"]} if r["dropped"] else "")
        raise typer.Exit(code=1)
    print({k: v for k, v in w.items() if k != "files"})
    ev = sum(1 for row in r["rows"] if row.get("universe_basis") == "REPORT_EVIDENCE")
    if ev:
        print(f"[yellow]{ev:,} of {len(r['rows']):,} rows include a company by report evidence (it published a "
              "periodic report for the year, but its listing record is incomplete); they are marked "
              "universe_basis = REPORT_EVIDENCE.[/yellow]")
    for f in w["files"]:
        print(f"Written: {f}")


@app.command("panel-chart")
def panel_chart_cmd(panel: str = typer.Argument(..., help="Panel CSV"),
                    kind: str = typer.Option("hist", help="hist, box, scatter, coverage or summary"),
                    x: str = typer.Option(None, help="Variable (hist, box, scatter x)"),
                    y: str = typer.Option(None, help="scatter: y variable"),
                    out: str = typer.Option("charts/panel", help="Output name without extension")):
    """Charts and summaries of a built panel (the dataset explorer from the command line)."""
    from .explorer import load_panel, summary, chart_for
    from .charts.builders import export_chart
    rows = load_panel(panel)
    if kind == "summary":
        _table(summary(rows), title=f"{panel}: {len(rows)} rows")
        return
    for f in export_chart(chart_for(rows, kind, x, y), out):
        print(f"Written: {f}")


@app.command("event-study")
def event_study_cmd(events: str = typer.Argument(..., help="e.g. corporate_actions:CASH_DIVIDEND, "
                                                           "regulatory:ADMINISTRATIVE_PENALTY, or a CSV (code,date)"),
                    security_code: str = typer.Option(None, "--security-code", "--code"),
                    date_field: str = typer.Option(None, help="Date column, e.g. ex_date (default announcement date)"),
                    model: str = typer.Option("market", help="market, adjusted or mean"),
                    benchmark: str = typer.Option("ew", help="ew (equal-weighted) or a CSV of index closes/returns"),
                    est_start: int = typer.Option(-250), est_end: int = typer.Option(-31),
                    win_start: int = typer.Option(-1), win_end: int = typer.Option(1),
                    min_estimation: int = typer.Option(60),
                    out: str = typer.Option("event_studies"), name: str = typer.Option("event_study")):
    """Abnormal returns around events, with average CAR, t-statistic and a CAAR chart."""
    from .eventstudy import select_events, event_study, write_event_study
    init_db()
    evs = select_events(events, security_code, date_field)
    r = event_study(evs, (est_start, est_end), (win_start, win_end), model, benchmark, min_estimation)
    print(r["summary"])
    for f in write_event_study(r, out, name):
        print(f"Written: {f}")


@app.command("price-chart")
def price_chart_cmd(code: str, out: str = typer.Option("charts/price", help="Output name without extension")):
    """Adjusted closes with corporate, regulatory, management and listing events (SVG and CSV)."""
    from .charts.builders import price_chart, export_chart
    init_db()
    for f in export_chart(price_chart(code), out):
        print(f"Written: {f}")


# --- v1.8: ownership and control ------------------------------------------------------

@app.command("extract-top-holders")
def extract_top_holders_cmd(security_code: str = typer.Option(None, "--security-code", "--code")):
    """Top-10 shareholders and top-10 tradable holders from downloaded periodic reports."""
    from .control import extract_top_holders
    print(extract_top_holders(security_code))


@app.command("extract-pledges")
def extract_pledges_cmd(security_code: str = typer.Option(None, "--security-code", "--code"),
                        use_documents: bool = typer.Option(True, "--use-documents/--titles-only")):
    """Share pledges and releases from announcements."""
    from .control import extract_pledges
    print(extract_pledges(security_code, use_documents))


@app.command("pledges")
def pledges_cmd(code: str):
    """Pledge and release events of one company."""
    from .models import PledgeEvent
    init_db()
    s = SessionLocal()
    try:
        c = s.query(Company).filter_by(security_code=code.zfill(6)).first()
        rows = [] if not c else [{"date": p.announcement_date, "type": p.event_type, "pledgor": p.pledgor,
                                  "pledgee": p.pledgee, "shares": p.shares, "of_holding": p.pct_of_holding,
                                  "of_total": p.pct_of_total, "start": p.start_date, "end": p.end_date,
                                  "method": p.extraction_method}
                                 for p in s.query(PledgeEvent).filter_by(company_id=c.id).order_by(PledgeEvent.announcement_date)]
    finally:
        s.close()
    _table(rows)


@app.command("extract-control")
def extract_control_cmd(security_code: str = typer.Option(None, "--security-code", "--code")):
    """Controlling shareholder, actual controller and ownership type from annual and interim reports."""
    from .control import extract_control
    print(extract_control(security_code))


@app.command("import-control-csv")
def import_control_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Columns: security_code, observation_date, controlling_shareholder, actual_controller,
    [controller_nature, ownership_type]."""
    from .control import import_control_csv
    print(import_control_csv(path, source))


@app.command("import-control-edges-csv")
def import_control_edges_csv_cmd(path: str, source: str = typer.Option("CSV_IMPORT")):
    """Control-chain links: security_code, observation_date, parent_name, child_name, pct."""
    from .control import import_control_edges_csv
    print(import_control_edges_csv(path, source))


@app.command("control")
def control_cmd(code: str, as_of: str = typer.Option(None, "--as-of")):
    """Controller, ownership type and control chain known at a date."""
    from .control import control_at
    r = control_at(code, as_of)
    print(r.get("control"))
    _table(r.get("chain") or [], title="Control chain")


@app.command("resolve-entities")
def resolve_entities_cmd():
    """Build the register of organisations (shareholders, subsidiaries, controllers, listed companies)."""
    from .control import resolve_entities
    print(resolve_entities())


@app.command("import-entities-csv")
def import_entities_csv_cmd(path: str):
    """Columns: name, [credit_code, aliases ('|'-separated), entity_type]. Credit codes are checked."""
    from .control import import_entities_csv
    print(import_entities_csv(path))


@app.command("entity")
def entity_cmd(name_or_id: str):
    """One organisation: aliases, shareholdings, subsidiaries and companies it controls."""
    import json as _json
    from .control import entity_profile
    print(_json.dumps(entity_profile(name_or_id), ensure_ascii=False, indent=2))


@app.command("resolve-persons")
def resolve_persons_cmd():
    """Resolve directors and officers across companies (name, gender, birth year)."""
    from .control import resolve_persons
    print(resolve_persons())


@app.command("interlocks")
def interlocks_cmd(code: str = typer.Option(None, "--security-code", "--code"), as_of: str = typer.Option(None, "--as-of")):
    """Companies that share a director."""
    from .control import interlocks
    _table(interlocks(as_of, code), ["company_a", "company_b", "count", "shared_directors"])


@app.command("common-controllers")
def common_controllers_cmd(as_of: str = typer.Option(None, "--as-of")):
    """Listed companies with the same actual controller (group affiliation)."""
    from .control import common_controllers
    _table(common_controllers(as_of))


# --- v1.9: operations and remaining events ----------------------------------------------

@app.command("daily-update")
def daily_update_cmd(until: str = typer.Option(None, help="Last day to cover (default today)"),
                     prices: bool = typer.Option(True, "--prices/--no-prices"),
                     extract: bool = typer.Option(True, "--extract/--no-extract")):
    """Incremental update: new announcements market-wide since the last run, new prices, extraction."""
    from .ops import daily_update
    con = _console()
    r = daily_update(until, prices, extract, progress=lambda d, t, k, st: con.print(f"[dim]{d}/{t} {k} {st}[/dim]")
                     if d % 50 == 0 or d == t else None)
    for k, v in r.items():
        print(f"{k}: " + (str({x: v[x] for x in ('status', 'done', 'failed', 'total')}) if isinstance(v, dict) else str(v)))


@app.command("job-create")
def job_create_cmd(kind: str = typer.Argument(..., help="catalogue, catalogue_day, market or extract"),
                   since: str = typer.Option("2024-01-01"), until: str = typer.Option(None),
                   disclosure_kind: str = typer.Option("reports", "--kind", help="Disclosure kind for catalogues"),
                   download: bool = typer.Option(False, "--download/--no-download"),
                   incremental: bool = typer.Option(True, "--incremental/--full"),
                   codes: str = typer.Option(None, help="Comma-separated codes (default: all companies)")):
    """Create a resumable job (one item per company, or per day for catalogue_day)."""
    from .ops import create_job
    params = {"since": since, "until": until, "kind": disclosure_kind, "download": download, "incremental": incremental,
              "start": since, "end": until, "codes": [c.strip() for c in codes.split(",")] if codes else None}
    print({"job": create_job(kind, params)})


@app.command("job-run")
def job_run_cmd(job_id: int):
    """Run or resume a job; interrupted jobs continue where they stopped."""
    from .ops import run_job
    con = _console()
    r = run_job(job_id, progress=lambda d, t, k, st: con.print(f"[dim]{d}/{t} {k} {st}[/dim]"))
    print({k: v for k, v in r.items() if k != "params"})


@app.command("job-cancel")
def job_cancel_cmd(job_id: int):
    """Ask a running job to stop after the current item (it can be resumed later)."""
    from .ops import request_cancel
    request_cancel(job_id)
    print(f"Cancel requested for job {job_id}.")


@app.command("jobs")
def jobs_cmd(limit: int = typer.Option(20)):
    """Recent jobs and their progress."""
    from .ops import list_jobs
    _table(list_jobs(limit))


@app.command("job")
def job_cmd(job_id: int):
    """One job, with the items that failed."""
    from .ops import job_summary
    r = job_summary(job_id)
    print({k: v for k, v in r.items() if k != "failed_items"})
    _table(r["failed_items"], title="Failed items (retried on the next run, up to three attempts)")


@app.command("high-water-marks")
def marks_cmd():
    """How far each source has been collected."""
    from .ops import marks
    _table(marks())


@app.command("estimate-daily")
def estimate_daily_cmd(announcements: int = typer.Option(4000), download_share: float = typer.Option(0.2)):
    """Requests and minutes for a daily update at the polite rate (one request per second)."""
    from .ops import estimate_daily_requests
    print(estimate_daily_requests(announcements, download_share=download_share))


@app.command("schedule")
def schedule_cmd(enable: bool = typer.Option(True, "--enable/--disable"), at: str = typer.Option("18:30"),
                 dry_run: bool = typer.Option(False, "--dry-run")):
    """Run the daily update automatically on weekdays (Windows Task Scheduler; a cron line elsewhere)."""
    from .ops import schedule
    print(schedule(enable, at, dry_run))


@app.command("storage-stats")
def storage_stats_cmd():
    """Database and document archive sizes by kind."""
    from .ops import storage_stats
    r = storage_stats()
    by = r.pop("by_kind")
    print(r)
    _table([{"kind": k, **v} for k, v in by.items()], title="Downloaded documents by kind")


@app.command("prune-documents")
def prune_documents_cmd(kinds: str = typer.Option("other_announcement", help="Comma-separated disclosure kinds"),
                        older_than_days: int = typer.Option(0), apply: bool = typer.Option(False, "--apply",
                                                                                            help="Delete (default: report only)")):
    """Delete downloaded documents of some kinds, keeping URL and hash so they can be fetched again."""
    from .ops import prune_documents
    print(prune_documents(tuple(k.strip() for k in kinds.split(",")), older_than_days, dry_run=not apply))


@app.command("refetch-document")
def refetch_document_cmd(disclosure_id: int):
    """Download a pruned document again and check its hash."""
    from .ops import refetch_document
    print(refetch_document(disclosure_id))


@app.command("export-duckdb")
def export_duckdb_cmd(out: str = typer.Option("ashares.duckdb")):
    """Copy the database into a DuckDB file for fast analytics (optional duckdb package)."""
    from .ops import export_duckdb
    print(export_duckdb(out))


@app.command("extract-transactions")
def extract_transactions_cmd(security_code: str = typer.Option(None, "--security-code", "--code"),
                             use_documents: bool = typer.Option(True, "--use-documents/--titles-only")):
    """Major restructurings (with stages), related-party transactions, guarantees and meeting resolutions."""
    from .transactions import extract_transactions
    print(extract_transactions(security_code, use_documents))


@app.command("transactions")
def transactions_cmd(code: str, event_type: str = typer.Option(None, help="MAJOR_RESTRUCTURING, RELATED_PARTY, "
                                                                           "GUARANTEE or SHAREHOLDER_MEETING")):
    """Transaction events of one company."""
    from .transactions import show_transactions
    _table(show_transactions(code, event_type))


@app.command("version")
def version_cmd():
    """Print the program version."""
    print(__version__)

@app.command("show-company")
def show_company(security_code: str):
    """Basic facts about one company."""
    init_db()
    code = security_code.zfill(6)
    session = SessionLocal()
    try:
        rows = session.query(Company).filter_by(security_code=code).all()
        if not rows:
            print("[yellow]No company found.[/yellow]")
            return
        for c in rows:
            print({
                "id": c.id,
                "code": c.security_code,
                "exchange": c.exchange,
                "board": c.board,
                "legal_name_cn": c.legal_name_cn,
                "short_name_cn": c.short_name_cn,
                "listing_date": c.listing_date,
                "org_id": c.org_id,
                "status": c.status,
                "source": c.source_last_seen,
            })
    finally:
        session.close()

if __name__ == "__main__":
    app()
