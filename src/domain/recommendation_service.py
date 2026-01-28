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
        self,
        user_id: int,
        candidate_ids: List[int],
        top_n: int,
        context: dict | None = None,
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
        self,
        user_id: int,
        candidate_ids: List[int],
        top_n: int,
        context: dict | None = None,
    ) -> List[Tuple[int, float]]:
        # Fetch actual recipe objects for the candidate_ids
        # This fixes the issue where service.recommend() would return a random subset
        # causing no overlap with candidate_ids.
        recipes = self.db.query(Recipe).filter(Recipe.id.in_(candidate_ids)).all()

        context = context or {}

        # Use the new explicit ranking method in InferenceService
        results = self.service.rank_recipes(user_id, recipes, context)

        # results is List[dict] with 'id' and 'score'
        return [(r["id"], r["score"]) for r in results[:top_n]]


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
        self,
        user_id: int,
        candidate_ids: List[int],
        top_n: int,
        context: dict | None = None,
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


class HybridStrategy(RecommendationStrategy):
    """Hybrid strategy combining SVD (collaborative) and RF (content-based).

    This strategy combines:
    - SVD: Personalization based on user-item interactions
    - RF: Contextual relevance (meal_type, season)

    The combination is MULTIPLICATIVE: Score = SVD_Score * RF_Score.
    This ensures that context acts as a gateway: if RF predicts a low score
    (indicating bad context fit, e.g. Steak for Breakfast), the final score
    will be low even if the user loves Steaks (high SVD).
    """

    def __init__(self, db: Session):
        self.db = db
        self.svd_strategy = SVDSurpriseStrategy(db)
        self.rf_strategy = RandomForestStrategy(db)

    def rank(
        self,
        user_id: int,
        candidate_ids: List[int],
        top_n: int,
        context: dict | None = None,
    ) -> List[Tuple[int, float]]:
        """Combine SVD and RF scores using multiplication."""
        # Get SVD scores (scale ~1-5)
        svd_scores = self.svd_strategy.rank(
            user_id, candidate_ids, len(candidate_ids), context
        )
        svd_map = {rid: max(0.1, score) for rid, score in svd_scores}

        # Get RF scores (scale ~1-5)
        rf_scores = self.rf_strategy.rank(
            user_id, candidate_ids, len(candidate_ids), context
        )
        rf_map = {rid: max(0.1, score) for rid, score in rf_scores}

        # Combine scores : Multiplicative approach
        # SVD(5) * RF(1) = 5
        # SVD(5) * RF(5) = 25
        # We take the SQRT to bring it back to a roughly 1-5 scale.
        # sqrt(25) = 5, sqrt(5) ~= 2.2, sqrt(1) = 1
        combined: List[Tuple[int, float]] = []
        import math

        for rid in candidate_ids:
            svd_s = svd_map.get(rid, 1.0)
            rf_s = rf_map.get(rid, 1.0)

            # Multiplicative interaction
            raw_score = svd_s * rf_s
            # Normalize back to linear scale
            hybrid_score = math.sqrt(raw_score)

            combined.append((rid, hybrid_score))

        # Sort by combined score descending
        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_n]


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
        Optional filtering constraints (e.g. ``{"vegetarian": True, "max_time": 30}``, ``{"meal_type": 1, "season": 0}``).
        Note: Context like meal_type/season should be passed in constraints for RF model.
    top_n: int
        Number of recipes to return.
    model_type: str
        ``"content_based"`` for the RandomForest pipeline, ``"collaborative"``
        for the SVD pipeline, or ``"hybrid"`` for combined SVD+RF scoring.
        Defaults to ``"collaborative"``.

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
    elif model_type == "hybrid":
        strategy = HybridStrategy(db)
    else:
        strategy = SVDSurpriseStrategy(db)

    # Convert constraints to context for RF
    context = {}
    if "meal_type" in constraints:
        context["meal_type"] = constraints["meal_type"]
    if "season" in constraints:
        context["season"] = constraints["season"]

    ranked = strategy.rank(
        user_id=user_id, candidate_ids=candidate_ids, top_n=top_n, context=context
    )
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


