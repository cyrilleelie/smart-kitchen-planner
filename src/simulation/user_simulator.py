import random
from sqlalchemy.orm import Session
from sqlalchemy import func

# Import de la connexion centralisée
from src.database.connection import engine
from src.database.models import User, Recipe, Interaction

def simulate_user_history():
    print("🤖 Démarrage du simulateur d'interactions...")

    # On utilise le contexte manager avec l'engine importé
    with Session(engine) as session:
        # 1. Récupérer l'utilisateur test
        user = session.query(User).filter(User.username == "test_user_01").first()
        
        if not user:
            print("❌ Erreur : L'utilisateur 'test_user_01' n'existe pas. Lancez init_db d'abord.")
            return

        # 2. Définir un "Goût" arbitraire (ex: Cuisine Mexicaine et Rapide)
        # On cherche des recettes qui contiennent ces mots-clés
        print("   -> Recherche de recettes 'Mexican' & 'Easy'...")
        
        # Requête SQL via SQLAlchemy pour trouver des recettes cibles
        liked_recipes = session.query(Recipe).filter(
            (Recipe.tags.like('%mexican%')) | 
            (Recipe.tags.like('%easy%'))
        ).order_by(func.random()).limit(20).all()

        if not liked_recipes:
            print("⚠️ Aucune recette trouvée pour ce profil. Vérifiez les données.")
            return

        # 3. Créer les interactions (Likes)
        new_interactions = []
        for recipe in liked_recipes:
            # On simule une note élevée (4 ou 5) pour ces plats
            rating = random.choice([4, 5])
            
            interaction = Interaction(
                user_id=user.id,
                recipe_id=recipe.id,
                rating=rating,
                # date=... (La date par défaut est auto-gérée par le modèle si default=func.now())
            )
            new_interactions.append(interaction)

        # 4. Sauvegarde
        session.add_all(new_interactions)
        session.commit()
        
        print(f"✅ Succès : {len(new_interactions)} interactions ajoutées pour {user.username}.")
        print("   Le profil utilisateur est prêt pour l'analyse IA.")

if __name__ == "__main__":
    simulate_user_history()