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
from src.recommender.features import extract_explicit_features  # noqa: E402


MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
EXPERIMENT_NAME = "SmartRetail_Context_Ranking"

# --- CONSTANTES DE STATUT ---
STATUS_OK = 0  # Pas de drift
STATUS_DRIFT = 1  # Drift détecté
STATUS_SKIPPED = 2  # Pas assez de données / Pas de référence

# --- SEUILS DE VALIDATION VOLUME ---
MIN_SAMPLES_CURRENT = 100  # Nombre minimum de logs pour une analyse significative
MIN_VOLUME_RATIO = (
    0.1  # Ratio min curr/ref (évite de comparer distributions déséquilibrées)
)


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


def compute_cosine_similarity(vec_a, vec_b):
    """
    Calcule la similarité cosinus entre deux vecteurs.
    Utilisé pour réduire les 768 dimensions d'embeddings en une métrique unique
    plus pertinente pour la détection de drift.
    """
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


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
                    # RF Logic - Cosine Similarity Approach
                    # Au lieu de 770 features (embeddings + context), on utilise:
                    # - cosine_similarity: similarité user↔recipe (plus pertinent sémantiquement)
                    # - meal_type: contexte catégoriel
                    # - season: contexte catégoriel
                    # - prediction: score prédit

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
                        r_vec_cached = (
                            parse_vector(r_obj.embedding) if r_obj else np.zeros(384)
                        )
                        # Extract explicit features
                        r_ex_cached = (
                            extract_explicit_features(r_obj)
                            if r_obj
                            else {
                                "is_breakfast": 0,
                                "is_dishes": 0,
                                "is_light": 0,
                                "is_winter_comfort": 0,
                                "is_summer_fresh": 0,
                            }
                        )
                        recipe_cache[r_id] = (r_vec_cached, r_ex_cached)

                    r_vec, r_explicit = recipe_cache[r_id]

                    # Calcul de la similarité cosinus (réduit 768D → 1D)
                    cosine_sim = compute_cosine_similarity(u_vec, r_vec)

                    # Construction du row avec features réduites + explicites
                    row_dict = {
                        "cosine_similarity": cosine_sim,
                        "meal_type": float(meal),
                        "season": float(season),
                        "is_breakfast": float(r_explicit["is_breakfast"]),
                        "is_dishes": float(r_explicit["is_dishes"]),
                        "is_light": float(r_explicit["is_light"]),
                        "is_winter": float(
                            r_explicit["is_winter_comfort"]
                        ),  # Map to simplified name used in train_model
                        "is_summer": float(r_explicit["is_summer_fresh"]),
                    }

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

    # Vérification du volume minimum de données courantes
    if len(curr_df) < MIN_SAMPLES_CURRENT:
        print(
            f"   ⚠️ Volume insuffisant : {len(curr_df)} < {MIN_SAMPLES_CURRENT} échantillons."
        )
        print("   ⏭️ SKIP : Pas assez de données récentes pour une analyse fiable.")
        return STATUS_SKIPPED

    # Vérification du ratio de volume (évite les comparaisons déséquilibrées)
    volume_ratio = len(curr_df) / len(ref_df)
    if volume_ratio < MIN_VOLUME_RATIO:
        print(
            f"   ⚠️ Déséquilibre de volume : ratio = {volume_ratio:.2%} < {MIN_VOLUME_RATIO:.0%}"
        )
        print(f"      ({len(curr_df)} courant vs {len(ref_df)} référence)")
        print("   ⏭️ SKIP : Baisse d'activité détectée, pas de drift réel.")
        return STATUS_SKIPPED

    print(
        f"   📊 Volume : {len(ref_df)} (Ref: J-14->J-7) vs {len(curr_df)} (Curr: J-7->J-0)"
    )

    # 4. Config & Mapping
    report_metrics = []

    if model_type == "rf":
        # RANDOM FOREST STRATEGY - Cosine Similarity Approach
        from evidently.pipeline.column_mapping import ColumnMapping

        # Features à monitorer : Cosine Sim + Contexte + Explicites + Prediction
        categorical_features = [
            "meal_type",
            "season",
            "is_breakfast",
            "is_dishes",
            "is_light",
            "is_winter",
            "is_summer",
        ]
        numerical_features = ["cosine_similarity", "prediction"]

        features_to_monitor = numerical_features + categorical_features

        available = [
            c
            for c in features_to_monitor
            if c in ref_df.columns and c in curr_df.columns
        ]

        if not available:
            print("   ⚠️ Aucune feature commune trouvée.")
            return STATUS_SKIPPED

        # Select data
        ref_data = ref_df[available].copy()
        curr_data = curr_df[available].copy()

        print(f"   📉 Features analysées : {available}")

        # Définition du mapping pour Evidently
        column_mapping = ColumnMapping()
        column_mapping.numerical_features = [
            c for c in numerical_features if c in available
        ]
        column_mapping.categorical_features = [
            c for c in categorical_features if c in available
        ]

        # Configuration des tests statistiques par type de feature
        per_column_stattest = {}
        for col in available:
            if col in categorical_features:
                # Catégoriel → Chi-Square
                per_column_stattest[col] = "chisquare"
            else:
                # Numérique (cosine_similarity, prediction) → Wasserstein
                per_column_stattest[col] = "wasserstein"

        # Add DatasetDriftMetric (Summary)
        # Seuil 5% sur les tests individuels
        # Seuil 25% sur le nombre de colonnes (drift_share) :
        #   Avec 9 colonnes, il suffit que 2-3 colonnes driftent pour déclencher l'alerte.
        #   C'est nécessaire car les features sont corrélées (ex: meal_type + is_breakfast).
        report_metrics.append(
            DatasetDriftMetric(
                columns=available,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.05,
                drift_share=0.25,
            )
        )

        # Add DataDriftTable for detailed view
        report_metrics.append(
            DataDriftTable(
                columns=available,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.05,
            )
        )

    elif model_type == "svd":
        # SVD STRATEGY (Predictions & Target)

        # Pas besoin de ColumnMapping pour SVD (features numériques uniquement)
        column_mapping = None

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
        # Seuil 10% (plus tolérant que RF car ratings sont plus stables)
        # Seuil 40% sur drift_share : 1 colonne sur 2 suffit à déclencher l'alerte
        report_metrics.append(
            DatasetDriftMetric(
                columns=available,
                per_column_stattest=per_column_stattest,
                stattest_threshold=0.1,
                drift_share=0.4,
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
        report.run(
            reference_data=ref_data,
            current_data=curr_data,
            column_mapping=column_mapping,
        )
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
