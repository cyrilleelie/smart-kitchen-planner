"""
simulate_drift.py - Script de simulation de drift pour les tests de monitoring.

Ce script génère des données de prediction logs avec des distributions différentes
de celles générées par simulate_activity.py, afin de provoquer un drift détectable.

Stratégies de drift implémentées :
1. Inversion des scores (high → low, low → high)
2. Contexte fixe (force meal_type et season à des valeurs constantes)
3. Offset de prédiction (ajoute un biais aux scores)
"""

import sys
import os
import argparse
import random
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User, Recipe, PredictionLog

# --- CONFIGURATION ---
RANDOM_SEED = 99  # Différent de simulate_activity.py (42)


def simulate_drift(
    start_date_str: str,
    end_date_str: str,
    simulations_count: int,
    drift_type: str = "invert",
):
    """
    Génère des prediction logs avec drift artificiel.

    Args:
        start_date_str: Date de début (YYYY-MM-DD)
        end_date_str: Date de fin (YYYY-MM-DD)
        simulations_count: Nombre de logs par utilisateur par jour
        drift_type: Type de drift à simuler
            - "invert": Inverse les scores (5→1, 1→5)
            - "fixed_context": Force meal_type=0, season=0
            - "offset": Ajoute +1.5 à tous les scores
            - "random": Scores complètement aléatoires (ignore persona)
    """
    random.seed(RANDOM_SEED)

    print(f"🔀 DRIFT SIMULATION: {start_date_str} → {end_date_str}")
    print(f"   - Logs/user/day: {simulations_count}")
    print(f"   - Drift type: {drift_type}")

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    with Session(engine) as session:
        users = session.query(User).all()
        recipes = session.query(Recipe).all()

        if not users:
            print("❌ No users found in DB.")
            return
        if not recipes:
            print("❌ No recipes found in DB.")
            return

        total_logs = 0
        current_date = start_date

        while current_date <= end_date:
            print(f"   📅 Processing {current_date.strftime('%Y-%m-%d')}...")
            daily_logs = []

            for user in users:
                sample_recipes = random.sample(
                    recipes, min(len(recipes), simulations_count)
                )

                for recipe in sample_recipes:
                    # --- DRIFT LOGIC ---
                    if drift_type == "invert":
                        # Inverse: ce qui était bon devient mauvais et vice-versa
                        base_score = random.uniform(1.0, 5.0)
                        pred_score = 6.0 - base_score  # 5→1, 1→5, 3→3
                    elif drift_type == "offset":
                        # Offset: tous les scores sont artificiellement élevés
                        base_score = random.uniform(1.0, 3.5)
                        pred_score = base_score + 1.5
                    elif drift_type == "random":
                        # Aléatoire pur: ignore tout pattern
                        pred_score = random.uniform(1.0, 5.0)
                    else:
                        # Default: score normal (pas vraiment de drift)
                        pred_score = random.uniform(2.5, 4.5)

                    pred_score = max(1.0, min(5.0, pred_score))

                    # --- CONTEXT ---
                    if drift_type == "fixed_context":
                        # Contexte fixe: force distribution uniforme → différent des données normales
                        meal = 0
                        season = 0
                    else:
                        # Contexte aléatoire normal
                        meal = random.randint(0, 2)
                        season = random.randint(0, 3)

                    input_features = {
                        "recipe_id": recipe.id,
                        "meal_type": meal,
                        "season": season,
                    }
                    pred_result = {"score": pred_score}

                    log = PredictionLog(
                        user_id=user.id,
                        input_features=json.dumps(input_features),
                        prediction_result=json.dumps(pred_result),
                        model_version="drift_simulated_v1",
                        timestamp=current_date,
                    )
                    daily_logs.append(log)

            if daily_logs:
                session.add_all(daily_logs)
                total_logs += len(daily_logs)

            session.commit()
            current_date += timedelta(days=1)

        print("✅ Drift Simulation Complete!")
        print(
            f"   - Added {total_logs} prediction logs with drift type '{drift_type}'."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simulate drifted prediction logs for monitoring tests."
    )
    parser.add_argument(
        "--start", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument("--end", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--simulations", type=int, default=20, help="Predictions per user per day"
    )
    parser.add_argument(
        "--drift-type",
        type=str,
        choices=["invert", "fixed_context", "offset", "random"],
        default="invert",
        help="Type of drift to simulate",
    )

    args = parser.parse_args()
    simulate_drift(args.start, args.end, args.simulations, args.drift_type)
