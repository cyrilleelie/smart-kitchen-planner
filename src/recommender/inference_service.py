import random
import os
import mlflow.sklearn
import numpy as np
import ast
from sqlalchemy.orm import Session
from src.database.models import Interaction, Recipe
import json
import logging
from src.utils.logging_config import setup_logging
from typing import Any
from src.recommender.profile_builder import UserProfiler
import datetime
from src.recommender.features import extract_explicit_features


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Configuration
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_URI)


class InferenceService:
    """
    Service responsible for loading ML models and generating context-aware recommendations.

    This service integrates with MLflow to load the latest production model and
    uses it to rank recipes based on user profile and current context (meal type, season).

    Attributes:
        db (Session): SQLAlchemy database session
        model (sklearn.base.BaseEstimator): Loaded ML model (RandomForest)
    """

    def __init__(self, db: Session):
        """
        Initialize the InferenceService.

        Args:
            db: Active database session
        """
        self.db = db
        self.model = self._load_model()

    def _load_model(self) -> Any | None:
        """
        Load the latest available model from MLflow.

        Returns:
            Any | None: The loaded scikit-learn model, or None if loading fails.
        """
        logger.info(f"🔄 Connexion MLflow: {MLFLOW_URI}")
        print("🔄 Chargement du modèle de ranking...")
        try:
            experiment = mlflow.get_experiment_by_name("SmartRetail_Context_Ranking")
            if not experiment:
                return None

            client = mlflow.MlflowClient()
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["attribute.start_time DESC"],
                max_results=1,
            )

            if runs:
                latest_run_id = runs[0].info.run_id
                model_uri = f"runs:/{latest_run_id}/model"
                self.model = mlflow.sklearn.load_model(model_uri)
                print(f"✅ Modèle chargé (Run ID: {latest_run_id})")
                return self.model

            # Fallback local
            raise Exception("No MLflow run found")

        except Exception as e:
            print(f"⚠️ Warning MLflow: {e}")
            logger.warning(f"⚠️ Warning MLflow: {e}")

            # Essayons de charger le modèle local
            local_path = "src/models/rf_model.pkl"
            if os.path.exists(local_path):
                import joblib

                try:
                    self.model = joblib.load(local_path)
                    print(f"✅ Modèle local chargé : {local_path}")
                    logger.info(f"✅ Modèle local chargé : {local_path}")
                    return self.model
                except Exception as local_e:
                    logger.error(f"❌ Erreur chargement local: {local_e}")

            return None

    def _parse_vector(self, embedding_data):
        """
        Parse embedding data into numpy array.

        Args:
            embedding_data: String representation or list of floats

        Returns:
            numpy array of float32

        Raises:
            json.JSONDecodeError: If string is not valid JSON
            ValueError: If data cannot be converted to array
        """
        if isinstance(embedding_data, str):
            try:
                parsed = json.loads(embedding_data)
                return np.array(parsed, dtype=np.float32)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse embedding: {e}")
                raise ValueError(f"Invalid embedding format: {embedding_data[:50]}...")
        elif isinstance(embedding_data, list):
            return np.array(embedding_data, dtype=np.float32)
        return np.zeros(384, dtype=np.float32)

    def get_user_vector(self, user_id: int, session: Session):
        likes = (
            session.query(Recipe.embedding)
            .join(Interaction)
            .filter(Interaction.user_id == user_id, Interaction.rating >= 4)
            .all()
        )

        vectors = [self._parse_vector(v[0]) for v in likes]

        if not vectors:
            return np.zeros(384, dtype=np.float32)
        return np.mean(vectors, axis=0).astype(np.float32)

    def _get_explicit_features_vec(self, recipe) -> np.ndarray:
        explicit = extract_explicit_features(recipe)
        return np.array(
            [
                explicit["is_breakfast"],
                explicit["is_dishes"],
                explicit["is_light"],
                explicit["is_winter_comfort"],
                explicit["is_summer_fresh"],
            ],
            dtype=np.float32,
        )

    def recommend(self, user_id: int, n: int = 5) -> list[dict[str, Any]]:
        """
        Generate contextual recommendations for a user.

        Args:
            user_id: ID of the target user
            n: Number of recommendations to return (default: 5)

        Returns:
            List[Dict[str, Any]]: List of recommended recipes with scores.
            Returns empty list if user not found or model error.
        """
        if not self.model:
            logger.error("❌ Modèle non chargé. Impossible de recommander.")
            return []

        # 1. Profil Utilisateur
        user_vector = UserProfiler(self.db).get_weighted_profile(user_id)
        if user_vector is None:
            logger.info("⚠️ Cold Start : Recommandation aléatoire")
            return []  # Le solver gérera le fallback

        # 2. Candidats (Optimisation: on ne score pas TOUT, juste un subset pertinent ou tout si petit)
        # Idéalement : Recherche vectorielle (ANN) d'abord. Ici : Brute-force sur 300 items pour démo.
        candidates = self.db.query(Recipe).limit(300).all()

        # Contexte Actuel
        hour = datetime.datetime.now().hour
        month = datetime.datetime.now().month

        # Vectorisation
        X_pred = []
        valid_candidates = []

        for r in candidates:
            r_vec = self._parse_vector(r.embedding)

            # Features (User + Recipe + Context)
            # [User(384) + Recipe(384) + MealType(1) + Season(1)] = 770 features
            # Simplification ici : on prend la moyenne user+recipe (juste pour l'exemple si le modèle attend ça)
            # ATTENTION : Le modèle a été entraîné sur [UserVec(384) + RecipeVec(384) + Ctx(2)]
            # Il faut matcher EXACTEMENT la structure d'entraînement.

            # ATTENTION : Le modèle s'attend à [User, Recipe, Context, Explicit]

            explicit_features = self._get_explicit_features_vec(r)

            features = np.concatenate(
                [
                    user_vector,
                    r_vec,
                    [self._get_meal_type_feature(hour)],
                    [self._get_season_feature(month)],
                    explicit_features,
                ]
            )

            X_pred.append(features)
            valid_candidates.append(r)

        # Prédiction Batch
        if X_pred:
            try:
                preds = self.model.predict(X_pred)

                # Combine scores
                results = []
                for r, score in zip(valid_candidates, preds):
                    results.append(
                        {
                            "id": r.id,
                            "name": r.name,
                            "score": float(score),
                            "type": "AI_CONTEXT",
                            "recipe": r,
                        }
                    )

                # Tri décroissant
                results.sort(key=lambda x: x["score"], reverse=True)
                return results[:n]
            except Exception as e:
                logger.error(f"❌ Erreur inférence : {e}")
                return []

        return []

    def _get_meal_type_feature(self, hour: int) -> float:
        """0: Breakfast, 1: Lunch/Dinner (Main), 2: Snack"""
        if 5 <= hour < 11:
            return 0.0
        if 15 <= hour < 18:
            return 2.0
        # Lunch (11-15) or Dinner (18+) -> Main Meal (1.0)
        return 1.0

    def _get_season_feature(self, month: int) -> float:
        """0: Winter, 1: Spring, 2: Summer, 3: Autumn"""
        if month in [12, 1, 2]:
            return 0.0
        if month in [3, 4, 5]:
            return 1.0
        if month in [6, 7, 8]:
            return 2.0
        return 3.0

    def rank_recipes(
        self, user_id: int, recipes: list[Recipe], context: dict
    ) -> list[dict[str, Any]]:
        """
        Rank a specific list of recipes given a user context.
        """
        if not self.model:
            return []

        user_vector = UserProfiler(self.db).get_weighted_profile(user_id)
        if user_vector is None:
            return []

        # Extract context or default to current time
        if "meal_type" in context:
            meal_feature = float(context["meal_type"])
        else:
            meal_feature = self._get_meal_type_feature(datetime.datetime.now().hour)

        if "season" in context:
            season_feature = float(context["season"])
        else:
            season_feature = self._get_season_feature(datetime.datetime.now().month)

        X_pred = []
        valid_candidates = []

        for r in recipes:
            try:
                r_vec = self._parse_vector(r.embedding)
                explicit_features = self._get_explicit_features_vec(r)
                features = np.concatenate(
                    [
                        user_vector,
                        r_vec,
                        [meal_feature],
                        [season_feature],
                        explicit_features,
                    ]
                )

                X_pred.append(features)
                valid_candidates.append(r)
            except Exception:
                continue

        if not X_pred:
            return []

        try:
            preds = self.model.predict(X_pred)
            results = []
            for r, score in zip(valid_candidates, preds):
                results.append(
                    {
                        "id": r.id,
                        "score": float(score),
                    }
                )
            # Sort desc
            results.sort(key=lambda x: x["score"], reverse=True)
            return results
        except Exception as e:
            logger.error(f"❌ Erreur rank_recipes : {e}")
            return []

    def _get_calories(self, recipe):
        """Helper pour extraire les calories proprement"""
        try:
            if recipe.nutrition_info:
                # nutrition_info est souvent stocké comme string "['450.5', ...]"
                return float(ast.literal_eval(recipe.nutrition_info)[0])
        except Exception:
            return 0.0
        return 0.0

    def recommend_weekly_batch(
        self,
        user_id: int,
        meal_type: int,
        season: int,
        session: Session,
        n_days=7,
        target_calories=None,
    ):
        """
        Génère un lot de recettes en respectant la cible calorique.
        """
        if not self.model:
            return []

        # 1. On récupère un large pool de candidats
        # On augmente un peu la limite (ex: 1000) pour avoir assez de candidats après filtrage calorique
        candidates = session.query(Recipe).limit(1000).all()
        if not candidates:
            return []

        # --- FILTRAGE CALORIQUE ---
        if target_calories and target_calories > 0:
            min_cal = target_calories * 0.7  # -30%
            max_cal = target_calories * 1.3  # +30%

            # On ne garde que les recettes dans la fourchette (ou celles sans info nutritionnelle pour ne pas bloquer)
            filtered_candidates = []
            for r in candidates:
                cals = self._get_calories(r)
                if cals == 0 or (min_cal <= cals <= max_cal):
                    filtered_candidates.append(r)

            candidates = filtered_candidates

            # Sécurité : Si le filtrage est trop strict et vide la liste, on reprend tout
            if not candidates:
                candidates = session.query(Recipe).limit(100).all()

        user_vec = self.get_user_vector(user_id, session)
        context_features = np.array([meal_type, season], dtype=np.float32)

        X_pred = []
        valid_candidates = []

        # 2. Prédiction de masse (inchangée)
        for recipe in candidates:
            r_vec = self._parse_vector(recipe.embedding)
            explicit_features = self._get_explicit_features_vec(recipe)
            combined = np.concatenate(
                [user_vec, r_vec, context_features, explicit_features]
            )
            X_pred.append(combined)
            valid_candidates.append(recipe)

        if not X_pred:
            return []

        predictions = self.model.predict(np.array(X_pred))

        # 3. Création de la liste triée
        all_results = []
        for i, score in enumerate(predictions):
            all_results.append(
                {"recipe": valid_candidates[i], "score": score, "tag": None}
            )

        all_results.sort(key=lambda x: x["score"], reverse=True)

        # 4. Application de la Stratégie 80/20 (inchangée)
        n_perf = max(1, int(n_days * 0.8))
        n_disco = n_days - n_perf

        final_selection = []

        # A. Sélection PERFORMANCE
        perf_pool = all_results[:n_perf]
        for item in perf_pool:
            item["tag"] = "Performance"
            final_selection.append(item)

        # B. Sélection DÉCOUVERTE
        start_idx = int(len(all_results) * 0.10)
        end_idx = int(len(all_results) * 0.40)

        if start_idx >= end_idx:
            discovery_pool = all_results[n_perf : n_perf + n_disco]
        else:
            discovery_pool = all_results[start_idx:end_idx]

        if discovery_pool:
            discovery_pool = [x for x in discovery_pool if x not in final_selection]
            chosen_disco = random.sample(
                discovery_pool, min(len(discovery_pool), n_disco)
            )
            for item in chosen_disco:
                item["tag"] = "Découverte"
                final_selection.append(item)

        random.shuffle(final_selection)
        return final_selection[:n_days]
