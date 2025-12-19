from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from src.database.models import User, Interaction, Recipe
import random

class UserProfiler:
    def __init__(self, session: Session):
        self.session = session

    def get_user_vector(self, user_id: int):
        """
        Récupère l'historique (pour l'instant simplifié sans vecteurs complexes)
        """
        # Pour cette version, on ne calcule pas de vecteur complexe
        # On retourne simplement les IDs des recettes aimées
        interactions = self.session.query(Interaction).filter(
            Interaction.user_id == user_id,
            Interaction.rating >= 4
        ).all()
        return [i.recipe_id for i in interactions]

    def recommend_candidates(self, user_id: int, limit: int = 100):
        """
        Stratégie Hybride :
        1. Essaie de trouver des recommandations IA (basées sur l'historique)
        2. Si pas assez de données, complète avec de l'aléatoire (Découverte)
        """
        candidates = []
        
        # --- PHASE 1 : RECUPERATION BASEE SUR L'HISTORIQUE ---
        # (Ici, on pourrait mettre la logique FAISS / Vectorielle)
        # Pour l'instant, simulons une logique simple :
        # On ne veut pas recommander ce qu'il a déjà mangé récemment
        # ... (Logique placeholder) ...
        
        # --- PHASE 2 : REMPLISSAGE (COLD START) ---
        # Si on n'a pas atteint la limite (ce qui est le cas actuellement),
        # on va chercher des recettes au hasard dans la BDD pour donner du choix au solveur.
        
        current_count = len(candidates)
        missing = limit - current_count
        
        if missing > 0:
            print(f"⚠️ Cold Start : Ajout de {missing} recettes aléatoires pour nourrir le solveur.")
            
            # Récupération de recettes aléatoires via PostgreSQL (func.random())
            random_recipes = self.session.query(Recipe)\
                .order_by(func.random())\
                .limit(missing)\
                .all()
            
            for recipe in random_recipes:
                # On attribue un score artificiel
                # Un peu d'aléatoire pour que le solveur ne prenne pas toujours les mêmes
                fake_score = random.uniform(0.1, 0.9) 
                
                # Format (Recipe, Score) attendu par le solveur
                candidates.append((recipe, fake_score))

        return candidates