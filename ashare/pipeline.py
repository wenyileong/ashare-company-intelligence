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
    The quote list is applied only when it looks complete (over 3,000 rows).
    """
    from .models import SessionLocal, Company
    from .universe import looks_delisted
    note = None
    if info is None:
        try:
            from .market import fetch_listing_info
            info = fetch_listing_info()
        except Exception as exc:   # the universe itself is still usable
            info, note = {}, f"listing dates not fetched: {type(exc).__name__}: {exc}"
    complete = len(info) > 3000
    s = SessionLocal()
    counts = {"LISTED": 0, "DELISTED": 0, "NOT_IN_QUOTE_LIST": 0, "listing_dates_added": 0}
    try:
        for c in s.query(Company):
            row = info.get(c.security_code)
            if row:
                if row.get("listing_date") and not c.listing_date:
                    c.listing_date = row["listing_date"]
                    counts["listing_dates_added"] += 1
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
    if note:
        counts["note"] = note
    elif not complete:
        counts["note"] = f"quote list incomplete ({len(info)} rows); statuses from names only"
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