def generate_weekly_plan(
    db: Session,
    user_id: int,
    meal_type: int,
    season: int,
    n_days: int = 7,
    target_calories: int | None = None,
    model_type: str = "collaborative",
) -> List[dict]:
    """
    Generate a weekly batch of recipes respecting constraints and diversity (80/20).

    Logic:
    1. Fetch a large pool of candidates.
    2. Filter by calories (if target_calories provided).
    3. Rank using the selected strategy (content_based vs collaborative).
    4. Apply 80% Performance / 20% Discovery rule.
    """
    # 1. Fetch Candidates (Broad strategy: fetch all or limit to ~1000)
    # We apply constraint (Calorie) first to reduce load on ranker if possible,
    # but here we need to fetch objects to check calories.
    query = db.query(Recipe)

    # 1a. Pre-filter by calories if strictly required?
    # For now, let's fetch a reasonable pool and filter in memory to keep it simple
    # and consistent with previous InferenceService logic.
    candidates_pool = query.limit(1000).all()

    # 2. Filter by Calories
    filtered_ids = []
    recipe_map = {}

    if target_calories and target_calories > 0:
        min_cal = target_calories * 0.7
        max_cal = target_calories * 1.3

        for r in candidates_pool:
            cals = 0.0
            try:
                if r.nutrition_info:
                    # Assuming nutrition_info is valid JSON or eval-able list
                    # Safest generic parse as per previous service logic
                    import ast

                    cals = float(ast.literal_eval(r.nutrition_info)[0])
            except Exception:
                pass

            # Keep if valid or if 0 (unknown) to not block
            if cals == 0 or (min_cal <= cals <= max_cal):
                filtered_ids.append(r.id)
                recipe_map[r.id] = r
    else:
        filtered_ids = [r.id for r in candidates_pool]
        recipe_map = {r.id: r for r in candidates_pool}

    if not filtered_ids:
        # Fallback: take top 100 unfiltered
        fallback = query.limit(100).all()
        filtered_ids = [r.id for r in fallback]
        recipe_map = {r.id: r for r in fallback}

    # 3. Rank
    if model_type == "content_based":
        strategy = RandomForestStrategy(db)
    elif model_type == "hybrid":
        strategy = HybridStrategy(db)
    else:
        strategy = SVDSurpriseStrategy(db)

    # We need to rank ALL candidates to find the top ones
    # rank returns (id, score)
    context = {"meal_type": meal_type, "season": season}
    ranked = strategy.rank(
        user_id, filtered_ids, top_n=len(filtered_ids), context=context
    )

    if not ranked:
        return []

    # 4. 80/20 Strategy (Performance vs Discovery)
    # Reconstruct dict items with tags
    all_results = []
    for rid, score in ranked:
        all_results.append({"recipe": recipe_map[rid], "score": score, "tag": None})

    # If using collaborative or hybrid filtering, return purely the top recommendations (Performance)
    # to ensure strict adherence to context (Hybrid) or user preference (SVD).
    if model_type in ["collaborative", "hybrid"]:
        tag_label = "Hybrid" if model_type == "hybrid" else "SVD"
        final_selection = []
        for item in all_results[:n_days]:
            item["tag"] = tag_label
            final_selection.append(item)
        return final_selection

    n_perf = max(1, int(n_days * 0.8))
    n_disco = n_days - n_perf

    final_selection = []

    # A. Performance
    perf_pool = all_results[:n_perf]
    for item in perf_pool:
        item["tag"] = "Performance"
        final_selection.append(item)

    # B. Discovery (10% - 40% items)
    start_idx = int(len(all_results) * 0.10)
    end_idx = int(len(all_results) * 0.40)

    if start_idx >= end_idx:
        discovery_pool = all_results[n_perf : n_perf + n_disco]
    else:
        discovery_pool = all_results[start_idx:end_idx]

    if discovery_pool:
        import random

        discovery_pool = [x for x in discovery_pool if x not in final_selection]
        if discovery_pool:
            chosen_disco = random.sample(
                discovery_pool, min(len(discovery_pool), n_disco)
            )
            for item in chosen_disco:
                item["tag"] = "Découverte"
                final_selection.append(item)

    # Shuffle for variety
    import random

    random.shuffle(final_selection)

    return final_selection[:n_days]
