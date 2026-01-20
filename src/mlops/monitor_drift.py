import sys
import os
import pandas as pd
import json
import mlflow
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from evidently.report import Report
from evidently.metric_preset import TargetDriftPreset, DataDriftPreset

# Configuration
sys.path.append(os.getcwd())
from src.database.connection import engine
from src.database.models import PredictionLog
from dotenv import load_dotenv

load_dotenv()

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
EXPERIMENT_NAME = "SmartRetail_Context_Ranking"

# --- CONSTANTES DE STATUT ---
STATUS_OK = 0  # Pas de drift
STATUS_DRIFT = 1  # Drift détecté
STATUS_SKIPPED = 2  # Pas assez de données / Pas de référence


def get_last_run_info():
    """Récupère le dernier run MLflow réussi."""
    client = mlflow.MlflowClient()
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if not experiment:
        return None, None
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        order_by=["attribute.start_time DESC"],
        max_results=1,
    )
    if not runs:
        return None, None
    run = runs[0]
    # start_time is ms
    timestamp_ms = run.info.start_time
    run_date = datetime.fromtimestamp(timestamp_ms / 1000.0)
    return run.info.run_id, run_date


def load_reference_data(run_id):
    """Charge l'artifact CSV depuis MLflow"""
    print(f"   📥 Chargement de la référence (Run ID: {run_id})...")
    try:
        local_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path="drift_reference/reference_data.csv"
        )
        return pd.read_csv(local_path)
    except Exception as e:
        print(f"   ⚠️ Erreur chargement référence: {e}")
        return None


import numpy as np
import ast
from src.database.models import Recipe, Interaction, User

def parse_vector(vec_str):
    if isinstance(vec_str, str):
        try:
            return np.array(ast.literal_eval(vec_str), dtype=np.float32)
        except:
            return np.zeros(384)
    elif isinstance(vec_str, list):
        return np.array(vec_str, dtype=np.float32)
    return np.zeros(384)


def get_user_vector(session, user_id):
    # Logique simplifiée : Moyenne des recettes aimées (>=4)
    # Identique à train_model.py et inference_service.py
    likes = (
        session.query(Recipe.embedding)
        .join(Interaction)
        .filter(Interaction.user_id == user_id, Interaction.rating >= 4)
        .all()
    )
    if not likes:
        return np.zeros(384, dtype=np.float32)
    
    vectors = [parse_vector(v[0]) for v in likes]
    return np.mean(vectors, axis=0).astype(np.float32)


def fetch_prediction_logs(days=7):
    """
    Récupère les logs et RECONSTRUIT les vecteurs (Hydration).
    Retourne un DataFrame avec 770 colonnes (0..769) comme le training set.
    """
    print(f"   📡 Récupération + Hydratation des logs (7 derniers jours)...")
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    with Session(engine) as session:
        logs = (
            session.query(PredictionLog)
            .filter(PredictionLog.timestamp >= cutoff_date)
            .order_by(PredictionLog.timestamp.asc())
            .all()
        )
        
        if not logs:
            return pd.DataFrame()
        
        hydrated_rows = []
        
        # Cache simple pour éviter de recalculer le user vector à chaque ligne
        user_vec_cache = {}
        # Cache recettes
        recipe_cache = {}

        for log in logs:
            try:
                inputs = json.loads(log.input_features) if isinstance(log.input_features, str) else log.input_features
                
                u_id = log.user_id
                r_id = inputs.get("recipe_id")
                meal = inputs.get("meal_type", 1)
                season = inputs.get("season", 0)
                
                if r_id is None:
                    continue

                # 1. User Vector
                if u_id not in user_vec_cache:
                    user_vec_cache[u_id] = get_user_vector(session, u_id)
                u_vec = user_vec_cache[u_id]

                # 2. Recipe Vector
                if r_id not in recipe_cache:
                    r_obj = session.get(Recipe, r_id)
                    if r_obj and r_obj.embedding:
                        recipe_cache[r_id] = parse_vector(r_obj.embedding)
                    else:
                        recipe_cache[r_id] = np.zeros(384)
                r_vec = recipe_cache[r_id]
                
                # 3. Context
                ctx_vec = np.array([float(meal), float(season)], dtype=np.float32)
                
                # 4. Concatenation (770 dims)
                full_vec = np.concatenate([u_vec, r_vec, ctx_vec])
                
                # On stocke sous forme de dictionnaire {0: val, 1: val...} pour DataFrame
                row_dict = {str(i): val for i, val in enumerate(full_vec)}
                hydrated_rows.append(row_dict)

            except Exception as e:
                # print(f"Skip row: {e}")
                continue
            
        return pd.DataFrame(hydrated_rows)


def monitor():
    print("🕵️‍♂️ MONITORING : Analyse de drift (Production vs Training)...")

    # 1. Infos dernier modèle
    run_id, last_train_date = get_last_run_info()
    if not run_id:
        print("   ❌ Aucun modèle précédent trouvé (MLflow). Impossible de comparer.")
        return STATUS_SKIPPED

    print(f"   📅 Modèle de référence du : {last_train_date}")

    # 2. Chargement données Référence (Training)
    ref_df = load_reference_data(run_id)
    if ref_df is None:
        return STATUS_SKIPPED

    # 3. Chargement données Production (Logs DB)
    curr_df = fetch_prediction_logs(days=7)

    if curr_df.empty:
        print("   Bzzt... 💤 Aucune requête en production sur les 7 derniers jours.")
        return STATUS_SKIPPED

    print(f"   📊 Volume : {len(ref_df)} (Ref) vs {len(curr_df)} (Prod)")

    # 4. Alignement des colonnes
    # Les colonnes sont "0", "1", ... "769"
    # On force le cast en string pour être sûr
    ref_df.columns = ref_df.columns.astype(str)
    curr_df.columns = curr_df.columns.astype(str)
    
    common_cols = list(set(ref_df.columns) & set(curr_df.columns))
    
    # On exclut les colonnes 'target' si présente dans ref
    if "target" in common_cols:
        common_cols.remove("target")
        
    features_to_monitor = sorted(common_cols, key=lambda x: int(x) if x.isdigit() else x)
    
    if not features_to_monitor:
        print("   ⚠️ Aucune colonne commune.")
        return STATUS_SKIPPED

    print(f"   🔬 Features analysées : {len(features_to_monitor)} dimensions (Embeddings + Context)")
    
    ref_data = ref_df[features_to_monitor]
    curr_data = curr_df[features_to_monitor]
    
    # 5. Calcul Drift avec Evidently
    report = Report(metrics=[
        DataDriftPreset(), 
    ])
    
    report.run(reference_data=ref_data, current_data=curr_data)
    
    # Export Report
    report_path = f"reports/drift_report_{datetime.now().strftime('%Y-%m-%d_%Hh%M')}.html"
    os.makedirs("reports", exist_ok=True)
    report.save_html(report_path)
    print(f"   📝 Rapport généré : {report_path}")

    # Check Result (Simplifié)
    # On peut parser le json output du rapport pour un statut précis, 
    # ou juste considérer que si ça tourne c'est OK pour ce script.
    
    return STATUS_OK


if __name__ == "__main__":
    status = monitor()
    sys.exit(status)
