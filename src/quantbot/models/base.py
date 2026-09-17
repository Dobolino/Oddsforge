"""Abstract base for all prediction models (Layer 1).

A model answers exactly one question: how likely is each outcome? It returns a
:class:`Prediction` and never computes edge, EV, or stake. ``ModelPrediction``
is an alias for the schema so model signatures read clearly.

Leakage rules enforced here:
    * ``fit`` accepts only finished matches (results are known).
    * models are fitted on data strictly before a target match's
      ``prediction_timestamp``; :meth:`BaseModel.fit_until` provides a
      leak-free training slice for a given instant.
    * ``predict`` never reads ``match.result``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from quantbot.schemas import Match, Prediction

# The public name of a model's output. Alias to the shared schema.
ModelPrediction = Prediction


class NotFittedError(RuntimeError):
    """Raised when predict is called before fit."""


class BaseModel(ABC):
    """Base class for probabilistic 1X2 models."""

    #: Stable model identifier, written into every Prediction.
    name: str = "base"

    def __init__(self) -> None:
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    # --- Interface ---

    @abstractmethod
    def fit(self, matches: Sequence[Match]) -> None:
        """Estimate parameters from finished matches."""

    @abstractmethod
    def predict(self, match: Match) -> ModelPrediction:
        """Return outcome probabilities for a match without using its result."""

    # --- Shared helpers ---

    @staticmethod
    def _validate_training_matches(matches: Sequence[Match]) -> list[Match]:
        """Return matches sorted by kickoff; reject any that are not finished."""

        finished: list[Match] = []
        for m in matches:
            if not m.is_finished or m.result is None:
                raise ValueError(
                    f"training match {m.match_id!r} is not finished; "
                    "models may only be fitted on resolved matches"
                )
            finished.append(m)
        return sorted(finished, key=lambda m: m.kickoff)

    def _check_fitted(self) -> None:
        if not self._is_fitted:
            raise NotFittedError(f"{self.name} model is not fitted")

    def fit_until(self, matches: Sequence[Match], as_of: datetime) -> None:
        """Fit using only results published strictly before ``as_of``.

        A leak-free convenience wrapper for walk-forward evaluation: pass the
        full history and the target match's ``prediction_timestamp``.
        """

        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        train = [m for m in matches if m.result_known_before(as_of)]
        self.fit(train)
