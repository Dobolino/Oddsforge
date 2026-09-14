"""Betting-slip helper: combine tips into a theoretical accumulator.

Not for placing bets — only for showing how a multi-leg slip might look,
ranked for win chance or optionally boosted with higher-odds legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod

from quantbot.dashboard.ux import plain_signal_label
from quantbot.orchestrator import SignalReport
from quantbot.schemas import MatchOutcome


@dataclass(frozen=True)
class SlipLeg:
    match_id: str
    match: str
    tip: str
    outcome: MatchOutcome
    odds: float
    model_prob: float
    edge: float
    role: str  # "core" | "boost"


@dataclass(frozen=True)
class BettingSlip:
    legs: tuple[SlipLeg, ...]
    style: str  # "safe" | "boosted"

    @property
    def combined_odds(self) -> float:
        if not self.legs:
            return 1.0
        return prod(leg.odds for leg in self.legs)

    @property
    def combined_prob(self) -> float:
        """Independence assumption — illustrative only."""

        if not self.legs:
            return 0.0
        return prod(leg.model_prob for leg in self.legs)

    @property
    def expected_value(self) -> float:
        return self.combined_prob * self.combined_odds - 1.0


def _leg_from_report(report: SignalReport, lang: str, role: str) -> SlipLeg | None:
    signal = report.signal
    if not signal.is_bet or signal.chosen_outcome is None or signal.decimal_odds is None:
        return None
    metric = next(
        (m for m in signal.metrics if m.outcome is signal.chosen_outcome),
        None,
    )
    if metric is None:
        return None
    match = report.match
    return SlipLeg(
        match_id=match.match_id,
        match=f"{match.home_team.name} vs {match.away_team.name}",
        tip=plain_signal_label(signal.signal, lang),
        outcome=signal.chosen_outcome,
        odds=float(signal.decimal_odds),
        model_prob=float(metric.model_prob),
        edge=float(signal.edge or 0.0),
        role=role,
    )


def _value_legs(reports: list[SignalReport], lang: str) -> list[SlipLeg]:
    legs: list[SlipLeg] = []
    for report in reports:
        leg = _leg_from_report(report, lang, role="core")
        if leg is not None:
            legs.append(leg)
    return legs


def build_safe_slip(
    reports: list[SignalReport],
    *,
    lang: str = "de",
    max_legs: int = 3,
) -> BettingSlip | None:
    """Highest win-chance slip: value tips sorted by model probability."""

    legs = _value_legs(reports, lang)
    if not legs:
        return None
    legs.sort(key=lambda leg: (-leg.model_prob, -leg.edge))
    chosen = tuple(legs[: max(1, max_legs)])
    return BettingSlip(legs=chosen, style="safe")


def build_boosted_slip(
    reports: list[SignalReport],
    *,
    lang: str = "de",
    core_legs: int = 2,
    boost_legs: int = 2,
    min_boost_odds: float = 2.2,
) -> BettingSlip | None:
    """Safer core tips plus higher-odds legs to lift the combined price."""

    legs = _value_legs(reports, lang)
    if not legs:
        return None

    by_prob = sorted(legs, key=lambda leg: (-leg.model_prob, -leg.edge))
    core_n = max(1, min(core_legs, len(by_prob)))
    core = [
        SlipLeg(
            match_id=leg.match_id,
            match=leg.match,
            tip=leg.tip,
            outcome=leg.outcome,
            odds=leg.odds,
            model_prob=leg.model_prob,
            edge=leg.edge,
            role="core",
        )
        for leg in by_prob[:core_n]
    ]
    used = {leg.match_id for leg in core}

    boosters = [
        SlipLeg(
            match_id=leg.match_id,
            match=leg.match,
            tip=leg.tip,
            outcome=leg.outcome,
            odds=leg.odds,
            model_prob=leg.model_prob,
            edge=leg.edge,
            role="boost",
        )
        for leg in sorted(by_prob, key=lambda leg: (-leg.odds, -leg.edge))
        if leg.match_id not in used and leg.odds >= min_boost_odds
    ][: max(0, boost_legs)]

    chosen = tuple(core + boosters)
    return BettingSlip(legs=chosen, style="boosted")
