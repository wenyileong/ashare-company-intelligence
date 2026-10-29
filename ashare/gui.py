"""Desktop interface for A-share Company Intelligence.

Design: a sidebar of sections in workflow order, one page per section with a
short explanation, and one card per task. Every Run button builds the same
arguments as the command line and runs them through the CLI application, so
the GUI and the CLI cannot diverge. Each run is appended to ``run_log.txt``
in the data folder with its exact equivalent command, for reproducibility.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__

APP_NAME = "A-share Company Intelligence"
TODAY = _dt.date.today().isoformat()
LAST_YEAR_END = f"{_dt.date.today().year - 1}-12-31"   # v2.0.8 (finding 93): the last complete fiscal year
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# Specification
# ---------------------------------------------------------------------------


def F(key, label, kind="text", default="", flag=None, hint="", required=False):
    """Form field. kind: text | date | file | folder | bool | choice:a,b | code.
    flag: '--option', None (positional) or ('--on', '--off') for bool."""
    return {"key": key, "label": label, "kind": kind, "default": default, "flag": flag,
            "hint": hint, "required": required}


def CODE_OPT(hint="Leave blank to run for every company."):
    return F("security_code", "Security code", "code", "", "--security-code", hint)


CODE_REQ = F("code", "Security code", "code", "600519", None, "Six digits, e.g. 600519.", required=True)
SOURCE = F("source", "Source label", "text", "CSV_IMPORT", "--source",
           "Name of the dataset or vendor, kept as provenance.")
CSV_FILE = F("path", "CSV file", "file", "", None, required=True)
KINDS = "reports,annual,interim,quarterly,q1,earnings_forecast,distributions,corporate_actions,regulatory,all"
TABLES = ("all,companies,disclosures,financial_facts,market_bars,ownership_observations,"
          "capital_structure_observations,corporate_actions,capital_reconciliations,regulatory_events,"
          "validation_flags,research_queries,raw_records")


def A(label, command, fields=(), note="", after=None):
    return {"label": label, "command": command, "fields": list(fields), "note": note, "after": after}


SECTIONS = [
    {"id": "home", "group": "", "title": "Getting started", "intro": "", "actions": []},

    {"id": "universe", "group": "Collect", "title": "1  Universe",
     "intro": "The list of listed A-share companies (SSE Main, STAR, SZSE Main, ChiNext), taken from CNINFO. "
              "Run this first; every other step works on these companies.",
     "actions": [
         A("Update the company list", "update-universe", [],
           "Downloads CNINFO's official stock lists (about 5,000 companies). Takes under a minute."),
         A("Check the company list", "validate-universe", [], "Confirms each code matches its exchange and board."),
         A("Count by board", "universe-stats"),
         A("Diagnose the quote list", "diagnose-quote-list", [],
           "Listing dates come from Eastmoney's public quote list. If 'Update the company list' reports no listing "
           "dates, this tries each way of asking (about six requests) and says which works and what to do."),
         A("Look up a company", "show-company", [CODE_REQ]),
         A("Read listing events from announcements", "extract-listing-events", [CODE_OPT()],
           "IPOs, delistings, and name, code and board changes, from catalogued announcements (use kind 'all')."),
         A("Import historical listings", "import-listing-events-csv", [CSV_FILE, SOURCE],
           "For delisted companies and earlier changes. Columns: security_code, event_type, event_date, old_value, "
           "new_value."),
         A("Build listing history", "rebuild-security-history", [CODE_OPT()],
           "Turns listing events and risk warnings (ST, *ST) into dated name, board and status periods. Re-run after "
           "adding events."),
         A("Companies listed on a date", "universe-at", [
             F("on", "Date", "date", "2020-12-31", None, required=True),
             F("boards", "Boards", "text", "", "--boards", "Optional, e.g. STAR,CHINEXT"),
             F("out", "Save as CSV", "text", "", "--out", "Optional file name")],
           "Includes companies delisted since, under the names they had then, so samples avoid survivorship bias."),
         A("A company's listing history", "security-history", [CODE_REQ]),
     ]},

    {"id": "indices", "group": "Collect", "title": "12  Indices & calendar",
     "intro": "Index membership over time, the trading calendar and suspension days. Index lists come from published "
              "constituent adjustments or licensed files.",
     "actions": [
         A("Import index membership", "import-index-csv", [CSV_FILE, SOURCE],
           "Either periods (index_code, security_code, valid_from, valid_to) or adjustments (index_code, "
           "security_code, effective_date, action ADD/REMOVE or 调入/调出)."),
         A("Index constituents on a date", "index-members", [
             F("index", "Index code", "text", "000300", None, "000300 CSI 300, 000905 CSI 500, 000010 SSE 180, "
               "000688 STAR 50, 399330 SZSE 100, 399006 ChiNext", required=True),
             F("on", "Date", "date", TODAY, None, required=True)]),
         A("A company's indices", "company-indices", [CODE_REQ, F("on", "Date", "date", "", "--on", "Blank = today")],
           "Also shows whether a sustainability report was mandatory (constituents of SSE 180, STAR 50, SZSE 100 "
           "and ChiNext Index, from fiscal 2025)."),
         A("Build the trading calendar", "build-calendar", [],
           "Derives trading days from downloaded prices. An official calendar can be imported instead."),
         A("Import a trading calendar", "import-calendar-csv", [
             CSV_FILE, F("exchange", "Exchange", "choice:SSE,SZSE,BSE", "SSE", "--exchange")],
           "Columns: trade_date, is_open."),
         A("Suspension days", "suspensions", [
             CODE_REQ, F("start", "From", "date", "2025-01-01", "--start", required=True),
             F("end", "To", "date", TODAY, "--end", required=True)],
           "Open trading days without a price, grouped into spells, next to suspension announcements."),
     ]},

    {"id": "disclosures", "group": "Collect", "title": "2  Disclosures",
     "intro": "Announcements and reports from CNINFO. Downloading the documents lets later steps read figures, "
              "corporate actions and regulatory events from them.",
     "actions": [
         A("Catalogue announcements", "catalogue-disclosures", [
             F("since", "From", "date", "2026-01-01", "--since", required=True),
             F("until", "To", "date", TODAY, "--until", required=True),
             F("kind", "Type", "choice:" + KINDS, "reports", "--kind",
               "'reports' = periodic reports. Use 'all' before extracting regulatory events."),
             CODE_OPT("Blank = whole market: one market-wide query per period, busy days split so that nothing "
                      "is cut off."),
             F("download", "Download documents", "bool", True, ("--download-documents", "--no-download-documents"),
               "For the whole market this is many hours; untick it to catalogue first, then use 'Download "
               "catalogued documents' for the kinds you need."),
             F("refresh", "Fetch finished days again", "bool", False, ("--refresh", None),
               "Whole market: by default days already finished are skipped, so a rerun carries on where the last "
               "one stopped. Tick to fetch them again."),
         ], "Start with one company to check the connection, then widen. Progress appears below as it runs, and "
            "Stop ends it safely; running it again carries on from the first unfinished day. Each day's count is "
            "checked against CNINFO's total, and days that fall short or fail are listed at the end."),
         A("Re-catalogue busy days", "recatalogue-busy-days", [
             F("kind", "Type", "choice:" + KINDS, "all", "--kind"),
             F("since", "From", "date", "", "--since", "Optional"),
             F("until", "To", "date", "", "--until", "Optional")],
           "Fetches again failed days, days short under an earlier version, and days earlier versions cut short "
           "at 3,000 announcements. Days whose gap recurred under the current method are not repeated, since the "
           "same queries cannot close it."),
         A("Which days are catalogued", "catalogue-days", [
             F("kind", "Type", "choice:" + KINDS, "all", "--kind"),
             F("problems", "Only days not complete", "bool", True, ("--problems", None)),
             F("by_day", "One row per day", "bool", False, ("--by-day", None),
               "Normally a window of quiet days, read as one query, is one row with its total and gap.")],
           "Each day's status (DONE, SHORTFALL, FAILED, OPEN for today), with CNINFO's total and the number stored."),
         A("Check CNINFO's search filters", "probe-cninfo-filters", [
             F("day", "Very busy day", "date", "2026-04-29", "--day")],
           "About 70 to 120 requests: checks which board codes, industry and company filters and sort orders work "
           "for whole-market searches, and why some rows repeat. The catalogue checks the same things as it runs; "
           "keep the output for the record."),
         A("Check CNINFO's paging limit", "probe-cninfo-paging", [
             F("day", "Busy day", "date", "2026-04-24", "--day")],
           "Four requests: reads pages 1, 100, 101 and 150 of a busy day to see whether one query stops at 3,000 "
           "results. Keep the output for the record."),
         A("Download catalogued documents", "download-documents", [
             F("kinds", "Kinds", "choice:annual_report;annual_report,interim_report;"
               "annual_report,interim_report,quarterly_report;sustainability_report", "annual_report", "--kinds"),
             CODE_OPT("Blank = every company.")],
           "Downloads documents already in the catalogue that are not yet on disk, newest first. Resumable: files "
           "already downloaded are skipped."),
         A("Check documents for scanned pages", "scan-documents", [CODE_OPT()],
           "Lists downloaded PDFs without a text layer. No parser can read them; enter their values by hand "
           "or import them."),
         A("Find a disclosure by title", "search-disclosures", [
             F("query", "Words in title", "text", "", None, "e.g. 权益分派 or 行政处罚"), CODE_OPT(""),
             F("since", "From", "text", "", "--since", "Optional, YYYY-MM-DD")]),
     ]},

    {"id": "financials", "group": "Collect", "title": "3  Financials",
     "intro": "Financial statement figures read from downloaded reports. Native XBRL is used where present "
              "(high confidence); otherwise figures are read from PDF text (medium or low confidence).",
     "actions": [
         A("Extract figures from reports", "extract-financials", [
             CODE_OPT(), F("kind", "Reports", "choice:reports,annual,interim,quarterly,all", "reports", "--kind",
                           "'reports' reads the periodic reports; 'all' reads every downloaded document, most of "
                           "which carry no financial statements."),
             F("again", "Read documents again", "bool", False, ("--again", None),
               "Normally documents already read are skipped, so a stopped run continues where it stopped.")]),
         A("Check balance sheets", "validate-financials", [CODE_OPT()],
           "Tests assets = liabilities + equity for each report; failures are flagged, never changed."),
         A("Show a company's figures", "show-financials", [
             CODE_REQ, F("metric", "Metric", "text", "", "--metric", "e.g. revenue, net_profit, total_assets")]),
     ]},

    {"id": "market", "group": "Collect", "title": "4  Market data",
     "intro": "Daily prices. The public feeds (EASTMONEY_PUBLIC, TENCENT_PUBLIC) are not exchange-authoritative; "
              "choose one under Settings > Price source, after 'Test price sources'. Licensed data can be imported "
              "from CSV, and is preferred to a public feed for the same day.",
     "actions": [
         A("Test price sources", "diagnose-prices", [
             F("code", "Company", "code", "600519", None, "Any listed company; nothing is stored.")],
           "Asks each public source for this company's last month of prices and reports what each returned."),
         A("Download daily prices", "acquire-market", [
             CODE_OPT(), F("start", "From", "date", "2026-01-01", "--start", required=True),
             F("end", "To", "date", TODAY, "--end", required=True),
             F("provider", "Source", "choice:,eastmoney,tencent", "", "--provider",
               "Blank = the source chosen in Settings."),
             F("adjust", "Adjustment", "choice:none,forward,backward", "none", "--adjust",
               "Keep one adjustment type per analysis.")]),
         A("Import prices from CSV", "import-market-csv", [CSV_FILE, CODE_OPT("Only if the file holds one company."), SOURCE],
           "Columns: code, date, open, high, low, close (others optional)."),
         A("Show prices", "show-market", [CODE_REQ, F("start", "From", "text", "", "--start", "Optional")]),
     ]},

    {"id": "ownership", "group": "Collect", "title": "5  Ownership & capital",
     "intro": "Shareholders, pledges, controllers and share capital over time: read from the reports or imported "
              "from an authorised dataset.",
     "actions": [
         A("Read top-10 shareholders from reports", "extract-top-holders", [CODE_OPT(), F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "From 前十名股东持股情况 and the tradable-holder table of downloaded periodic reports."),
         A("Read controlling shareholder and actual controller", "extract-control", [CODE_OPT(), F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Also classifies ownership (central SOE, local SOE, private, foreign, collective, none) and records why."),
         A("Read share pledges", "extract-pledges", [CODE_OPT()],
           "Pledge and release announcements (catalogue with kind 'all' first)."),
         A("Import controllers", "import-control-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, observation_date, controlling_shareholder, actual_controller, ownership_type."),
         A("Import control-chain links", "import-control-edges-csv", [CSV_FILE, SOURCE],
           "For the percentages shown in the report's 方框图: security_code, observation_date, parent_name, "
           "child_name, pct."),
         A("Link entities and persons", "resolve-entities", [],
           "Builds the register of organisations met as shareholders, subsidiaries and controllers. Then run "
           "'Resolve directors across companies' on the Board & industry page."),
         A("Import shareholders", "import-ownership-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, observation_date, shareholder_name, rank, shares, ownership_pct …"),
         A("Import share capital", "import-capital-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, observation_date, total_shares, tradable_shares, restricted_shares …"),
         A("Show shareholders", "show-ownership", [CODE_REQ]),
         A("Show share capital", "show-capital", [CODE_REQ]),
     ]},

    {"id": "actions", "group": "Collect", "title": "6  Corporate actions",
     "intro": "Dividends, bonus and capitalisation issues, placements, rights issues, buybacks, cancellations and "
              "conversions, read from downloaded announcements.",
     "actions": [
         A("Read restructurings, related-party deals, guarantees and meetings", "extract-transactions", [CODE_OPT()],
           "Major asset restructurings with their stages, related-party transactions, external guarantees (with "
           "overdue amounts) and shareholder-meeting votes."),
         A("Show transactions", "transactions", [
             CODE_REQ, F("event_type", "Type", "choice:,MAJOR_RESTRUCTURING,RELATED_PARTY,GUARANTEE,SHAREHOLDER_MEETING",
                         "", "--event-type")]),
         A("Extract from announcements", "extract-corporate-actions", [
             CODE_OPT(), F("docs", "Read downloaded documents", "bool", True, ("--use-documents", "--titles-only"))]),
         A("Import from CSV", "import-corporate-actions-csv", [CSV_FILE, SOURCE],
           "Set the status column (e.g. COMPLETED) so reconciliation can use the rows."),
         A("Show actions", "show-actions", [CODE_REQ]),
         A("Reconcile share capital", "reconcile-capital", [CODE_OPT()],
           "Checks that capital at one date plus the actions since equals capital at the next date."),
     ]},

    {"id": "regulatory", "group": "Collect", "title": "7  Regulatory & legal",
     "intro": "Investigations, penalties, supervisory measures, exchange discipline, enquiries, litigation, "
              "audit opinions, risk warnings (ST/*ST) and suspensions.",
     "actions": [
         A("Extract from announcements", "extract-regulatory-events", [
             CODE_OPT(), F("docs", "Read downloaded documents", "bool", True, ("--use-documents", "--titles-only")),
             F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Catalogue disclosures with type 'all' first: these matters are filed under several categories."),
         A("Import a regulator's decision", "import-regulatory-document", [
             F("path", "File or web address", "file", "", None, "A CSRC or exchange decision (PDF, HTML or text).", required=True),
             F("security_code", "Security code", "code", "", "--security-code", "Blank = detect from the document.")]),
         A("Show events", "show-events", [CODE_REQ]),
         A("Regulatory status on a date", "regulatory-status", [
             CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD; blank = latest.")]),
     ]},

    {"id": "industry", "group": "Collect", "title": "8  Industry",
     "intro": "Industry classifications over time (CSRC 2012, Shenwan 2021 or another scheme), imported from the "
              "classification lists you obtain. They define peer groups for comparison.",
     "actions": [
         A("Import a classification list", "import-industry-csv", [
             CSV_FILE, F("scheme", "Scheme", "choice:CSRC_2012,SW_2021,CNINFO,CSRC_OTHER,CUSTOM", "CSRC_2012", "--scheme",
                         "CSRC lists are published by the CSRC; Shenwan lists are licensed."),
             F("effective_date", "Effective date", "text", "", "--effective-date",
               "Needed if the file has no date column, e.g. 2026-06-30."), SOURCE],
           "Accepts English or Chinese headers (证券代码, 门类代码, 大类代码, 行业名称 …). Codes are checked against the scheme."),
         A("Show a company's classifications", "show-industry", [CODE_REQ]),
         A("Companies per industry", "industry-summary", [
             F("scheme", "Scheme", "choice:CSRC_2012,SW_2021,CNINFO,CSRC_OTHER,CUSTOM", "CSRC_2012", "--scheme"),
             F("level", "Level", "choice:1,2,3", "1", "--level")]),
     ]},

    {"id": "management", "group": "Collect", "title": "9  Management",
     "intro": "Directors, supervisors and senior executives: appointments and resignations from announcements, and the "
              "officer table (tenure, shareholding, pay) from annual reports.",
     "actions": [
         A("Extract from announcements and annual reports", "extract-management", [
             CODE_OPT(), F("docs", "Read downloaded documents", "bool", True, ("--use-documents", "--titles-only")),
             F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Catalogue disclosures with type 'all' (announcements) and 'annual' (reports) first."),
         A("Import a roster", "import-management-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, observation_date, person_name, role, gender, age, tenure_start, tenure_end, remuneration."),
         A("Roster on a date", "roster", [CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")]),
         A("Show appointments and resignations", "show-management-events", [CODE_REQ]),
     ]},

    {"id": "segments", "group": "Collect", "title": "10  Segments & group",
     "intro": "Revenue by industry, product, region and sales model, and the group's subsidiaries and associates, "
              "read from downloaded annual and interim reports.",
     "actions": [
         A("Extract segments from reports", "extract-segments", [CODE_OPT(), F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Reads the 营业收入构成 table and the segment gross-margin table. Catalogue reports with documents first."),
         A("Extract subsidiaries from reports", "extract-subsidiaries", [CODE_OPT(), F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Reads 企业集团的构成 (stakes, places, acquisition method) and 主要控股参股公司分析 (financials)."),
         A("Import segments from CSV", "import-segments-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, reporting_period, dimension, segment_name, revenue, cost, gross_margin."),
         A("Import subsidiaries from CSV", "import-subsidiaries-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, observation_date, entity_name, relationship, registered_place, direct_pct, "
           "indirect_pct, acquisition_method."),
     ]},

    {"id": "people_esg", "group": "Collect", "title": "11  R&D, people & ESG",
     "intro": "R&D spending and staff, workforce composition and education, patents, environmental and social "
              "disclosures, sustainability reports and third-party ESG ratings.",
     "actions": [
         A("Extract R&D and workforce from reports", "extract-human-capital", [CODE_OPT(), F("again", "Read reports again", "bool", False, ("--again", None), "Normally reports already read by this version are skipped, so a stopped run continues where it stopped.")],
           "Reads the 研发投入 table, 员工情况 (functions and education) and patent counts."),
         A("Extract ESG from reports", "extract-esg", [CODE_OPT()],
           "Reads annual reports and sustainability/ESG reports: pollutant-discharge status, emissions, GHG, "
           "donations, rural revitalisation. Catalogue disclosures with type 'all' first."),
         A("Import ESG ratings", "import-esg-ratings-csv", [CSV_FILE, SOURCE],
           "Columns: security_code, provider, rating_date, rating, score. Ratings are licensed data."),
         A("Import R&D / workforce data", "import-human-capital-csv", [CSV_FILE, SOURCE],
           "Long format: security_code, reporting_period, item, value (item codes: run 'human-capital-items')."),
     ]},

    {"id": "company", "group": "Analyse", "title": "Company",
     "intro": "Everything known about one company, optionally as it was known on a past date "
              "(only information published by then is used).",
     "actions": [
         A("Company report (opens in browser)", "report", [
             CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")],
           "A single HTML page: identity, financial history, shareholders, regulatory matters, timeline.",
           after="open_report"),
         A("Financial series", "financial-series", [
             CODE_REQ, F("metric", "Metric", "choice:revenue,net_profit,net_profit_parent,total_assets,total_liabilities,"
                         "equity,operating_cash_flow,rd_expense,employees", "revenue", "--metric"),
             F("vintage", "Vintage", "choice:latest,original", "latest", "--vintage",
               "'original' = as first reported; 'latest' includes later restatements."),
             F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")]),
         A("Timeline", "timeline", [CODE_REQ]),
         A("Board and governance", "governance", [
             CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")],
           "Board size and independence, CEO duality, departures in the last 12 months, and screening checks "
           "against the CSRC independent-director rules."),
         A("Control and ownership type", "control", [
             CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")],
           "Controlling shareholder, actual controller, ownership type with its basis, and the control chain "
           "(drawn as a diagram)."),
         A("Resolve directors across companies", "resolve-persons", [],
           "Groups directors and officers by name, gender and birth year, so that interlocks can be found."),
         A("Board interlocks", "interlocks", [
             F("code", "Security code", "code", "", "--code", "Blank = all companies"),
             F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")],
           "Companies that share a director, drawn as a network."),
         A("Companies with the same controller", "common-controllers", [
             F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")]),
         A("Look up an organisation", "entity", [F("name", "Name or id", "text", "", None, required=True)],
           "Aliases, shareholdings, subsidiaries and companies it controls."),
         A("Business segments", "segments", [
             CODE_REQ, F("dimension", "Dimension", "choice:,INDUSTRY,PRODUCT,REGION,SALES_MODEL,REPORTABLE_SEGMENT", "",
                         "--dimension", "Blank = all dimensions."),
             F("period", "Period", "text", "", "--period", "Optional YYYY-MM-DD; blank = latest.")],
           "Shares, growth and gross margins by segment, overseas revenue share and concentration (HHI)."),
         A("Segment history", "segment-history", [
             CODE_REQ, F("dimension", "Dimension", "choice:PRODUCT,INDUSTRY,REGION,SALES_MODEL,REPORTABLE_SEGMENT",
                         "PRODUCT", "--dimension")]),
         A("Group structure", "subsidiaries", [
             CODE_REQ, F("as_of", "As of", "text", "", "--as-of", "Optional YYYY-MM-DD.")],
           "Subsidiaries and associates with stakes and jurisdictions, offshore entities, and consolidation with "
           "50% or less (listed for review)."),
         A("Changes in group scope", "scope-changes", [
             CODE_REQ, F("date_from", "From", "text", "", "--from", "Optional; blank = previous report."),
             F("date_to", "To", "text", "", "--to", "Optional; blank = latest report.")]),
         A("R&D and workforce", "human-capital", [
             CODE_REQ, F("period", "Period", "text", "", "--period", "Optional YYYY-MM-DD; blank = latest year.")],
           "R&D intensity and capitalisation, R&D staff, workforce by function and education, patents."),
         A("R&D and workforce history", "human-capital-history", [CODE_REQ]),
         A("ESG profile", "esg", [
             CODE_REQ, F("year", "Fiscal year", "year", "", "--year", "Optional, e.g. 2025; blank = latest.")],
           "Disclosed environmental and social data, governance indicators, regulatory actions and ratings. "
           "No composite score is calculated."),
         A("Industry peers", "peers", [
             CODE_REQ, F("scheme", "Scheme", "choice:CSRC_2012,SW_2021,CNINFO,CSRC_OTHER,CUSTOM", "CSRC_2012", "--scheme"),
             F("level", "Level", "choice:1,2,3", "2", "--level")]),
         A("Position within industry", "industry-stats", [
             CODE_REQ, F("metric", "Metric or ratio", "choice:revenue,net_profit,total_assets,net_margin,roa,roe,"
                         "liabilities_to_assets,rd_intensity", "net_margin", "--metric"),
             F("scheme", "Scheme", "choice:CSRC_2012,SW_2021,CNINFO,CSRC_OTHER,CUSTOM", "CSRC_2012", "--scheme"),
             F("min_class", "Minimum confidence", "choice:LOW,MEDIUM,HIGH", "LOW", "--min-class",
               "Exclude peer values below this confidence class.")],
           "Median, quartiles and the company's percentile among its peers."),
         A("Compare companies", "compare", [
             F("codes", "Codes", "text", "600519,000858", "--codes", "Comma-separated.", required=True),
             F("metrics", "Metrics", "text", "revenue,net_profit,total_assets,total_liabilities", "--metrics")]),
         A("Price statistics", "market-stats", [
             CODE_REQ, F("start", "From", "text", "", "--start", "Optional"), F("end", "To", "text", "", "--end", "Optional")]),
     ]},

    {"id": "datasets", "group": "Analyse", "title": "Datasets",
     "intro": "Research panels without look-ahead, valuation, and event studies. Every panel comes with a codebook "
              "and a manifest, so the dataset can be described and rebuilt.",
     "actions": [
         A("Build a panel", "build-panel", [
             F("variables", "Variables", "text", "", "--variables",
               "Blank = a standard set. See 'List panel variables'."),
             F("unit", "Unit", "choice:year,quarter,month", "year", "--unit"),
             F("align", "Alignment", "choice:fiscal,pit", "fiscal", "--align",
               "fiscal = values for each fiscal period; pit = what was published by each date"),
             F("start", "From", "date", "2018-01-01", "--start", required=True),
             F("end", "To", "date", LAST_YEAR_END, "--end",
               "Fiscal rows need a year that has ended; use Unit = quarter for this year's interim figures."),
             F("as_of", "Known by", "date", "", "--as-of", "Optional: use only information published by then"),
             F("index", "Index", "text", "", "--index", "Optional, e.g. 000300"),
             F("winsor", "Winsorise (%)", "number", "", "--winsor", "Optional, e.g. 1"),
             F("min_class", "Minimum confidence", "choice:,LOW,MEDIUM,HIGH", "", "--min-class"),
             F("exclude_financials", "Exclude financial firms", "bool", False, ("--exclude-financials", None)),
             F("formats", "Formats", "choice:csv,dta;csv;csv,dta,parquet", "csv,dta", "--formats",
               "dta = Stata; parquet needs pyarrow"),
             F("universe_basis", "Companies in each row", "choice:auto,listing,report-evidence", "auto",
               "--universe-basis", "auto = listed on the date by its listing record, or (yearly rows) published a "
               "report for that year; marked in the universe_basis column"),
             F("name", "Name", "text", "panel", "--name")],
           "Writes to the panels folder: the data, a codebook (Markdown and HTML), R loader and a manifest. Opens the "
           "explorer when done. A panel with no rows is not written; the output says why and what to do.",
           after="explore"),
         A("List panel variables", "panel-variables", [
             F("group", "Group", "choice:,financial,derived,ratio,market,governance,human_capital,segments,"
               "ownership,index,listing,industry,regulatory", "", "--group")]),
         A("Open the dataset explorer", "version", [],
           "Histograms, distributions by year, scatter plots with a fitted line, coverage and correlations of any "
           "panel.", after="explore"),
         A("Price-adjustment factors", "adjustment-factors", [CODE_OPT()],
           "Computed from recorded dividends, bonus and capitalisation issues and rights issues, and compared with "
           "provider-adjusted prices."),
         A("Market value and valuation ratios", "market-snapshots", [
             CODE_OPT(), F("frequency", "Frequency", "choice:month,day", "month", "--frequency")],
           "Market cap, P/E, P/B, P/S and EV at each month end, from information published by then."),
         A("Price chart with events", "price-chart", [CODE_REQ],
           "Adjusted closes with dividends, regulatory, management and listing events marked."),
         A("Event study", "event-study", [
             F("events", "Events", "text", "corporate_actions:CASH_DIVIDEND", None,
               "table:TYPE (corporate_actions, regulatory, management, listing) or a CSV of code,date",
               required=True),
             F("model", "Model", "choice:market,adjusted,mean", "market", "--model"),
             F("win_start", "Window from", "integer", "-1", "--win-start"),
             F("win_end", "Window to", "integer", "1", "--win-end"),
             F("out", "Folder", "folder", "event_studies", "--out"),
             F("name", "Name", "text", "event_study", "--name")],
           "Market model estimated over trading days −250 to −31 against an equal-weighted benchmark (change on the "
           "command line). Writes per-event CARs, the average with t-statistic, and a chart."),
     ]},

    {"id": "validate", "group": "Analyse", "title": "Validate",
     "intro": "Checks the data without changing it: accounting identities, capital reconciliation, figures that "
              "differ between reports (restatements), ownership consistency, and conflicts between sources.",
     "actions": [
         A("Run all checks", "validate-all", [CODE_OPT()],
           "Also links related events (e.g. an investigation and its penalty). Re-run after adding data."),
         A("Show findings", "show-flags", [
             CODE_OPT(""), F("severity", "Severity", "choice:,ERROR,WARN,INFO", "", "--severity"),
             F("rule", "Rule", "text", "", "--rule", "Optional, e.g. SEGMENT_SUM_MISMATCH: lists that rule's rows"),
             F("details", "List every finding", "bool", False, ("--details", None),
               "Off: a count by rule and the companies with most findings."),
             F("export", "Export to CSV", "text", "", "--export", "Optional file name, e.g. exports/findings.csv")],
           "Starts with a summary; a company, a rule or 'List every finding' shows the rows, with company codes."),
     ]},

    {"id": "research", "group": "Analyse", "title": "Research",
     "intro": "Search inside documents, trace any figure back to its source page, and produce reproducible outputs.",
     "actions": [
         A("Index documents for search", "index-documents", [CODE_OPT()],
           "Reads the text of downloaded documents once, so they can be searched."),
         A("Search inside documents", "search-documents", [
             F("query", "Text", "text", "", None, "e.g. 资金占用 or 保留意见", required=True), CODE_OPT("")]),
         A("Trace a figure to its source", "trace", [
             F("table", "Table", "choice:financial_facts,corporate_actions,regulatory_events,ownership_observations,"
               "capital_structure_observations,market_bars", "financial_facts", None),
             F("row_id", "Row id", "text", "", None, "The id shown in lists and exports.", required=True)],
           "Shows document, page, raw text, method and checks the file's hash."),
         A("Read-only query (SQL)", "query", [
             F("sql", "SQL", "text", "SELECT security_code, short_name_cn FROM companies LIMIT 20", None, required=True),
             F("out", "Save to", "text", "", "--out", "Optional file name, e.g. exports/result.csv")],
           "Every query is logged with a fingerprint of the data, so results can be reproduced."),
         A("Export tables to CSV", "export", [
             F("table", "Table", "choice:" + TABLES, "all", None), F("out", "Folder", "folder", "exports", "--out-dir"),
             CODE_OPT("")], "UTF-8 CSV that opens directly in Excel.", after="open_folder"),
         A("Export a chart", "chart", [
             F("kind", "Chart", "choice:financials,segments,history,flags", "financials", None),
             F("code", "Security code", "code", "600519", "--code"),
             F("metrics", "Metrics (financials)", "text", "revenue,net_profit_parent", "--metrics"),
             F("out", "Save as", "text", "charts/chart", "--out", "Name without extension")],
           "Writes an SVG (for papers and slides) and a CSV of exactly the plotted data; PNG too when "
           "matplotlib is installed (source installations).", after="open_folder"),
         A("Create a dataset release", "release", [
             F("formats", "Formats", "choice:csv,sqlite;csv;csv,sqlite,parquet", "csv,sqlite", "--formats",
               "Parquet needs the optional pyarrow package."), CODE_OPT(""),
             F("pseudonymise", "Pseudonymise personal names", "bool", False, ("--pseudonymise", None),
               "Directors, officers and natural-person shareholders become stable identifiers (P…)."),
             F("coarsen", "Ages in five-year bands", "bool", False, ("--coarsen", None),
               "With pseudonymisation."),
             F("drop_free_text", "Drop titles and other free text", "bool", False, ("--drop-free-text", None),
               "With pseudonymisation: the strictest setting."),
             F("include_licensed", "Include licensed data", "bool", False, ("--include-licensed", None),
               "Only for your own use: vendor data may not be redistributed."),
             F("author", "Author (for the citation)", "text", "", "--author")],
           "A dated folder with CSVs, a database snapshot, a data-quality report, CITATION.cff and a manifest of "
           "file hashes. Licensed data (vendor ratings, Shenwan industries, unlabelled CSV imports) are left out "
           "unless you tick the box; the manifest records what was left out.", after="open_folder"),
         A("Data-quality report", "quality-report", [
             F("out", "Folder", "folder", "reports/quality", "--out-dir")],
           "Coverage by layer, board and year, parser precision, review results, flag rates and known gaps.",
           after="open_folder"),
         A("Show licence classes", "licences", [],
           "Rows per table by licence class and source label. Imports are treated as licensed until tagged."),
         A("Tag a source's licence", "set-licence", [
             F("source", "Source label", "text", "CSV_IMPORT", None, required=True),
             F("licence", "Licence class", "choice:PUBLIC_DISCLOSURE,PUBLIC_FEED,DERIVED,MANUAL,LICENSED", "MANUAL",
               None)],
           "For example, tag your own hand-coded CSV as MANUAL so that it is included in releases."),
     ]},

    {"id": "review", "group": "Check", "title": "Review", "intro": "", "actions": []},
    {"id": "operations", "group": "Check", "title": "Operations", "intro": "", "actions": []},

    {"id": "selftest", "group": "Check", "title": "Self-test",
     "intro": "Confirms that each public source (CNINFO, SSE, SZSE and the price feed) still answers in the shape "
              "this program expects. Run it on first use and whenever a collection step returns nothing.",
     "actions": [
         A("Run the live self-test", "self-test", [F("out", "Report folder", "folder", "selftest", "--out")],
           "About 16 polite requests (one per second). PASS = working; WARN = answered but looks unusual; "
           "FAIL = the site changed and an update is needed; NETWORK UNREACHABLE = no connection from this computer "
           "(check your network, proxy or firewall). Send selftest_report.json with any bug report.",
           after="open_report"),
         A("Check the self-test itself (offline)", "self-test", [
             F("out", "Report folder", "folder", "selftest_offline", "--out"),
             F("offline", "Use canned responses", "bool", True, ("--offline", None))],
           "Runs the same checks against built-in sample responses, without the network."),
     ]},

    {"id": "accuracy", "group": "Check", "title": "Parser accuracy",
     "intro": "Measures how accurately figures are read from documents, against a 'golden corpus' of reports whose "
              "values you have checked by hand. The result sets the confidence attached to extracted values.",
     "actions": [
         A("Add a report to a golden corpus", "corpus-template", [
             F("corpus", "Corpus folder", "folder", "corpus", "--corpus", required=True),
             F("document", "Report", "file", "", "--document", "A downloaded PDF, or a disclosure id.", required=True),
             F("title", "Title", "text", "", "--title", "e.g. 2025年年度报告 (decides which parsers apply)"),
             F("date", "Announcement date", "date", "", "--date")],
           "Copies the report into the corpus and writes a draft of the values the parsers read. Open the draft "
           "(expected/<id>.json), correct it against the report, then set \"verified\": true."),
         A("Evaluate parsers", "evaluate-parsers", [
             F("corpus", "Corpus folder", "folder", "corpus", "--corpus", required=True),
             F("calibrate", "Use results to calibrate confidence", "bool", False, ("--calibrate", None)),
             F("report", "Save full result", "text", "", "--report", "Optional, e.g. evaluation.json")],
           "Precision = share of values read that are right; recall = share of true values found; abstention = "
           "values not read at all (preferred to wrong ones). Calibration needs at least 30 checked values per parser."),
         A("Build a synthetic test corpus", "synthetic-corpus", [
             F("out", "Folder", "folder", "corpus_synthetic", "--out")],
           "Generated documents with known values, for checking that the parsers still work. Not used for calibration."),
         A("Show calibration", "calibration", []),
         A("List parsers", "parsers", []),
     ]},

    {"id": "settings", "group": "", "title": "Settings", "intro": "", "actions": []},
]


# Keep the Company page short: business/group views and board/industry views
# get their own pages under Analyse.
def _split_company_page():
    company = next(sec for sec in SECTIONS if sec["id"] == "company")
    groups = {
        "structure": ("Business & group", "How the company earns its revenue and how the group is organised, "
                      "for the latest report or as known on a past date.",
                      ("segments", "segment-history", "subsidiaries", "scope-changes")),
        "board": ("Board & industry", "Who runs the company and how it compares with its industry peers.",
                  ("governance", "peers", "industry-stats", "control", "resolve-persons", "interlocks",
                   "common-controllers", "entity")),
        "people": ("People & ESG", "R&D effort, workforce and sustainability information for one year.",
                   ("human-capital", "human-capital-history", "esg")),
    }
    pos = SECTIONS.index(company) + 1
    for sid, (title, intro, commands) in groups.items():
        actions = [a for a in company["actions"] if a["command"] in commands]
        company["actions"] = [a for a in company["actions"] if a["command"] not in commands]
        SECTIONS.insert(pos, {"id": sid, "group": "Analyse", "title": title, "intro": intro, "actions": actions})
        pos += 1


_split_company_page()


def _number_collect_pages():
    """Collect pages are numbered in workflow order (v1.6: computed, not typed)."""
    n = 0
    for sec in SECTIONS:
        if sec["group"] == "Collect":
            n += 1
            sec["title"] = f"{n}  " + re.sub(r"^\d+\s+", "", sec["title"])


_number_collect_pages()


def build_argv(command: str, fields: list, values: dict) -> list[str]:
    """Translate form values into CLI arguments (pure; unit-tested)."""
    argv = [command]
    for f in fields:
        value = values.get(f["key"])
        if f["kind"] == "bool":
            flag = f["flag"][0] if value else f["flag"][1]
            if flag:  # a one-sided switch has no 'off' flag
                argv.append(flag)
            continue
        value = "" if value is None else str(value).strip()
        if not value:
            continue
        if f["flag"] is None:
            argv.append(value)
        else:
            argv += [f["flag"], value]
    return argv


def check_values(fields: list, values: dict) -> list[str]:
    """Return human-readable problems with the form (pure; unit-tested)."""
    problems = []
    for f in fields:
        v = values.get(f["key"])
        v = "" if v is None or isinstance(v, bool) else str(v).strip()
        if f["required"] and not v:
            problems.append(f"{f['label']} is required.")
        if v and f["kind"] == "date" and not DATE_RE.match(v):
            problems.append(f"{f['label']} must be a date like 2026-01-31.")
        if v and f["kind"] == "code" and not re.fullmatch(r"\d{1,6}", v):
            problems.append(f"{f['label']} must be a six-digit code.")
        if v and f["kind"] == "year" and not re.fullmatch(r"(19|20)\d{2}", v):
            problems.append(f"{f['label']} must be a year such as 2025.")
        if v and f["kind"] == "number" and not re.fullmatch(r"-?\d+(\.\d+)?", v):
            problems.append(f"{f['label']} must be a number.")
        if v and f["kind"] == "integer" and not re.fullmatch(r"-?\d+", v):
            problems.append(f"{f['label']} must be a whole number.")
    return problems


# ---------------------------------------------------------------------------
# Settings and running
# ---------------------------------------------------------------------------

def _settings_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "AShareScraper" / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        p = _settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def default_data_folder() -> Path:
    return Path.home() / "Documents" / "AShareScraper"


def apply_data_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["ASHARE_DB"] = str(folder / "ashares.db")
    os.environ["ASHARE_RAW_DIR"] = str(folder / "raw")
    os.environ["ASHARE_DISCLOSURE_DIR"] = str(folder / "disclosures")
    os.environ["ASHARE_MARKET_RAW_DIR"] = str(folder / "market_raw")
    os.chdir(folder)


class _Tee(io.StringIO):
    """Captures output and forwards each completed line to a callback (v2.0.1:
    long actions show progress as they run instead of only at the end)."""

    def __init__(self, stream=None):
        super().__init__()
        self._stream, self._pending = stream, ""

    def write(self, text):
        n = super().write(text)
        if self._stream:
            self._pending += text
            if "\n" in self._pending:
                head, self._pending = self._pending.rsplit("\n", 1)
                self._stream(head + "\n")
        return n

    def flush_pending(self):
        if self._stream and self._pending:
            self._stream(self._pending)
            self._pending = ""


# v2.0.6 (finding 51): what running a stopped command again does, said only where it is true.
RESUME_NOTES = {
    "catalogue-disclosures": "running it again resumes with the first unfinished day",
    "recatalogue-busy-days": "running it again resumes with the first unfinished day",
    "download-documents": "running it again downloads only the documents still missing",
    "extract-financials": "documents read so far are saved; running it again continues with the rest",
    # v2.0.8 (findings 76 and 79): the table extractors resume too
    "extract-top-holders": "reports read so far are saved; running it again continues with the rest",
    "extract-control": "reports read so far are saved; running it again continues with the rest",
    "extract-segments": "reports read so far are saved; running it again continues with the rest",
    "extract-subsidiaries": "reports read so far are saved; running it again continues with the rest",
    "extract-human-capital": "reports read so far are saved; running it again continues with the rest",
    "extract-management": "annual reports read so far are saved; running it again continues with the rest",
    "update-universe": "quote-list pages fetched today are kept; running it again continues",
    "job-run": "running the job again resumes where it stopped",
}


def stop_message(argv: list[str], exc) -> str:
    note = RESUME_NOTES.get(argv[0] if argv else "")
    return f"Stopped: {exc}" + (f"; {note}" if note else "")


def run_command(argv: list[str], stream=None) -> tuple[int, str]:
    """Run one CLI command in-process and capture its output; with *stream*,
    each line is also passed on as it is written."""
    from .cli import app
    from .http import Cancelled, reset_cancel
    reset_cancel()
    buf = _Tee(stream)
    os.environ["COLUMNS"] = os.environ.get("ASHARE_GUI_COLUMNS", "150")
    code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rv = app(argv, standalone_mode=False)
            if isinstance(rv, int) and not isinstance(rv, bool):    # typer.Exit(code) returns its code here
                code = rv
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        except Cancelled as exc:
            code = 130
            print(stop_message(argv, exc))
        except Exception as exc:
            code = 1
            msg = getattr(exc, "format_message", None)
            if callable(msg):
                print(msg())
            elif os.getenv("ASHARE_DEBUG"):
                print("".join(traceback.format_exception(exc)))
            else:
                from .errors import friendly_error
                print(friendly_error(exc))
    buf.flush_pending()
    return code, buf.getvalue()


def open_path(path) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def database_summary() -> dict:
    """Row counts for the home page."""
    from .models import init_db, engine
    init_db()
    out = {}
    with engine().connect() as conn:
        for t, label in (("companies", "Companies"), ("disclosures", "Disclosures"),
                         ("financial_facts", "Financial figures"), ("market_bars", "Price bars"),
                         ("corporate_actions", "Corporate actions"), ("regulatory_events", "Regulatory events"),
                         ("validation_flags", "Validation findings")):
            out[label] = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {t}").scalar()
    return out


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

PALETTE = {"bg": "#ffffff", "side": "#f4f4f6", "line": "#e3e3e8", "fg": "#1d1d1f", "muted": "#6e6e73",
           "accent": "#9c1c24", "accent_hover": "#7f161d", "sel": "#e8e8ed", "card": "#fafafb",
           "out_bg": "#fbfbfc"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x800")
        self.minsize(960, 640)
        self.configure(bg=PALETTE["bg"])
        self.settings = load_settings()
        self.folder = Path(self.settings.get("data_folder") or default_data_folder())
        apply_data_folder(self.folder)
        os.environ["ASHARE_OPTIONAL_BOARDS"] = ",".join(self.settings.get("optional_boards") or [])
        os.environ["ASHARE_PRICE_SOURCE"] = self.settings.get("price_source") or "eastmoney"
        self.out_queue: queue.Queue = queue.Queue()
        self.busy = False
        self.run_buttons: list[ttk.Button] = []
        self.pages: dict[str, ttk.Frame] = {}
        self.nav: dict[str, tk.Label] = {}
        self._fonts()
        self._style()
        self._build()
        self.show("home")
        self.after(80, self._drain)
        threading.Thread(target=self._init_db, daemon=True).start()

    # -- appearance ---------------------------------------------------------
    def _fonts(self):
        from tkinter import font as tkfont
        families = set(tkfont.families(self))

        def pick(*names):
            return next((n for n in names if n in families), names[-1])
        base = pick("Segoe UI", "Microsoft YaHei UI", "Helvetica Neue", "DejaVu Sans", "TkDefaultFont")
        # Output tables need a fixed-width font to stay aligned.
        mono = pick("Consolas", "Cascadia Mono", "Menlo", "DejaVu Sans Mono", "Courier New", "TkFixedFont")
        self.f_body = (base, 10)
        self.f_small = (base, 9)
        self.f_bold = (base, 10, "bold")
        self.f_title = (base, 17, "bold")
        self.f_card = (base, 11, "bold")
        self.f_nav = (base, 10)
        self.f_group = (base, 8, "bold")
        self.f_mono = (mono, 9)
        self.f_big = (base, 20, "bold")

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        P = PALETTE
        s.configure(".", background=P["bg"], foreground=P["fg"], font=self.f_body)
        s.configure("TFrame", background=P["bg"])
        s.configure("Side.TFrame", background=P["side"])
        s.configure("Card.TFrame", background=P["card"], relief="solid", borderwidth=1)
        s.configure("TLabel", background=P["bg"], foreground=P["fg"])
        s.configure("Card.TLabel", background=P["card"])
        s.configure("Muted.TLabel", background=P["bg"], foreground=P["muted"], font=self.f_small)
        s.configure("CardMuted.TLabel", background=P["card"], foreground=P["muted"], font=self.f_small)
        s.configure("Title.TLabel", font=self.f_title)
        s.configure("CardTitle.TLabel", background=P["card"], font=self.f_card)
        s.configure("TEntry", fieldbackground="#ffffff", bordercolor=P["line"], lightcolor=P["line"], padding=4)
        s.configure("TCombobox", fieldbackground="#ffffff", bordercolor=P["line"], padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], selectbackground=[("readonly", "#ffffff")],
              selectforeground=[("readonly", P["fg"])])
        s.configure("TCheckbutton", background=P["card"])
        s.configure("Plain.TCheckbutton", background=P["bg"])
        s.configure("Accent.TButton", background=P["accent"], foreground="#ffffff", borderwidth=0,
                    focusthickness=0, padding=(16, 6), font=self.f_bold)
        s.map("Accent.TButton", background=[("disabled", "#c9c9ce"), ("active", P["accent_hover"])])
        s.configure("TButton", padding=(10, 4), bordercolor=P["line"])
        s.configure("Small.TButton", padding=(8, 1), font=self.f_small, bordercolor=P["line"])
        s.configure("Link.TButton", background=P["bg"], foreground=P["accent"], borderwidth=0, padding=(0, 2))
        s.map("Link.TButton", background=[("active", P["bg"])], foreground=[("active", P["accent_hover"])])
        s.configure("Horizontal.TProgressbar", background=P["accent"], troughcolor=P["line"], borderwidth=0)

    # -- layout -------------------------------------------------------------
    def _build(self):
        P = PALETTE
        side = ttk.Frame(self, style="Side.TFrame", width=224)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="A-share", justify="left", bg=P["side"], fg=P["accent"],
                 font=self.f_card, anchor="w").pack(fill="x", padx=18, pady=(18, 0))
        tk.Label(side, text="Company Intelligence", justify="left", bg=P["side"], fg=P["fg"],
                 font=self.f_bold, anchor="w").pack(fill="x", padx=18, pady=(0, 12))
        group = None
        for sec in SECTIONS:
            if sec["group"] != group:
                group = sec["group"]
                if group:
                    tk.Label(side, text=group.upper(), bg=P["side"], fg=P["muted"], font=self.f_group,
                             anchor="w").pack(fill="x", padx=18, pady=(8, 1))
                elif sec["id"] == "settings":
                    tk.Frame(side, height=1, bg=P["line"]).pack(fill="x", padx=14, pady=(12, 6))
            lbl = tk.Label(side, text=sec["title"], bg=P["side"], fg=P["fg"], font=self.f_nav, anchor="w",
                           padx=18, pady=2, cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, i=sec["id"]: self.show(i))
            lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=P["sel"]) if w is not self._current_nav() else None)
            lbl.bind("<Leave>", lambda e, w=lbl: w.configure(bg=P["side"]) if w is not self._current_nav() else None)
            self.nav[sec["id"]] = lbl
        self.side_folder = tk.Label(side, text="", bg=P["side"], fg=P["muted"], font=self.f_small,
                                    anchor="w", justify="left", wraplength=200)
        self.side_folder.pack(side="bottom", fill="x", padx=18, pady=(0, 6))
        self._update_folder_label()

        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True)
        # Output panel at the bottom with a fixed, modest height; the page
        # above takes the remaining space. "Expand" toggles a taller panel.
        out = ttk.Frame(right)
        out.pack(side="bottom", fill="x")
        self.page_host = ttk.Frame(right)
        self.page_host.pack(side="top", fill="both", expand=True)
        for sec in SECTIONS:
            self.pages[sec["id"]] = self._build_page(sec)
        tk.Frame(out, height=1, bg=P["line"]).pack(fill="x")
        bar = ttk.Frame(out, padding=(20, 8, 20, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Output", font=self.f_bold).pack(side="left")
        self.status = tk.StringVar(value="Ready")
        self.status_lbl = ttk.Label(bar, textvariable=self.status, style="Muted.TLabel")
        self.status_lbl.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.stop_btn = ttk.Button(bar, text="Stop", style="Small.TButton", command=self._stop)
        for text, cmd in (("Clear", lambda: self.log.delete("1.0", "end")), ("Copy", self._copy),
                          ("Expand", self._toggle_output),
                          ("Run log", lambda: self._open(self.folder / "run_log.txt"))):
            ttk.Button(bar, text=text, style="Small.TButton", command=cmd).pack(side="right", padx=(6, 0))
        box = ttk.Frame(out, padding=(20, 0, 20, 14))
        box.pack(fill="both", expand=True)
        self.log = tk.Text(box, wrap="none", height=11, font=self.f_mono, bg=P["out_bg"], fg=P["fg"], relief="flat",
                           borderwidth=0, highlightthickness=1, highlightbackground=P["line"], padx=10, pady=8)
        ys = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        xs = ttk.Scrollbar(box, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("cmd", foreground=PALETTE["accent"], font=self.f_mono)
        self.log.tag_configure("muted", foreground=PALETTE["muted"])

    def _scrollable(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0, bg=PALETTE["bg"])
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(28, 22, 28, 22))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def wheel(e):
            if e.num == 4:
                canvas.yview_scroll(-2, "units")
            elif e.num == 5:
                canvas.yview_scroll(2, "units")
            else:
                canvas.yview_scroll(int(-e.delta / 120) * 2, "units")
        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", wheel), canvas.bind_all("<Button-4>", wheel),
                                          canvas.bind_all("<Button-5>", wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"), canvas.unbind_all("<Button-4>"),
                                          canvas.unbind_all("<Button-5>")))
        return inner

    def _header(self, inner, title, intro):
        ttk.Label(inner, text=re.sub(r"^\d+\s+", "", title), style="Title.TLabel").pack(anchor="w")
        if intro:
            lbl = ttk.Label(inner, text=intro, style="Muted.TLabel", wraplength=760, justify="left")
            lbl.pack(anchor="w", pady=(4, 16))
            inner.bind("<Configure>", lambda e, l=lbl: l.configure(wraplength=max(400, e.width - 130)), add="+")

    def _build_page(self, sec):
        frame = ttk.Frame(self.page_host)
        inner = self._scrollable(frame)
        if sec["id"] == "home":
            self._build_home(inner)
            return frame
        if sec["id"] == "settings":
            self._build_settings(inner)
            return frame
        if sec["id"] == "operations":
            for w in frame.winfo_children():
                w.destroy()
            from .gui_review import OperationsPage
            self.operations_page = OperationsPage(self, frame)
            return frame
        if sec["id"] == "review":
            # the review page manages its own layout; drop the scrolling frame
            for w in frame.winfo_children():
                w.destroy()
            from .gui_review import ReviewPage
            self.review_page = ReviewPage(self, frame)
            return frame
        self._header(inner, sec["title"], sec["intro"])
        for action in sec["actions"]:
            self._build_card(inner, action)
        return frame

    def _build_card(self, parent, action):
        P = PALETTE
        card = tk.Frame(parent, bg=P["card"], highlightthickness=1, highlightbackground=P["line"])
        card.pack(fill="x", pady=6)
        body = tk.Frame(card, bg=P["card"])
        body.pack(fill="x", padx=16, pady=12)
        head = tk.Frame(body, bg=P["card"])
        head.pack(fill="x")
        ttk.Label(head, text=action["label"], style="CardTitle.TLabel").pack(side="left")
        values = {}
        btn = ttk.Button(head, text="Run", style="Accent.TButton",
                         command=lambda a=action, v=values: self._run(a, v))
        btn.pack(side="right")
        self.run_buttons.append(btn)
        if action["note"]:
            ttk.Label(body, text=action["note"], style="CardMuted.TLabel", wraplength=700,
                      justify="left").pack(anchor="w", pady=(2, 0))
        if action["fields"]:
            grid = tk.Frame(body, bg=P["card"])
            grid.pack(fill="x", pady=(10, 0))
            for c in range(3):
                grid.columnconfigure(c, uniform="field", weight=1)
            for i, f in enumerate(action["fields"]):
                cell = tk.Frame(grid, bg=P["card"])
                cell.grid(row=i // 3, column=i % 3, sticky="nw", padx=(0, 22), pady=(0, 8))
                values[f["key"]] = self._field(cell, f)
        return card

    def _field(self, cell, f):
        kind = f["kind"]
        if kind == "bool":
            var = tk.BooleanVar(value=bool(f["default"]))
            ttk.Checkbutton(cell, text=f["label"], variable=var).pack(anchor="w", pady=(18, 0))
            if f["hint"]:
                ttk.Label(cell, text=f["hint"], style="CardMuted.TLabel", wraplength=230,
                          justify="left").pack(anchor="w", pady=(2, 0))
            return var
        label = f["label"] + (" *" if f["required"] else "")
        ttk.Label(cell, text=label, style="Card.TLabel", font=self.f_small).pack(anchor="w")
        var = tk.StringVar(value=f["default"])
        if kind.startswith("choice:"):
            opts = kind[7:].split(";") if ";" in kind else kind[7:].split(",")
            w = ttk.Combobox(cell, textvariable=var, values=opts, state="readonly",
                             width=max(14, min(34, max(len(o) for o in opts) + 2)))
            w.pack(anchor="w")
        elif kind in ("file", "folder"):
            row = tk.Frame(cell, bg=PALETTE["card"])
            row.pack(anchor="w")
            ttk.Entry(row, textvariable=var, width=24).pack(side="left")
            ttk.Button(row, text="Browse…", style="Small.TButton",
                       command=lambda: self._browse(var, kind)).pack(side="left", padx=(4, 0))
        else:
            width = {"date": 12, "code": 10, "year": 8, "number": 8, "integer": 8}.get(kind, 46 if f["key"] == "sql" else 24)
            ttk.Entry(cell, textvariable=var, width=width).pack(anchor="w")
        if f["hint"]:
            ttk.Label(cell, text=f["hint"], style="CardMuted.TLabel", wraplength=230,
                      justify="left").pack(anchor="w", pady=(2, 0))
        return var

    def _build_home(self, inner):
        P = PALETTE
        ttk.Label(inner, text="Getting started", style="Title.TLabel").pack(anchor="w")
        ttk.Label(inner, text="Collect data step by step, then analyse and validate it. Every action keeps a record of "
                              "its source document, so any figure can be traced back.",
                  style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(4, 16))
        self.summary_frame = tk.Frame(inner, bg=P["bg"])
        self.summary_frame.pack(fill="x", pady=(0, 18))
        steps = [
            ("universe", "Update the company list", "Downloads the list of listed companies from CNINFO."),
            ("disclosures", "Catalogue announcements for a company", "Try one code (e.g. 600519) with documents downloaded."),
            ("financials", "Extract financial figures", "Reads statements from the downloaded reports."),
            ("actions", "Extract corporate actions and regulatory events", "Also see the Regulatory & legal section."),
            ("industry", "Import an industry classification list (optional)", "Enables peer groups and industry statistics."),
            ("validate", "Run all checks", "Flags inconsistencies; never changes data."),
            ("company", "Open the company report", "A one-page summary you can save or print."),
        ]
        ttk.Label(inner, text="Suggested first run", font=self.f_bold).pack(anchor="w", pady=(0, 6))
        for n, (sid, title, note) in enumerate(steps, 1):
            row = tk.Frame(inner, bg=P["bg"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=str(n), width=3, bg=P["sel"], fg=P["fg"], font=self.f_bold).pack(side="left", padx=(0, 12))
            col = tk.Frame(row, bg=P["bg"])
            col.pack(side="left", fill="x", expand=True)
            ttk.Button(col, text=title, style="Link.TButton", command=lambda i=sid: self.show(i)).pack(anchor="w")
            ttk.Label(col, text=note, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(inner, text="Notes", font=self.f_bold).pack(anchor="w", pady=(20, 4))
        for line in ("Requests are rate-limited (one per second) and never bypass logins or CAPTCHAs.",
                     "Public price feeds are labelled as such and are not exchange-authoritative.",
                     "'As of' dates use only information published by that date, avoiding look-ahead bias.",
                     "Fields marked * are required. Leaving a security code blank usually means all companies."):
            ttk.Label(inner, text="•  " + line, style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=1)

    def _refresh_summary(self):
        try:
            counts = database_summary()
        except Exception:
            return
        P = PALETTE
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for i, (k, v) in enumerate(counts.items()):
            box = tk.Frame(self.summary_frame, bg=P["card"], highlightthickness=1, highlightbackground=P["line"])
            box.grid(row=0, column=i, sticky="nsew", padx=(0, 8))
            self.summary_frame.columnconfigure(i, weight=1)
            tk.Label(box, text=f"{v:,}", bg=P["card"], fg=P["fg"], font=self.f_big).pack(anchor="w", padx=12, pady=(8, 0))
            tk.Label(box, text=k, bg=P["card"], fg=P["muted"], font=self.f_small).pack(anchor="w", padx=12, pady=(0, 8))

    def _build_settings(self, inner):
        ttk.Label(inner, text="Settings", style="Title.TLabel").pack(anchor="w")
        ttk.Label(inner, text="Where the database, downloaded documents, exports and reports are kept.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        self.folder_var = tk.StringVar(value=str(self.folder))
        row = ttk.Frame(inner)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder_var, state="readonly", width=70).pack(side="left")
        ttk.Button(row, text="Change…", command=self._choose_folder).pack(side="left", padx=6)
        ttk.Button(row, text="Open", command=lambda: self._open(self.folder)).pack(side="left")
        ttk.Label(inner, text="Contents: ashares.db (database), disclosures\\ and raw\\ (original documents and "
                              "responses), exports\\, reports\\, releases\\, run_log.txt (every action with its "
                              "equivalent command).", style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(inner, text="Optional boards", font=self.f_bold).pack(anchor="w", pady=(22, 4))
        ttk.Label(inner, text="Off by default. When on, 'Update the company list' also accepts these securities "
                              "(their CNINFO list and query settings are not yet verified against the live site; "
                              "run the self-test after enabling).", style="Muted.TLabel", wraplength=760,
                  justify="left").pack(anchor="w")
        self.board_vars = {}
        enabled = set(self.settings.get("optional_boards") or [])
        for key, label in (("BSE", "Beijing Stock Exchange (codes 920, 43, 83, 87, 88)"),
                           ("B_SHARE", "B-shares (SSE 900, SZSE 200; USD and HKD)")):
            var = tk.BooleanVar(value=key in enabled)
            self.board_vars[key] = var
            ttk.Checkbutton(inner, text=label, variable=var, style="Plain.TCheckbutton",
                            command=self._save_boards).pack(anchor="w", pady=(4, 0))
        ttk.Label(inner, text="Price source", font=self.f_bold).pack(anchor="w", pady=(22, 4))
        ttk.Label(inner, text="Where daily prices come from: downloads, the backfill and the daily update. Both public "
                              "sources are unofficial feeds, not exchange-authoritative; their terms are yours to "
                              "check. 'Test price sources' (Market data) shows which one answers from your network. "
                              "'None' downloads nothing: import licensed prices from CSV instead. Imported prices "
                              "are always preferred to a public feed's for the same day.", style="Muted.TLabel",
                  wraplength=760, justify="left").pack(anchor="w")
        self.price_var = tk.StringVar(value=self.settings.get("price_source") or "eastmoney")
        prow = ttk.Frame(inner)
        prow.pack(fill="x", pady=(6, 0))
        for key, label in (("eastmoney", "Eastmoney (public)"), ("tencent", "Tencent (public)"),
                           ("none", "None: CSV import only")):
            ttk.Radiobutton(prow, text=label, value=key, variable=self.price_var,
                            command=self._save_price_source).pack(side="left", padx=(0, 14))
        ttk.Label(inner, text="Updates", font=self.f_bold).pack(anchor="w", pady=(22, 4))
        ttk.Label(inner, text="The program contacts no update server unless you enter one here. The check only "
                              "reports whether a newer version exists; it never downloads or installs anything.",
                  style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w")
        urow = ttk.Frame(inner)
        urow.pack(fill="x", pady=(6, 0))
        self.update_var = tk.StringVar(value=self.settings.get("update_url") or "")
        ttk.Entry(urow, textvariable=self.update_var, width=60).pack(side="left")
        ttk.Button(urow, text="Check for updates", command=self._check_update).pack(side="left", padx=6)
        ttk.Label(inner, text="About", font=self.f_bold).pack(anchor="w", pady=(22, 4))
        ttk.Label(inner, text=f"{APP_NAME} v{__version__}. The same functions are available from the command line as "
                              "ashare-cli.exe in the program folder (run 'ashare-cli --help'). The user guide, "
                              "methods document and codebook are in the docs folder.",
                  style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w")

    def _check_update(self):
        url = self.update_var.get().strip()
        self.settings["update_url"] = url
        save_settings(self.settings)

        def work():
            from .update import check_for_update
            r = check_for_update(url or None)
            extra = f"\n{r['url']}\nSHA-256: {r.get('sha256') or 'not given'}" if r.get("url") else ""
            self.after(0, lambda: messagebox.showinfo(APP_NAME, r["message"] + extra))
        threading.Thread(target=work, daemon=True).start()

    def _save_price_source(self):
        v = self.price_var.get()
        self.settings["price_source"] = v
        save_settings(self.settings)
        os.environ["ASHARE_PRICE_SOURCE"] = v
        self._log(f"Price source: {v}\n", "muted")

    def _save_boards(self):
        on = [k for k, v in self.board_vars.items() if v.get()]
        self.settings["optional_boards"] = on
        save_settings(self.settings)
        os.environ["ASHARE_OPTIONAL_BOARDS"] = ",".join(on)
        self._log(f"Optional boards: {', '.join(on) or 'none'}\n", "muted")

    # -- behaviour ------------------------------------------------------------
    def _current_nav(self):
        return self.nav.get(getattr(self, "_current", None))

    def show(self, sid):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[sid].pack(fill="both", expand=True)
        for i, lbl in self.nav.items():
            lbl.configure(bg=PALETTE["sel"] if i == sid else PALETTE["side"],
                          font=self.f_bold if i == sid else self.f_nav)
        self._current = sid
        if sid == "home":
            self._refresh_summary()

    def _update_folder_label(self):
        parts = self.folder.parts
        short = str(Path(*parts[-2:])) if len(parts) > 2 else str(self.folder)
        self.side_folder.configure(text=f"v{__version__} · data: {self.folder.name}")

    def _init_db(self):
        code, out = run_command(["init-db"])
        if code:
            self._log(out)
        self.after(0, self._refresh_summary)

    def _browse(self, var, kind):
        p = (filedialog.askopenfilename(initialdir=str(self.folder)) if kind == "file"
             else filedialog.askdirectory(initialdir=str(self.folder)))
        if p:
            var.set(p)

    def _choose_folder(self):
        p = filedialog.askdirectory(initialdir=str(self.folder), title="Choose data folder")
        if not p:
            return
        self.folder = Path(p)
        apply_data_folder(self.folder)
        self.folder_var.set(str(self.folder))
        self._update_folder_label()
        self.settings["data_folder"] = str(self.folder)
        save_settings(self.settings)
        self._log(f"Data folder changed to {self.folder}\n", "muted")
        threading.Thread(target=self._init_db, daemon=True).start()

    def _open(self, path):
        try:
            Path(path).touch(exist_ok=True) if str(path).endswith(".txt") else None
            open_path(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _toggle_output(self):
        self.log.configure(height=11 if int(self.log.cget("height")) > 11 else 30)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.log.get("1.0", "end"))

    def _run(self, action, values):
        if self.busy:
            return
        vals = {k: v.get() for k, v in values.items()}
        problems = check_values(action["fields"], vals)
        if problems:
            messagebox.showwarning(action["label"], "\n".join(problems))
            return
        if not self._confirm_heavy(action, vals):
            return
        argv = build_argv(action["command"], action["fields"], vals)
        self._last_vals = vals
        self.busy = True
        for b in self.run_buttons:
            b.state(["disabled"])
        self.status.set(f"Running: {action['label']}…")
        self.progress.pack(side="left", padx=8)
        self.progress.start(12)
        self.stop_btn.pack(side="left", padx=(10, 0), before=self.status_lbl)   # first, so it always has room
        self.stop_btn.state(["!disabled"])
        shown = " ".join(a if " " not in a else f'"{a}"' for a in argv)
        self._log(f"\n› {action['label']}   (ashare-cli {shown})\n", "cmd")

        def work():
            started = _dt.datetime.now()
            code, out = run_command(argv, stream=self._log)
            elapsed = (_dt.datetime.now() - started).total_seconds()
            if out and not out.endswith("\n"):
                self._log("\n")
            self._log({0: "Done", 3: "Finished with gaps", 130: "Stopped"}.get(code, "Failed")
                      + f" after {elapsed:.1f}s\n", "muted")
            try:
                with open(self.folder / "run_log.txt", "a", encoding="utf-8") as fh:
                    fh.write(f"\n=== {started.isoformat(timespec='seconds')}  v{__version__}  "
                             f"ashare-cli {shown}\n{out}[exit {code}, {elapsed:.1f}s]\n")
            except Exception:
                pass
            self.after(0, lambda: self._done(action, code, out))

        threading.Thread(target=work, daemon=True).start()

    def _stop(self):
        from .http import request_cancel
        request_cancel()
        self.stop_btn.state(["disabled"])
        self.status.set("Stopping after the current request…")

    def _confirm_heavy(self, action, vals) -> bool:
        """Warn before whole-market actions that take hours (v2.0.1)."""
        cmd = action["command"]
        whole = not (vals.get("security_code") or vals.get("code"))
        if not whole or cmd not in ("catalogue-disclosures", "acquire-market", "download-documents"):
            return True
        try:
            n = database_summary().get("Companies", 0)
        except Exception:
            n = 0
        if cmd == "catalogue-disclosures" and not vals.get("download"):
            return True             # market-wide catalogue: a few hundred requests
        text = {"catalogue-disclosures": "This catalogues announcements for all {n:,} companies and then downloads "
                                         "the reports. Downloading a year of reports for the whole market is tens "
                                         "of thousands of files (tens of GB) and takes many hours at the polite rate.",
                "acquire-market": "This downloads price history for all {n:,} companies, one request each "
                                  "(about {m} minutes). For daily prices, Operations > Daily update needs about 60 "
                                  "requests.",
                "download-documents": "This downloads every catalogued document of the chosen kinds that is not yet "
                                      "on disk; for the whole market that can be many hours."}[cmd]
        return messagebox.askyesno(action["label"], text.format(n=n, m=n // 60 + 1) +
                                   "\n\nYou can press Stop at any time; running it again resumes. Try one company "
                                   "first by entering a security code.\n\nContinue?")

    def _done(self, action, code, out):
        self.busy = False
        self.progress.stop()
        self.progress.pack_forget()
        self.stop_btn.pack_forget()
        for b in self.run_buttons:
            b.state(["!disabled"])
        self.status.set({0: "Ready", 3: "Finished with gaps (see the list in the output)",
                         130: "Stopped; run it again to resume"}.get(code, "Last action failed (see output)"))
        if code == 0:
            self._maybe_chart(action, getattr(self, "_last_vals", {}))
        if code == 0 and action.get("after") == "explore":
            from .gui_review import ExplorerWindow
            vals = getattr(self, "_last_vals", {})
            panel = (self.folder / "panels" / f"{vals.get('name') or 'panel'}.csv") if action["command"] == "build-panel" \
                else None
            ExplorerWindow(self, str(panel) if panel and panel.exists() else None)
        if code == 0 and action.get("after") == "open_report":
            m = re.search(r"(?:Report written|Report):\s*(.+\.html)", out)
            if m:
                webbrowser.open(Path(m.group(1).strip()).resolve().as_uri())
        elif code == 0 and action.get("after") == "open_folder":
            m = re.search(r"'(?:release|folder)': '([^']+)'", out)
            target = Path(m.group(1)) if m else self.folder / "exports"
            try:
                open_path(target if target.exists() else self.folder)
            except Exception:
                pass
        if self._current == "home":
            self._refresh_summary()

    def _maybe_chart(self, action, vals):
        """Show the chart for chartable actions (v1.5)."""
        from .gui_review import CHARTS, ChartWindow
        builder = CHARTS.get(action["command"])
        if not builder:
            return
        try:
            spec = builder(vals)
        except Exception as exc:
            self._log(f"(No chart: {exc})\n", "muted")
            return
        if spec.graph is not None:
            if len(spec.graph.get("nodes") or []) < 2:
                return
        elif not any(p.y is not None for s in spec.series for p in s.points):
            return
        if getattr(self, "chart_window", None) is None or not self.chart_window.winfo_exists():
            self.chart_window = ChartWindow(self)
        self.chart_window.show(spec)

    def run_quiet(self, argv, label):
        """Run a command without a card (used by chart clicks)."""
        def work():
            code, out = run_command(argv)
            self._log(f"\n› {label}\n", "cmd")
            self._log(out if out.endswith("\n") or not out else out + "\n")
        threading.Thread(target=work, daemon=True).start()

    def show_review(self):
        self.show("review")

    def _log(self, text, tag=None):
        self.out_queue.put((text, tag))

    def _drain(self):
        try:
            while True:
                text, tag = self.out_queue.get_nowait()
                self.log.insert("end", text, tag) if tag else self.log.insert("end", text)
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(80, self._drain)


def run():
    App().mainloop()


if __name__ == "__main__":
    run()
