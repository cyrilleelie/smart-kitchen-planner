import json
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

# Import de la connexion centralisée
from src.database.connection import engine
from src.database.models import Recipe

def generate_recipe_embeddings():
    print("🧠 Chargement du modèle NLP (Sentence-BERT)...")
    # Chargement du modèle (téléchargé automatiquement au premier lancement)
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    with Session(engine) as session:
        # 1. Récupérer les recettes sans embedding (ou toutes si on veut forcer la mise à jour)
        # Pour optimiser, on ne prend que celles où embedding est NULL
        recipes = session.query(Recipe).filter(Recipe.embedding == None).all()
        
        total = len(recipes)
        print(f"   -> {total} recettes à vectoriser trouvées.")
        
        if total == 0:
            print("✨ Tout est déjà vectorisé. Rien à faire.")
            return