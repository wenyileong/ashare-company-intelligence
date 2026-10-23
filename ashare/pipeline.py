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
    s = SessionLocal()
    counts = {"LISTED": 0, "DELISTED": 0, "NOT_IN_QUOTE_LIST": 0, "listing_dates_added": 0,
              "listing_dates_by_source": {"exchanges": 0, "quote_list": 0}}
    try:
        for c in s.query(Company):
            ex = (exchanges or {}).get(c.security_code)
            row = info.get(c.security_code)
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
            elif complete:
                c.status = "NOT_IN_QUOTE_LIST"
            if c.status in counts:
                counts[c.status] += 1
        s.commit()
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
