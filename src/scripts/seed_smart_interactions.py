import sys
import os
import random
import ast

# Configuration du chemin pour les imports
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session  # noqa: E402
from src.database.connection import engine  # noqa: E402
from src.database.models import User, Recipe, Interaction  # noqa: E402

# --- CONFIGURATION ---
NB_RECIPES_TO_RATE = 2000  # Nombre de recettes notées par utilisateur
RANDOM_SEED = 42  # Reproductibilité


def parse_list(str_value):
    """Transforme une string "['a', 'b']" en liste Python réelle"""
    try:
        if not str_value:
            return []
        if isinstance(str_value, list):
            return str_value
        return ast.literal_eval(str_value)
    except Exception:
        return []


def get_simulated_score(user_id, recipe):
    """
    Logique de notation complexe pour 5 Personas distincts.
    """
    # Parsing des données
    tags = parse_list(recipe.tags)
    ingredients = parse_list(recipe.ingredients)

    # On normalise tout en minuscules pour faciliter la comparaison
    tags_str = " ".join(tags).lower()
    ing_str = " ".join(ingredients).lower()
    name_str = recipe.name.lower()

    score = 3.0  # Note neutre de départ

    # --- 1. LE VÉGÉTARIEN HEALTHY ---
    if user_id == 1:
        # Bonus
        if "vegetarian" in tags_str or "vegan" in tags_str:
            score += 1.5
        if "salad" in tags_str or "healthy" in tags_str:
            score += 1.0
        if recipe.calories and recipe.calories < 400:
            score += 0.5

        # Malus (Repoussoirs forts)
        for meat in ["chicken", "beef", "pork", "bacon", "steak", "sausage"]:
            if meat in ing_str:
                score -= 3.0
        if "deep-fried" in tags_str:
            score -= 1.0

    # --- 2. LE TRADITIONNEL (VIANDE & PATATES) ---
    elif user_id == 2:
        # Bonus
        if any(x in ing_str for x in ["beef", "steak", "pork", "roast", "meat"]):
            score += 1.5
        if recipe.minutes > 60:
            score += 1.0  # Aime le mijoté
        if "comfort-food" in tags_str:
            score += 1.0

        # Malus
        if "tofu" in ing_str or "vegan" in tags_str:
            score -= 2.5
        if "salad" in name_str:
            score -= 1.0

    # --- 3. L'EXPLORATEUR ÉPICÉ (WORLD FOOD) ---
    elif user_id == 3:
        # Bonus
        spicy_keywords = [
            "spicy",
            "curry",
            "chili",
            "sriracha",
            "cajun",
            "mexican",
            "indian",
            "thai",
            "asian",
        ]
        if any(k in tags_str or k in name_str for k in spicy_keywords):
            score += 2.0
        if "rice" in ing_str:
            score += 0.5

        # Malus
        if "bland" in tags_str or "simple" in tags_str:
            score -= 1.0
        if "european" in tags_str and "spicy" not in tags_str:
            score -= 0.5

    # --- 4. LE FIT & SPORT (PROTEIN & CONTROL) ---
    elif user_id == 4:
        # Bonus (Cherche le poulet/poisson sans trop de gras)
        if (
            "chicken" in ing_str
            or "fish" in ing_str
            or "tuna" in ing_str
            or "egg" in ing_str
        ):
            score += 1.5
        if "high-protein" in tags_str:
            score += 1.5

        # Malus (Trop calorique ou sucre)
        if recipe.calories and recipe.calories > 800:
            score -= 2.0
        if "dessert" in tags_str or "cake" in tags_str or "chocolate" in ing_str:
            score -= 3.0

    # --- 5. LE BEC SUCRÉ (DESSERT ONLY) ---
    elif user_id == 5:
        # Bonus
        if "dessert" in tags_str or "cookie" in tags_str or "cake" in tags_str:
            score += 2.5
        if "chocolate" in ing_str or "sugar" in ing_str or "fruit" in tags_str:
            score += 1.0

        # Malus
        if "main-dish" in tags_str or "dinner-party" in tags_str:
            score -= 1.5
        if "onion" in ing_str or "garlic" in ing_str:
            score -= 2.0

    # Ajout de bruit (Noise) pour le réalisme
    noise = random.uniform(-0.6, 0.6)
    final_score = round(score + noise)

    # Bornage strict entre 1 et 5
    return int(max(1, min(5, final_score)))


def seed_interactions():
    print(f"🌱 Génération multi-persona (Seed: {RANDOM_SEED})...")
    random.seed(RANDOM_SEED)

    with Session(engine) as session:
        # 1. Nettoyage
        print("   🧹 Reset table interactions...")
        session.query(Interaction).delete()

        # 2. Création des 5 Personas
        personas = [
            (1, "Végé_Bio"),
            (2, "Viande_Tradi"),
            (3, "Spicy_Mike"),
            (4, "Fit_Gym"),
            (5, "Sweet_Tooth"),
        ]

        users_obj = []
        for pid, name in personas:
            user = session.get(User, pid)
            if not user:
                user = User(id=pid, username=name)
                session.add(user)
            users_obj.append(user)
        session.commit()
        print(f"   👥 {len(users_obj)} Personas créés.")

        # 3. Récupération des recettes
        recipes = session.query(Recipe).limit(10000).all()
        if not recipes:
            print("   ❌ Erreur : Base vide. Lancez init_db.py.")
            return

        print(
            f"   🎲 Simulation de {NB_RECIPES_TO_RATE} notes/user sur un pool de {len(recipes)} recettes..."
        )

        new_interactions = []

        for user in users_obj:
            user_sample = random.sample(recipes, min(len(recipes), NB_RECIPES_TO_RATE))

            for recipe in user_sample:
                rating = get_simulated_score(user.id, recipe)

                # CORRECTION ICI : Retrait de 'liked='
                new_interactions.append(
                    Interaction(user_id=user.id, recipe_id=recipe.id, rating=rating)
                )

        # 4. Insert en Batch
        session.add_all(new_interactions)
        session.commit()

        print(f"✅ Terminé ! {len(new_interactions)} interactions générées.")


if __name__ == "__main__":
    seed_interactions()
