from dataclasses import dataclass
import re

BOARD_MAP = {
    "SSE": {
        "600": "SSE_MAIN",
        "601": "SSE_MAIN",
        "603": "SSE_MAIN",
        "605": "SSE_MAIN",
        "688": "STAR",
        "689": "STAR",       # v2.0.2: STAR Market depositary receipts (e.g. 689009)
    },
    "SZSE": {
        "000": "SZSE_MAIN",
        "001": "SZSE_MAIN",
        "002": "SZSE_MAIN",
        "003": "SZSE_MAIN",
        "300": "CHINEXT",
        "301": "CHINEXT",
        "302": "CHINEXT",    # v2.0.2: new ChiNext code range (e.g. 302132, AVIC Chengdu Aircraft)
    },
}

@dataclass(frozen=True)
class AShare:
    code: str
    exchange: str
    board: str
    legal_name_cn: str | None
    short_name_cn: str | None
    org_id: str | None
    listing_date: str | None = None
    status: str | None = None

def clean_code(value) -> str:
    code = str(value).strip()
    if code.isdigit():
        return code.zfill(6)
    match = re.search(r"(\d{6})", code)
    if not match:
        raise ValueError(f"Cannot extract six-digit security code from {value!r}")
    return match.group(1)

# v1.6: optional boards, disabled by default. Enable with the environment
# variable ASHARE_OPTIONAL_BOARDS (comma-separated: BSE, B_SHARE) or in the
# desktop Settings page. Ordinary A-share behaviour is unchanged when they
# are off: B-share codes (900xxx, 200xxx) and BSE codes stay excluded.
OPTIONAL_BOARD_MAP = {
    "BSE": {"BSE": {"920": "BSE", "43": "BSE", "83": "BSE", "87": "BSE", "88": "BSE"}},
    # v2.1 (finding 9): Shenzhen B shares also use 201xxx (201872 is China Merchants Port's B share, 招港B)
    "B_SHARE": {"SSE": {"900": "SSE_B"}, "SZSE": {"200": "SZSE_B", "201": "SZSE_B"}},
}
SECURITY_TYPES = {"SSE_B": ("B_SHARE", "USD"), "SZSE_B": ("B_SHARE", "HKD"), "BSE": ("A_SHARE", "CNY")}


def enabled_optional_boards() -> set[str]:
    import os
    raw = os.environ.get("ASHARE_OPTIONAL_BOARDS", "")
    return {x.strip().upper() for x in raw.split(",") if x.strip().upper() in OPTIONAL_BOARD_MAP}


def _optional_maps(optional):
    names = enabled_optional_boards() if optional is None else {o.upper() for o in optional}
    for name in names:
        for exchange, prefixes in OPTIONAL_BOARD_MAP.get(name, {}).items():
            yield exchange, prefixes


def infer_exchange(code: str, optional=None) -> str | None:
    """Exchange of an ordinary A-share code, or of an enabled optional board."""
    code = clean_code(code)
    if code.startswith(tuple(BOARD_MAP["SSE"])):
        return "SSE"
    if code.startswith(tuple(BOARD_MAP["SZSE"])):
        return "SZSE"
    for exchange, prefixes in _optional_maps(optional):
        if code.startswith(tuple(prefixes)):
            return exchange
    return None

def infer_board(exchange: str, code: str, optional=None) -> str | None:
    exchange = exchange.upper()
    code = clean_code(code)
    for prefix, board in BOARD_MAP.get(exchange, {}).items():
        if code.startswith(prefix):
            return board
    for ex, prefixes in _optional_maps(optional):
        if ex == exchange:
            for prefix, board in prefixes.items():
                if code.startswith(prefix):
                    return board
    return None


def is_supported(code: str, optional=None) -> bool:
    """Ordinary A-share, or a security on an enabled optional board."""
    return infer_exchange(code, optional) is not None

def is_a_share(code: str) -> bool:
    """Ordinary SSE/SZSE A-share (optional boards never count)."""
    return infer_exchange(code, optional=()) is not None

def validate_a_share(item: AShare) -> list[str]:
    errors = []
    if not is_supported(item.code):
        errors.append("not an ordinary SSE/SZSE A-share code (or an optional board that is not enabled)")
    if infer_exchange(item.code) != item.exchange:
        errors.append("exchange/code mismatch")
    if infer_board(item.exchange, item.code) != item.board:
        errors.append("board/code mismatch")
    if not item.legal_name_cn:
        errors.append("missing Chinese company name")
    return errors


# v2.0.2: short names CNINFO keeps for delisted companies (国华退, 大明退市, PT金田A).
DELISTED_NAME_RE = re.compile(r"(退市|退$|退[AB]$|^PT)")


def looks_delisted(short_name: str | None) -> bool:
    return bool(short_name and DELISTED_NAME_RE.search(short_name.strip()))


def rejection_reason(code: str) -> str:
    """Why a code from the CNINFO list is not collected, in plain words."""
    code = clean_code(code)
    if code.startswith(("920", "43", "83", "87", "88")):
        return "Beijing Stock Exchange (enable under Settings > Optional boards)"
    if code.startswith(("900", "200", "201")):
        return "B shares (enable under Settings > Optional boards)"
    return "code range not recognised"
