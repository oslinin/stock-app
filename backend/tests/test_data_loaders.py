"""Parquet cache round-trip + sanity validators catching a corrupted
fixture — no network (fetch_dolthub_chain is smoke-tested manually)."""

import pandas as pd
import pytest

from app.backtests.data import cache_path, load_cached, save_cache, validate_chain_data

GOOD_ROW = {
    "underlying_symbol": "SPY",
    "quote_date": "2024-01-02",
    "expiration": "2024-02-16",
    "strike": 470.0,
    "option_type": "P",
    "bid": 1.20,
    "ask": 1.30,
}


def df_of(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_valid_data_has_no_errors():
    assert validate_chain_data(df_of(GOOD_ROW)) == []


def test_missing_required_column_is_caught():
    bad = df_of({**GOOD_ROW})
    bad = bad.drop(columns=["bid"])
    errors = validate_chain_data(bad)
    assert any("bid" in e for e in errors)


def test_empty_dataframe_is_caught():
    assert validate_chain_data(pd.DataFrame(columns=list(GOOD_ROW))) == ["no rows"]


def test_negative_bid_is_caught():
    bad = {**GOOD_ROW, "bid": -1.0}
    errors = validate_chain_data(df_of(bad))
    assert any("negative" in e for e in errors)


def test_ask_below_bid_is_caught():
    bad = {**GOOD_ROW, "bid": 2.0, "ask": 1.0}
    errors = validate_chain_data(df_of(bad))
    assert any("ask < bid" in e for e in errors)


def test_non_positive_strike_is_caught():
    bad = {**GOOD_ROW, "strike": 0.0}
    errors = validate_chain_data(df_of(bad))
    assert any("strike" in e for e in errors)


def test_invalid_option_type_is_caught():
    bad = {**GOOD_ROW, "option_type": "X"}
    errors = validate_chain_data(df_of(bad))
    assert any("option_type" in e for e in errors)


def test_duplicate_rows_are_caught():
    errors = validate_chain_data(df_of(GOOD_ROW, dict(GOOD_ROW)))
    assert any("duplicate" in e for e in errors)


def test_expiration_before_quote_date_is_caught():
    bad = {**GOOD_ROW, "expiration": "2023-01-01"}
    errors = validate_chain_data(df_of(bad))
    assert any("expiration before quote_date" in e for e in errors)


def test_multiple_problems_all_reported():
    bad = {**GOOD_ROW, "bid": -1.0, "strike": -5.0}
    errors = validate_chain_data(df_of(bad))
    assert len(errors) >= 2


def test_cache_round_trip(tmp_path):
    df = df_of(GOOD_ROW)
    path = save_cache(tmp_path, "SPY", "2024-01-01", "2024-02-01", df)
    assert path == cache_path(tmp_path, "SPY", "2024-01-01", "2024-02-01")
    loaded = load_cached(tmp_path, "SPY", "2024-01-01", "2024-02-01")
    pd.testing.assert_frame_equal(loaded, df)


def test_cache_miss_returns_none(tmp_path):
    assert load_cached(tmp_path, "SPY", "2024-01-01", "2024-02-01") is None
