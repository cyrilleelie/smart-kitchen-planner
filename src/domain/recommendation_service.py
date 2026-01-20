# src/domain/recommendation_service.py
"""Recommendation service supporting multiple strategies.

- RandomForestStrategy: uses the existing InferenceService (content‑based model).
- SVDSurpriseStrategy: uses a collaborative‑filtering SVD model from scikit‑surprise.

The public function ``generate_recommendations`` selects the appropriate strategy
based on the ``model_type`` argument (``content_based`` or ``collaborative``).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

# Internal imports
from src.database.models import Recipe, Interaction
from src.recommender.inference_service import InferenceService

# Surprise imports – the model is stored with ``surprise.dump``
import surprise

logger = logging.getLogger(__name__)


class RecommendationStrategy(ABC):
    """Abstract base class for recommendation strategies."""

    @abstractmethod
    def rank(
        self, user_id: int, candidate_ids: List[int], top_n: int
    ) -> List[Tuple[int, float]]:
        """Return a list of ``(recipe_id, score)`` tuples sorted by descending score.

        Implementations must handle cold‑start cases internally.
        """


class RandomForestStrategy(RecommendationStrategy):
    """Legacy content‑based strategy using the existing RandomForest model.

    It delegates to :class:`InferenceService` which already knows how to score a
    list of candidates. The service returns a list of dictionaries containing a
    ``recipe`` key; we extract the ``id`` and ``score``.
    """

    def __init__(self, db: Session):
        self.db = db
        self.service = InferenceService(db)

    def rank(
        self, user_id: int, candidate_ids: List[int], top_n: int
    ) -> List[Tuple[int, float]]:
        # The InferenceService currently does not accept a pre‑filtered list, so we
        # call its ``recommend`` method and then filter the results.
        raw_recs = self.service.recommend(user_id=user_id, n=top_n * 5)  # oversample
        # Filter to the candidate set
        filtered = [r for r in raw_recs if r["id"] in candidate_ids]
        # Sort and keep top_n
        filtered.sort(key=lambda x: x["score"], reverse=True)
        return [(r["id"], r["score"]) for r in filtered[:top_n]]


class SVDSurpriseStrategy(RecommendationStrategy):
    """Collaborative‑filtering strategy using a scikit‑surprise SVD model.

    The model is loaded from ``src/models/svd_model.pkl``. For each candidate
    recipe we call ``algo.predict(user_id, recipe_id)``. If the user is unknown to
    the model (i.e. the prediction returns ``nan``), we fall back to the global
    average rating of the recipe.
    """

    def __init__(self, db: Session):
        self.db = db
        # Load the SVD model – ``surprise.dump`` stores a tuple (predictions, algo)
        model_path = "src/models/svd_model.pkl"
        try:
            _, self.algo = surprise.dump.load(model_path)
        except Exception as e:
            logger.error(f"Failed to load SVD model from {model_path}: {e}")
            raise

    def _global_average(self, recipe_id: int) -> float:
        avg = (
            self.db.query(func.avg(Interaction.rating))
            .filter(Interaction.recipe_id == recipe_id)
            .scalar()
        )
        return float(avg) if avg is not None else 0.0

    def rank(
        self, user_id: int, candidate_ids: List[int], top_n: int
    ) -> List[Tuple[int, float]]:
        scores: List[Tuple[int, float]] = []
        for rid in candidate_ids:
            pred = self.algo.predict(uid=user_id, iid=rid)
            score = pred.est
            # Surprise returns ``nan`` when the user/item is unknown
            if score != score:  # NaN check
                score = self._global_average(rid)
            scores.append((rid, score))
        # Sort by score descending and keep top_n
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]


def _apply_constraints(db: Session, constraints: dict) -> List[int]:
    """Return a list of recipe IDs that satisfy the supplied constraints.

    Supported keys (example): ``vegetarian`` (bool), ``max_time`` (int minutes).
    The function can be extended as needed.
    """
    query = db.query(Recipe.id)
    if constraints.get("vegetarian") is True:
        # 'tags' is stored as a string, e.g. "['vegetarian', 'healthy']"
        query = query.filter(Recipe.tags.ilike("%vegetarian%"))
    if max_time := constraints.get("max_time"):
        query = query.filter(Recipe.minutes <= max_time)
    # Add more constraint handling here if required
    return [r[0] for r in query.all()]


def generate_recommendations(
    db: Session,
    user_id: int,
    constraints: dict | None = None,
    top_n: int = 10,
    model_type: str = "collaborative",
) -> List[Tuple[Recipe, float]]:
    """Public API used by the FastAPI endpoint.

    Parameters
    ----------
    db: Session
        Active SQLAlchemy session.
    user_id: int
        Identifier of the target user.
    constraints: dict | None
        Optional filtering constraints (e.g. ``{"vegetarian": True, "max_time": 30}``).
    top_n: int
        Number of recipes to return.
    model_type: str
        ``"content_based"`` for the RandomForest pipeline or ``"collaborative"``
        for the SVD pipeline. Defaults to ``"collaborative"`` as requested.

    Returns
    -------
    List[Tuple[Recipe, float]]
        A list of (recipe, score) tuples sorted by descending score.
    """
    constraints = constraints or {}
    candidate_ids = _apply_constraints(db, constraints)
    if not candidate_ids:
        return []

    if model_type == "content_based":
        strategy = RandomForestStrategy(db)
    else:
        strategy = SVDSurpriseStrategy(db)

    ranked = strategy.rank(user_id=user_id, candidate_ids=candidate_ids, top_n=top_n)
    # Fetch full Recipe objects preserving order
    if not ranked:
        return []

    ordered_ids = [rid for rid, _ in ranked]
    scores_map = {rid: score for rid, score in ranked}

    recipes = db.query(Recipe).filter(Recipe.id.in_(ordered_ids)).all()
    recipe_map = {r.id: r for r in recipes}

    # Return (Recipe, score) tuples in the ranked order
    return [
        (recipe_map[rid], scores_map[rid]) for rid in ordered_ids if rid in recipe_map
    ]
