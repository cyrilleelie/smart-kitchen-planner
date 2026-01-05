import pandas as pd
import ast
import re
import os
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.database.models import Base, Recipe, User, Interaction
from src.database.connection import engine

def clean_text(text):
    if not isinstance(text, str):
        return str(text)
    return re.sub(r'[\r\n]+', ' ', text).strip()

def init_database():
    print("🔧 Vérification de la Base de Données...")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # --- BLOC 1 : RECETTES ---
        if session.query(Recipe).count() > 0:
            print("   ✅ Les recettes sont déjà chargées.")
        else:
            print("   🌱 Base vide détectée -> Chargement du Dataset...")
            csv_path = "/app/data/raw/RAW_recipes.csv"
            
        try:
            chunk_size = 5000; limit = 5000; count = 0
            dtype_dict = {'name': str, 'tags': str, 'description': str, 'minutes': int, 'n_steps': 'Int64'}
            for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype=dtype_dict):
                recipes_buffer = []
                for _, row in chunk.iterrows():
                    try: cal = float(ast.literal_eval(row['nutrition'])[0])
                    except: cal = 0.0
                    ing = row['ingredients'] if 'ingredients' in row else "[]"
                    recipes_buffer.append(Recipe(
                        id=row['id'], name=clean_text(row['name']), minutes=int(row['minutes']),
                        tags=row['tags'], calories=cal, description=clean_text(row['description'])[:500],
                        ingredients=ing
                    ))
                session.add_all(recipes_buffer)
                session.commit()
                count += len(recipes_buffer)
                if count >= limit: break
            print(f"   ✅ {count} recettes insérées.")
        except Exception as e: print(f"   ❌ Erreur CSV : {e}")

        # --- BLOC 2 : UTILISATEUR CORRIGÉ ---
        target_user_id = 1
        existing_user = session.query(User).filter(User.id == target_user_id).first()
        
        if not existing_user:
            print(f"   👤 Création de l'utilisateur ID {target_user_id}...")
            # CORRECTION ICI : username au lieu de name
            user = User(id=target_user_id, username="Chef Cyril") 
            session.add(user)
            session.commit()
            print("   ✅ Utilisateur créé !")
        else:
            print("   ✅ Utilisateur présent.")

if __name__ == "__main__":
    init_database()