"""Option Omega trade-log CSV import: normalized-alias column matching,
$()% cleanup, and a clear rejection for a malformed export."""

import pytest

from app.backtests.oo_import import parse_oo_trade_log


def test_parses_a_well_formed_export():
    csv_text = (
        "Date Opened,Date Closed,P/L,Legs,No. of Contracts\n"
        "01/15/2024,02/01/2024,\"$125.50\",\"-1 P95, +1 P90\",1\n"
        "02/05/2024,02/20/2024,\"($60.00)\",\"-1 P95, +1 P90\",1\n"
    )
    trades = parse_oo_trade_log(csv_text)
    assert len(trades) == 2
    assert trades[0] == {
        "entryDate": "2024-01-15",
        "exitDate": "2024-02-01",
        "pnl": 125.50,
        "legs": "-1 P95, +1 P90",
        "contracts": 1.0,
    }
    assert trades[1]["pnl"] == -60.00


def test_accepts_alternate_column_names():
    csv_text = "Opened,Closed,PnL\n2024-01-01,2024-01-15,100\n"
    trades = parse_oo_trade_log(csv_text)
    assert trades[0]["pnl"] == 100.0


def test_accepts_iso_dates():
    csv_text = "Date Opened,Date Closed,P/L\n2024-03-01,2024-03-20,50\n"
    trades = parse_oo_trade_log(csv_text)
    assert trades[0]["entryDate"] == "2024-03-01"


def test_missing_required_column_raises_clear_error():
    csv_text = "Date Opened,Legs\n01/15/2024,\"-1 P95\"\n"
    with pytest.raises(ValueError, match="missing column"):
        parse_oo_trade_log(csv_text)


def test_unparseable_pnl_raises_clear_error():
    csv_text = "Date Opened,Date Closed,P/L\n01/15/2024,02/01/2024,not-a-number\n"
    with pytest.raises(ValueError, match="unparseable number"):
        parse_oo_trade_log(csv_text)


def test_unparseable_date_raises_clear_error():
    csv_text = "Date Opened,Date Closed,P/L\nnot-a-date,02/01/2024,100\n"
    with pytest.raises(ValueError, match="unparseable open date"):
        parse_oo_trade_log(csv_text)


def test_blank_rows_are_skipped():
    csv_text = "Date Opened,Date Closed,P/L\n01/15/2024,02/01/2024,100\n,,\n"
    trades = parse_oo_trade_log(csv_text)
    assert len(trades) == 1


def test_no_header_row_raises():
    with pytest.raises(ValueError, match="no header row"):
        parse_oo_trade_log("")
