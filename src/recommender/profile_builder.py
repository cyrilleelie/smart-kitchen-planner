from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from src.database.models import User, Interaction, Recipe
from collections import Counter
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

    # N'oubliez pas d'importer Counter en haut du fichier
    from collections import Counter 

    def recommend_candidates(self, user_id: int, limit: int = 100):
        candidates = []
        
        # --- 1. ANALYSE FINE DU PROFIL ---
        liked_interactions = self.session.query(Interaction).join(Recipe).filter(
            Interaction.user_id == user_id, 
            Interaction.rating >= 4
        ).all()
        
        # On compte la fréquence des tags pour pondérer
        tag_counter = Counter()
        for i in liked_interactions:
            raw = i.recipe.tags
            if isinstance(raw, str):
                clean = raw.replace('[','').replace(']','').replace("'", "").split(',')
                clean = [t.strip() for t in clean]
            else:
                clean = raw
            tag_counter.update(clean)
            
        # BLACKLIST (Technique)
        BLACKLIST = {
            "time-to-make", "preparation", "course", "main-ingredient", "dietary",
            "easy", "number-of-servings", "technique", "equipment", "5-minutes-or-less",
            "15-minutes-or-less", "30-minutes-or-less", "60-minutes-or-less"
        }
        
        # On ne garde que le TOP 20 des tags les plus fréquents chez l'user
        # Cela évite qu'un tag vu une seule fois ne pollue tout
        most_common_tags = [t for t, c in tag_counter.most_common(20) if t not in BLACKLIST]
        
        # --- 2. SCORING PLUS STRICT ---
        if most_common_tags:
            # On scanne un échantillon plus large (1000) pour filtrer
            pool = self.session.query(Recipe).limit(1000).all()
            
            for recipe in pool:
                r_tags = str(recipe.tags)
                # On compte combien de tags du TOP 20 sont présents dans la recette
                match_count = sum(1 for tag in most_common_tags if tag in r_tags)
                
                if match_count > 0:
                    # NOUVELLE FORMULE :
                    # Base : 0.5 (Moyenne)
                    # Bonus : +3% par tag matché
                    # Plafond : 0.98
                    score = 0.5 + (match_count * 0.03)
                    score = min(score, 0.98) # Cap
                    
                    # On ne garde que ceux qui dépassent la moyenne (0.5)
                    candidates.append((recipe, score))
        
        # Tri décroissant par score
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # --- 3. REMPLISSAGE (Si besoin) ---
        candidates = candidates[:limit] # On garde les meilleurs
        
        missing = limit - len(candidates)
        if missing > 0:
            random_recipes = self.session.query(Recipe).order_by(func.random()).limit(missing).all()
            for recipe in random_recipes:
                # Score pénalisé pour l'aléatoire (0.1 - 0.4)
                # Ainsi, le solveur privilégiera TOUJOURS les recettes matchées (0.5+)
                score = random.uniform(0.1, 0.4)
                candidates.append((recipe, score))
        
        return candidates
    
    def get_user_ratings(self, user_id: int) -> dict:
        """
        Récupère tout l'historique d'un utilisateur sous forme de dict
        Exemple retour : {102: 5, 450: 3, ...}
        """
        interactions = self.session.query(Interaction).filter(
            Interaction.user_id == user_id
        ).all()
        return {i.recipe_id: i.rating for i in interactions}