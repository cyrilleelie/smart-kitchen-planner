import sys
import os
import pandas as pd
import mlflow
from datetime import datetime
from sqlalchemy.orm import Session
from evidently.report import Report
from evidently.metric_preset import TargetDriftPreset

# Configuration
sys.path.append(os.getcwd())
from src.database.connection import engine
from src.database.models import Interaction
from dotenv import load_dotenv

load_dotenv()

MLFLOW_URI = "http://mlflow:5000"
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


def fetch_new_data_since(last_training_date):
    """Récupère les interactions APRÈS le dernier entraînement."""
    print(f"   📡 Récupération des interactions depuis le {last_training_date}...")
    with Session(engine) as session:
        results = (
            session.query(Interaction.rating)
            .filter(Interaction.date > last_training_date)
            .order_by(Interaction.date.asc())
            .all()
        )
        if not results:
            return pd.DataFrame()
        data = [{"target": r.rating} for r in results]
        return pd.DataFrame(data)


def monitor():
    print("🕵️‍♂️ MONITORING : Analyse cumulative...")

    # 1. Infos dernier modèle
    run_id, last_date = get_last_run_info()
    if not run_id:
        print("   ❌ Aucun modèle précédent trouvé.")
        return STATUS_SKIPPED

    print(f"   📅 Dernier entraînement : {last_date}")

    # 2. Chargement données
    ref_df = load_reference_data(run_id)
    curr_df = fetch_new_data_since(last_date)

    if ref_df is None:
        return STATUS_SKIPPED

    if curr_df.empty:
        print("   💤 Aucune nouvelle donnée depuis le dernier entraînement.")
        return STATUS_SKIPPED

    if len(curr_df) < 50:
        print(f"   ⏳ Pas assez de données ({len(curr_df)}/50) pour un test fiable.")
        return STATUS_SKIPPED

    # 3. Analyse Evidently
    drift_report = Report(
        metrics=[TargetDriftPreset(stattest="ks", stattest_threshold=0.05)]
    )
    drift_report.run(reference_data=ref_df, current_data=curr_df)

    # 4. Export & Résultats
    os.makedirs("reports", exist_ok=True)

    # Archivage
    timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    report_filename = f"drift_report_{timestamp}.html"
    drift_report.save_html(os.path.join("reports", report_filename))
    drift_report.save_html(os.path.join("reports", "drift_report_latest.html"))

    metrics = drift_report.as_dict()
    drift_detected = metrics["metrics"][0]["result"]["drift_detected"]
    p_value = metrics["metrics"][0]["result"].get("p_value", 0.0)

    print(f"   📊 Résultat KS-Test : Drift={drift_detected} (P-Value: {p_value:.4f})")

    if drift_detected:
        print("   🚨 DRIFT CONFIRMÉ !")
        return STATUS_DRIFT
    else:
        print("   ✅ RAS. Distribution stable.")
        return STATUS_OK


if __name__ == "__main__":
    status = monitor()
    sys.exit(status)
