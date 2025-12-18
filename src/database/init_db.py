import pandas as pd
import ast
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pathlib import Path

# Import des modèles
from src.database.models import Base, Recipe, User

# --- CONFIGURATION ---
DB_URL = "sqlite:///smartretail.db"
RAW_DATA_PATH = Path("data/raw/RAW_recipes.csv")
LIMIT_RECIPES = 5000  # Mettez None pour tout charger

def parse_list(string_list):
    """Convertit une string "['a', 'b']" en liste python réelle ['a', 'b']"""
    if pd.isna(string_list): return []
    try:
        return ast.literal_eval(string_list)
    except:
        return []

def parse_nutrition(nutrition_str):
    """Extrait les calories et les infos nutritionnelles"""
    if pd.isna(nutrition_str): return 0.0, {}
    try:
        vals = ast.literal_eval(nutrition_str)
        calories = float(vals[0])
        nut_info = {
            "total_fat": vals[1], "sugar": vals[2], "sodium": vals[3],
            "protein": vals[4], "sat_fat": vals[5], "carbs": vals[6]
        }
        return calories, nut_info
    except:
        return 0.0, {}

def init_db():
    print(f"🔧 Initialisation de la base de données : {DB_URL}")
    engine = create_engine(DB_URL)
    
    # 1. Création des tables
    Base.metadata.create_all(engine)
    
    if not RAW_DATA_PATH.exists():
        print(f"❌ Erreur : Fichier introuvable à {RAW_DATA_PATH}")
        return

    print(f"📂 Chargement du CSV...")
    df = pd.read_csv(RAW_DATA_PATH, nrows=LIMIT_RECIPES)
    
    # --- CORRECTION ICI : Nettoyage des données manquantes ---
    initial_count = len(df)
    df = df.dropna(subset=['name', 'minutes', 'nutrition']) # On supprime les lignes critiques vides
    dropped_count = initial_count - len(df)
    if dropped_count > 0:
        print(f"🧹 Nettoyage : {dropped_count} recettes ignorées (données manquantes).")

    # 3. Insertion
    with Session(engine) as session:
        # Check simple pour éviter les doublons si on relance
        if session.query(Recipe).count() > 0:
            print("⚠️ La base contient déjà des recettes. Pour recharger, supprimez le fichier smartretail.db.")
        else:
            print("Processing et insertion...")
            recipes_buffer = []
            
            for _, row in df.iterrows():
                calories, nut_info = parse_nutrition(row['nutrition'])
                
                recipe = Recipe(
                    name=str(row['name']), # Force en string pour éviter les erreurs
                    description=str(row['description']) if pd.notna(row['description']) else "",
                    minutes=int(row['minutes']),
                    n_steps=int(row['n_steps']),
                    calories=calories,
                    nutrition_info=nut_info,
                    steps=parse_list(row['steps']),
                    ingredients=parse_list(row['ingredients']),
                    tags=parse_list(row['tags']),
                    embedding=None
                )
                recipes_buffer.append(recipe)
            
            session.add_all(recipes_buffer)
            
            # Ajout User Test
            test_user = User(
                username="test_user_01",
                preferences={"mexican": 0.9, "easy": 0.8},
                dietary_restrictions=[],
                goals={"target_calories": 2000}
            )
            session.add(test_user)
            
            session.commit()
            print(f"✅ Succès ! {len(recipes_buffer)} recettes insérées.")

if __name__ == "__main__":
    init_db()