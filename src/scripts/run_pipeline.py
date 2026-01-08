import sys
import os
from dotenv import load_dotenv # 1. On importe dotenv

# 2. ON CHARGE L'ENVIRONNEMENT IMMÉDIATEMENT
# Avant même d'importer la database ou d'autres modules du projet
load_dotenv() 

# Ajout du root au path pour les imports
sys.path.append(os.getcwd())

# 3. Maintenant on peut importer le reste, l'engine sera créé avec la bonne URL
from src.database.connection import engine
from sqlalchemy.orm import Session
from src.data_engineering.processor import DataPipeline
from src.recommender.vectorizer import generate_recipe_embeddings

def main():
    print("🎬 --- DÉBUT DU PIPELINE GLOBAL ---")
    
    # Vérification visuelle
    print(f"🔍 DEBUG : URL détectée par le pipeline -> {engine.url}")

    # ÉTAPE 1 : Pipeline TF-IDF
    with Session(engine) as db:
        pipeline = DataPipeline(db)
        pipeline.run_pipeline()
    
    print("\n-----------------------------------\n")

    # ÉTAPE 2 : Pipeline Embeddings
    generate_recipe_embeddings()
    
    print("🎬 --- FIN DU PIPELINE GLOBAL ---")

if __name__ == "__main__":
    main()