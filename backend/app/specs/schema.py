"""OptionsStrategySpec: the machine-readable strategy contract.

Every strategy in the platform — hand-entered, LLM-extracted from a
video transcript, or extracted from a PDF corpus — is an instance of
this schema, stored as spec_json on a spec_version row. Three compilers
(doc, backtest, bot) consume it; the interpreter evaluates its
conditions live.

Design rules pinned by tests:
- JSON round-trips are stable (spec_json is the source of truth).
- `Unspecified` is an explicit sentinel (the literal string
  "unspecified"): a rule the source never stated. Extraction must never
  invent values; compile_bot later refuses to run while exits are
  unspecified.
- `Condition.kind` is a closed enum so the interpreter/compilers can
  enumerate exactly what they support; anything else belongs in
  `unsupported_conditions` as free text.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Union

from pydantic import BaseModel, Field

UNSPECIFIED = "unspecified"
Unspecified = Literal["unspecified"]


def is_unspecified(value: object) -> bool:
    return value == UNSPECIFIED


class Provenance(BaseModel):
    """Where a rule came from: verbatim quote plus a locator (video
    timestamp or corpus page)."""

    quote: str = ""
    timestamp_s: int | None = None
    page: int | None = None


ConditionKind = Literal[
    "iv_rank_gte",
    "iv_rank_lte",
    "dte_between",
    "delta_between",
    "vix_below",
    "vix_above",
    "price_above_sma",
    "price_below_sma",
    "day_of_week_in",
    "no_earnings_within_days",
    "credit_min_pct_width",
    "funding_rate_gte",
    "funding_rate_lte",
    "edge_score_gte",
    "cot_zscore_gte",
    "gex_regime_is",
]


class Condition(BaseModel):
    kind: ConditionKind
    params: dict = Field(default_factory=dict)
    provenance: Provenance | None = None


class DeltaTarget(BaseModel):
    kind: Literal["delta_target"] = "delta_target"
    delta: float


class PctOTM(BaseModel):
    kind: Literal["pct_otm"] = "pct_otm"
    pct: float


class AtmOffset(BaseModel):
    kind: Literal["atm_offset"] = "atm_offset"
    offset: float


class FixedWidthFromLeg(BaseModel):
    kind: Literal["fixed_width_from_leg"] = "fixed_width_from_leg"
    from_leg: int
    width: float


StrikeRule = Annotated[
    Union[DeltaTarget, PctOTM, AtmOffset, FixedWidthFromLeg],
    Field(discriminator="kind"),
]


class LegSpec(BaseModel):
    right: Literal["C", "P"]
    direction: Literal["long", "short"]
    ratio: int = 1
    strike_rule: StrikeRule
    dte_target: int | None = None
    dte_window: tuple[int, int] | None = None
    provenance: Provenance | None = None


class ExitRules(BaseModel):
    profit_target_pct_credit: float | Unspecified = UNSPECIFIED
    stop_loss_x_credit: float | Unspecified = UNSPECIFIED
    time_exit_dte: float | Unspecified = UNSPECIFIED
    provenance: dict[str, Provenance] = Field(default_factory=dict)

    FIELDS: ClassVar[tuple[str, ...]] = (
        "profit_target_pct_credit",
        "stop_loss_x_credit",
        "time_exit_dte",
    )

    def unspecified_fields(self) -> list[str]:
        return [f for f in self.FIELDS if is_unspecified(getattr(self, f))]


RollActionKind = Literal[
    "roll_out_same_strike",
    "roll_out_and_away",
    "roll_untested_side",
    "close",
    "convert_to",
]


class AdjustmentRule(BaseModel):
    trigger: Condition
    action: RollActionKind
    params: dict = Field(default_factory=dict)
    provenance: Provenance | None = None


class Sizing(BaseModel):
    bp_pct: float | None = None
    fixed_contracts: int | None = None
    max_concurrent: int = 1
    provenance: Provenance | None = None


class Meta(BaseModel):
    name: str
    category: Literal["options", "stock", "crypto"] = "options"
    origin: Literal["youtube", "corpus", "manual"] = "manual"
    source_ref: str = ""  # video URL, corpus file/section, or empty
    description: str = ""


class Universe(BaseModel):
    underlyings: list[str] = Field(default_factory=list)
    sec_type: Literal["option", "stock", "perp"] = "option"


class OptionsStrategySpec(BaseModel):
    meta: Meta
    universe: Universe = Field(default_factory=Universe)
    structure: list[LegSpec] = Field(default_factory=list)
    entry: list[Condition] = Field(default_factory=list)
    exit: ExitRules = Field(default_factory=ExitRules)
    adjustments: list[AdjustmentRule] = Field(default_factory=list)
    sizing: Sizing = Field(default_factory=Sizing)
    gates: list[Condition] = Field(default_factory=list)
    unsupported_conditions: list[str] = Field(default_factory=list)

    def needs_review(self) -> bool:
        """Unstated exits or rules the schema can't express require a
        human before this spec may drive anything."""
        return bool(self.exit.unspecified_fields()) or bool(self.unsupported_conditions)

    def section_status(self) -> dict[str, str]:
        """Per-section defined|partial|undefined, shown as badges in the UI."""
        exit_unspecified = self.exit.unspecified_fields()
        if len(exit_unspecified) == len(ExitRules.FIELDS):
            exit_status = "undefined"
        elif exit_unspecified:
            exit_status = "partial"
        else:
            exit_status = "defined"
        return {
            "entry": "defined" if self.entry else "undefined",
            "exit": exit_status,
            "adjustments": "defined" if self.adjustments else "undefined",
            "sizing": "defined"
            if (self.sizing.bp_pct is not None or self.sizing.fixed_contracts is not None)
            else "undefined",
        }
