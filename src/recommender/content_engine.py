import os
import joblib
import spacy
from sklearn.metrics.pairwise import linear_kernel
# IMPORT CENTRALISÉ
from src.utils.constants import STOP_WORDS_METIER 

# Chemins
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "data", "artifacts")

class ContentEngine:
    def __init__(self):
        """
        Charge le cerveau (Vecteurs + Modèle) en mémoire au démarrage.
        """
        print("🧠 Chargement du ContentEngine...")
        try:
            self.vectorizer = joblib.load(os.path.join(ARTIFACTS_DIR, "tfidf_vectorizer.pkl"))
            self.tfidf_matrix = joblib.load(os.path.join(ARTIFACTS_DIR, "tfidf_matrix.pkl"))
            self.recipe_ids = joblib.load(os.path.join(ARTIFACTS_DIR, "recipe_ids.pkl"))
            
            # Chargement NLP
            self.nlp = spacy.load("en_core_web_sm")
            self.nlp.disable_pipes(["parser", "ner"])
            
            print(f"✅ ContentEngine prêt. {len(self.recipe_ids)} recettes indexées.")
        except FileNotFoundError:
            print("⚠️ Artifacts manquants. Avez-vous lancé le pipeline ETL ?")
            self.vectorizer = None

    def _clean_query(self, query: str) -> str:
        """Nettoie la requête utilisateur comme on a nettoyé les recettes."""
        if not query:
            return ""
        
        doc = self.nlp(query.lower())
        tokens = [
            token.lemma_ for token in doc 
            if (not token.is_stop and not token.is_punct and 
                len(token.lemma_) > 2 and 
                token.lemma_ not in STOP_WORDS_METIER) # Utilisation de la liste partagée
        ]
        return " ".join(tokens)

    def recommend(self, user_ingredients: list[str], top_k=5) -> list[int]:
        """
        Entrée : Liste d'ingrédients (ex: ['chicken', 'rice', 'salt'])
        Sortie : Liste d'IDs de recettes
        """
        if not self.vectorizer:
            return []

        # 1. On transforme la liste d'ingrédients en une seule chaîne propre
        raw_query = " ".join(user_ingredients)
        clean_query = self._clean_query(raw_query)
        
        print(f"🔎 Recherche pour : '{clean_query}' (Brut: {user_ingredients})")

        if not clean_query:
            print("⚠️ Attention : La requête nettoyée est vide (tous les mots étaient des stop-words).")
            return []

        # 2. Vectorisation de la demande
        query_vec = self.vectorizer.transform([clean_query])

        # 3. Calcul de similarité (Cosine Similarity)
        cosine_sim = linear_kernel(query_vec, self.tfidf_matrix).flatten()

        # 4. Tri des résultats
        top_indices = cosine_sim.argsort()[-top_k:][::-1]

        # 5. Conversion Indices -> IDs Recettes
        recommended_ids = [self.recipe_ids[i] for i in top_indices]
        
        # Debug : Afficher les scores
        for i, idx in enumerate(top_indices):
            # On récupère le score pour info
            score = cosine_sim[idx]
            if score > 0:
                print(f"   #{i+1} ID {self.recipe_ids[idx]} (Score: {score:.4f})")
            
        return recommended_ids