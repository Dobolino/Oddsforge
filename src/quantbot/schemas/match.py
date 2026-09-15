"""Match and team schemas.

The critical guardrail lives here: every :class:`Match` carries a
``prediction_timestamp``. No feature attached to a match may originate after
this instant. Downstream feature builders must enforce this to avoid data
leakage.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import QuantBotModel
from quantbot.schemas.enums import InjuryStatus, League, MatchOutcome, MatchStatus


class Team(QuantBotModel):
    """A football team."""

    team_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    short_name: str | None = Field(default=None, min_length=1)


class MatchResult(QuantBotModel):
    """Final score of a finished match.

    Only present for historical matches. Never available at prediction time.
    ``home_xg`` / ``away_xg`` are optional expected-goals values; when absent,
    feature builders fall back to actual goals as a documented proxy.
    """

    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    home_xg: float | None = Field(default=None, ge=0.0)
    away_xg: float | None = Field(default=None, ge=0.0)

    @property
    def outcome(self) -> MatchOutcome:
        if self.home_goals > self.away_goals:
            return MatchOutcome.HOME
        if self.home_goals < self.away_goals:
            return MatchOutcome.AWAY
        return MatchOutcome.DRAW

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals


class Match(QuantBotModel):
    """A single football fixture.

    Attributes:
        prediction_timestamp: The instant at which prediction is made. All
            features must be temporally isolated to before this point.
        kickoff: Scheduled kickoff time (timezone-aware).
        result: Final score, present only for finished matches.
    """

    match_id: str = Field(min_length=1)
    league: League
    season: str = Field(min_length=4, description="e.g. '2024-2025'")
    kickoff: datetime
    prediction_timestamp: datetime
    home_team: Team
    away_team: Team
    status: MatchStatus = MatchStatus.SCHEDULED
    home_injury_status: InjuryStatus = InjuryStatus.UNKNOWN
    away_injury_status: InjuryStatus = InjuryStatus.UNKNOWN
    result: MatchResult | None = None

    @model_validator(mode="after")
    def _validate_temporal_and_teams(self) -> Match:
        if self.home_team.team_id == self.away_team.team_id:
            raise ValueError("home_team and away_team must differ")

        for label, value in (
            ("kickoff", self.kickoff),
            ("prediction_timestamp", self.prediction_timestamp),
        ):
            if value.tzinfo is None:
                raise ValueError(f"{label} must be timezone-aware")

        # Predictions are made before kickoff; a prediction stamped after
        # kickoff would leak in-play information.
        if self.prediction_timestamp > self.kickoff:
            raise ValueError(
                "prediction_timestamp must not be after kickoff "
                "(would leak in-play information)"
            )

        if self.result is not None and self.status is not MatchStatus.FINISHED:
            raise ValueError("result may only be set when status is FINISHED")

        return self

    @property
    def is_finished(self) -> bool:
        return self.status is MatchStatus.FINISHED and self.result is not None
