import random
import numpy as np
from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from src.database.models import Recipe, User, Interaction

class UserSimulator:
    def __init__(self, session: Session):
        self.session = session
        # On charge les recettes en cache pour éviter de requêter la DB à chaque boucle
        # Pour 5000 recettes, ça tient largement en RAM
        print("Chargement du catalogue recettes en mémoire...")
        self.recipes = session.query(Recipe).all()
        print(f"Simulateur prêt avec {len(self.recipes)} recettes.")

    def _get_season(self, date: datetime) -> str:
        """Retourne 'winter', 'spring', 'summer', 'autumn'"""
        m = date.month
        if m in [12, 1, 2]: return 'winter'
        if m in [3, 4, 5]: return 'spring'
        if m in [6, 7, 8]: return 'summer'
        return 'autumn'

    def _calculate_score(self, user: User, recipe: Recipe, date: datetime) -> float:
        """
        LE PUZZLE ISTP : C'est ici que réside l'intelligence du simulateur.
        Retourne une probabilité (0.0 à 1.0) que l'user choisisse cette recette ce jour-là.
        """
        score = 0.5 # Base neutre
        
        # 1. Matching des préférences (Ex: User aime 'mexican', Recette a le tag 'mexican')
        # user.preferences est un dict, ex: {'mexican': 0.8, 'soup': 0.2}
        for tag, weight in user.preferences.items():
            if tag in recipe.tags:
                score += weight
        
        # 2. Gestion de la Saisonnalité (Contexte)
        current_season = self._get_season(date)
        # TODO: Implémenter une logique : Si saison = 'winter' et tag recette = 'comfort-food' ou 'stew' -> Boost score
        
        # 3. Lassitude (Drift)
        # TODO: (Avancé) Réduire le score si l'utilisateur a mangé ça hier
        
        # Ajout d'un bruit aléatoire pour ne pas être trop robotique
        noise = np.random.normal(0, 0.1) 
        return np.clip(score + noise, 0, 1)

    def run_simulation(self, user_id: int, start_date: datetime, days: int = 30):
        """Génère un historique d'interactions pour un user donné"""
        user = self.session.get(User, user_id)
        if not user:
            print(f"User {user_id} introuvable.")
            return

        print(f"Simulation pour {user.username} sur {days} jours...")
        interactions_buffer = []
        current_date = start_date

        for _ in range(days):
            # Pour chaque jour, on évalue toutes les recettes (ou un subset)
            # et on en choisit une (dîner) basée sur le score
            
            # On prend un échantillon aléatoire de 50 recettes pour aller vite
            candidate_recipes = random.sample(self.recipes, 50)
            
            best_recipe = None
            max_score = -1
            
            for recipe in candidate_recipes:
                score = self._calculate_score(user, recipe, current_date)
                if score > max_score:
                    max_score = score
                    best_recipe = recipe
            
            # Si le score est suffisant, on crée une interaction
            if best_recipe and max_score > 0.4: # Seuil d'acceptation
                # Simulation d'une note (1-5) corrélée au score d'envie
                simulated_rating = int(min(5, max(1, max_score * 5)))
                
                interaction = Interaction(
                    user_id=user.id,
                    recipe_id=best_recipe.id,
                    rating=simulated_rating,
                    timestamp=current_date,
                    context_snapshot={"season": self._get_season(current_date)}
                )
                interactions_buffer.append(interaction)
            
            current_date += timedelta(days=1)

        self.session.add_all(interactions_buffer)
        self.session.commit()
        print(f"✅ {len(interactions_buffer)} interactions générées pour {user.username}.")

# --- Bloc de test rapide ---
if __name__ == "__main__":
    from sqlalchemy import create_engine
    
    engine = create_engine("sqlite:///smartretail.db")
    with Session(engine) as session:
        sim = UserSimulator(session)
        # On simule pour l'user ID 1 (créé par init_db)
        sim.run_simulation(user_id=1, start_date=datetime(2023, 1, 1), days=90)