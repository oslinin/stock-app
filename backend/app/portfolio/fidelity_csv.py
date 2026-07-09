"""Fidelity Positions-CSV parser: normalizes exported rows into position
dicts (options + stock), skipping header noise and the disclaimer footer
a real export trails with. Option symbol format ref: medloh/stockpile."""

from __future__ import annotations

import csv
import io
import re

OPTION_SYMBOL_RE = re.compile(r"^-([A-Z]+\d*)(\d{2})(\d{2})(\d{2})([CP])([\d.]+)$")


def _clean_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s or s in ("--", "n/a", "N/A"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _parse_symbol(raw: str) -> dict:
    m = OPTION_SYMBOL_RE.match(raw.strip())
    if not m:
        return {"symbol": raw.strip(), "secType": "STK", "right": None, "strike": None, "expiry": None}
    root, yy, mm, dd, right, strike = m.groups()
    return {
        "symbol": root,
        "secType": "OPT",
        "right": right,
        "strike": float(strike),
        "expiry": f"20{yy}-{mm}-{dd}",
    }


def parse_fidelity_csv(text: str) -> list[dict]:
    """A row with no symbol or no parseable quantity is header noise, a
    blank spacer, or the disclaimer/footer text a real export trails
    with — skip it rather than guessing."""
    positions = []
    for row in csv.DictReader(io.StringIO(text)):
        symbol_raw = (row.get("Symbol") or "").strip()
        quantity = _clean_number(row.get("Quantity"))
        if not symbol_raw or quantity is None:
            continue
        parsed = _parse_symbol(symbol_raw)
        positions.append(
            {
                **parsed,
                "quantity": quantity,
                "multiplier": 100.0 if parsed["secType"] == "OPT" else 1.0,
                "lastPrice": _clean_number(row.get("Last Price")),
                "avgCost": _clean_number(row.get("Average Cost Basis")),
                "description": (row.get("Description") or "").strip(),
                "accountNumber": (row.get("Account Number") or "").strip(),
                "source": "fidelity_csv",
            }
        )
    return positions
