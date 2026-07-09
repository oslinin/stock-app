"""Bot tick state machine against SimBroker + a scripted MarketContext:
FLAT -> ENTRY_SIGNALED -> ORDER_PENDING -> IN_POSITION — using the real
spec interpreter, leg resolver, and risk gate a live bot would use.
Only the broker and clock are simulated (plan)."""

import asyncio
from types import SimpleNamespace

from app.bots.runtime import tick
from app.bots.sim_broker import SimBroker
from app.specs.interpreter import MarketContext
from tests.test_spec_schema import sample_spec

# matches sample_spec()'s structure: short 0.30-delta put (leg 0),
# long put 5 wide from leg 0 (fixed_width_from_leg)
CHAIN = [
    {"strike": 95.0, "right": "P", "bid": 1.00, "ask": 1.10, "delta": -0.30, "iv": 0.25, "expiry": "2026-08-21"},
    {"strike": 90.0, "right": "P", "bid": 0.40, "ask": 0.50, "delta": -0.12, "iv": 0.28, "expiry": "2026-08-21"},
]

RISK_INPUTS = dict(
    net_liq=100_000.0,
    open_positions=0,
    realized_pnl_today=0.0,
    global_max_bp_pct=0.5,
    global_max_concurrent=10,
    daily_loss_halt_usd=0.0,
)


def make_bot(**overrides):
    defaults = dict(status="running", bp_pct=0.5, max_concurrent=2, fixed_contracts=1)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def run(**kwargs):
    kwargs.setdefault("bot", make_bot())
    kwargs.setdefault("spec", sample_spec())
    kwargs.setdefault("chain", CHAIN)
    kwargs.setdefault("broker", SimBroker())
    kwargs.setdefault("risk_inputs", RISK_INPUTS)
    return asyncio.run(tick(**kwargs))


def test_flat_stays_flat_when_entry_conditions_fail():
    # iv_rank clamps to 0 (current below the whole history) — well under 30
    ctx = MarketContext(price=100.0, iv_history=[0.20, 0.30], current_iv=0.15)
    result = run(position_state="FLAT", order_id=None, ctx=ctx)
    assert result.position_state == "FLAT"
    assert result.action == "wait"


def test_flat_to_entry_signaled_when_conditions_pass():
    ctx = MarketContext(price=100.0, iv_history=[0.10, 0.20], current_iv=0.30)  # iv_rank 100
    result = run(position_state="FLAT", order_id=None, ctx=ctx)
    assert result.position_state == "ENTRY_SIGNALED"


def test_entry_signaled_resolves_legs_and_places_pending_order():
    ctx = MarketContext(price=100.0)
    result = run(position_state="ENTRY_SIGNALED", order_id=None, ctx=ctx)
    assert result.position_state == "ORDER_PENDING"
    assert result.order_id is not None
    assert result.whatif["available"] is True


def test_order_pending_fills_on_next_tick():
    ctx = MarketContext(price=100.0)
    broker = SimBroker()
    placed = run(position_state="ENTRY_SIGNALED", order_id=None, ctx=ctx, broker=broker)
    filled = run(position_state="ORDER_PENDING", order_id=placed.order_id, ctx=ctx, broker=broker)
    assert filled.position_state == "IN_POSITION"
    assert "filled at" in filled.detail


def test_risk_gate_blocks_oversized_order_and_returns_to_flat():
    ctx = MarketContext(price=100.0)
    tiny_account = {**RISK_INPUTS, "net_liq": 10.0}
    result = run(position_state="ENTRY_SIGNALED", order_id=None, ctx=ctx, risk_inputs=tiny_account)
    assert result.position_state == "FLAT"
    assert result.action == "risk_blocked"


def test_non_running_bot_skips_the_tick():
    ctx = MarketContext(price=100.0)
    result = run(bot=make_bot(status="paused"), position_state="FLAT", order_id=None, ctx=ctx)
    assert result.action == "skipped"
    assert result.position_state == "FLAT"


def test_in_position_holds_without_managing():
    ctx = MarketContext(price=100.0)
    result = run(position_state="IN_POSITION", order_id="1", ctx=ctx)
    assert result.position_state == "IN_POSITION"
    assert result.action == "hold"
