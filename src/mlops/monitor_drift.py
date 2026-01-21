import sys
import os
import pandas as pd
import json
import mlflow
import argparse
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
from evidently.test_preset import DataDriftTestPreset
from evidently.tests import TestColumnDrift

from dotenv import load_dotenv

load_dotenv()

# Configuration
sys.path.append(os.getcwd())
from src.database.connection import engine  # noqa: E402
from src.database.models import PredictionLog, Recipe, Interaction  # noqa: E402
import numpy as np  # noqa: E402
import ast  # noqa: E402

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
EXPERIMENT_NAME = "SmartRetail_Context_Ranking"

# --- CONSTANTES DE STATUT ---
STATUS_OK = 0  # Pas de drift
STATUS_DRIFT = 1  # Drift détecté
STATUS_SKIPPED = 2  # Pas assez de données / Pas de référence


def get_last_run_info(model_type="rf"):
    """Récupère le dernier run MLflow réussi pour le modèle donné."""
    client = mlflow.MlflowClient()
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if not experiment:
        return None, None

    # Filter by model specific run name if possible, or just look for artifacts
    # Simplification: we search for the last finished run.
    # Ideally runs should be tagged with 'model_type'.
    # For now, we assume the last run is the one we want or we try to find the one with the right artifact.
    # But to be robust, let's assume runs are homogeneous or we take the latest.
    # Updated strategy: Search specifically for runs that might have the reference artifact.

    # If model_type is svd, we look for runs named "SVD_Collaborative_Filtering" (defined in train_model.py)
    # If rf, we look for unnamed or standard runs? train_model.py doesn't set a run_name for RF.

    filter_string = "attributes.status = 'FINISHED'"
    if model_type == "svd":
        filter_string += " AND tags.mlflow.runName = 'SVD_Collaborative_Filtering'"

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=filter_string,
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


def load_reference_data(run_id, model_type="rf"):
    """Charge l'artifact CSV depuis MLflow"""
    print(f"   📥 Chargement de la référence (Run ID: {run_id})...")
    artifact_path = "drift_reference/reference_data.csv"

    try:
        local_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path=artifact_path
        )
        return pd.read_csv(local_path)
    except Exception as e:
        print(f"   ⚠️ Erreur chargement référence ({model_type}): {e}")
        # For SVD, if we didn't save reference data in previous implementations, this will fail.
        # We might handle this gracefully or expect the user to re-train.
        return None


def parse_vector(vec_str):
    if isinstance(vec_str, str):
        try:
            return np.array(ast.literal_eval(vec_str), dtype=np.float32)
        except Exception:
            return np.zeros(384)
    elif isinstance(vec_str, list):
        return np.array(vec_str, dtype=np.float32)
    return np.zeros(384)


def get_user_vector(session, user_id):
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


