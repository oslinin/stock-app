"""Compiles an OptionsStrategySpec into (a) an optopsy strategy function
name + kwargs for the local engine, and (b) an Option Omega setup sheet
+ Custom-Signals CSV for the manual bridge. A rule the engine can't
express — a structure shape optopsy has no function for, a strike rule
with no optopsy filter equivalent, or a P&L-triggered exit (optopsy only
has a calendar exit_dte, no native PT/SL) — is reported in
unsupported[], shown as "backtest ignores: X" (plan), never silently
dropped.
"""

from __future__ import annotations

from ..specs.schema import DeltaTarget, OptionsStrategySpec, PctOTM

# Only single legs and 2-leg same-right verticals map to an optopsy
# strategy this phase — straddles/strangles/condors/butterflies/
# calendars/diagonals aren't (compile as unsupported=True instead).
SINGLE_LEG_MAP = {
    ("P", "short"): "short_puts",
    ("P", "long"): "long_puts",
    ("C", "short"): "short_calls",
    ("C", "long"): "long_calls",
}

DELTA_BAND = 0.05


def _strategy_name(spec: OptionsStrategySpec) -> tuple[str | None, list[str]]:
    legs = spec.structure
    if len(legs) == 1:
        key = (legs[0].right, legs[0].direction)
        name = SINGLE_LEG_MAP.get(key)
        return (name, []) if name else (None, [f"single-leg shape {key} not mapped to an optopsy strategy"])
    if len(legs) == 2 and legs[0].right == legs[1].right:
        has_short = any(leg.direction == "short" for leg in legs)
        prefix = "short" if has_short else "long"
        suffix = "put_spread" if legs[0].right == "P" else "call_spread"
        return f"{prefix}_{suffix}", []
    return None, [
        f"{len(legs)}-leg structure not mapped to an optopsy strategy — only single legs and "
        "2-leg same-right verticals are supported this phase"
    ]


def _entry_filters(spec: OptionsStrategySpec) -> tuple[dict, list[str]]:
    kwargs: dict = {}
    unsupported: list[str] = []
    leg = spec.structure[0]

    if leg.dte_window:
        kwargs["max_entry_dte"] = leg.dte_window[1]
    elif leg.dte_target:
        kwargs["max_entry_dte"] = leg.dte_target

    rule = leg.strike_rule
    if isinstance(rule, DeltaTarget):
        kwargs["delta_min"] = round(rule.delta - DELTA_BAND, 4)
        kwargs["delta_max"] = round(rule.delta + DELTA_BAND, 4)
    elif isinstance(rule, PctOTM):
        kwargs["max_otm_pct"] = rule.pct
    else:
        unsupported.append(f"strike rule {rule.kind} not mapped to an optopsy entry filter")

    if spec.exit.time_exit_dte not in (None, "unspecified"):
        kwargs["exit_dte"] = spec.exit.time_exit_dte

    unsupported.append(
        "profit_target_pct_credit/stop_loss_x_credit are not passed to optopsy — it has no "
        "native P&L-triggered exit, only a calendar exit_dte; a trade-level PT/SL simulation "
        "over optopsy's raw output is a documented follow-up"
    )
    return kwargs, unsupported


def _oo_setup_sheet(spec: OptionsStrategySpec, strategy: str | None, kwargs: dict) -> dict:
    leg = spec.structure[0] if spec.structure else None
    target_delta = None
    if kwargs.get("delta_min") is not None and kwargs.get("delta_max") is not None:
        target_delta = round((kwargs["delta_min"] + kwargs["delta_max"]) / 2, 2)
    return {
        "underlying": spec.universe.underlyings[0] if spec.universe.underlyings else "",
        "strategyShape": strategy or "unsupported — configure manually in OO",
        "right": leg.right if leg else None,
        "targetDelta": target_delta,
        "maxEntryDte": kwargs.get("max_entry_dte"),
        "exitDte": kwargs.get("exit_dte"),
        "profitTargetPctCredit": spec.exit.profit_target_pct_credit,
        "stopLossXCredit": spec.exit.stop_loss_x_credit,
        "sizing": {"bpPct": spec.sizing.bp_pct, "fixedContracts": spec.sizing.fixed_contracts},
    }


def _oo_signals_csv(spec: OptionsStrategySpec) -> str:
    """Gate/entry conditions optopsy/OO can't natively express (VIX
    regime, IV rank, day-of-week) as a date,signal CSV — how they reach
    OO through its sanctioned Custom-Signals upload. Populating actual
    rows needs historical data (the worker/data layer's job, not this
    pure compiler) — this emits the header + column contract only."""
    return "date,signal\n"


def compile_backtest(spec: OptionsStrategySpec) -> dict:
    strategy, structure_unsupported = _strategy_name(spec)
    kwargs, filter_unsupported = _entry_filters(spec) if strategy else ({}, [])
    return {
        "supported": strategy is not None,
        "optopsyStrategy": strategy,
        "optopsyKwargs": kwargs,
        "ooSetupSheet": _oo_setup_sheet(spec, strategy, kwargs),
        "ooSignalsCsv": _oo_signals_csv(spec),
        "unsupported": [*structure_unsupported, *filter_unsupported],
    }
