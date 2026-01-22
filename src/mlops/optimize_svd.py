import os
import sys
import json
import logging
import pandas as pd
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

from src.database.connection import engine
from src.database.models import Interaction, Recipe
from src.utils.logging_config import setup_logging

# Load Surpise
try:
    # import surprise # Unused
    from surprise import Dataset, Reader, SVD
    from surprise.model_selection import GridSearchCV
except ImportError:
    print("❌ Error: scikit-surprise is not installed.")
    sys.exit(1)

setup_logging()
logger = logging.getLogger(__name__)
load_dotenv()


def optimize_svd():
    logger.info("🚀 Starting SVD Hyperparameter Optimization (GridSearchCV)...")

    # 1. Load Data from DB
    with Session(engine) as session:
        results = session.query(Interaction, Recipe).join(Recipe).all()
        if not results:
            logger.error("❌ Error: No interaction data found in DB.")
            return

        data_list = []
        for interaction, recipe in results:
            data_list.append(
                {
                    "user_id": interaction.user_id,
                    "recipe_id": recipe.id,
                    "rating": interaction.rating,
                }
            )

    df = pd.DataFrame(data_list)
    logger.info(f"   📊 Loaded {len(df)} interactions.")

    # 2. Prepare Surprise Dataset
    reader = Reader(rating_scale=(1, 5))
    data = Dataset.load_from_df(df[["user_id", "recipe_id", "rating"]], reader)

    # 3. Define Parameter Grid
    param_grid = {
        "n_factors": [20, 50, 100, 150],
        "n_epochs": [20, 30, 50],
        "lr_all": [0.002, 0.005, 0.01],
        "reg_all": [0.02, 0.05, 0.1],
    }

    logger.info(f"   ⚙️  Testing grid: {param_grid}")

    # 4. Run Grid Search
    # measures=['rmse'] -> Optimize for RMSE
    # cv=3 -> 3-Fold Cross Validation to be faster (increase to 5 for more robustness if needed)
    gs = GridSearchCV(SVD, param_grid, measures=["rmse"], cv=3, n_jobs=-1)

    logger.info("   ⏳ Running Grid Search (this may take a while)...")
    gs.fit(data)

    # 5. Process Results
    best_rmse = gs.best_score["rmse"]
    best_params = gs.best_params["rmse"]

    logger.info("   ✅ Optimization Complete!")
    logger.info(f"      🏆 Best RMSE: {best_rmse:.4f}")
    logger.info(f"      🔧 Best Params: {best_params}")

    # 6. Save Best Params
    output_dir = "src/models"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "svd_best_params.json")

    with open(output_path, "w") as f:
        json.dump(best_params, f, indent=4)

    logger.info(f"   💾 Best parameters saved to: {output_path}")


if __name__ == "__main__":
    optimize_svd()
