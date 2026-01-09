import sys
import os
import json
import random
import argparse
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, text

# Configuration des chemins
sys.path.append(os.getcwd())
from src.database.connection import engine
from src.database.models import User, Recipe, Interaction

def load_persona(json_path):
    with open(json_path, 'r') as f:
        return json.load(f)

def get_weighted_rating(values, weights):
    """Retourne une note pondérée (ex: 70% de chance d'avoir 5, 30% d'avoir 4)"""
    return random.choices(values, weights=weights, k=1)[0]

def analyze_recipe_taste(recipe, rules):
    """Détermine la note basée sur le contenu de la recette (Titre + Tags)"""
    # On normalise le texte pour la recherche
    text_content = (recipe.name + " " + (recipe.tags if recipe.tags else "")).lower()
    
    # 1. Vérification des DISLIKES (Prioritaire : si je suis vegan, la viande est éliminatoire)
    for kw in rules['dislikes']['keywords']:
        if kw in text_content:
            return get_weighted_rating(rules['dislikes']['rating_dist'], rules['dislikes']['weights'])
            
    # 2. Vérification des LIKES
    for kw in rules['likes']['keywords']:
        if kw in text_content:
            return get_weighted_rating(rules['likes']['rating_dist'], rules['likes']['weights'])
            
    # 3. NEUTRE (Aucun mot clé trouvé)
    return get_weighted_rating(rules['neutral']['rating_dist'], rules['neutral']['weights'])

def inject_data(json_file):
    print(f"🚀 Chargement du profil depuis : {json_file}")
    persona = load_persona(json_file)
    
    with Session(engine) as session:
        # On force PostgreSQL à mettre à jour son compteur d'ID au max actuel + 1
        try:
            print("   🔧 Resynchronisation de la séquence des IDs...")
            session.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id),0) + 1, false) FROM users;"))
            session.commit()
        except Exception as e:
            print(f"   ⚠️ Avertissement (Séquence) : {e}")
            session.rollback()
        # ----------------------------------------

        # A. Création / Récupération du User
        user = session.query(User).filter(User.username == persona['username']).first()
        if not user:
            user = User(
                username=persona['username'],
                preferences=persona['preferences']
            )
            session.add(user)
            session.commit()
            print(f"   👤 Nouvel utilisateur créé : {user.username} (ID: {user.id})")
        else:
            print(f"   👤 Utilisateur existant trouvé : {user.username} (ID: {user.id})")

        # B. Récupération des recettes
        # On mélange aléatoirement pour ne pas toujours noter les mêmes
        all_recipes = session.query(Recipe).order_by(func.random()).all()
        
        target_count = persona['interaction_count']
        if len(all_recipes) < target_count:
            print(f"   ⚠️ Attention : La base ne contient que {len(all_recipes)} recettes. On notera tout.")
            target_count = len(all_recipes)

        # C. Génération des interactions cohérentes
        print(f"   🧠 Analyse et notation de {target_count} recettes...")
        
        interactions_added = 0
        rules = persona['behavior_rules']
        
        for recipe in all_recipes[:target_count]:
            # Vérifie si l'interaction existe déjà pour éviter les doublons DB
            existing = session.query(Interaction).filter(
                Interaction.user_id == user.id, 
                Interaction.recipe_id == recipe.id
            ).first()
            
            if existing:
                continue

            # Calcul de la note "intelligente"
            rating = analyze_recipe_taste(recipe, rules)
            
            interaction = Interaction(
                user_id=user.id,
                recipe_id=recipe.id,
                rating=rating,
                date=datetime.utcnow() # Date fraîche pour le monitoring
            )
            session.add(interaction)
            interactions_added += 1

        session.commit()
        print(f"   ✅ Injection terminée ! {interactions_added} nouvelles interactions ajoutées.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Injecte des données utilisateur simulées via JSON")
    parser.add_argument("json_file", help="Chemin vers le fichier JSON du persona")
    args = parser.parse_args()
    
    inject_data(args.json_file)