"""Prediction schema: the model's probabilistic output (Layer 1).

Guardrail: a prediction carries ONLY probabilities and supporting model
metadata. It never contains edge, EV, stake, or any value judgement. Value is
computed later by Layer 3 and Layer 4.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import MatchOutcome


class ScoreMatrix(QuantBotModel):
    """Probability distribution over exact scorelines.

    ``matrix[i][j]`` is P(home scores i, away scores j). Rows index home
    goals, columns index away goals. Probabilities sum to 1.0.
    """

    matrix: list[list[float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> ScoreMatrix:
        width = len(self.matrix[0])
        total = 0.0
        for row in self.matrix:
            if len(row) != width:
                raise ValueError("score matrix rows must all have equal length")
            for cell in row:
                if cell < 0.0:
                    raise ValueError("score matrix probabilities must be non-negative")
                total += cell
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            raise ValueError(f"score matrix must sum to 1.0, got {total}")
        return self

    def outcome_probabilities(self) -> dict[MatchOutcome, float]:
        """Marginalize the scoreline matrix into 1X2 probabilities."""

        home = draw = away = 0.0
        for i, row in enumerate(self.matrix):
            for j, cell in enumerate(row):
                if i > j:
                    home += cell
                elif i == j:
                    draw += cell
                else:
                    away += cell
        return {
            MatchOutcome.HOME: home,
            MatchOutcome.DRAW: draw,
            MatchOutcome.AWAY: away,
        }

    def totals_probabilities(self, line: float = 2.5) -> dict[str, float]:
        """Over/Under probabilities for a totals line (e.g. 2.5 goals).

        ``over`` is P(home_goals + away_goals > line), ``under`` is
        P(total < line). For half-lines such as 2.5 there is no push mass;
        over + under equals 1.0.
        """

        from quantbot.schemas.enums import TotalsSide

        over = under = 0.0
        for i, row in enumerate(self.matrix):
            for j, cell in enumerate(row):
                total = i + j
                if total > line:
                    over += cell
                elif total < line:
                    under += cell
                # Exactly on an integer line would be a push; half-lines skip.
        mass = over + under
        if mass <= 0.0:
            return {TotalsSide.OVER: 0.5, TotalsSide.UNDER: 0.5}
        return {
            TotalsSide.OVER: over / mass,
            TotalsSide.UNDER: under / mass,
        }

class Prediction(QuantBotModel):
    """A model's probabilistic forecast for one match.

    Attributes:
        prob_home/draw/away: Outcome probabilities summing to 1.0.
        model_name: Identifier of the producing model (e.g. 'dixon_coles').
        prediction_timestamp: Must match the match's prediction time; used to
            verify temporal isolation downstream.
        confidence: Model self-assessed confidence on a 0-100 scale.
        score_matrix: Optional exact-score distribution (Poisson models).
    """

    match_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    prediction_timestamp: datetime
    prob_home: float = Field(ge=0.0, le=1.0)
    prob_draw: float = Field(ge=0.0, le=1.0)
    prob_away: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=50.0, ge=0.0, le=100.0)
    score_matrix: ScoreMatrix | None = None

    @model_validator(mode="after")
    def _validate(self) -> Prediction:
        if self.prediction_timestamp.tzinfo is None:
            raise ValueError("prediction_timestamp must be timezone-aware")
        total = self.prob_home + self.prob_draw + self.prob_away
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            raise ValueError(f"outcome probabilities must sum to 1.0, got {total}")
        return self

    def probabilities(self) -> dict[MatchOutcome, float]:
        return {
            MatchOutcome.HOME: self.prob_home,
            MatchOutcome.DRAW: self.prob_draw,
            MatchOutcome.AWAY: self.prob_away,
        }

    def probability_of(self, outcome: MatchOutcome) -> float:
        return self.probabilities()[outcome]
