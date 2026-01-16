import random
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from src.database.models import Recipe
from src.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

class MenuSolver:
    """
    Heuristic-based menu generator/solver.
    
    Generates a meal plan by balancing performance-based recommendations (matches)
    with discovery items to ensure diversity. Uses dynamic quantiles on the
    candidate score distribution to bucket recipes.
    """

    def __init__(
        self, 
        db: Session, 
        user_vector: Optional[List[float]], 
        days: int, 
        target_calories: float, 
        meals_per_day: int
    ):
        """
        Initialize the MenuSolver.

        Args:
            db: Database session.
            user_vector: The user's preference vector (list of floats).
            days: Number of days to plan.
            target_calories: Daily calorie target.
            meals_per_day: Number of meals per day.
        """
        self.db = db
        self.user_vector = np.array(user_vector) if user_vector is not None and len(user_vector) > 0 else None
        self.days = days
        self.target_calories = target_calories
        self.meals_per_day = meals_per_day
        self.cal_max = target_calories * 1.5

    def solve(self) -> List[Dict[str, Any]]:
        """
        Execute the solving algorithm to generate a menu.

        Returns:
            List of dictionaries representing the selected meals, including
            day, recipe_id, algo_type, and score.
        """
        logger.info("🔧 [SOLVER] Strategy: Dynamic Quantiles (Auto Calibration)")
        
        # 1. LOAD CANDIDATES
        try:
            candidates = self.db.query(Recipe.id, Recipe.embedding, Recipe.calories).filter(
                Recipe.embedding != None,
                Recipe.minutes <= 120
            ).all()
        except Exception as e:
            logger.error(f"❌ Failed to load candidates from DB: {e}")
            return []

        scored_items = []
        scores_list = []
        
        for r_id, r_emb, r_cal in candidates:
            if r_cal is None: continue
            score = self._calculate_similarity(r_emb)
            scored_items.append({"id": r_id, "score": score, "calories": r_cal})
            scores_list.append(score)

        if not scores_list: 
            logger.warning("⚠️ No scores generated. Returning empty menu.")
            return []

        # 2. STATISTICAL CALIBRATION
        thresh_perf = np.percentile(scores_list, 80)
        thresh_disco_high = np.percentile(scores_list, 40)
        thresh_disco_low = np.percentile(scores_list, 5) 

        logger.info(f"📊 Calibration: PERF > {thresh_perf:.4f} | DISCO between {thresh_disco_low:.4f} and {thresh_disco_high:.4f}")

        # 3. BUCKETING
        bucket_perf = []
        bucket_disco = []
        
        for item in scored_items:
            s = item["score"]
            if s >= thresh_perf:
                item["type"] = "PERF"
                bucket_perf.append(item)
            elif thresh_disco_low <= s <= thresh_disco_high:
                item["type"] = "DISCO"
                bucket_disco.append(item)
            else:
                item["type"] = "NEUTRAL" 
        
        logger.info(f"📦 Buckets: {len(bucket_perf)} Perf | {len(bucket_disco)} Disco")

        # 4. SELECTION
        total_slots = self.days * self.meals_per_day
        nb_discovery = max(1, int(total_slots * 0.20))
        nb_performance = total_slots - nb_discovery

        final_selection = []
        used_ids = set()

        # A. Fill PERFORMANCE
        bucket_perf.sort(key=lambda x: x["score"], reverse=True) 
        top_perf = bucket_perf[:150] 
        random.shuffle(top_perf)
        
        for item in top_perf:
            if len(final_selection) >= nb_performance: break
            final_selection.append(item)
            used_ids.add(item["id"])

        # B. Fill DISCOVERY
        random.shuffle(bucket_disco)
        for item in bucket_disco:
            if len(final_selection) >= total_slots: break
            final_selection.append(item)
            used_ids.add(item["id"])

        # C. Fallback "RESCUE"
        if len(final_selection) < total_slots:
            logger.warning("⚠️ Fallback activated (Insufficient buckets)")
            remaining_pool = [x for x in scored_items if x["id"] not in used_ids]
            remaining_pool.sort(key=lambda x: x["score"], reverse=True)
            for item in remaining_pool:
                if len(final_selection) >= total_slots: break
                item["type"] = "RESCUE"
                final_selection.append(item)

        # 5. FINALIZE
        random.shuffle(final_selection)
        menu = []
        
        logger.info("🕵️ [AUDIT MENU]")
        
        for i, item in enumerate(final_selection):
            day_num = (i // self.meals_per_day) + 1
            
            menu.append({
                "day": day_num,
                "recipe_id": item["id"],
                "algo_type": item.get("type", "PERF"),
                "score": item["score"]
            })

            logger.info(f"Day {day_num:<2} | ID {item['id']:<6} | Score {item['score']:.4f} | {item['type']}")
            
        return menu

    def calculate_score(self, recipe: Recipe) -> float:
        """Helper to calculate similarity score for a recipe object."""
        return self._calculate_similarity(recipe.embedding)

    def _calculate_similarity(self, embedding_data: Union[str, List[float], None]) -> float:
        """
        Calculate cosine similarity between user vector and recipe embedding.
        
        Args:
            embedding_data: Recipe embedding (JSON string or list).
            
        Returns:
            Similarity score (0-1). Returns 0.5 on error.
        """
        if self.user_vector is None or embedding_data is None: return 0.5
        
        try:
            if isinstance(embedding_data, str):
                vec = np.array(json.loads(embedding_data))
            else:
                vec = np.array(embedding_data)
                
            norm_u = np.linalg.norm(self.user_vector)
            norm_r = np.linalg.norm(vec)
            
            if norm_u == 0 or norm_r == 0: return 0.5
            
            dot = np.dot(self.user_vector, vec)
            sim = dot / (norm_u * norm_r)
            return float((sim + 1) / 2)
            
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Error calculating similarity: {e}. Data: {str(embedding_data)[:20]}...")
            return 0.5
        except Exception as e:
            logger.error(f"Unexpected error in similarity calc: {e}", exc_info=True)
            return 0.5