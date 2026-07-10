"""Screener registry: pure functions over symbol_metrics-shaped rows
(plain dicts — no DB, no chain fetch). Premium-yield ranking, an IV-rank
filter, and a shared liquidity filter every screener respects."""

import pytest

from app.watchlist.screeners import SCREENER_REGISTRY, run_screener


def row(symbol, **overrides):
    base = {
        "symbol": symbol,
        "underlying_px": 100.0,
        "atm_iv": 0.30,
        "iv_rank": 50.0,
        "iv_percentile": 50.0,
        "expected_move": 5.0,
        "premium_yield": 0.002,
        "open_interest": 500,
        "spread_pct": 0.05,
        "sampled_delta": 0.25,
        "sampled_dte": 30,
    }
    base.update(overrides)
    return base


def test_registry_has_the_three_named_screeners():
    assert set(SCREENER_REGISTRY) == {
        "expensive_premium",
        "high_ivr",
        "delta_dte_candidates",
    }


def test_expensive_premium_ranks_by_premium_yield_descending():
    rows = [
        row("LOW", premium_yield=0.001),
        row("HIGH", premium_yield=0.01),
        row("MID", premium_yield=0.005),
    ]
    ranked = run_screener("expensive_premium", rows, {})
    assert [r["symbol"] for r in ranked] == ["HIGH", "MID", "LOW"]


def test_expensive_premium_skips_rows_missing_the_metric():
    rows = [row("HAS", premium_yield=0.01), row("MISSING", premium_yield=None)]
    ranked = run_screener("expensive_premium", rows, {})
    assert [r["symbol"] for r in ranked] == ["HAS"]


def test_high_ivr_filters_by_threshold_and_ranks_descending():
    rows = [row("LOW", iv_rank=20.0), row("HIGH", iv_rank=90.0), row("MID", iv_rank=60.0)]
    ranked = run_screener("high_ivr", rows, {"min_iv_rank": 50})
    assert [r["symbol"] for r in ranked] == ["HIGH", "MID"]


def test_high_ivr_default_threshold():
    rows = [row("A", iv_rank=49.9), row("B", iv_rank=50.0)]
    ranked = run_screener("high_ivr", rows, {})  # default min_iv_rank=50
    assert [r["symbol"] for r in ranked] == ["B"]


def test_delta_dte_candidates_filters_both_dimensions():
    rows = [
        row("GOOD", sampled_delta=0.25, sampled_dte=30),
        row("DELTA_TOO_HIGH", sampled_delta=0.45, sampled_dte=30),
        row("DTE_TOO_SHORT", sampled_delta=0.25, sampled_dte=10),
        row("SHORT_SIDE_OK", sampled_delta=-0.20, sampled_dte=40),  # abs() handles short puts
    ]
    matched = {r["symbol"] for r in run_screener("delta_dte_candidates", rows, {})}
    assert matched == {"GOOD", "SHORT_SIDE_OK"}


def test_delta_dte_candidates_custom_band():
    rows = [row("A", sampled_delta=0.10, sampled_dte=30)]
    assert run_screener("delta_dte_candidates", rows, {"delta_min": 0.05, "delta_max": 0.15}) == rows


# ------------------------------------------------------- liquidity filter


def test_liquidity_filter_excludes_thin_open_interest():
    rows = [row("THICK", open_interest=1000), row("THIN", open_interest=10)]
    ranked = run_screener("expensive_premium", rows, {"min_open_interest": 100})
    assert [r["symbol"] for r in ranked] == ["THICK"]


def test_liquidity_filter_excludes_wide_spreads():
    rows = [row("TIGHT", spread_pct=0.02), row("WIDE", spread_pct=0.40)]
    ranked = run_screener("expensive_premium", rows, {"max_spread_pct": 0.10})
    assert [r["symbol"] for r in ranked] == ["TIGHT"]


def test_liquidity_filter_applies_across_all_screeners():
    rows = [row("THIN", open_interest=1, iv_rank=90.0)]
    assert run_screener("high_ivr", rows, {"min_open_interest": 100}) == []


def test_unknown_screener_id_raises():
    with pytest.raises(KeyError):
        run_screener("not_a_real_screener", [], {})
