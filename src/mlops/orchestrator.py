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


def run_pipeline():
    print("🤖 ORCHESTRATEUR : Démarrage de la vérification...")
    print("==================================================")

    # 1. Lancer le Monitoring
    # La fonction monitor() renvoie True si Drift détecté, False sinon
    drift_status = monitor()

    if drift_status == STATUS_DRIFT:
        print("\n⚠️  ALERTE : Dérive confirmée par le monitoring.")
        print("🔄 DÉCISION : Lancement immédiat du réentraînement...")
        print("--------------------------------------------------")

        try:
            # 2. Lancer l'entraînement
            train()
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
    # On mesure le temps d'exécution total
    start_time = time.time()
    run_pipeline()
    duration = time.time() - start_time
    print(f"⏱️  Temps d'exécution total : {duration:.2f} secondes")
