"""Match Card: a full, transparent analysis of one fixture (Layer 3).

Bundles what the models say, how much they agree, the uncertainty band, fair
vs market odds, the model-versus-market divergence, a data-quality breakdown,
a separate reliability score, and a plain-language explanation of why the
signal exists. Reliability is deliberately kept apart from win probability.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

from quantbot.analysis.confidence import ConfidenceEvaluator, DataQualitySignals, ensemble_agreement
from quantbot.schemas import MarketData, Match, MatchOutcome, Prediction, ValueSignal

_ORDER: tuple[MatchOutcome, ...] = (MatchOutcome.HOME, MatchOutcome.DRAW, MatchOutcome.AWAY)


def divergence_tier(edge: float) -> str:
    """Bucket the model-minus-market gap. 'extreme' is not the same as 'good'."""

    a = abs(edge)
    if a < 0.02:
        return "none"
    if a < 0.05:
        return "slight"
    if a < 0.08:
        return "interesting"
    if a < 0.12:
        return "strong"
    return "extreme"


@dataclass
class MatchCard:
    match_id: str
    home: str
    away: str
    probs: dict[str, float]
    uncertainty: dict[str, dict[str, float]]
    models: list[dict[str, object]]
    agreement: float
    fair_odds: dict[str, float]
    market_odds: dict[str, float]
    divergence: dict[str, dict[str, object]]
    data_quality: float
    data_quality_components: list[dict[str, object]]
    reliability: float
    reliability_level: str
    model_confidence: float
    signal: str
    chosen: str | None
    expected_value: float | None
    stake_fraction: float
    reasons: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _reasons(
    features: dict[str, float],
    market_probs: dict[MatchOutcome, float],
    model_probs: dict[MatchOutcome, float],
    chosen: MatchOutcome,
) -> list[dict[str, str]]:
    """Plain-language, bilingual reasons derived from the features and market."""

    out: list[dict[str, str]] = []

    elo = features.get("elo_diff", 0.0)
    if abs(elo) >= 15:
        side_de, side_en = ("Heim", "home") if elo > 0 else ("Auswärts", "away")
        out.append({
            "de": f"Elo-Vorteil {side_de}: {elo:+.0f} Punkte",
            "en": f"Elo advantage {side_en}: {elo:+.0f} points",
        })

    form = features.get("home_form_points", 0.0) - features.get("away_form_points", 0.0)
    if abs(form) >= 0.3:
        who_de, who_en = ("Heimteam", "home team") if form > 0 else ("Auswärtsteam", "away team")
        out.append({
            "de": f"Bessere Form {who_de} ({form:+.2f} Punkte pro Spiel)",
            "en": f"Better form for the {who_en} ({form:+.2f} points per game)",
        })

    home_xg = features.get("home_xg_for_avg", 0.0) - features.get("home_xg_against_avg", 0.0)
    away_xg = features.get("away_xg_for_avg", 0.0) - features.get("away_xg_against_avg", 0.0)
    xg = home_xg - away_xg
    if abs(xg) >= 0.3:
        out.append({
            "de": f"xG-Differenz {xg:+.2f} zugunsten {'Heim' if xg > 0 else 'Auswärts'}",
            "en": f"xG difference {xg:+.2f} favoring {'home' if xg > 0 else 'away'}",
        })

    rest = features.get("home_rest_days", 0.0) - features.get("away_rest_days", 0.0)
    if abs(rest) >= 1.0:
        who_de, who_en = ("Heim", "home") if rest > 0 else ("Auswärts", "away")
        out.append({
            "de": f"Mehr Erholung {who_de}: {abs(rest):.0f} Tage",
            "en": f"More rest for {who_en}: {abs(rest):.0f} days",
        })

    mp = market_probs[chosen] * 100
    op = model_probs[chosen] * 100
    out.append({
        "de": f"Markt {mp:.1f}% gegen Modell {op:.1f}% auf {chosen.value}",
        "en": f"Market {mp:.1f}% vs model {op:.1f}% on {chosen.value}",
    })
    return out


def build_match_card(
    match: Match,
    sub_predictions: dict[str, Prediction],
    ensemble_prediction: Prediction,
    market: MarketData,
    decimal_odds: dict[MatchOutcome, float],
    signal: ValueSignal,
    features: dict[str, float],
    quality: DataQualitySignals,
    evaluator: ConfidenceEvaluator | None = None,
) -> MatchCard:
    evaluator = evaluator or ConfidenceEvaluator()
    probs = ensemble_prediction.probabilities()
    market_probs = market.fair_probabilities()

    # Uncertainty band from the spread across sub-models.
    uncertainty: dict[str, dict[str, float]] = {}
    for o in _ORDER:
        vals = [p.probability_of(o) for p in sub_predictions.values()] or [probs[o]]
        uncertainty[o.value] = {
            "mid": round(probs[o], 4),
            "low": round(min(vals), 4),
            "high": round(max(vals), 4),
        }

    models = [
        {
            "name": name,
            "home": round(p.prob_home, 4),
            "draw": round(p.prob_draw, 4),
            "away": round(p.prob_away, 4),
        }
        for name, p in sub_predictions.items()
    ]
    agreement = round(ensemble_agreement(list(sub_predictions.values())) * 100, 1)

    divergence: dict[str, dict[str, object]] = {}
    for o in _ORDER:
        edge = probs[o] - market_probs[o]
        divergence[o.value] = {"edge": round(edge, 4), "tier": divergence_tier(edge)}

    dq = evaluator.data_quality(quality)
    reliability, rel_level = evaluator.reliability_score(
        ensemble_agreement(list(sub_predictions.values())),
        dq,
        min(quality.home_matches, quality.away_matches),
        quality.liquidity,
    )

    chosen = signal.chosen_outcome or max(_ORDER, key=lambda o: probs[o] - market_probs[o])

    return MatchCard(
        match_id=match.match_id,
        home=match.home_team.name,
        away=match.away_team.name,
        probs={o.value: round(probs[o], 4) for o in _ORDER},
        uncertainty=uncertainty,
        models=models,
        agreement=agreement,
        fair_odds={o.value: round(v, 3) for o, v in market.fair_odds().items()},
        market_odds={o.value: round(decimal_odds[o], 3) for o in _ORDER},
        divergence=divergence,
        data_quality=dq,
        data_quality_components=evaluator.data_quality_components(quality),
        reliability=reliability,
        reliability_level=rel_level.value,
        model_confidence=round(ensemble_prediction.confidence, 1),
        signal=signal.signal.value,
        chosen=signal.chosen_outcome.value if signal.chosen_outcome else None,
        expected_value=signal.expected_value,
        stake_fraction=round(signal.stake_fraction * 100, 2),
        reasons=_reasons(features, market_probs, probs, chosen),
    )
