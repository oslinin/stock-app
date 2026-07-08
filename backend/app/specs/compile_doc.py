"""Compile a spec into a human-readable strategy doc.

Output: markdown (rule tables with verbatim quotes, Unspecified flags,
section-status matrix) plus an illustrative expiration payoff computed
with the existing spread_math. Strikes are ILLUSTRATIVE: strike rules
are abstract (0.30 delta, 5-wide), so we synthesize representative
strikes around a reference price and say so in the assumptions.
"""

from __future__ import annotations

from ..strategies.spread_math import PayLeg, breakevens, payoff_points
from .schema import (
    LegSpec,
    OptionsStrategySpec,
    Provenance,
    is_unspecified,
)

# rule-of-thumb OTM distance for an illustrative delta-target strike:
# a 0.50-delta option is ATM; each 0.01 of delta ~ 0.2% of spot.
_DELTA_OTM_SCALE = 0.20
# with no pricing model, assume a credit spread collects 1/3 of width
_CREDIT_FRACTION_OF_WIDTH = 1.0 / 3.0


def _round_strike(value: float) -> float:
    return round(value)


def _leg_strike(leg: LegSpec, reference_price: float, resolved: list[float]) -> float:
    rule = leg.strike_rule
    if rule.kind == "delta_target":
        otm_frac = max(0.5 - rule.delta, 0.0) * _DELTA_OTM_SCALE
        sign = -1.0 if leg.right == "P" else 1.0
        return _round_strike(reference_price * (1.0 + sign * otm_frac))
    if rule.kind == "pct_otm":
        sign = -1.0 if leg.right == "P" else 1.0
        return _round_strike(reference_price * (1.0 + sign * rule.pct / 100.0))
    if rule.kind == "atm_offset":
        return _round_strike(reference_price + rule.offset)
    if rule.kind == "fixed_width_from_leg":
        anchor = resolved[rule.from_leg]
        # width extends away from the money
        sign = -1.0 if leg.right == "P" else 1.0
        return anchor + sign * rule.width
    raise ValueError(f"unknown strike rule {rule.kind}")  # pragma: no cover


def illustrative_legs(
    spec: OptionsStrategySpec, reference_price: float = 100.0
) -> tuple[list[PayLeg], dict]:
    """Map abstract strike rules to representative strikes for the payoff."""
    strikes: list[float] = []
    for leg in spec.structure:
        strikes.append(_leg_strike(leg, reference_price, strikes))
    legs = [
        PayLeg(
            right=leg.right,
            strike=strike,
            qty=(1 if leg.direction == "long" else -1) * leg.ratio,
        )
        for leg, strike in zip(spec.structure, strikes)
    ]
    assumptions = {
        "reference_price": reference_price,
        "note": (
            "Illustrative strikes derived from the spec's strike rules at a "
            f"reference price of {reference_price}; not live quotes."
        ),
    }
    return legs, assumptions


def _estimate_net_cost(legs: list[PayLeg]) -> float:
    """Per-share net cost estimate (negative = credit received).

    Without a pricing model: vertical-style structures are assumed to
    collect/pay one third of the total strike width; the direction comes
    from whether the structure is net short (credit) or net long (debit).
    """
    if not legs:
        return 0.0
    strikes = [leg.strike for leg in legs]
    width = max(strikes) - min(strikes)
    net_qty = sum(leg.qty for leg in legs)
    if width == 0.0:
        return 0.0
    magnitude = width * _CREDIT_FRACTION_OF_WIDTH
    if net_qty < 0:
        return -magnitude  # net short -> credit
    if net_qty > 0:
        return magnitude  # net long -> debit
    # balanced (spread): sign by the nearer-the-money leg's direction
    # (short the expensive leg -> credit)
    inner = min(legs, key=lambda l: l.strike) if legs[0].right == "C" else max(
        legs, key=lambda l: l.strike
    )
    return -magnitude if inner.qty < 0 else magnitude


def _provenance_cell(prov: Provenance | None, source_ref: str) -> str:
    if prov is None or not prov.quote:
        return "—"
    quote = f'"{prov.quote}"'
    if prov.timestamp_s is not None and "youtube" in source_ref:
        sep = "&" if "?" in source_ref else "?"
        return f"{quote} ([{prov.timestamp_s}s]({source_ref}{sep}t={prov.timestamp_s}))"
    if prov.timestamp_s is not None:
        return f"{quote} (at {prov.timestamp_s}s)"
    if prov.page is not None:
        return f"{quote} (p. {prov.page})"
    return quote


