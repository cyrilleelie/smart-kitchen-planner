import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sklearn.metrics.pairwise import cosine_similarity
from src.database.models import User, Interaction, Recipe

class UserProfiler:
    def __init__(self, session: Session):
        self.session = session

    def get_user_vector(self, user_id: int, use_decay=True):
        """
        Calcule le vecteur de goût.
        :param use_decay: Si True, applique une pondération temporelle (Les likes récents comptent plus).
        """
        # 1. On récupère TOUT l'historique positif (Note >= 3)
        # Note : On ignore les notes 1 et 2 (les rejets), car ils ne constituent pas un goût
        interactions = self.session.query(Interaction).filter(
            Interaction.user_id == user_id,
            Interaction.rating >= 3
        ).order_by(desc(Interaction.timestamp)).all()

        if not interactions:
            return None

        vectors = []
        weights = []
        
        # Date de référence (maintenant)
        now = datetime.now()

        for interaction in interactions:
            if interaction.recipe.embedding:
                vec = np.array(interaction.recipe.embedding)
                vectors.append(vec)
                
                if use_decay:
                    # Formule de décroissance : 1 / (1 + jours_écoulés)
                    # Hier = 1.0, Il y a 30 jours = 0.03
                    days_diff = (now - interaction.timestamp).days
                    # On ajoute un petit epsilon pour éviter la division par zéro si c'est aujourd'hui
                    weight = 1 / (max(days_diff, 0) + 1)
                    weights.append(weight)
                else:
                    weights.append(1.0)
        
        if not vectors:
            return None

        # 2. Moyenne Pondérée (Weighted Average)
        # C'est ici que la magie opère : les vieux vecteurs "viande" sont écrasés par les récents
        user_vector = np.average(vectors, axis=0, weights=weights if use_decay else None)
        return user_vector

    def recommend_candidates(self, user_id: int, limit=100, use_decay=True):
        """Génère les candidats basés sur le profil à jour"""
        user_vector = self.get_user_vector(user_id, use_decay=use_decay)
        
        if user_vector is None:
            # Fallback : Populaire ou Random
            return self.session.query(Recipe).limit(limit).all(), [0.5]*limit

        # Récupération de toutes les recettes vectorisées
        all_recipes = self.session.query(Recipe).filter(Recipe.embedding != None).all()
        recipe_vectors = np.array([np.array(r.embedding) for r in all_recipes])
        
        # Similarité
        similarities = cosine_similarity(user_vector.reshape(1, -1), recipe_vectors)[0]
        
        # Tri
        top_indices = np.argsort(similarities)[::-1][:limit]
        
        candidates = []
        scores = []
        for idx in top_indices:
            candidates.append(all_recipes[idx])
            scores.append(similarities[idx] * 100)
            
        return candidates, scores