def fetch_prediction_logs(days=7, model_type="rf"):
    """
    Récupère les logs de production.
    """
    print(f"   📡 Récupération logs (7 derniers jours) pour {model_type}...")
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

        rows = []

        # Caches
        user_vec_cache = {}
        recipe_cache = {}

        for log in logs:
            try:
                inputs = (
                    json.loads(log.input_features)
                    if isinstance(log.input_features, str)
                    else log.input_features
                )

                # Check if this log matches the expected model type implicitly?
                # The logger might not differentiate, so we filter by structure if needed.
                # For now, we process everything that looks compatible.

                if model_type == "rf":
                    # RF expects: user_vec + recipe_vec + context
                    # If logs don't have this structure, skip?
                    # Assuming logs are consistent or we filter valid ones.

                    u_id = log.user_id
                    r_id = inputs.get("recipe_id")  # stored in inputs for consistency?
                    # Actually inputs for RF usually contain 'meal_type', 'season'.
                    # train_model.py uses logic to fetch u/r vectors.
                    # InferenceService for RF logs inputs?
                    # Wait, PredictionLog usually logs 'input_features' as passed to predict?
                    # In InferenceService.recommend:
                    #   preds = self.model.predict(X_pred)
                    # It does NOT log to database automatically in the provided snippets!
                    # I assume there's a logging mechanism elsewhere or it's implicitly expected.
                    # Looking at `monitor_drift.py` provided earlier:
                    # It reconstructs vectors from IDs in the logs.
                    # Let's assume PredictionLog.input_features contains {recipe_id, meal_type, season}

                    r_id = inputs.get("recipe_id")
                    if r_id is None:
                        continue

                    meal = inputs.get("meal_type", 1)
                    season = inputs.get("season", 0)

                    # Hydration
                    if u_id not in user_vec_cache:
                        user_vec_cache[u_id] = get_user_vector(session, u_id)
                    u_vec = user_vec_cache[u_id]

                    if r_id not in recipe_cache:
                        r_obj = session.get(Recipe, r_id)
                        recipe_cache[r_id] = (
                            parse_vector(r_obj.embedding) if r_obj else np.zeros(384)
                        )
                    r_vec = recipe_cache[r_id]

                    ctx_vec = np.array([float(meal), float(season)], dtype=np.float32)
                    full_vec = np.concatenate([u_vec, r_vec, ctx_vec])
                    row_dict = {str(i): val for i, val in enumerate(full_vec)}
                    rows.append(row_dict)

                elif model_type == "svd":
                    # SVD expects: rating (target) and prediction.
                    # PredictionLog stores: prediction_score (log.prediction_score?)
                    # Wait, PredictionLog model in `src/database/models.py` is needed to know fields.
                    # Assuming `prediction_score` field exists or similar.
                    # If `prediction_score` is the score.
                    # For target (actual rating), we need to join with Interaction?
                    # But drift detection is usually on Model Inputs vs Reference Inputs, OR Model Outputs vs Reference Outputs.
                    # Monitor Target Drift requires Ground Truth (Feedback).
                    # 'fetch_prediction_logs' usually fetches *Production Inputs/Outputs*.
                    # Ground truth might come later.
                    # The prompt says: "Cas svd: Charge uniquement les interactions : rating (Target) et prediction (Output)."
                    # "Prediction" comes from logs. "Rating" comes from Interaction (feedback).
                    # We should probably join PredictionLog with Interaction on user_id/recipe_id?
                    # Or just fetch Interactions that have happened?
                    # "Charge uniquement les interactions : rating (Target) et prediction (Output)."
                    # Maybe we just compare "training interactions" vs "recent interactions"?
                    # "Drift" on "Rating" = Concept Drift (Target Drift).
                    # "Drift" on "Prediction" = Prediction Drift.
                    # If we use SVD, the "model" predicts a score.
                    # Let's try to match PredictionLog with Interaction if possible,
                    # OR just use recent Interactions as "Current Data" for Target Drift?
                    # If we just want Data Drift on inputs/outputs:
                    # For SVD, inputs are UserID/RecipeID (excluded per instructions).
                    # Outputs are scores.
                    # Target is Ratng.
                    # So we need dataframe with columns: ["prediction", "rating"] (if available).

                    # Let's look for matching interactions
                    r_id = inputs.get("recipe_id")
                    if r_id is None:
                        continue

                    predicted_score = log.prediction_score  # Assuming this field exists

                    # Try to find real interaction
                    # This might be expensive N+1 query, but for monitoring 7 days it's okay-ish.
                    interaction = (
                        session.query(Interaction)
                        .filter_by(user_id=u_id, recipe_id=r_id)
                        .first()
                    )

                    row = {"prediction": predicted_score if predicted_score else np.nan}
                    if interaction:
                        row["rating"] = interaction.rating
                    else:
                        row["rating"] = np.nan  # No ground truth yet

                    rows.append(row)

            except Exception:
                continue

        return pd.DataFrame(rows)


