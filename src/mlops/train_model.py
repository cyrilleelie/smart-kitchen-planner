import sys
import os
import ast
import json
import random
import logging
from dotenv import load_dotenv

import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from sqlalchemy.orm import Session
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

# Add current working directory to sys.path to allow local imports
sys.path.append(os.getcwd())

from src.utils.logging_config import setup_logging
from src.database.connection import engine  # noqa: E402
from src.database.models import Interaction, Recipe  # noqa: E402

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()

try:
    import surprise
    from surprise import Dataset, Reader, SVD
    from surprise.model_selection import train_test_split as surprise_train_test_split
except ImportError:
    surprise = None
    Dataset = Reader = SVD = None
    surprise_train_test_split = None
    logger.warning(
        "scikit-surprise is not installed; SVD pipeline will be unavailable."
    )

# --- CONFIGURATION MLOPS ---
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
EXPERIMENT_NAME = "SmartRetail_Context_Ranking"

# --- HEURISTIQUES MÉTIER SIMPLIFIÉES ---
# Nous avons fusionné Déjeuner et Dîner en "main_meal"
CONTEXT_RULES = {
    "breakfast": [
        "pancake",
        "waffle",
        "toast",
        "coffee",
        "cereal",
        "oat",
        "yogurt",
        "smoothie",
        "croissant",
        "porridge",
        "granola",
        "egg",
        "bacon",
    ],
    # Fusion Déjeuner / Dîner -> Repas Principal
    "main_meal": [
        "roast",
        "steak",
        "stew",
        "casserole",
        "pasta",
        "curry",
        "lasagna",
        "gratin",
        "burger",
        "rice",
        "noodle",
        "pizza",
        "chicken",
        "beef",
        "pork",
        "fish",
        "salad",
        "soup",
    ],
    "snack": [
        "snack",
        "cookie",
        "muffin",
        "bar",
        "smoothie",
        "fruit",
        "chips",
        "dip",
        "popcorn",
        "bites",
        "nuts",
        "energy",
        "cracker",
        "hummus",
    ],
    "summer": ["salad", "ice cream", "sorbet", "gazpacho", "cold", "fresh", "grill"],
    "winter": ["soup", "stew", "roast", "comfort", "hot", "gratin", "fondue"],
}


def parse_vector(vec_str):
    if isinstance(vec_str, str):
        return np.array(eval(vec_str), dtype=np.float32)
    elif isinstance(vec_str, list):
        return np.array(vec_str, dtype=np.float32)
    elif isinstance(vec_str, np.ndarray):
        return vec_str
    return np.zeros(384)


def parse_list(str_value):
    try:
        if not str_value:
            return []
        if isinstance(str_value, list):
            return str_value
        return ast.literal_eval(str_value)
    except Exception:
        return []


def calculate_context_penalty(recipe, meal_type, season):
    """
    Simule l'adéquation recette/contexte.
    NOUVELLE MAPPING :
    meal_type: 0 (Matin), 1 (Repas Principal - Midi/Soir), 2 (Snack)
    season: 0 (Hiver), 1 (Printemps), 2 (Ete), 3 (Automne)
    """
    text = (recipe.name + " " + " ".join(parse_list(recipe.tags))).lower()
    penalty = 0.0

    is_breakfast_kw = any(kw in text for kw in CONTEXT_RULES["breakfast"])
    is_snack_kw = any(kw in text for kw in CONTEXT_RULES["snack"])
    is_main_kw = any(kw in text for kw in CONTEXT_RULES["main_meal"])

    # --- 0 : PETIT DÉJEUNER ---
    if meal_type == 0:
        # Si c'est un plat principal -> PÉNALITÉ MAXIMALE
        if is_main_kw:
            penalty -= 4.0

        # Si ça ne ressemble pas à un petit déj -> Pénalité
        elif not is_breakfast_kw:
            penalty -= 1.5

    # --- 1 : REPAS PRINCIPAL (MIDI / SOIR) ---
    elif meal_type == 1:
        # On ne veut pas de petit-dej ou de snack comme plat de résistance
        # Sauf si c'est un dessert (ex: tarte aux fruits qui match 'fruit' du snack)
        # On ne veut pas de petit-dej ou de snack comme plat de résistance
        # Sauf si c'est un dessert ou si c'est A LA FOIS main et breakfast (ex: bacon burger, carbonara)
        if (
            (is_breakfast_kw or is_snack_kw)
            and not is_main_kw
            and "dessert" not in text
        ):
            penalty -= 1.0  # Reduced from -2.0

        # Bonus si c'est clairement un plat principal
        if is_main_kw:
            penalty += 0.5

    # --- 2 : SNACK ---
    elif meal_type == 2:
        # Si c'est un gros plat -> PÉNALITÉ MAXIMALE
        if is_main_kw:
            penalty -= 4.0

        # Un snack doit être rapide
        elif recipe.minutes > 20:
            penalty -= 2.5

        # Bonus contextuel
        elif is_snack_kw:
            penalty += 0.5

        else:
            penalty -= 1.0

    # --- LOGIQUE SAISONS (Inchangée) ---
    is_winter = any(kw in text for kw in CONTEXT_RULES["winter"])
    if season == 2 and is_winter:  # Soupe en été
        penalty -= 1.5

    is_summer = any(kw in text for kw in CONTEXT_RULES["summer"])
    if season == 0 and is_summer:  # Glace en hiver
        penalty -= 1.5

    return penalty


