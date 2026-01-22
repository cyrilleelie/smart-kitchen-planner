import sys
import os
import json
import random
import argparse
from sqlalchemy.orm import Session
from sqlalchemy import text

# Configuration des chemins
sys.path.append(os.getcwd())
from src.database.connection import engine  # noqa: E402
from src.database.models import User  # noqa: E402
from src.utils.translations import PREFERENCE_TAGS_MAP  # noqa: E402

# Création du mapping inverse : EN -> FR
TAGS_EN_TO_FR = {v: k for k, v in PREFERENCE_TAGS_MAP.items()}


def load_persona(json_path):
    with open(json_path, "r") as f:
        return json.load(f)


def translate_preferences(english_prefs):
    """Traduit les préférences (anglais du JSON) vers les labels UI (français attendus par UserProfiler)"""
    french_prefs = []
    for p in english_prefs:
        p_clean = (
            p.strip().lower()
        )  # Sécurité : tout en minuscules pour matcher les valeurs
        found = False
        # Recherche exacte
        if p_clean in TAGS_EN_TO_FR:
            french_prefs.append(TAGS_EN_TO_FR[p_clean])
            found = True
        else:
            # Fallback : recherche un peu plus souple ou log
            # Parfois "vegetarian" vs "Vegetarian"
            # On parcourt les valeurs si match direct échoue (peu performant mais ok pour script one-shot)
            for en_val, fr_key in TAGS_EN_TO_FR.items():
                if en_val.lower() == p_clean:
                    french_prefs.append(fr_key)
                    found = True
                    break

        if not found:
            print(
                f"   ⚠️ Warning: Le tag '{p}' n'a pas de traduction connue. Il sera ignoré par UserProfiler."
            )

    return french_prefs


def get_weighted_rating(values, weights):
    """Retourne une note pondérée (ex: 70% de chance d'avoir 5, 30% d'avoir 4)"""
    return random.choices(values, weights=weights, k=1)[0]


def analyze_recipe_taste(recipe, rules):
    """Détermine la note basée sur le contenu de la recette (Titre + Tags)"""
    # On normalise le texte pour la recherche
    text_content = (recipe.name + " " + (recipe.tags if recipe.tags else "")).lower()

    # 1. Vérification des DISLIKES (Prioritaire : si je suis vegan, la viande est éliminatoire)
    for kw in rules["dislikes"]["keywords"]:
        if kw in text_content:
            return get_weighted_rating(
                rules["dislikes"]["rating_dist"], rules["dislikes"]["weights"]
            )

    # 2. Vérification des LIKES
    for kw in rules["likes"]["keywords"]:
        if kw in text_content:
            return get_weighted_rating(
                rules["likes"]["rating_dist"], rules["likes"]["weights"]
            )

    # 3. NEUTRE (Aucun mot clé trouvé)
    return get_weighted_rating(
        rules["neutral"]["rating_dist"], rules["neutral"]["weights"]
    )


def inject_data(json_file):
    print(f"🚀 Chargement du profil depuis : {json_file}")
    persona = load_persona(json_file)

    with Session(engine) as session:
        # On force PostgreSQL à mettre à jour son compteur d'ID au max actuel + 1
        try:
            print("   🔧 Resynchronisation de la séquence des IDs...")
            session.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id),0) + 1, false) FROM users;"
                )
            )
            session.commit()
        except Exception as e:
            print(f"   ⚠️ Avertissement (Séquence) : {e}")
            session.rollback()
        # ----------------------------------------

        # A. Création / Récupération du User
        user = session.query(User).filter(User.username == persona["username"]).first()
        if not user:
            # TRADUCTION DES PREFERENCES AVANT INSERTION
            translated_prefs = translate_preferences(persona["preferences"])
            print(
                f"   📝 Traduction préférences : {persona['preferences']} -> {translated_prefs}"
            )

            user = User(username=persona["username"], preferences=translated_prefs)
            session.add(user)
            session.commit()
            print(f"   👤 Nouvel utilisateur créé : {user.username} (ID: {user.id})")
        else:
            print(
                f"   👤 Utilisateur existant trouvé : {user.username} (ID: {user.id})"
            )

        # B. Récupération des recettes (Désactivé : Simulation via simulate_activity.py)
        # ------------------------------------------------------------------------------------------------
        # # On mélange aléatoirement pour ne pas toujours noter les mêmes
        # all_recipes = session.query(Recipe).order_by(func.random()).all()
        #
        # target_count = persona["interaction_count"]
        # if len(all_recipes) < target_count:
        #     print(
        #         f"   ⚠️ Attention : La base ne contient que {len(all_recipes)} recettes. On notera tout."
        #     )
        #     target_count = len(all_recipes)
        #
        # # C. Génération des interactions cohérentes
        # print(f"   🧠 Analyse et notation de {target_count} recettes...")
        #
        # interactions_added = 0
        # rules = persona["behavior_rules"]
        #
        # for recipe in all_recipes[:target_count]:
        #     # Vérifie si l'interaction existe déjà pour éviter les doublons DB
        #     existing = (
        #         session.query(Interaction)
        #         .filter(
        #             Interaction.user_id == user.id, Interaction.recipe_id == recipe.id
        #         )
        #         .first()
        #     )
        #
        #     if existing:
        #         continue
        #
        #     # Calcul de la note "intelligente"
        #     rating = analyze_recipe_taste(recipe, rules)
        #
        #     interaction = Interaction(
        #         user_id=user.id,
        #         recipe_id=recipe.id,
        #         rating=rating,
        #         date=datetime.utcnow(),  # Date fraîche pour le monitoring
        #     )
        #     session.add(interaction)
        #     interactions_added += 1
        #
        # session.commit()
        # print(
        #     f"   ✅ Injection terminée ! {interactions_added} nouvelles interactions ajoutées."
        # )
        # ------------------------------------------------------------------------------------------------
        print(
            f"   ✅ Utilisateur {user.username} initialisé (Interactions désactivées dans ce script)."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Injecte des données utilisateur simulées via JSON (dans data/personas/)"
    )
    parser.add_argument(
        "persona_name", help="Nom du fichier persona (sans extension, ex: 'sportif')"
    )
    args = parser.parse_args()

    # Construct path: data/personas/{name}.json
    base_dir = os.path.join(os.getcwd(), "data", "personas")
    filename = f"{args.persona_name}.json"
    full_path = os.path.join(base_dir, filename)

    if not os.path.exists(full_path):
        print(f"❌ Erreur : Le fichier '{full_path}' n'existe pas.")
        print(f"   Dossier scanné : {base_dir}")
        sys.exit(1)

    inject_data(full_path)
