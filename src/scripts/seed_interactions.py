import random
from datetime import datetime
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User, Recipe, Interaction


def seed_interactions():
    print("🌱 Génération d'un historique factice...")

    with Session(engine) as session:
        # 1. Vérifier l'utilisateur
        user = session.query(User).filter(User.id == 1).first()
        if not user:
            print("❌ Erreur : L'utilisateur ID 1 n'existe pas.")
            return

        # 2. Récupérer des recettes variées (ex: 20 recettes aléatoires)
        # On essaie de prendre des recettes avec 'chicken' pour faciliter le test frigo
        recipes = (
            session.query(Recipe).filter(Recipe.name.ilike("%chicken%")).limit(10).all()
        )
        others = session.query(Recipe).limit(10).all()
        all_recipes = recipes + others

        if not all_recipes:
            print("❌ Pas de recettes en base.")
            return

        # 3. Créer des interactions
        count = 0
        for recipe in all_recipes:
            # On simule que l'utilisateur a déjà noté ces plats
            # On vérifie si l'interaction existe déjà
            exists = (
                session.query(Interaction)
                .filter_by(user_id=1, recipe_id=recipe.id)
                .first()
            )

            if not exists:
                score = random.choice([4, 5])  # On met de bonnes notes
                interaction = Interaction(
                    user_id=1, recipe_id=recipe.id, rating=score, date=datetime.utcnow()
                )
                session.add(interaction)
                count += 1

        session.commit()
        print(f"✅ {count} interactions ajoutées pour Chef Cyril !")


if __name__ == "__main__":
    seed_interactions()