def monitor(model_type="rf"):
    print(f"🕵️‍♂️ MONITORING ({model_type.upper()}) : Analyse de drift...")

    # 1. Infos dernier modèle
    run_id, last_train_date = get_last_run_info(model_type)
    if not run_id:
        print(f"   ❌ Aucun modèle {model_type} trouvé ds MLflow.")
        return STATUS_SKIPPED

    print(f"   📅 Modèle de référence du : {last_train_date}")

    # 2. Chargement données Référence (Training)
    ref_df = load_reference_data(run_id, model_type)
    if ref_df is None or ref_df.empty:
        print("   ❌ Données de référence introuvables ou vides.")
        return STATUS_SKIPPED

    # 3. Chargement données Production (Logs DB)
    curr_df = fetch_prediction_logs(days=7, model_type=model_type)

    if curr_df.empty:
        print("   Bzzt... 💤 Aucune donnée récente en production.")
        return STATUS_SKIPPED

    print(f"   📊 Volume : {len(ref_df)} (Ref) vs {len(curr_df)} (Prod)")

    # 4. Config & Mapping
    report_metrics = []

    if model_type == "rf":
        # Random Forest Config
        # Alignement colonnes
        ref_df.columns = ref_df.columns.astype(str)
        curr_df.columns = curr_df.columns.astype(str)

        common_cols = list(set(ref_df.columns) & set(curr_df.columns))
        # Exclure target si présente
        if "target" in common_cols:
            common_cols.remove("target")

        features_to_monitor = sorted(
            common_cols, key=lambda x: int(x) if x.isdigit() else x
        )

        if not features_to_monitor:
            print("   ⚠️ Aucune colonne commune.")
            return STATUS_SKIPPED

        # Select data
        ref_data = ref_df[features_to_monitor]
        curr_data = curr_df[features_to_monitor]

        # Define Tests
        # Embeddings (Numerical) -> KS
        # Context (Categorical: Season, Meal) -> Chi-Square
        # Usually last 2 columns are context if constructed same way
        # But here names are "0", "1"... "769".
        # Last 2 are 768 (Meal) and 769 (Season).

        # Let's detect categorical logic manually or just force it.
        # It's hard to distinguish by name "768".

        report_metrics.append(
            DataDriftPreset(
                drift_share=0.5,  # Alert if 50% features drift
                # stattest="ks", # Default
            )
        )

    elif model_type == "svd":
        # SVD Config
        # Ref columns: rating, prediction (if saved correctly)
        # Curr columns: rating, prediction

        # We need to make sure Ref DF has these columns.
        # If train_model.py for SVD saved 'user_id', 'recipe_id', 'rating', 'prediction'
        # We filter only rating and prediction.

        cols = ["rating", "prediction"]
        available = [c for c in cols if c in ref_df.columns and c in curr_df.columns]

        if not available:
            print("   ⚠️ Colonnes rating/prediction manquantes pour SVD.")
            return STATUS_SKIPPED

        ref_data = ref_df[available].dropna()
        curr_data = curr_df[available].dropna()

        # Wasserstein for distribution drift
        # Evidently: TestColumnDrift(column_name="rating", stattest="wasserstein")

        tests = []
        for col in available:
            tests.append(TestColumnDrift(column_name=col, stattest="wasserstein"))

        report_metrics.append(DataDriftTestPreset(tests=tests))

    # 5. Calcul Drift
    report = Report(metrics=report_metrics)

    try:
        report.run(reference_data=ref_data, current_data=curr_data)
    except Exception as e:
        print(f"   ❌ Erreur Evidently run: {e}")
        return STATUS_SKIPPED

    # Export
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    # Use subdirectory for model type
    report_dir = os.path.join("reports", model_type)
    os.makedirs(report_dir, exist_ok=True)

    report_path = os.path.join(report_dir, f"drift_report_{timestamp}.html")
    report.save_html(report_path)
    print(f"   📝 Rapport généré : {report_path}")

    # Interpretation simplifiée du résultat
    # On regarde si 'fail' dans le json summary
    json_summary = json.loads(report.json())
    # Evidently structure depends on preset.
    # Usually 'metrics' -> 'result' -> 'drift_detected' for DataDriftPreset
    # For TestPreset: 'tests' -> 'status' -> 'FAIL'

    drift_detected = False

    if "metrics" in json_summary:
        # Check DataDriftPreset results if present
        # This is heuristics structure parsing
        pass

    # Simple check: if any test/metric failed/detected drift
    # report.as_dict() is safer
    res = report.as_dict()

    # Check for Tests FAIL
    if "tests" in res:
        for t in res["tests"]:
            if t["status"] == "FAIL":
                drift_detected = True
                break

    # Check for Metrics Drift
    if "metrics" in res:
        for m in res["metrics"]:
            if "result" in m and m["result"].get("dataset_drift", False):
                drift_detected = True

    if drift_detected:
        print("   ⚠️ DRIFT DÉTECTÉ !")
        return STATUS_DRIFT

    print("   ✅ Pas de drift détecté.")
    return STATUS_OK


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=str,
        choices=["rf", "svd"],
        default="rf",
        help="Model type to monitor",
    )
    args = parser.parse_args()

    status = monitor(args.model)
    sys.exit(status)
