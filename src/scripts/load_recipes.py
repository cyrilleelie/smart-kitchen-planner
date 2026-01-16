import pandas as pd
import ast
import os
import sys
import argparse
from sqlalchemy import text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.getcwd())

from src.database.models import Recipe  # noqa: E402
from src.database.connection import engine  # noqa: E402

# CONFIGURATION
CSV_PATHS = ["data/raw/RAW_recipes.csv"]


def get_csv_path():
    for path in CSV_PATHS:
        if os.path.exists(path):
            return path
    return None


def load_recipes(count: int):
    print(f"📦 --- CHARGEMENT DE {count} NOUVELLES RECETTES ---")

    with Session(engine) as session:
        # 1. IDs EXISTANTS
        print("📊 Analyse de la base existante...")
        existing_ids = set(flat_id for flat_id, in session.query(Recipe.id).all())
        current_count = len(existing_ids)
        print(f"   -> {current_count} recettes en stock.")

        csv_path = get_csv_path()
        if not csv_path:
            print("❌ Erreur : Fichier CSV source introuvable.")
            return

        # 2. LECTURE & FILTRAGE
        print("📖 Lecture du CSV...")
        df_full = pd.read_csv(csv_path)

        # On ne garde que ce qui n'est PAS dans la base
        new_candidates = df_full[~df_full["id"].isin(existing_ids)]

        if new_candidates.empty:
            print("✨ Stock épuisé ! Tout le CSV est déjà en base.")
            return

        # 3. SÉLECTION ET CHARGEMENT
        # On mélange les candidats pour charger un échantillon aléatoire (ou les n premiers dispos)
        print("🎲 Sélection des nouvelles recettes...")
        batch = new_candidates.sample(frac=1).head(count)

        print(f"📥 Injection de {len(batch)} nouvelles recettes...")

        new_recipes = []
        for _, row in batch.iterrows():
            try:
                cal = 0.0
                try:
                    cal = float(ast.literal_eval(row["nutrition"])[0])
                except Exception:
                    pass

                recipe = Recipe(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    minutes=int(row["minutes"]),
                    tags=str(row["tags"]),
                    nutrition_info=str(row["nutrition"]),
                    calories=cal,
                    description=(
                        str(row["description"])[:500]
                        if pd.notna(row["description"])
                        else ""
                    ),
                    ingredients=str(row["ingredients"]),
                    n_steps=int(row["n_steps"]),
                    steps=str(row["steps"]),
                    embedding=None,  # Arrive vierge, à calculer ensuite
                )
                new_recipes.append(recipe)
            except Exception:
                continue

        session.add_all(new_recipes)
        session.commit()

        # Mise à jour séquence (PostgreSQL)
        try:
            # On met à jour la séquence par rapport au MAX ID présent en base
            session.execute(
                text(
                    "SELECT setval('recipes_id_seq', (SELECT MAX(id) FROM recipes), true)"
                )
            )
            session.commit()
        except Exception as e:
            # Sur SQLite ou si la séquence n'existe pas, ça peut catch, ce n'est pas bloquant
            print(f"   ℹ️ Ajustement séquence ignoré ({e})")

        print(f"✅ Succès : {len(new_recipes)} recettes ajoutées.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de chargement de nouvelles recettes."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Nombre de recettes à charger (défaut: 1000)",
    )
    args = parser.parse_args()

    load_recipes(args.count)
