"""Risk gate: BP%, concurrency, and daily-loss halt — pure functions,
synthetic account numbers, no DB/broker involved."""

from app.bots.risk import (
    check_bp_pct,
    check_concurrency,
    check_daily_loss_halt,
    run_risk_gate,
)

BASE = dict(
    margin_required=5_000.0,
    net_liq=100_000.0,
    bp_pct=0.10,
    global_max_bp_pct=0.5,
    open_positions=0,
    bot_max_concurrent=2,
    global_max_concurrent=10,
    realized_pnl_today=0.0,
    daily_loss_halt_usd=1_000.0,
)


def test_bp_pct_passes_within_limit():
    assert check_bp_pct(5_000, 100_000, 0.10, 0.5).passed  # 5% of 100k, limit 10%


def test_bp_pct_fails_over_bot_limit():
    result = check_bp_pct(15_000, 100_000, 0.10, 0.5)  # 15% > bot's own 10% cap
    assert not result.passed
    assert "10.0%" in result.reason


def test_bp_pct_uses_the_tighter_of_bot_and_global_limit():
    # bot allows 50%, but the global cap is 10%
    result = check_bp_pct(15_000, 100_000, 0.50, 0.10)
    assert not result.passed
    assert "10.0%" in result.reason


def test_bp_pct_fails_closed_with_no_net_liq():
    assert not check_bp_pct(1_000, 0, 0.10, 0.5).passed


def test_concurrency_passes_below_limit():
    assert check_concurrency(1, 2, 10).passed


def test_concurrency_fails_at_limit():
    assert not check_concurrency(2, 2, 10).passed


def test_concurrency_uses_the_tighter_of_bot_and_global_limit():
    assert not check_concurrency(3, 10, 3).passed


def test_daily_loss_halt_passes_above_threshold():
    assert check_daily_loss_halt(-500, 1_000).passed


def test_daily_loss_halt_fails_at_or_below_threshold():
    assert not check_daily_loss_halt(-1_000, 1_000).passed
    assert not check_daily_loss_halt(-1_500, 1_000).passed


def test_daily_loss_halt_disabled_when_zero():
    assert check_daily_loss_halt(-1_000_000, 0).passed


def test_run_risk_gate_passes_all_clear():
    assert run_risk_gate(**BASE).passed


def test_run_risk_gate_stops_at_first_failure_daily_loss():
    blocked = {**BASE, "realized_pnl_today": -2_000.0}
    result = run_risk_gate(**blocked)
    assert not result.passed
    assert "daily realized loss" in result.reason


def test_run_risk_gate_reports_concurrency_before_bp_when_both_fail():
    blocked = {**BASE, "open_positions": 2, "margin_required": 999_999.0}
    result = run_risk_gate(**blocked)
    assert not result.passed
    assert "open position" in result.reason
