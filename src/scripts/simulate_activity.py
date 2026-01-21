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
from src.database.models import User, Recipe, Interaction, PredictionLog
import glob
from src.scripts.inject_persona import analyze_recipe_taste, load_persona

# --- CONFIGURATION ---
RANDOM_SEED = 42


def load_persona_map(persona_dir="data/personas"):
    """
    Scans a directory for JSON persona files and builds a map:
    { "username": { "rules": ..., "path": ... } }
    """
    mapping = {}
    pattern = os.path.join(persona_dir, "*.json")
    files = glob.glob(pattern)

    print(f"📂 Scanning personas in '{persona_dir}'...")
    for f_path in files:
        try:
            data = load_persona(f_path)
            u = data.get("username")
            if u:
                mapping[u] = {"rules": data.get("behavior_rules", {}), "path": f_path}
        except Exception as e:
            print(f"   ⚠️ Error loading {f_path}: {e}")

    print(f"   ✅ Found {len(mapping)} personas.")
    return mapping


def simulate_activity(
    start_date_str, end_date_str, interactions_count, simulations_count
):
    print(f"🚀 Simulation Activity: {start_date_str} -> {end_date_str}")
    print(f"   - Interactions/day: {interactions_count}")
    print(f"   - Simulations/day : {simulations_count}")

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    # 1. Load Persona Map
    persona_map = load_persona_map()

    with Session(engine) as session:
        # 2. Get All Users
        users = session.query(User).all()
        recipes = session.query(Recipe).all()

        if not users:
            print("❌ No users found in DB.")
            return
        if not recipes:
            print("❌ No recipes found in DB.")
            return

        total_interactions = 0
        total_logs = 0

        # Iterate through days
        current_date = start_date
        while current_date <= end_date:
            print(f"   📅 Processing {current_date.strftime('%Y-%m-%d')}...")
            daily_interactions = []
            daily_logs = []

            for user in users:
                # MATCH USER WITH PERSONA
                persona_data = persona_map.get(user.username)

                if not persona_data:
                    continue

                rules = persona_data["rules"]

                # --- A. GENERATE INTERACTIONS ---
                if interactions_count > 0:
                    sample_recipes = random.sample(
                        recipes, min(len(recipes), interactions_count)
                    )
                    for recipe in sample_recipes:
                        rating = analyze_recipe_taste(recipe, rules)
                        interaction = Interaction(
                            user_id=user.id,
                            recipe_id=recipe.id,
                            rating=rating,
                            date=current_date,
                        )
                        daily_interactions.append(interaction)

                # --- B. GENERATE PREDICTION LOGS (SIMULATIONS) ---
                if simulations_count > 0:
                    sample_recipes_logs = random.sample(
                        recipes, min(len(recipes), simulations_count)
                    )
                    for recipe in sample_recipes_logs:
                        # Reuse taste logic to get a baseline, then add noise for "predicted score"
                        base_rating = analyze_recipe_taste(recipe, rules)
                        pred_score = base_rating + random.uniform(-0.2, 0.2)
                        pred_score = max(1.0, min(5.0, pred_score))

                        # Random Context
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
                            model_version="simulated_v2",
                            timestamp=current_date,
                        )
                        daily_logs.append(log)

            # Commit Daily Batch
            if daily_interactions:
                session.add_all(daily_interactions)
                total_interactions += len(daily_interactions)

            if daily_logs:
                session.add_all(daily_logs)
                total_logs += len(daily_logs)

            session.commit()

            current_date += timedelta(days=1)

        print("✅ Simulation Complete!")
        print(f"   - Added {total_interactions} interactions.")
        print(f"   - Added {total_logs} prediction logs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--interactions", type=int, default=0, help="Interactions per user per day"
    )
    parser.add_argument(
        "--simulations", type=int, default=0, help="Predictions (logs) per user per day"
    )

    args = parser.parse_args()
    simulate_activity(args.start, args.end, args.interactions, args.simulations)
