import os
import joblib
import spacy
import pandas as pd
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from src.database.models import Recipe
from src.utils.constants import STOP_WORDS_METIER

ARTIFACTS_DIR = "/app/data/artifacts"
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

class DataPipeline:
    def __init__(self, db: Session):
        self.db = db
        try:
            self.nlp = spacy.load("en_core_web_sm")
            # Optimisation : On désactive les composants inutiles pour aller plus vite
            self.nlp.disable_pipes(["parser", "ner"]) 
        except OSError:
            print("⚠️ Modèle Spacy non trouvé. Run: python -m spacy download en_core_web_sm")
            self.nlp = None

        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=1000,
            dtype='float32'
        )

    def _clean_text(self, text_list):
        """
        Nettoyage NLP V2 : Lemmatisation + Filtrage Métier Custom
        """
        if not text_list:
            return ""
        
        # Nettoyage structurel basique
        clean_str = str(text_list).replace("[", "").replace("]", "").replace("'", "").replace(",", " ")
        
        if not self.nlp:
            return clean_str.lower()

        # Tokenization via Spacy
        doc = self.nlp(clean_str.lower())
        
        tokens = []
        for token in doc:
            # 1. On garde le lemme (racine du mot)
            lemma = token.lemma_
            
            # 2. FILTRE DRASTIQUE
            if (not token.is_stop and         # Pas un mot vide anglais (the, a, is...)
                not token.is_punct and        # Pas de ponctuation
                len(lemma) > 2 and            # Pas de mots de 1 ou 2 lettres
                lemma not in STOP_WORDS_METIER): # Pas dans notre liste noire
                
                tokens.append(lemma)
        
        return " ".join(tokens)

    def run_pipeline(self):
        print("🚀 Démarrage du Pipeline ETL (V2 - Hard Cleaning)...")

        # 1. EXTRACT
        recipes = self.db.query(Recipe).all()
        if not recipes:
            print("❌ Aucune recette.")
            return

        print(f"📦 Extraction : {len(recipes)} recettes.")
        
        df = pd.DataFrame([{
            'id': r.id, 
            'tags': r.tags, 
            'ingredients': r.ingredients
        } for r in recipes])

        # 2. TRANSFORM
        print("🧹 Nettoyage NLP Avancé... (Patience)")
        # On donne plus de poids aux tags (x2) qu'aux ingrédients
        # Astuce : on répète la colonne tags pour qu'elle pèse plus lourd dans le TF-IDF
        df['combined_text'] = df['tags'] + " " + df['tags'] + " " + df['ingredients']
        df['processed_text'] = df['combined_text'].apply(self._clean_text)

        # 3. VECTORIZE
        print("🧮 Calcul TF-IDF...")
        tfidf_matrix = self.vectorizer.fit_transform(df['processed_text'])
        
        feature_names = self.vectorizer.get_feature_names_out()
        print(f"✨ Nouveau Vocabulaire (Top 10): {feature_names[:10]}")

        # 4. LOAD
        print("💾 Sauvegarde...")
        joblib.dump(self.vectorizer, os.path.join(ARTIFACTS_DIR, "tfidf_vectorizer.pkl"))
        joblib.dump(tfidf_matrix, os.path.join(ARTIFACTS_DIR, "tfidf_matrix.pkl"))
        joblib.dump(df['id'].tolist(), os.path.join(ARTIFACTS_DIR, "recipe_ids.pkl"))

        print("✅ Pipeline terminé !")