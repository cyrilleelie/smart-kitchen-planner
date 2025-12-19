import pandas as pd
import ast
import re
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.database.models import Base, Recipe, User, Interaction
from src.database.connection import engine

def clean_text(text):
    """Nettoie les retours à la ligne et les espaces superflus"""
    if not isinstance(text, str):
        return str(text)
    # Remplace les retours charriot par un espace
    return re.sub(r'[\r\n]+', ' ', text).strip()

def init_database():
    print("🔧 Initialisation Blindée de la Base de Données...")
    
    # 1. DESTRUCTION RADICALE (Via SQL Brut pour être sûr)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS interactions CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS recipes CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        conn.commit()
    print("   💥 Anciennes tables détruites (SQL Brut).")

    # 2. Création propre via SQLAlchemy
    # IMPORTANT: Assurez-vous que models.py a bien 'name = Column(String)' !
    Base.metadata.create_all(bind=engine)
    print("   ✅ Nouvelles tables créées.")

    csv_path = "data/raw/RAW_recipes.csv"
    print(f"   📂 Lecture du fichier : {csv_path}")
    
    chunk_size = 5000 
    limit = 10000 
    
    try:
        with Session(engine) as session:
            count = 0
            # On force les types pour aider Pandas
            dtype_dict = {
                'name': str, 
                'tags': str, 
                'description': str,
                'minutes': int,
                'n_steps': 'Int64' # Permet les NULLs
            }

            for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype=dtype_dict):
                recipes_buffer = []
                
                for _, row in chunk.iterrows():
                    # Parsing sécurisé de la nutrition
                    try:
                        nutri_list = ast.literal_eval(row['nutrition'])
                        calories = float(nutri_list[0])
                    except:
                        calories = 0.0
                    
                    # Nettoyage des textes (Votre intuition sur les newlines !)
                    clean_name = clean_text(row['name'])
                    clean_desc = clean_text(row['description'])

                    recipe = Recipe(
                        name=clean_name,
                        minutes=int(row['minutes']),
                        tags=row['tags'], 
                        calories=calories,
                        description=clean_desc[:500] # On tronque
                    )
                    recipes_buffer.append(recipe)
                
                session.add_all(recipes_buffer)
                session.commit()
                
                count += len(recipes_buffer)
                print(f"      -> {count} recettes insérées...")
                
                if count >= limit:
                    break
            
            # User Test
            test_user = User(username="test_user_01")
            session.add(test_user)
            session.commit()
            print("   👤 Utilisateur de test créé.")

    except FileNotFoundError:
        print("❌ ERREUR : CSV introuvable.")
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE : {e}")

if __name__ == "__main__":
    init_database()