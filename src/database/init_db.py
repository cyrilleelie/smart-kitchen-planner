import pandas as pd
import ast
import re
import os
import sys

# Hack pour trouver les modules src si exécuté en script
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from src.database.models import Base, Recipe, User
from src.database.connection import engine
from src.recommender.cleaner import TagCleaner # <--- On importe le nettoyeur

def clean_text(text):
    if not isinstance(text, str): return str(text)
    return re.sub(r'[\r\n]+', ' ', text).strip()

def init_database():
    print("🔧 INITIALISATION & NETTOYAGE AUTO...")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # 1. Vérification existant
        if session.query(Recipe).count() > 0:
            print("   ✅ La base contient déjà des données. On ne touche à rien.")
            return

        print("   🌱 Base vide -> Chargement et Nettoyage du Dataset...")
        
        # 2. Localisation CSV
        possible_paths = [
            "/app/data/RAW_recipes.csv", "/app/data/raw/RAW_recipes.csv",
            "data/RAW_recipes.csv", "data/raw/RAW_recipes.csv"
        ]
        csv_path = next((p for p in possible_paths if os.path.exists(p)), None)
        
        if not csv_path:
            print("   ❌ ERREUR : CSV introuvable.")
            return

        # 3. Chargement & Nettoyage à la volée
        try:
            chunk_size = 5000; limit = 5000; count = 0
            # On charge tout pour avoir les infos, mais on nettoie les tags
            dtype_dict = {'name': str, 'tags': str, 'description': str, 'minutes': int}
            
            for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype=dtype_dict):
                recipes_buffer = []
                for _, row in chunk.iterrows():
                    try: cal = float(ast.literal_eval(row['nutrition'])[0])
                    except: cal = 0.0
                    
                    ing = row['ingredients'] if isinstance(row['ingredients'], str) else "[]"
                    
                    # --- NETTOYAGE DES TAGS ICI ---
                    raw_tags = row['tags']
                    try:
                        tags_list = ast.literal_eval(raw_tags) if isinstance(raw_tags, str) else []
                        # On ne garde que ce qui n'est pas du bruit
                        clean_tags = [t for t in tags_list if TagCleaner.get_tag_category(t) != "NOISE"]
                        tags_str = str(clean_tags)
                    except:
                        tags_str = "[]"
                    # ------------------------------

                    recipes_buffer.append(Recipe(
                        id=row['id'], 
                        name=clean_text(row['name']), 
                        minutes=int(row['minutes']),
                        tags=tags_str, # On sauvegarde la version PROPRE
                        calories=cal, 
                        description=clean_text(row['description'])[:500],
                        ingredients=ing
                    ))
                
                session.add_all(recipes_buffer)
                session.commit()
                count += len(recipes_buffer)
                if count >= limit: break
                
            print(f"   ✅ {count} recettes importées et nettoyées !")

            # 4. User par défaut
            if session.query(User).count() == 0:
                session.add(User(id=1, username="Chef Cyril"))
                session.commit()
                print("   👤 Utilisateur créé.")

        except Exception as e:
            print(f"   ❌ Erreur import : {e}")

if __name__ == "__main__":
    init_database()