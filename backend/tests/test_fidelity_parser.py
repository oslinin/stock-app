"""Fidelity Positions-CSV parser: options symbols, negative quantities,
$()% quirks, and the disclaimer/footer rows a real export trails with."""

from app.portfolio.fidelity_csv import parse_fidelity_csv

HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Last Price Change,Current Value,Today's Gain/Loss Dollar,"
    "Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,"
    "Percent Of Account,Cost Basis Total,Average Cost Basis,Type"
)


def csv_text(*rows: str) -> str:
    return "\n".join([HEADER, *rows, "", "Date downloaded 07/09/2026 3:32 PM ET", "",
                       "Brokerage services are provided by Fidelity Brokerage Services LLC."])


def test_parses_a_stock_row():
    rows = csv_text(
        'Z12345678,Individual,AAPL,APPLE INC,100,$230.50,$1.20,"$23,050.00",'
        '"$120.00","0.52%","$3,050.00","15.25%","12.00%","$20,000.00","$200.00",Cash'
    )
    positions = parse_fidelity_csv(rows)
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "AAPL"
    assert p["secType"] == "STK"
    assert p["right"] is None
    assert p["quantity"] == 100.0
    assert p["multiplier"] == 1.0
    assert p["lastPrice"] == 230.50
    assert p["avgCost"] == 200.00
    assert p["accountNumber"] == "Z12345678"


def test_parses_a_short_stock_row_with_minus_sign():
    rows = csv_text('Z12345678,Individual,TSLA,TESLA INC,-50,$250.00,,,,,,,,,,Margin')
    positions = parse_fidelity_csv(rows)
    assert positions[0]["quantity"] == -50.0


def test_parses_a_short_position_with_parenthesized_quantity():
    rows = csv_text('Z12345678,Individual,GME,GAMESTOP CORP,(25),$20.00,,,,,,,,,,Margin')
    positions = parse_fidelity_csv(rows)
    assert positions[0]["quantity"] == -25.0


def test_parses_an_option_symbol():
    rows = csv_text(
        'Z12345678,Individual,-AAPL250117C150,AAPL Jan 17 2025 150 Call,-1,$3.20,,,,,,,,,,Margin'
    )
    positions = parse_fidelity_csv(rows)
    p = positions[0]
    assert p["symbol"] == "AAPL"
    assert p["secType"] == "OPT"
    assert p["right"] == "C"
    assert p["strike"] == 150.0
    assert p["expiry"] == "2025-01-17"
    assert p["quantity"] == -1.0
    assert p["multiplier"] == 100.0


def test_parses_an_option_symbol_with_fractional_strike():
    rows = csv_text(
        'Z12345678,Individual,-SPY250620P512.5,SPY Jun 20 2025 512.5 Put,2,$4.10,,,,,,,,,,Margin'
    )
    positions = parse_fidelity_csv(rows)
    assert positions[0]["strike"] == 512.5
    assert positions[0]["right"] == "P"


def test_cleans_dollar_comma_and_percent_quirks():
    rows = csv_text(
        'Z12345678,Individual,MSFT,MICROSOFT CORP,10,"$1,234.56",,,,,,,,,"$1,000.00",Cash'
    )
    p = parse_fidelity_csv(rows)[0]
    assert p["lastPrice"] == 1234.56
    assert p["avgCost"] == 1000.00


def test_skips_blank_and_disclaimer_footer_rows():
    rows = csv_text('Z12345678,Individual,AAPL,APPLE INC,100,$230.50,,,,,,,,,,Cash')
    positions = parse_fidelity_csv(rows)
    assert len(positions) == 1  # blank row + disclaimer text row both dropped


def test_skips_rows_with_no_parseable_quantity():
    rows = csv_text('Z12345678,Individual,Pending Activity,,,,,,,,,,,,,')
    assert parse_fidelity_csv(rows) == []