def train():
    logger.info(
        "🚀 Démarrage de l'entraînement Context-Aware (Simplifié: 3 types de repas)..."
    )

    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    with Session(engine) as session:
        # 0. Check for embeddings presence
        missing_emb_count = (
            session.query(Recipe).filter(Recipe.embedding.is_(None)).count()
        )
        if missing_emb_count > 0:
            total_recipes = session.query(Recipe).count()
            msg = f"❌ CRITICAL: {missing_emb_count}/{total_recipes} recipes have NO embeddings! Please run 'python src/scripts/generate_embeddings.py' first."
            logger.error(msg)
            raise ValueError(msg)

        logger.info("   📥 Chargement des interactions brutes...")
        results = session.query(Interaction, Recipe).join(Recipe).all()

        if not results:
            logger.error("   ❌ Erreur : Pas de données.")
            return

        # 1. Préparation des données brutes
        raw_data = []
        for interaction, recipe in results:
            raw_data.append(
                {
                    "user_id": interaction.user_id,
                    "base_rating": interaction.rating,
                    "recipe_vec": parse_vector(recipe.embedding),
                    "recipe_obj": recipe,
                }
            )

        df_raw = pd.DataFrame(raw_data)
        logger.info(f"   📚 Interactions réelles : {len(df_raw)}")

    # 2. Feature Engineering : Vecteurs Utilisateurs
    logger.info("   🧠 Calcul des profils utilisateurs...")
    user_vectors = {}
    for user_id in df_raw["user_id"].unique():
        user_likes = df_raw[
            (df_raw["user_id"] == user_id) & (df_raw["base_rating"] >= 4)
        ]
        if not user_likes.empty:
            vectors = np.stack(user_likes["recipe_vec"].values)
            user_mean_vec = np.mean(vectors, axis=0)
        else:
            user_mean_vec = np.zeros(384)
        user_vectors[user_id] = user_mean_vec

    # 3. DATA AUGMENTATION
    logger.info("   🧪 Génération des scénarios d'entraînement...")

    X_list = []
    y_list = []

    for index, row in df_raw.iterrows():
        u_vec = user_vectors[row["user_id"]]
        r_vec = row["recipe_vec"]
        base_score = row["base_rating"]

        # On simule 4 contextes aléatoires
        for _ in range(4):
            # NOUVEAU : Choix parmi 0 (Matin), 1 (Repas), 2 (Snack) uniquement
            simulated_meal = random.choice([0, 1, 2])
            simulated_season = random.choice([0, 1, 2, 3])

            penalty = calculate_context_penalty(
                row["recipe_obj"], simulated_meal, simulated_season
            )

            target_score = max(1, min(5, base_score + penalty))

            context_features = np.array(
                [simulated_meal, simulated_season], dtype=np.float32
            )
            combined_features = np.concatenate([u_vec, r_vec, context_features])

            X_list.append(combined_features)
            y_list.append(target_score)

    X = np.array(X_list)
    y = np.array(y_list)

    logger.info(f"   📊 Dataset augmenté final : {len(X)} lignes.")

    # 4. Entraînement
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"   📡 Connexion à MLflow ({MLFLOW_URI})...")
    with mlflow.start_run():
        params = {"n_estimators": 50, "max_depth": 15}
        mlflow.log_params(params)

        logger.info("   🏋️‍♂️ Entraînement du modèle (Random Forest)...")
        model = RandomForestRegressor(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            n_jobs=-1,
            random_state=42,
        )
        model.fit(X_train, y_train)

        # --- AJOUT MLOPS : Sauvegarde de la Reference Data ---
        logger.info("   💾 Sauvegarde de la Reference Data pour Evidently...")

        # On reconstitue un DataFrame propre pour le futur monitoring
        # On sauve X_train (features) + y_train (target réelle) + prediction

        # 1. Calcul des prédictions sur le jeu d'entraînement (Reference)
        train_preds = model.predict(X_train)

        # Note: X_train est un numpy array, on le convertit en DF pour plus de clarté
        ref_df = pd.DataFrame(X_train)
        ref_df.columns = ref_df.columns.astype(str)  # Force string headers
        ref_df["target"] = y_train
        ref_df["prediction"] = train_preds

        # On sauvegarde en CSV localement puis on l'envoie sur MLflow
        ref_path = "reference_data.csv"
        # On prend un sample si le dataset est géant (>50k lignes), sinon tout
        ref_df.to_csv(ref_path, index=False)

        mlflow.log_artifact(ref_path, "drift_reference")

        if os.path.exists(ref_path):
            os.remove(ref_path)
        # ----------------------------------------------------

        predictions = model.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        mae = mean_absolute_error(y_test, predictions)

        print(f"   ✅ RMSE: {rmse:.4f} | MAE: {mae:.4f}")
        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mae", mae)

        mlflow.sklearn.log_model(model, "model")
        logger.info("   💾 Modèle sauvegardé dans MLflow !")

        # Save locally as fallback
        import joblib

        local_path = "src/models/rf_model.pkl"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        joblib.dump(model, local_path)
        logger.info(f"   💾 Modèle sauvegardé localement : {local_path}")


