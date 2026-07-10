"""Beta comes from IB Gateway's fundamental-ratios feed, never from an
in-process calculation. extract_beta() is the one pure piece: pulling
the Beta tag out of an ib_async FundamentalRatios-shaped object (or
recognizing it's absent / IB's own "no data" sentinel)."""

from types import SimpleNamespace

from app.portfolio.beta import extract_beta


def test_extracts_beta_from_ratios_object():
    ratios = SimpleNamespace(Beta=1.23)
    assert extract_beta(ratios) == 1.23


def test_none_ratios_returns_none():
    assert extract_beta(None) is None


def test_missing_beta_attribute_returns_none():
    ratios = SimpleNamespace(PE=15.0)  # no Beta tag on this contract
    assert extract_beta(ratios) is None


def test_ib_no_data_sentinel_nan_returns_none():
    # ib_async turns IB's -99999.99 "no data" sentinel into NaN itself
    ratios = SimpleNamespace(Beta=float("nan"))
    assert extract_beta(ratios) is None


def test_non_numeric_beta_returns_none():
    ratios = SimpleNamespace(Beta="")
    assert extract_beta(ratios) is None
