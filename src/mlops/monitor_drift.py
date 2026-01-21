import sys
import os
import pandas as pd
import json
import mlflow
import argparse
from datetime import datetime, timedelta


from sqlalchemy.orm import Session
from evidently.report import Report
from evidently.metrics import DatasetDriftMetric, DataDriftTable

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


def fetch_prediction_logs(start_days=7, end_days=0, model_type="rf"):
    """
    Récupère les logs de production sur une fenêtre glissante.
    :param start_days: Début de la fenêtre (jours avant aujourd'hui)
    :param end_days: Fin de la fenêtre (jours avant aujourd'hui, 0 = maintenant)
    """
    print(
        f"   📡 Récupération logs (J-{start_days} à J-{end_days}) pour {model_type}..."
    )

    start_date = datetime.utcnow() - timedelta(days=start_days)
    end_date = datetime.utcnow() - timedelta(days=end_days)

    with Session(engine) as session:
        logs = (
            session.query(PredictionLog)
            .filter(
                PredictionLog.timestamp >= start_date,
                PredictionLog.timestamp < end_date,
            )
            .order_by(PredictionLog.timestamp.asc())
            .all()
        )

        if not logs:
            return pd.DataFrame()

        rows = []
        user_vec_cache = {}
        recipe_cache = {}

        for log in logs:
            try:
                inputs = (
                    json.loads(log.input_features)
                    if isinstance(log.input_features, str)
                    else log.input_features
                )

                if model_type == "rf":
                    # RF Logic (Features + Prediction)

                    # 1. Inputs & Context
                    u_id = log.user_id
                    r_id = inputs.get("recipe_id")
                    if r_id is None:
                        continue

                    meal = inputs.get("meal_type", 1)
                    season = inputs.get("season", 0)

                    # Hydration (Vectors)
                    if u_id not in user_vec_cache:
                        user_vec_cache[u_id] = get_user_vector(session, u_id)
                    u_vec = user_vec_cache[u_id]

                    if r_id not in recipe_cache:
                        r_obj = session.get(Recipe, r_id)
                        recipe_cache[r_id] = (
                            parse_vector(r_obj.embedding) if r_obj else np.zeros(384)
                        )
                    r_vec = recipe_cache[r_id]

                    # Reconstruction [User(384) + Recipe(384) + Context(2)]
                    ctx_vec = np.array([float(meal), float(season)], dtype=np.float32)
                    full_vec = np.concatenate([u_vec, r_vec, ctx_vec])
                    row_dict = {str(i): val for i, val in enumerate(full_vec)}

                    # Add Prediction Score
                    pred_res = (
                        json.loads(log.prediction_result)
                        if isinstance(log.prediction_result, str)
                        else log.prediction_result
                    )
                    predicted_score = pred_res.get("score") if pred_res else None
                    row_dict["prediction"] = (
                        predicted_score if predicted_score is not None else np.nan
                    )

                    rows.append(row_dict)

                elif model_type == "svd":
                    # SVD Logic (Prediction + Rating)
                    u_id = log.user_id
                    r_id = inputs.get("recipe_id")
                    if r_id is None:
                        continue

                    pred_res = (
                        json.loads(log.prediction_result)
                        if isinstance(log.prediction_result, str)
                        else log.prediction_result
                    )
                    predicted_score = pred_res.get("score") if pred_res else None

                    # Try to find real interaction
                    interaction = (
                        session.query(Interaction)
                        .filter_by(user_id=u_id, recipe_id=r_id)
                        .first()
                    )

                    row = {
                        "prediction": (
                            predicted_score if predicted_score is not None else np.nan
                        )
                    }
                    if interaction:
                        row["rating"] = interaction.rating
                    else:
                        row["rating"] = np.nan

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

    # 1. Infos dernier modèle
    run_id, last_train_date = get_last_run_info(model_type)
    if not run_id:
        print(f"   ❌ Aucun modèle {model_type} trouvé ds MLflow.")
        # On continue quand même pour le monitoring "sliding window" purement production ?
        # Non, on garde l'info mais la référence change.

    print(f"   📅 Modèle de référence du : {last_train_date}")

    # 2. Chargement données : SLIDING WINDOW STRATEGY
    # Au lieu de comparer Training vs Prod, on compare Prod(J-14 à J-7) vs Prod(J-7 à J-0).
    # Cela annule le biais de sélection du recommender.

    # Current: [J-7, Today]
    curr_df = fetch_prediction_logs(start_days=7, end_days=0, model_type=model_type)

    # Reference: [J-14, J-7]
    ref_df = fetch_prediction_logs(start_days=14, end_days=7, model_type=model_type)

    if curr_df.empty:
        print("   Bzzt... 💤 Aucune donnée récente en production (J-7 à J-0).")
        return STATUS_SKIPPED

    if ref_df.empty:
        print("   ⚠️ Pas assez d'historique (J-14 à J-7) pour comparaison glissante.")
        # Fallback: On pourrait utiliser le Training set, mais l'utilisateur refuse le biais.
        # Donc on SKIP pour éviter de trigger un réentraînement inutile au démarrage.
        print("   ⏭️ SKIP : En attente de plus de données pour établir une baseline.")
        return STATUS_SKIPPED

    print(
        f"   📊 Volume : {len(ref_df)} (Ref: J-14->J-7) vs {len(curr_df)} (Curr: J-7->J-0)"
    )

    # 4. Config & Mapping
    report_metrics = []

    if model_type == "rf":
        # RANDOM FOREST STRATEGY (Hybrid: Features + Prediction Filtered)

        # A. Filter Reference by Prediction Score (Anti-Selection Bias)
        # WITH SLIDING WINDOW (Prod vs Prod), bias is consistent, so no need to filter.
        # We compare "Recent Recommendations" vs "Previous Recommendations".

        # B. Prepare Feature Columns
        # Ref columns are "0", "1", ..., "769", "target", "prediction"
        ref_df.columns = ref_df.columns.astype(str)
        curr_df.columns = curr_df.columns.astype(str)

        # Identify numerical embeddings (0-767) vs categorical context (768, 769)
        # Total 770 features.
        # 0-767: Embeddings (Numerical) -> KS Test
        # 768: Meal (Categorical) -> Chi-Square
        # 769: Season (Categorical) -> Chi-Square

        features_to_monitor = []
        for i in range(770):
            col_name = str(i)
            if col_name in ref_df.columns and col_name in curr_df.columns:
                features_to_monitor.append(col_name)

        if not features_to_monitor:
            print("   ⚠️ Aucune feature commune trouvée.")
            return STATUS_SKIPPED

        # Select data
        ref_data = ref_df[features_to_monitor].copy()  # Ensure copy
        curr_data = curr_df[features_to_monitor].copy()

        print(
            f"   📉 Features analysées : {len(features_to_monitor)} colonnes (Embeddings + Context)"
        )

        # C. Configure Tests
        # Use DatasetDriftMetric for a summary report instead of individual ColumnDriftMetric
        # Map columns to specific tests using DataDriftOptions

        per_column_stattest = {}
        for col in features_to_monitor:
            idx = int(col)
            if idx >= 768:
                # Categorical (Context)
                ref_data[col] = ref_data[col].astype(str)
                curr_data[col] = curr_data[col].astype(str)
                per_column_stattest[col] = "chisquare"
            else:
                # Numerical (Embeddings)
                per_column_stattest[col] = "ks"

        # Add DatasetDriftMetric (Summary) using explicit per-column tests
        # We set stattest_threshold to 0.01 (1%) instead of 0.05 to reduce false positives
        # due to the natural selection bias of the recommender (Exploration vs Exploitation).
        report_metrics.append(
            DatasetDriftMetric(
                columns=features_to_monitor,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.01,
            )
        )

        # Add DataDriftTable for detailed (but concise) list of drifting features.
        report_metrics.append(
            DataDriftTable(
                columns=features_to_monitor,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.01,
            )
        )

    elif model_type == "svd":
        # SVD STRATEGY (Predictions & Target)

        # A. Filter Reference (Anti-Selection Bias) - NOT NEEDED for Sliding Window

        cols = ["rating", "prediction"]
        available = [c for c in cols if c in ref_df.columns and c in curr_df.columns]

        if not available:
            print(f"   ⚠️ Colonnes {cols} manquantes pour SVD.")
            return STATUS_SKIPPED

        ref_data = ref_df[available].dropna()
        curr_data = curr_df[available].dropna()

        print(f"   📉 Colonnes analysées : {available}")

        per_column_stattest = {}
        for col in available:
            per_column_stattest[col] = "wasserstein"

        # Add DatasetDriftMetric (Summary)
        report_metrics.append(
            DatasetDriftMetric(
                columns=available,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.1,
            )
        )

        # Add DataDriftTable (Detail)
        report_metrics.append(
            DataDriftTable(
                columns=available,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.1,
            )
        )

    # 5. Calcul Drift
    report = Report(metrics=report_metrics)

    try:
        report.run(reference_data=ref_data, current_data=curr_data)
    except Exception as e:
        print(f"   ❌ Erreur Evidently run: {e}")
        return STATUS_SKIPPED

    # Export
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    report_dir = os.path.join("reports", model_type)
    os.makedirs(report_dir, exist_ok=True)

    report_path = os.path.join(report_dir, f"drift_report_{timestamp}.html")
    report.save_html(report_path)
    print(f"   📝 Rapport généré : {report_path}")

    # Interpretation
    drift_detected = False
    res = report.as_dict()

    # Check for Tests FAIL
    if "metrics" in res:
        for m in res["metrics"]:
            # DatasetDriftMetric specific logic
            if m["metric"] == "DatasetDriftMetric":
                n_drifted = m["result"]["number_of_drifted_columns"]
                share_drifted = m["result"]["share_of_drifted_columns"]
                n_features = m["result"]["number_of_columns"]
                # evidently 0.4: 'dataset_drift' boolean.
                drift_detected_metric = m["result"].get(
                    "dataset_drift", m["result"].get("drift_detected", False)
                )

                print("   📊 Détails DatasetDriftMetric :")
                print(
                    f"      - Colonnes en drift : {n_drifted} / {n_features} ({share_drifted:.2%})"
                )
                print(
                    f"      - Statut Global : {'🔴 DRIFT' if drift_detected_metric else '✅ OK'}"
                )

                if drift_detected_metric:
                    drift_detected = True

            # Other metrics (ColumnDriftMetric, etc.)
            elif "result" in m and m["result"].get("drift_detected", False):
                # For DataDriftTable, it interprets drift based on same logic usually
                pass

    if drift_detected:
        print("   ⚠️ DRIFT DÉTECTÉ (Global) !")
        return STATUS_DRIFT

    print("   ✅ Pas de drift détecté (Global).")
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
