from .sources.cninfo import CNInfoAdapter
from .storage import store_raw, upsert_ashares

def enrich_listing_status(info: dict | None = None) -> dict:
    """v2.0.2: listing dates and status for the companies in the database.

    * Listing dates come from the public quote list (one pass, ~60 requests).
    * A company in the quote list is LISTED; one whose CNINFO short name marks
      it as delisted (国华退, 大明退市, PT...) is DELISTED (date unknown until a
      delisting announcement is extracted or imported); any other company
      absent from the quote list is NOT_IN_QUOTE_LIST (suspended, or delisted
      recently).
    v2.0.3: a partial quote list is applied too (listing dates and LISTED for
    the companies it holds); NOT_IN_QUOTE_LIST is set only from a complete list.
    v2.0.7 (findings 58 and 66): with ``info`` left out, the exchanges' own stock lists are read first (three
    requests); the quote list is asked only if they leave companies without a listing date, since it refused
    every request for hours at a time in the live runs.
    """
    from .models import SessionLocal, Company
    from .universe import looks_delisted
    note = None
    exchanges = None
    if info is None:
        try:
            from .exchange_lists import exchange_listing_info
            exchanges = exchange_listing_info()
        except Exception as exc:   # never stops the update
            exchanges, note = None, f"exchange lists not read: {type(exc).__name__}: {exc}"
        s = SessionLocal()
        try:
            # companies the exchanges list without a date (a company absent from them has no quote either)
            missing = [c.security_code for c in s.query(Company)
                       if not c.listing_date and exchanges is not None and c.security_code in exchanges
                       and not exchanges[c.security_code].get("listing_date")]
        finally:
            s.close()
        if exchanges is not None and exchanges.complete and not missing:
            info = {}                     # every company dated by its exchange: the quote list is not needed
        else:
            try:
                from .market import fetch_listing_info
                info = fetch_listing_info()
            except Exception as exc:   # the universe itself is still usable
                info, note = {}, f"listing dates not fetched: {type(exc).__name__}: {exc}"
    complete = getattr(info, "complete", len(info) > 3000)
    # v2.1 (finding 104): the optional boards. The exchanges' A-share lists do not cover the Beijing Stock Exchange
    # (and the B shares only when their lists are read), and the companies there were never in "missing" above, so
    # the quote list was never asked for them. It is now asked for each enabled optional board that has undated
    # companies, that board alone.
    from .exchange_lists import LISTED_BOARDS
    from .universe import enabled_optional_boards
    optional_boards = {"BSE": {"BSE"}, "B_SHARE": {"SSE_B", "SZSE_B"}}
    extra: dict = {}
    extra_complete: set = set()
    extra_notes: list[str] = []
    if exchanges is not None or info:
        s = SessionLocal()
        try:
            undated = [(c.board, c.security_code) for c in s.query(Company.board, Company.security_code,
                                                                   Company.listing_date) if not c.listing_date]
        finally:
            s.close()
        for name in sorted(enabled_optional_boards()):
            need = [code for b, code in undated if b in optional_boards[name]
                    and not ((exchanges or {}).get(code) or {}).get("listing_date")]
            if not need:
                continue
            try:
                from .quotelist import listing_info
                got = listing_info(board=name)
                extra.update(got)
                if got.complete:
                    extra_complete |= optional_boards[name]
                if getattr(got, "note", None):
                    extra_notes.append(f"{name}: {got.note}")
            except Exception as exc:      # never stops the update
                extra_notes.append(f"{name}: quote list not read ({type(exc).__name__}: {exc})")
    covered = exchanges.covered if exchanges is not None else set()
    s = SessionLocal()
    counts = {"LISTED": 0, "DELISTED": 0, "NOT_IN_QUOTE_LIST": 0, "NOT_IN_EXCHANGE_LIST": 0,
              "listing_dates_added": 0, "listing_dates_by_source": {"exchanges": 0, "quote_list": 0}}
    a_boards = {"SSE_MAIN", "STAR", "SZSE_MAIN", "CHINEXT"}
    changed: list[str] = []
    try:
        for c in s.query(Company):
            before = (c.listing_date, c.status)
            ex = (exchanges or {}).get(c.security_code)
            row = info.get(c.security_code) or extra.get(c.security_code)
            if ex and ex.get("listing_date") and not c.listing_date:
                c.listing_date = ex["listing_date"]
                counts["listing_dates_added"] += 1
                counts["listing_dates_by_source"]["exchanges"] += 1
            if row and row.get("listing_date") and not c.listing_date:
                c.listing_date = row["listing_date"]
                counts["listing_dates_added"] += 1
                counts["listing_dates_by_source"]["quote_list"] += 1
            if ex or row:
                if c.status != "DELISTED" or not looks_delisted(c.short_name_cn):
                    c.status = "LISTED"
            elif looks_delisted(c.short_name_cn):
                c.status = "DELISTED"
            elif c.board in covered:
                # v2.0.8 (finding 71): absent from its own board's list, read whole in this run, and not named as
                # delisted. v2.1 (finding 104): only on the evidence of the company's own board's list.
                c.status = "NOT_IN_EXCHANGE_LIST"
            elif c.status == "NOT_IN_EXCHANGE_LIST" and c.board not in LISTED_BOARDS:
                # v2.1 (finding 104): v2.0.8 and v2.0.9 marked companies on boards with no exchange list (the
                # Beijing Stock Exchange); the mark is undone. A board whose list failed this run is left alone.
                c.status = "LISTED"
            elif complete and c.board in a_boards:
                c.status = "NOT_IN_QUOTE_LIST"
            elif c.board in extra_complete:
                c.status = "NOT_IN_QUOTE_LIST"
            if c.status in counts:
                counts[c.status] += 1
            if (c.listing_date, c.status) != before:
                changed.append(c.security_code)
        s.commit()
    finally:
        s.close()
    # v2.0.8 (finding 92): a listing history derived before these dates were known would hide them from panels;
    # that includes histories derived before an earlier update added the dates (as in the author's database).
    from .models import SecurityHistory
    s = SessionLocal()
    try:
        starts: dict[int, list] = {}
        for cid, vf in s.query(SecurityHistory.company_id, SecurityHistory.valid_from).filter(
                SecurityHistory.source == "DERIVED"):
            starts.setdefault(cid, []).append(vf)
        dated = {c.id: c.security_code for c in s.query(Company.id, Company.security_code, Company.listing_date)
                 if c.listing_date}
        changed += [dated[cid] for cid, vfs in starts.items() if cid in dated and not any(vfs)
                    and dated[cid] not in changed]
    finally:
        s.close()
    counts["history_rebuilt"] = 0
    if changed:
        from . import security_master
        try:
            counts["history_rebuilt"] = security_master.rebuild_security_history(codes=changed)["companies"]
        except Exception as exc:          # never fails the update: the list and dates are already saved
            counts["history_note"] = (f"listing history not rebuilt ({type(exc).__name__}: {exc}); run 'Build "
                                      "listing history' (rebuild-security-history)")
    else:
        counts["history_rebuilt"] = 0
    if extra_notes:
        counts["optional_board_notes"] = extra_notes
    s = SessionLocal()
    try:
        by_board: dict = {}
        for c in s.query(Company.board, Company.listing_date, Company.status):
            if not c.listing_date and c.status in ("LISTED", None):
                by_board[c.board or "?"] = by_board.get(c.board or "?", 0) + 1
        counts["undated_listed_by_board"] = by_board
    finally:
        s.close()
    if exchanges is not None:
        from .exchange_lists import summary
        counts["exchange_lists"] = summary(exchanges)
        counts["exchange_lists_complete"] = bool(exchanges.complete)
    if note:
        counts["note"] = note
    elif getattr(info, "note", None):
        counts["note"] = info.note
    elif not complete and info:
        counts["note"] = f"quote list incomplete ({len(info)} rows); 'not in the quote list' not set"
    counts["quote_list_complete"] = bool(complete)
    counts["quote_list_used"] = info is not None and (bool(info) or getattr(info, "note", None) is not None)
    if extra:
        counts["quote_list_used"] = True
        counts["optional_board_dates"] = len(extra)
    return counts


def update_universe(source="cninfo", listing_dates: bool = True):
    if source != "cninfo":
        raise ValueError(
            "Only the verified CNINFO machine-readable universe source "
            "is enabled for automatic acquisition in v0.3."
        )

    adapter = CNInfoAdapter()
    all_items = []
    raw_records = []

    try:
        # get_stock_mappings yields individual records but the raw response
        # is also captured inside the adapter. We collect the individual
        # normalised records here.
        for item in adapter.get_universe():
            all_items.append(item)
        for record in getattr(adapter, "last_source_records", []):
            store_raw(record.source, record.url, record.payload, record.metadata)
        result = upsert_ashares(all_items, source_name="CNINFO")
        seen_ids = result.pop("_seen_ids", set())
        if len(seen_ids) > 1000:  # only a full list can show that a company has gone
            from .security_master import mark_missing_from_list
            result["missing_from_list"] = mark_missing_from_list(seen_ids, "CNINFO")
        out = {**result, "source": source, "observations": len(all_items)}
        out["status"] = enrich_listing_status(None if listing_dates else {})
        return out
    finally:
        adapter.close()
