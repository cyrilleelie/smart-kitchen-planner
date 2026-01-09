import random
import mlflow.sklearn
import numpy as np
import ast
from sqlalchemy.orm import Session
from src.database.models import Interaction, Recipe

# Configuration
MLFLOW_URI = "http://mlflow:5000"
mlflow.set_tracking_uri(MLFLOW_URI)

class InferenceService:
    def __init__(self):
        self.model = None
        self.load_latest_model()

    def load_latest_model(self):
        """Charge le modèle depuis MLflow"""
        print("🔄 Chargement du modèle de ranking...")
        try:
            experiment = mlflow.get_experiment_by_name("SmartRetail_Context_Ranking")
            if not experiment:
                return

            client = mlflow.MlflowClient()
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["attribute.start_time DESC"],
                max_results=1
            )
            
            if runs:
                latest_run_id = runs[0].info.run_id
                model_uri = f"runs:/{latest_run_id}/model"
                self.model = mlflow.sklearn.load_model(model_uri)
                print(f"✅ Modèle chargé (Run ID: {latest_run_id})")
        except Exception as e:
            print(f"❌ Erreur chargement modèle: {e}")

    def _parse_vector(self, embedding_data):
        """Helper pour parser les vecteurs stockés en string ou list"""
        if isinstance(embedding_data, str):
            return np.array(eval(embedding_data), dtype=np.float32)
        elif isinstance(embedding_data, list):
            return np.array(embedding_data, dtype=np.float32)
        return np.zeros(384, dtype=np.float32)

    def get_user_vector(self, user_id: int, session: Session):
        likes = session.query(Recipe.embedding)\
            .join(Interaction)\
            .filter(Interaction.user_id == user_id, Interaction.rating >= 4)\
            .all()
        
        vectors = [self._parse_vector(v[0]) for v in likes]
        
        if not vectors:
            return np.zeros(384, dtype=np.float32)
        return np.mean(vectors, axis=0).astype(np.float32)

    def recommend(self, user_id: int, meal_type: int, season: int, session: Session, top_k=5):
        if not self.model:
            return []

        # Candidats (Optimisation: on pourrait filtrer ici par type de plat si tags dispos)
        candidates = session.query(Recipe).limit(300).all()
        if not candidates: return []

        user_vec = self.get_user_vector(user_id, session)
        context_features = np.array([meal_type, season], dtype=np.float32)
        
        X_pred = []
        valid_candidates = []

        for recipe in candidates:
            r_vec = self._parse_vector(recipe.embedding)
            combined = np.concatenate([user_vec, r_vec, context_features])
            X_pred.append(combined)
            valid_candidates.append(recipe)

        if not X_pred: return []
            
        predictions = self.model.predict(np.array(X_pred))
        
        results = []
        for i, score in enumerate(predictions):
            results.append({"recipe": valid_candidates[i], "score": score})
            
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _get_calories(self, recipe):
        """Helper pour extraire les calories proprement"""
        try:
            if recipe.nutrition_info:
                # nutrition_info est souvent stocké comme string "['450.5', ...]"
                return float(ast.literal_eval(recipe.nutrition_info)[0])
        except:
            return 0.0
        return 0.0

    def recommend_weekly_batch(self, user_id: int, meal_type: int, season: int, session: Session, n_days=7, target_calories=None):
        """
        Génère un lot de recettes en respectant la cible calorique.
        """
        if not self.model:
            return []

        # 1. On récupère un large pool de candidats
        # On augmente un peu la limite (ex: 1000) pour avoir assez de candidats après filtrage calorique
        candidates = session.query(Recipe).limit(1000).all()
        if not candidates: return []

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
            combined = np.concatenate([user_vec, r_vec, context_features])
            X_pred.append(combined)
            valid_candidates.append(recipe)

        if not X_pred: return []
        
        predictions = self.model.predict(np.array(X_pred))
        
        # 3. Création de la liste triée
        all_results = []
        for i, score in enumerate(predictions):
            all_results.append({
                "recipe": valid_candidates[i], 
                "score": score,
                "tag": None
            })
            
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
            discovery_pool = all_results[n_perf:n_perf+n_disco]
        else:
            discovery_pool = all_results[start_idx:end_idx]
        
        if discovery_pool:
            discovery_pool = [x for x in discovery_pool if x not in final_selection]
            chosen_disco = random.sample(discovery_pool, min(len(discovery_pool), n_disco))
            for item in chosen_disco:
                item["tag"] = "Découverte"
                final_selection.append(item)

        random.shuffle(final_selection)
        return final_selection[:n_days]

recommender_service = InferenceService()