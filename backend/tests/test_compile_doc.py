"""compile_doc tests: illustrative payoff legs feed the existing
spread_math, and the markdown doc renders provenance quotes and flags
Unspecified fields instead of inventing values."""

from __future__ import annotations

from app.specs.compile_doc import compile_doc, illustrative_legs
from tests.test_spec_schema import sample_spec


def test_illustrative_legs_put_credit_spread():
    spec = sample_spec()
    legs, assumptions = illustrative_legs(spec, reference_price=100.0)
    assert len(legs) == 2
    short, long_ = legs
    # short 0.30-delta put sits OTM below the reference price
    assert short.right == "P" and short.qty == -1
    assert 0 < short.strike < 100.0
    # long leg is the fixed width further from the money
    assert long_.right == "P" and long_.qty == 1
    assert long_.strike == short.strike - 5.0
    assert assumptions["reference_price"] == 100.0
    # strikes are illustrative -> the doc must say so
    assert "illustrative" in assumptions["note"].lower()


def test_payoff_has_credit_spread_shape():
    spec = sample_spec()
    doc = compile_doc(spec, reference_price=100.0)
    payoff = doc["payoff"]
    points = payoff["points"]
    breakevens = payoff["breakevens"]
    short_strike = max(l["strike"] for l in payoff["legs"])
    long_strike = min(l["strike"] for l in payoff["legs"])
    # exactly one breakeven, strictly between the strikes
    assert len(breakevens) == 1
    assert long_strike < breakevens[0] < short_strike
    ys = [p["y"] for p in points]
    max_gain, max_loss = max(ys), min(ys)
    # credit received caps the gain; width minus credit caps the loss
    credit = payoff["assumptions"]["net_credit_per_share"]
    width = short_strike - long_strike
    assert max_gain == round(credit * 100, 2)
    assert max_loss == round(-(width - credit) * 100, 2)
    # right tail (far above short strike) is the full profit for a put spread
    assert points[-1]["y"] == max_gain


def test_markdown_renders_rules_and_unspecified_flags():
    spec = sample_spec()
    doc = compile_doc(spec, reference_price=100.0)
    md = doc["markdown"]
    # verbatim provenance quote appears in the entry rules table
    assert "I only sell when IV rank is over 30" in md
    # unstated stop loss is flagged, never invented
    assert "not stated in source" in md
    assert "stop_loss" in md
    # section status matrix is present
    assert "entry" in md and "defined" in md
    # structure summary mentions the legs
    assert "short" in md.lower() and "put" in md.lower()


def test_markdown_labels_claimed_performance_as_claims():
    spec = sample_spec()
    claimed = {"win_rate_pct": 85, "quote": "this wins about 85% of the time"}
    doc = compile_doc(spec, reference_price=100.0, claimed_performance=claimed)
    md = doc["markdown"]
    assert "85" in md
    # claims must be labeled as source claims, not results
    assert "claim" in md.lower()


def test_provenance_timestamp_renders_video_link():
    spec = sample_spec()
    spec.entry[0].provenance.timestamp_s = 754
    spec.meta.source_ref = "https://www.youtube.com/watch?v=abc123"
    doc = compile_doc(spec, reference_price=100.0)
    assert "t=754" in doc["markdown"]


def test_doc_includes_needs_review_and_sections():
    spec = sample_spec()
    doc = compile_doc(spec, reference_price=100.0)
    assert doc["needs_review"] is True
    assert doc["sections"]["exit"] == "partial"
