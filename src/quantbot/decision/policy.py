"""Versioned decision policy shared by CLI, dashboard, backtest, tracker, slip.

Guardrail: UI modes change presentation only. Demo and live use explicit
profiles; live never silently inherits demo-lenient filters.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite

from quantbot.config import Settings, get_settings
from quantbot.decision.rules import NoBetRules, Reason
from quantbot.decision.sizing import HARD_STAKE_CAP, KellySizer


POLICY_VERSION = "1.0.0"


class PolicyProfile(str, Enum):
    LIVE = "live"
    DEMO = "demo"


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALID = "valid"
    DEGRADED = "degraded"
    EXPIRED = "expired"


class DecisionStatus(str, Enum):
    """Coarse outcome of the central policy evaluation."""

    INVALID_DATA = "invalid_data"
    MODEL_NOT_VALIDATED = "model_not_validated"
    NO_BET = "no_bet"
    VALUE_EXPLORATORY = "value_exploratory"
    VALUE_RELEASED = "value_released"


# Stable reason codes (audit / i18n keys stay technical English).
INVALID_ODDS = Reason(
    code="INVALID_DATA_ODDS",
    de="Die Quote ist ungültig oder fehlt — keine Auswertung.",
    en="Odds are invalid or missing — no evaluation.",
    technical="invalid or non-finite decimal odds",
)
INVALID_PROB = Reason(
    code="INVALID_DATA_PROB",
    de="Die Modellwahrscheinlichkeit ist ungültig — keine Auswertung.",
    en="Model probability is invalid — no evaluation.",
    technical="invalid or non-finite model probability",
)
INVALID_HISTORY = Reason(
    code="INVALID_DATA_HISTORY",
    de="Zu wenig Team-Historie für eine belastbare Auswertung.",
    en="Too little team history for a reliable evaluation.",
    technical="insufficient finished matches for either team",
)
MODEL_UNVALIDATED_NO_SIZING = Reason(
    code="MODEL_NOT_VALIDATED_NO_SIZING",
    de="Modell nicht empirisch freigegeben — nur explorativ, kein Simulations-Einsatz.",
    en="Model not empirically released — exploratory only, no simulated stake.",
    technical="validation_status is not VALID; sizing blocked",
)
HIGH_RISK_FORCED = Reason(
    code="VALUE_HIGH_RISK_FORCED",
    de="High-Risk: bestes EV trotz dünner Daten — nur explorativ, kein Einsatz.",
    en="High-risk: best EV despite thin data — exploratory only, no stake.",
    technical="force_best_ev_on_no_bet released exploratory VALUE",
)
MISSING_ODDS = Reason(
    code="INVALID_DATA_MISSING_ODDS",
    de="Keine Marktquote für dieses Spiel — wird trotzdem in der Liste gezeigt.",
    en="No market odds for this match — still listed for visibility.",
    technical="get_latest_odds returned None",
)
MODEL_NOT_FIT = Reason(
    code="INVALID_DATA_MODEL_NOT_FIT",
    de="Modell konnte nicht fitten (zu wenig Historie) — Spiel bleibt sichtbar.",
    en="Model could not fit (too little history) — match still listed.",
    technical="model.fit_until raised NotFittedError/ValueError",
)
HIGH_RISK_MARKET_FALLBACK = Reason(
    code="VALUE_HIGH_RISK_MARKET_FALLBACK",
    de="High-Risk: Markt-Favorit (kein Modell-Fit) — nur explorativ, kein Einsatz.",
    en="High-risk: market favourite (no model fit) — exploratory only, no stake.",
    technical="force_best_ev_on_no_bet market-implied tip after model fit failure",
)


@dataclass(frozen=True)
class DecisionPolicy:
    """Immutable, versioned decision thresholds and release gates.

    Thresholds are marked heuristic until chronological validation artifacts
    exist. Overlapping guards are intentional.
    """

    version: str = POLICY_VERSION
    profile: PolicyProfile = PolicyProfile.LIVE
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED

    # No-bet heuristics (documented as such — not proof of calibration).
    min_ev: float = 0.0
    min_edge: float = 0.03
    max_overround: float = 0.12
    min_data_quality: float = 60.0
    min_model_confidence: float = 55.0
    min_odds: float = 1.2
    max_odds: float = 15.0
    max_plausible_ev: float = 0.50

    min_team_matches: int = 3
    kelly_fraction: float = 0.10
    max_stake_fraction: float = HARD_STAKE_CAP

    # Without a VALID validation artifact, never release Kelly sizing.
    require_validation_for_sizing: bool = True
    # Exploratory VALUE_* display when filters pass but validation is missing.
    allow_exploratory_value_signals: bool = True
    # High-risk UI: if all filters fail, still surface the best-EV side as
    # exploratory VALUE (stake 0) so every priced match gets a recommendation.
    force_best_ev_on_no_bet: bool = False

    def rules(self) -> NoBetRules:
        return NoBetRules(
            min_ev=self.min_ev,
            min_edge=self.min_edge,
            max_overround=self.max_overround,
            min_data_quality=self.min_data_quality,
            min_model_confidence=self.min_model_confidence,
            min_odds=self.min_odds,
            max_odds=self.max_odds,
            max_plausible_ev=self.max_plausible_ev,
        )

    def sizer(self) -> KellySizer:
        return KellySizer(
            kelly_fraction=self.kelly_fraction,
            max_fraction=self.max_stake_fraction,
        )

    @property
    def sizing_released(self) -> bool:
        return (
            self.validation_status is ValidationStatus.VALID
            or not self.require_validation_for_sizing
        )

    def with_validation(self, status: ValidationStatus) -> DecisionPolicy:
        return replace(self, validation_status=status)


def live_policy(settings: Settings | None = None) -> DecisionPolicy:
    """Strict live profile — never inherits demo-lenient filters."""

    s = settings or get_settings()
    return DecisionPolicy(
        profile=PolicyProfile.LIVE,
        validation_status=ValidationStatus.UNVALIDATED,
        min_edge=s.min_edge,
        min_data_quality=s.min_data_quality,
        min_model_confidence=s.min_model_confidence,
        kelly_fraction=s.kelly_fraction,
        require_validation_for_sizing=True,
        allow_exploratory_value_signals=True,
    )


def demo_policy(settings: Settings | None = None) -> DecisionPolicy:
    """Explicit demo profile: same core filters, still no silent live bleed.

    Demo remains labelled exploratory. Tracker may call
    :func:`demo_tracker_policy` when a looser paper trail is intentional.
    """

    base = live_policy(settings)
    return replace(base, profile=PolicyProfile.DEMO)


def demo_tracker_policy() -> DecisionPolicy:
    """Explicit loose profile for demo tip-history only (never for live)."""

    return DecisionPolicy(
        profile=PolicyProfile.DEMO,
        validation_status=ValidationStatus.UNVALIDATED,
        min_ev=0.02,
        min_edge=0.0,
        max_overround=1.0,
        min_data_quality=0.0,
        min_model_confidence=0.0,
        min_odds=1.01,
        max_odds=100.0,
        kelly_fraction=0.25,
        require_validation_for_sizing=False,
        allow_exploratory_value_signals=True,
        min_team_matches=0,
    )


def high_risk_policy(settings: Settings | None = None) -> DecisionPolicy:
    """Explicit high-risk profile: thin history (Nations League) still gets tips.

    Still exploratory (no Kelly sizing without validation). Does not place bets.
    """

    s = settings or get_settings()
    return DecisionPolicy(
        profile=PolicyProfile.LIVE,
        validation_status=ValidationStatus.UNVALIDATED,
        min_ev=-0.02,
        min_edge=0.0,
        max_overround=0.25,
        min_data_quality=0.0,
        min_model_confidence=0.0,
        min_odds=1.05,
        max_odds=25.0,
        max_plausible_ev=1.5,
        min_team_matches=0,
        kelly_fraction=min(0.05, float(s.kelly_fraction)),
        require_validation_for_sizing=True,
        allow_exploratory_value_signals=True,
        force_best_ev_on_no_bet=True,
    )


def policy_for_mode(*, live: bool, settings: Settings | None = None) -> DecisionPolicy:
    return live_policy(settings) if live else demo_policy(settings)


def validate_candidate_inputs(
    *,
    model_prob: float | None,
    decimal_odds: float | None,
    home_matches: int | None = None,
    away_matches: int | None = None,
    min_team_matches: int = 0,
) -> tuple[Reason, ...]:
    """Return INVALID_DATA reasons; empty means inputs are evaluable."""

    reasons: list[Reason] = []
    if model_prob is None or not isfinite(model_prob) or not 0.0 <= model_prob <= 1.0:
        reasons.append(INVALID_PROB)
    if decimal_odds is None or not isfinite(decimal_odds) or decimal_odds <= 1.0:
        reasons.append(INVALID_ODDS)
    if min_team_matches > 0 and home_matches is not None and away_matches is not None:
        if min(home_matches, away_matches) < min_team_matches:
            reasons.append(INVALID_HISTORY)
    return tuple(reasons)
