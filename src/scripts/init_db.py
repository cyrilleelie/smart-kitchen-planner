import pandas as pd
import ast
import os
import sys
from sqlalchemy import text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.getcwd())

from src.database.models import Base, Recipe  # noqa: E402
from src.database.connection import engine  # noqa: E402
from src.recommender.vectorizer import generate_recipe_embeddings  # noqa: E402


# CONFIGURATION
INITIAL_LIMIT = 5000
CSV_PATHS = [
    "data/raw/RAW_recipes.csv",
    "/app/data/raw/RAW_recipes.csv",
    "data/RAW_recipes.csv",
]


def get_csv_path():
    for path in CSV_PATHS:
        if os.path.exists(path):
            return path
    return None


def init_database():
    print(f"🔥 --- INITIALISATION DIVERSIFIÉE ({INITIAL_LIMIT} recettes) ---")

    # 1. RESET
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    csv_path = get_csv_path()
    if not csv_path:
        return

    print("📖 Lecture et Mélange du CSV complet...")
    # On lit TOUT pour pouvoir bien mélanger (230k lignes ~ 100Mo RAM, c'est ok)
    df = pd.read_csv(csv_path)

    # --- LE SHUFFLE MAGIQUE ---
    # frac=1 signifie "prendre 100% des données" mais dans le désordre
    # random_state=42 assure que tu auras toujours le même "set aléatoire" (reproductibilité)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    # On ne garde que les X premiers APRÈS mélange
    df_subset = df.head(INITIAL_LIMIT)

    with Session(engine) as session:
        print(f"📥 Insertion de {len(df_subset)} recettes variées...")
        recipes_buffer = []

        for _, row in df_subset.iterrows():
            try:
                nutrition = ast.literal_eval(row["nutrition"])
                cal = float(nutrition[0])
            except Exception:
                cal = 0.0

            recipe = Recipe(
                id=int(row["id"]),  # ID original conservé
                name=str(row["name"]),
                minutes=int(row["minutes"]),
                tags=row["tags"] if isinstance(row["tags"], str) else "[]",
                nutrition_info=str(row["nutrition"]),
                calories=cal,
                description=(
                    str(row["description"])[:500]
                    if pd.notna(row["description"])
                    else ""
                ),
                ingredients=(
                    row["ingredients"] if isinstance(row["ingredients"], str) else "[]"
                ),
                n_steps=int(row["n_steps"]),
                steps=str(row["steps"]),
            )
            recipes_buffer.append(recipe)

        session.add_all(recipes_buffer)
        session.commit()

        # Mise à jour de la séquence pour éviter les conflits futurs
        try:
            max_id = int(
                df["id"].max()
            )  # On prend le max global du CSV pour être large
            session.execute(text(f"SELECT setval('recipes_id_seq', {max_id}, true)"))
            session.commit()
        except Exception:
            pass

        print("   ✅ Base initialisée avec succès.")

        # Lancement automatique de la vectorisation (si nécessaire)
        generate_recipe_embeddings()


if __name__ == "__main__":
    init_database()