# New SVD training pipeline using scikit-surprise
def train_svd():
    logger.info("🚀 Démarrage de l'entraînement du modèle SVD (scikit-surprise)...")
    with Session(engine) as session:
        results = session.query(Interaction, Recipe).join(Recipe).all()
        if not results:
            logger.error("   ❌ Erreur : Pas de données pour SVD.")
            return
        data = []
        for interaction, recipe in results:
            data.append(
                {
                    "user_id": interaction.user_id,
                    "recipe_id": recipe.id,
                    "rating": interaction.rating,
                }
            )
    df = pd.DataFrame(data)
    reader = Reader(rating_scale=(1, 5))
    surprise_data = Dataset.load_from_df(df[["user_id", "recipe_id", "rating"]], reader)
    trainset, testset = surprise_train_test_split(
        surprise_data, test_size=0.2, random_state=42
    )
    print(f"   📡 Connexion à MLflow ({MLFLOW_URI})...")
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="SVD_Collaborative_Filtering"):
        # 1. Load Optimized Params if available
        params_path = "src/models/svd_best_params.json"
        if os.path.exists(params_path):
            logger.info(f"   ⚙️  Loading optimized SVD parameters from {params_path}...")
            with open(params_path, "r") as f:
                best_params = json.load(f)
            # Ensure keys match SVD arguments
            params = best_params
        else:
            logger.info("   ⚙️  Using default SVD parameters.")
            params = {"n_factors": 100, "n_epochs": 20, "lr_all": 0.005, "reg_all": 0.02}
        
        mlflow.log_params(params)

        # 2. Train Model
        algo = SVD(**params)
        algo.fit(trainset)
        predictions = algo.test(testset)
        svd_rmse = surprise.accuracy.rmse(predictions, verbose=False)

        logger.info(f"   ✅ SVD RMSE: {svd_rmse:.4f}")
        mlflow.log_metric("rmse", svd_rmse)

        os.makedirs(os.path.dirname("src/models/svd_model.pkl"), exist_ok=True)
        surprise.dump.dump("src/models/svd_model.pkl", algo=algo)
        logger.info("   💾 Modèle SVD sauvegardé !")

        # Log model file as artifact because surprise is not directly supported by mlflow.sklearn
        # Save reference data (Rating, Prediction) for monitoring
        # Prediction on trainset (approximate 'reference' distribution)
        train_preds = algo.test(trainset.build_testset())
        ref_data = []
        for p in train_preds:
            ref_data.append(
                {
                    "user_id": p.uid,
                    "recipe_id": p.iid,
                    "rating": p.r_ui,
                    "prediction": p.est,
                }
            )

        ref_df = pd.DataFrame(ref_data)
        ref_path = "reference_data.csv"
        ref_df.to_csv(ref_path, index=False)
        mlflow.log_artifact(ref_path, "drift_reference")
        if os.path.exists(ref_path):
            os.remove(ref_path)

        mlflow.log_artifact("src/models/svd_model.pkl", artifact_path="model")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train recommendation models")
    parser.add_argument(
        "--pipeline",
        choices=["rf", "svd"],
        default="rf",
        help="Select which pipeline to train: rf (Random Forest) or svd (Surprise SVD)",
    )
    args = parser.parse_args()
    if args.pipeline == "svd":
        train_svd()
    else:
        train()
