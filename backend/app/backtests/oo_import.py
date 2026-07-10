"""Option Omega trade-log CSV importer — the manual bridge's return
path. OO has no public API for its export schema (its docs page 403s
from this sandbox), so this matches columns by normalized-alias rather
than one exact literal header string, and cleans the same $/,/% quirks
the Fidelity parser already handles. A CSV missing a required column
(open date, close date, or P/L) is rejected with a clear error — plan:
"malformed OO CSV rejected with a clear error" — rather than silently
importing garbage."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

REQUIRED_ALIASES = {
    "openDate": {"dateopened", "opened", "openedon", "entrydate", "dateentered"},
    "closeDate": {"dateclosed", "closed", "closedon", "exitdate", "dateexited"},
    "pnl": {"pl", "pnl", "profitloss", "pandl", "totalpl"},
}
OPTIONAL_ALIASES = {
    "legs": {"legs", "leg"},
    "premium": {"premium", "totalpremium"},
    "contracts": {"noofcontracts", "contracts", "numcontracts", "quantity"},
}

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%B %d, %Y")


def _normalize(header: str) -> str:
    return "".join(ch.lower() for ch in header if ch.isalnum())


def _match_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize(f): f for f in fieldnames}
    matched: dict[str, str] = {}
    missing: list[str] = []
    for field, aliases in REQUIRED_ALIASES.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found is None:
            missing.append(field)
        else:
            matched[field] = found
    if missing:
        raise ValueError(
            f"malformed Option Omega export: missing column(s) for {', '.join(missing)} "
            f"(saw headers: {', '.join(fieldnames)})"
        )
    for field, aliases in OPTIONAL_ALIASES.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found is not None:
            matched[field] = found
    return matched


def _clean_number(raw: str | None) -> float:
    if raw is None:
        raise ValueError("malformed Option Omega export: empty P/L value")
    s = raw.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "")
    try:
        value = float(s)
    except ValueError:
        raise ValueError(f"malformed Option Omega export: unparseable number {raw!r}") from None
    return -value if negative else value


def _parse_date(raw: str | None, field: str) -> date:
    if raw is None or not raw.strip():
        raise ValueError(f"malformed Option Omega export: empty {field}")
    text = raw.strip().split(" ")[0]  # drop a trailing time-of-day if present
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"malformed Option Omega export: unparseable {field} {raw!r}")


def parse_oo_trade_log(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("malformed Option Omega export: no header row")
    columns = _match_columns(reader.fieldnames)

    trades = []
    for row in reader:
        if not any((row.get(v) or "").strip() for v in columns.values()):
            continue  # blank spacer row
        trades.append(
            {
                "entryDate": _parse_date(row.get(columns["openDate"]), "open date").isoformat(),
                "exitDate": _parse_date(row.get(columns["closeDate"]), "close date").isoformat(),
                "pnl": _clean_number(row.get(columns["pnl"])),
                "legs": row.get(columns.get("legs", ""), "") or "",
                "contracts": _clean_number(row[columns["contracts"]]) if columns.get("contracts") else None,
            }
        )
    return trades
