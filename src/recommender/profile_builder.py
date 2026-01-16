import json
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.database.models import User, Interaction, Recipe
import logging
import json

logger = logging.getLogger(__name__)

# IMPORT DEPUIS LES UTILS (C'est beaucoup plus propre)
from src.utils.translations import PREFERENCE_TAGS_MAP

class UserProfiler:
    """
    Builds a weighted user profile vector from explicit preferences and implicit interactions.
    
    Attributes:
        db (Session): SQLAlchemy database session
    """
    
    def __init__(self, db: Session):
        """
        Initialize the UserProfiler.

        Args:
            db: Active database session
        """
        self.db = db

    def get_converted_tags(self, raw_tags: list[str]) -> list[str]:
        """
        Convert raw UI tags (French) to internal tags (English).

        Args:
            raw_tags: List of tags in French (e.g. ['Véxétarien'])

        Returns:
            List[str]: List of corresponding English tags (e.g. ['vegetarian']).
        """
        # On nettoie et on mappe
        clean_tags = []
        for tag in raw_tags:
            t = tag.strip()
            if t in PREFERENCE_TAGS_MAP:
                clean_tags.append(PREFERENCE_TAGS_MAP[t])
        return clean_tags

    def get_weighted_profile(self, user_id: int, request_tags: list[str] = None) -> np.ndarray | None:
        """
        Compute the weighted average vector for a user.

        Combines:
        1. Explicit Preference Vectors (from tags) - weighted x3
        2. Implicit Interaction Vectors (from liked recipes) - weighted x1

        Args:
            user_id: ID of the user
            request_tags: List of explicit preference tags (French)

        Returns:
            np.ndarray | None: The 384-dimensional user vector, or None if Cold Start.
        """
        vectors = []
        
        # --- A. RÉCUPÉRATION ET TRADUCTION ---
        # 1. Préférences stockées
        user = self.db.query(User).filter(User.id == user_id).first()
        stored_prefs = user.preferences if user and user.preferences else []
        
        # 2. Préférences de la requête
        current_request = request_tags if request_tags else []
        
        # 3. Fusion et Traduction
        raw_tags_combined = list(set(stored_prefs + current_request))
        active_tags = self.get_converted_tags(raw_tags_combined)
        
        if active_tags:
            logger.info(f"👤 [PROFILER] Tags actifs (EN) pour User {user_id}: {active_tags}")

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
                    # Filter out empty lists from parsing errors
                    tag_vectors = [vec for vec in tag_vectors if vec]
                    if tag_vectors:
                        avg_tag_vec = np.mean(tag_vectors, axis=0)
                        # Poids fort (x3)
                        vectors.extend([avg_tag_vec] * 3)
                else:
                    logger.warning(f"   ⚠️ Tag '{tag}' ignoré (aucune recette trouvée).")

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
                    if vec: # Ensure embedding was successfully parsed
                        vectors.append(vec)
                        count_interactions += 1
                except Exception as e:
                    logger.warning(f"Failed to parse embedding for recipe {interaction.recipe.id}: {e}")
                    continue
        
        if count_interactions > 0:
            logger.info(f"   ⭐ [PROFILER] {count_interactions} recettes aimées intégrées.")

        # --- D. FUSION FINALE ---
        if not vectors:
            # Fallback : si on a vraiment rien, on ne plante pas, on renvoie None
            # Le Solver basculera en mode "Aléatoire" ou "Populaire"
            return None

        # Moyenne pondérée
        final_vector = np.mean(vectors, axis=0)
        return final_vector.astype(np.float32)

    def _parse_embedding(self, embedding_field: str | list | None) -> list | Any:
        """
        Parse embedding field safely.

        Args:
            embedding_field: Raw embedding data from DB (str or list)

        Returns:
            list: Parsed embedding list or empty list if failure.
        """
        if embedding_field is None: return []
        if isinstance(embedding_field, str): 
            try:
                return json.loads(embedding_field)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON for embedding: {embedding_field[:50]}...")
                return []
        return embedding_field