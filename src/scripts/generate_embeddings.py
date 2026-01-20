import sys
import os
from dotenv import load_dotenv

# 1. Chargement Environnement
load_dotenv()
sys.path.append(os.getcwd())

from src.database.connection import engine  # noqa: E402

# On ne garde que l'import utile
from src.recommender.vectorizer import generate_recipe_embeddings  # noqa: E402


def main():
    print("🎬 --- DÉBUT DE LA VECTORISATION ---")
    print("   (Script: generate_embeddings.py)")

    # Vérification visuelle
    print(f"🔍 DEBUG : URL Base de données -> {engine.url}")

    # ÉTAPE UNIQUE : Calcul des Embeddings pour les recettes sans vecteur
    generate_recipe_embeddings()

    print("🎬 --- FIN DE LA VECTORISATION ---")


if __name__ == "__main__":
    main()
