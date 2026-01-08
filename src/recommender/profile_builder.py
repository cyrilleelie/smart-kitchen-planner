import json
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.database.models import User, Interaction, Recipe

# IMPORT DEPUIS LES UTILS (C'est beaucoup plus propre)
from src.utils.translations import PREFERENCE_TAGS_MAP

class UserProfiler:
    def __init__(self, db: Session):
        self.db = db

    def get_converted_tags(self, preferences: list) -> list:
        """Traduit les tags FR du front en tags EN pour la BDD"""
        if not preferences:
            return []
        
        # On utilise le dictionnaire importé
        # .get(p, p) signifie : si on trouve la traduction, on la prend.
        # Sinon, on garde le mot d'origine (au cas où le front envoie déjà de l'anglais ou un nouveau tag)
        return [PREFERENCE_TAGS_MAP.get(p, p) for p in preferences]

    def get_weighted_profile(self, user_id: int, request_tags: list = None):
        """
        Génère le vecteur utilisateur à la volée.
        """
        vectors = []
        
        # --- A. RÉCUPÉRATION ET TRADUCTION ---
        # 1. Préférences stockées
        user = self.db.query(User).filter(User.id == user_id).first()
        stored_prefs = user.preferences if user and user.preferences else []
        
        # 2. Préférences de la requête
        current_request = request_tags if request_tags else []
        
        # 3. Fusion et Traduction
        raw_tags = list(set(stored_prefs + current_request))
        active_tags = self.get_converted_tags(raw_tags)
        
        if active_tags:
            print(f"👤 [PROFILER] Tags actifs (EN) pour User {user_id}: {active_tags}")

        # --- B. VECTEURS D'INTENTION (Tags) ---
        if active_tags:
            for tag in active_tags:
                # Recherche élargie (Tags OU Titre)
                sample_recipes = self.db.query(Recipe).filter(
                    or_(
                        Recipe.tags.ilike(f"%{tag}%"),
                        Recipe.name.ilike(f"%{tag}%")
                    )
                ).filter(Recipe.embedding != None).limit(15).all()
                
                if sample_recipes:
                    tag_vectors = [self._parse_embedding(r.embedding) for r in sample_recipes]
                    avg_tag_vec = np.mean(tag_vectors, axis=0)
                    # Poids fort (x3)
                    vectors.extend([avg_tag_vec] * 3)
                else:
                    print(f"   ⚠️ Tag '{tag}' ignoré (aucune recette trouvée).")

        # --- C. VECTEUR HISTORIQUE (Interactions) ---
        interactions = self.db.query(Interaction).filter(
            Interaction.user_id == user_id, 
            Interaction.rating >= 4
        ).all()

        count_interactions = 0
        for interaction in interactions:
            if interaction.recipe and interaction.recipe.embedding:
                try:
                    vec = self._parse_embedding(interaction.recipe.embedding)
                    vectors.append(vec)
                    count_interactions += 1
                except:
                    continue
        
        if count_interactions > 0:
            print(f"   ⭐ [PROFILER] {count_interactions} recettes aimées intégrées.")

        # --- D. FUSION FINALE ---
        if not vectors:
            # Fallback : si on a vraiment rien, on ne plante pas, on renvoie None
            # Le Solver basculera en mode "Aléatoire" ou "Populaire"
            return None

        user_vector = np.mean(vectors, axis=0).tolist()
        return user_vector

    def _parse_embedding(self, embedding_field):
        if embedding_field is None: return []
        if isinstance(embedding_field, str): return json.loads(embedding_field)
        return embedding_field