def compile_doc(
    spec: OptionsStrategySpec,
    reference_price: float = 100.0,
    claimed_performance: dict | None = None,
) -> dict:
    legs, assumptions = illustrative_legs(spec, reference_price)
    net_cost = _estimate_net_cost(legs)
    assumptions["net_credit_per_share"] = round(-net_cost, 4) if net_cost < 0 else 0.0
    assumptions["net_debit_per_share"] = round(net_cost, 4) if net_cost > 0 else 0.0
    points = payoff_points(legs, net_cost) if legs else []
    payoff = {
        "legs": [{"right": l.right, "strike": l.strike, "qty": l.qty} for l in legs],
        "points": points,
        "breakevens": breakevens(points),
        "assumptions": assumptions,
    }

    sections = spec.section_status()
    src = spec.meta.source_ref
    md: list[str] = [f"# {spec.meta.name}", ""]
    if spec.meta.description:
        md += [spec.meta.description, ""]
    md += [
        f"**Category:** {spec.meta.category} · **Origin:** {spec.meta.origin}"
        + (f" · **Source:** {src}" if src else ""),
        "",
        "## Structure",
        "",
        "| Leg | Direction | Right | Strike rule | DTE |",
        "|---|---|---|---|---|",
    ]
    for i, leg in enumerate(spec.structure):
        rule = leg.strike_rule
        rule_txt = ", ".join(
            f"{k}={v}" for k, v in rule.model_dump().items() if k != "kind"
        )
        dte = leg.dte_target if leg.dte_target is not None else "—"
        md.append(
            f"| {i} | {leg.direction} | {'call' if leg.right == 'C' else 'put'} "
            f"| {rule.kind} ({rule_txt}) | {dte} |"
        )

    md += ["", "## Entry rules", ""]
    if spec.entry:
        md += ["| Condition | Params | Source |", "|---|---|---|"]
        for cond in spec.entry:
            md.append(
                f"| {cond.kind} | {cond.params} | "
                f"{_provenance_cell(cond.provenance, src)} |"
            )
    else:
        md.append("_No entry conditions — **undefined** in source._")

    md += ["", "## Exit rules", "", "| Rule | Value | Source |", "|---|---|---|"]
    labels = {
        "profit_target_pct_credit": "Profit target (% of credit)",
        "stop_loss_x_credit": "Stop loss (× credit)",
        "time_exit_dte": "Time exit (DTE)",
    }
    for field in spec.exit.FIELDS:
        value = getattr(spec.exit, field)
        prov = spec.exit.provenance.get(field)
        if is_unspecified(value):
            md.append(f"| {labels[field]} ({field}) | ⚠ **not stated in source** | — |")
        else:
            md.append(
                f"| {labels[field]} ({field}) | {value} | "
                f"{_provenance_cell(prov, src)} |"
            )

    md += ["", "## Adjustments", ""]
    if spec.adjustments:
        md += ["| Trigger | Action | Source |", "|---|---|---|"]
        for adj in spec.adjustments:
            md.append(
                f"| {adj.trigger.kind} {adj.trigger.params} | {adj.action} | "
                f"{_provenance_cell(adj.provenance or adj.trigger.provenance, src)} |"
            )
    else:
        md.append("_No adjustment rules stated in source._")

    md += ["", "## Sizing", ""]
    if sections["sizing"] == "defined":
        parts = []
        if spec.sizing.bp_pct is not None:
            parts.append(f"{spec.sizing.bp_pct}% of buying power")
        if spec.sizing.fixed_contracts is not None:
            parts.append(f"{spec.sizing.fixed_contracts} contracts")
        parts.append(f"max {spec.sizing.max_concurrent} concurrent")
        md.append(" · ".join(parts))
    else:
        md.append("_⚠ not stated in source._")

    if spec.gates:
        md += ["", "## Gates", ""]
        for gate in spec.gates:
            md.append(f"- {gate.kind} {gate.params}")

    if spec.unsupported_conditions:
        md += ["", "## Rules the schema cannot express", ""]
        md += [f"- {rule}" for rule in spec.unsupported_conditions]

    md += [
        "",
        "## Section status",
        "",
        "| Section | Status |",
        "|---|---|",
    ]
    md += [f"| {name} | {value} |" for name, value in sections.items()]

    if claimed_performance:
        md += [
            "",
            "## Claimed performance (as stated by the source — unverified claims)",
            "",
        ]
        quote = claimed_performance.get("quote", "")
        for key, value in claimed_performance.items():
            if key == "quote":
                continue
            md.append(f"- **{key}**: {value} _(source claim)_")
        if quote:
            md.append(f'- Quote: "{quote}"')

    return {
        "markdown": "\n".join(md),
        "payoff": payoff,
        "sections": sections,
        "needs_review": spec.needs_review(),
    }
