import sys
import os
import time
from src.mlops.monitor_drift import monitor, STATUS_DRIFT
from dotenv import load_dotenv

# Chargement environnement
load_dotenv()

# Configuration des chemins
sys.path.append(os.getcwd())

# Import des modules métiers
from src.mlops.train_model import train  # noqa: E402


def run_pipeline(model_type="rf"):
    print(f"🤖 ORCHESTRATEUR ({model_type}) : Démarrage...")
    print("==================================================")

    # 1. Lancer le Monitoring
    drift_status = monitor(model_type=model_type)

    if drift_status == STATUS_DRIFT:
        print("\n⚠️  ALERTE : Dérive confirmée par le monitoring.")
        print("🔄 DÉCISION : Lancement immédiat du réentraînement...")
        print("--------------------------------------------------")

        try:
            # 2. Lancer l'entraînement
            # Note: train() function in train_model.py doesn't accept args directly,
            # but we can call the specific function or update train_model to expose a cleaner API.
            # train_model.py has `train()` (RF) and `train_svd()` (SVD).

            if model_type == "rf":
                train()
            elif model_type == "svd":
                from src.mlops.train_model import train_svd

                train_svd()
            else:
                print(f"Unknown model type: {model_type}")
                return

            print("\n✅ ORCHESTRATEUR : Cycle de réentraînement terminé avec succès.")
            print("   -> Le nouveau modèle est enregistré dans MLflow.")
            print("   -> La nouvelle référence de données est à jour.")

        except Exception as e:
            print(f"\n❌ ERREUR CRITIQUE lors de l'entraînement : {e}")
            sys.exit(1)

    else:
        print("\n✅ STATUS : Le modèle est sain. Aucune action requise.")
        print("   -> On continue de surveiller.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, choices=["rf", "svd"], default="rf")
    args = parser.parse_args()

    # On mesure le temps d'exécution total
    start_time = time.time()
    run_pipeline(model_type=args.model)
    duration = time.time() - start_time
    print(f"⏱️  Temps d'exécution total : {duration:.2f} secondes")
