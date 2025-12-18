import json
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import Recipe

def generate_embeddings():
    print("🧠 Chargement du modèle NLP (Sentence-BERT)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    engine = create_engine("sqlite:///smartretail.db")
    
    with Session(engine) as session:
        print("📂 Récupération de TOUTES les recettes pour forcer la vectorisation...")
        
        # CHANGEMENT ICI : On prend tout, sans filtre conditionnel hasardeux
        recipes = session.query(Recipe).all() 
        
        print(f"🔄 Vectorisation de {len(recipes)} recettes en cours...")
        print("   (Cela va prendre environ 60-90 secondes, patientez...)")
        
        texts = []
        for r in recipes:
            # Concaténation Nom + Tags pour le contexte
            tags_str = " ".join(r.tags) if r.tags else ""
            full_text = f"{r.name} {tags_str}"
            texts.append(full_text)
        
        # Encodage
        embeddings = model.encode(texts, show_progress_bar=True)
        
        print("💾 Sauvegarde en base...")
        for i, recipe in enumerate(recipes):
            recipe.embedding = embeddings[i].tolist()
        
        session.commit()
        print(f"✅ Terminé ! {len(recipes)} recettes ont été mises à jour.")

if __name__ == "__main__":
    generate_embeddings()