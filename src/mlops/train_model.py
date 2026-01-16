import sys
import os
import pandas as pd
import numpy as np
import random
from sqlalchemy.orm import Session
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error
import mlflow
import mlflow.sklearn
import ast
from dotenv import load_dotenv
import logging
from src.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration des chemins
sys.path.append(os.getcwd())

from src.database.connection import engine  # noqa: E402
from src.database.models import Interaction, Recipe  # noqa: E402

# --- CONFIGURATION MLOPS ---
MLFLOW_URI = "http://mlflow:5000"
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
        if (is_breakfast_kw or is_snack_kw) and "dessert" not in text:
            penalty -= 2.0

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
        # On sauve X_train (features) + y_train (target réelle)
        # C'est ce que le modèle "connaît" par coeur.

        # Note: X_train est un numpy array, on le convertit en DF pour plus de clarté
        # Idéalement, nomme tes colonnes si tu peux, sinon des indices suffisent
        ref_df = pd.DataFrame(X_train)
        ref_df["target"] = y_train

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
        logger.info("   💾 Modèle sauvegardé !")


if __name__ == "__main__":
    train()
