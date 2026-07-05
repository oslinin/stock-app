"""AJ Brown's VIX hedge for options sellers.

Structure (same monthly VIX expiration, ~15-34 DTE):
- CALL DEBIT spread with both strikes BELOW the expiry's future price
  (long lower call, short call one width higher) — the crash winner.
- PUT CREDIT spread ABOVE the future (short higher put, long put one width
  lower) — the financing leg.

Hard screening requirement: both verticals the same width (default 1.0 point
= $100 at the $100/pt VIX multiplier) and NET DEBIT per combo under the cap
(default $100), ranked toward $0. Expensive builds (e.g. mismatched widths /
wide long-dated quotes producing a $2,000+ debit) are rejected; when nothing
qualifies the screener reports WAIT with the closest candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from .base import Strategy
from .spread_math import PayLeg

STRIKE_TOL = 1e-6
MULTIPLIER = 100


@dataclass
class VixHedgeParams:
    width: float = 1.0
    dte_min: int = 15
    dte_max: int = 34
    net_debit_cap_usd: float = 100.0
    contracts: int = 1
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    or_minutes: int = 30
    low_lookback_days: int = 120
    low_quantile: float = 0.4
    abs_low: float = 20.0
    armed_ttl_days: int = 4
    strike_window_below: float = 8.0
    strike_window_above: float = 5.0


@dataclass
class Quote:
    con_id: int = 0
    bid: float | None = None
    ask: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        if self.ask <= 0 or self.bid < 0 or self.ask < self.bid:
            return None
        return (self.bid + self.ask) / 2

    @property
    def wide(self) -> bool:
        m = self.mid
        if m is None:
            return True
        return (self.ask - self.bid) > max(0.10, 0.25 * m)


@dataclass
class ChainRow:
    strike: float
    call: Quote = field(default_factory=Quote)
    put: Quote = field(default_factory=Quote)


@dataclass
class ComboSelection:
    call_long: float
    call_short: float
    put_long: float
    put_short: float
    call_debit: float
    put_credit: float
    warnings: list[str] = field(default_factory=list)

    @property
    def net(self) -> float:
        """Net cost per share; positive = net debit."""
        return self.call_debit - self.put_credit

    @property
    def net_usd(self) -> float:
        return self.net * MULTIPLIER

    def legs(self) -> list[PayLeg]:
        return [
            PayLeg("C", self.call_long, +1),
            PayLeg("C", self.call_short, -1),
            PayLeg("P", self.put_short, -1),
            PayLeg("P", self.put_long, +1),
        ]


@dataclass
class SelectionResult:
    found: bool
    best: ComboSelection | None
    alternatives: list[ComboSelection]
    candidates_checked: int
    reason: str


def _find_strike(rows: dict[float, ChainRow], target: float) -> float | None:
    for k in rows:
        if abs(k - target) < STRIKE_TOL:
            return k
    return None


def select_spread(
    rows: list[ChainRow], center: float, params: VixHedgeParams
) -> SelectionResult:
    """Enumerate equal-width call-debit + put-credit pairs and pick the one
    with net debit closest to zero, subject to net_usd < net_debit_cap_usd."""
    by_strike = {r.strike: r for r in rows}
    width = params.width

    call_spreads: list[tuple[float, float, float, list[str]]] = []
    put_spreads: list[tuple[float, float, float, list[str]]] = []

    for k1 in sorted(by_strike):
        k2 = _find_strike(by_strike, k1 + width)
        if k2 is None:
            continue
        lo, hi = by_strike[k1], by_strike[k2]

        # call debit spread: both strikes at/below the future price
        if k2 <= center + STRIKE_TOL:
            m_long, m_short = lo.call.mid, hi.call.mid
            if m_long is not None and m_short is not None:
                debit = m_long - m_short
                if 0 < debit < width:
                    warns = []
                    if lo.call.wide:
                        warns.append(f"wide market on {k1:g}C")
                    if hi.call.wide:
                        warns.append(f"wide market on {k2:g}C")
                    call_spreads.append((k1, k2, debit, warns))

        # put credit spread: both strikes at/above the future price
        if k1 >= center - STRIKE_TOL:
            m_long, m_short = lo.put.mid, hi.put.mid
            if m_long is not None and m_short is not None:
                credit = m_short - m_long
                if 0 < credit < width:
                    warns = []
                    if hi.put.wide:
                        warns.append(f"wide market on {k2:g}P")
                    if lo.put.wide:
                        warns.append(f"wide market on {k1:g}P")
                    put_spreads.append((k1, k2, credit, warns))

    combos: list[ComboSelection] = []
    for ck1, ck2, debit, cw in call_spreads:
        for pk1, pk2, credit, pw in put_spreads:
            combos.append(
                ComboSelection(
                    call_long=ck1,
                    call_short=ck2,
                    put_long=pk1,
                    put_short=pk2,
                    call_debit=round(debit, 4),
                    put_credit=round(credit, 4),
                    warnings=cw + pw,
                )
            )

    checked = len(combos)
    if not combos:
        return SelectionResult(
            False, None, [], 0,
            "no complete quotes for equal-width call-debit and put-credit spreads",
        )

    combos.sort(key=lambda c: abs(c.net))
    qualifying = [c for c in combos if c.net_usd < params.net_debit_cap_usd]
    if not qualifying:
        closest = combos[0]
        return SelectionResult(
            False,
            closest,
            combos[1:4],
            checked,
            f"cheapest combo costs ${closest.net_usd:.0f} net debit, "
            f"over the ${params.net_debit_cap_usd:.0f} cap",
        )
    return SelectionResult(True, qualifying[0], qualifying[1:5], checked, "ok")


class VixHedgeStrategy(Strategy):
    id = "vix_hedge"
    name = "VIX Hedge (AJ Brown)"
    description = (
        "Call debit spread below the VIX future + put credit spread above it, "
        "equal $100 widths, net debit under $100. Breaks even most of the time, "
        "wins big in a volatility spike."
    )
    underlying_symbol = "VIX"
    underlying_sec_type = "IND"

    def __init__(self, settings: Settings):
        self.params = VixHedgeParams(
            width=settings.vix_spread_width,
            dte_min=settings.vix_dte_min,
            dte_max=settings.vix_dte_max,
            net_debit_cap_usd=settings.vix_net_debit_cap_usd,
            macd_fast=settings.vix_macd_fast,
            macd_slow=settings.vix_macd_slow,
            macd_signal=settings.vix_macd_signal,
            or_minutes=settings.vix_or_minutes,
            low_lookback_days=settings.vix_low_lookback_days,
            low_quantile=settings.vix_low_quantile,
            abs_low=settings.vix_abs_low,
            armed_ttl_days=settings.vix_armed_ttl_days,
            strike_window_below=settings.vix_strike_window_below,
            strike_window_above=settings.vix_strike_window_above,
        )

    def params_dict(self) -> dict[str, Any]:
        p = self.params
        return {
            "macd": {"fast": p.macd_fast, "slow": p.macd_slow, "signal": p.macd_signal},
            "openingRangeMinutes": p.or_minutes,
            "spreadWidth": p.width,
            "netDebitCapUsd": p.net_debit_cap_usd,
            "dteMin": p.dte_min,
            "dteMax": p.dte_max,
            "lowLookbackDays": p.low_lookback_days,
            "lowQuantile": p.low_quantile,
            "absLow": p.abs_low,
        }
