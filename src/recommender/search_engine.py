import numpy as np
import ast
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import Recipe

def search_recipes(query_text: str, top_k=5):
    print(f"🔎 Recherche pour : '{query_text}'")
    
    # 1. Connexion et Chargement
    engine = create_engine("sqlite:///smartretail.db")
    session = Session(engine)
    
    # On récupère toutes les recettes
    # Note: En prod, on utiliserait une base vectorielle (Milvus/FAISS), 
    # mais pour 5000 recettes, Numpy en mémoire est ultra-rapide (<10ms).
    recipes = session.query(Recipe).all()
    
    # --- CHECK DE SÉCURITÉ (Au cas où le vectorizer a échoué) ---
    valid_recipes = [r for r in recipes if r.embedding is not None]
    if not valid_recipes:
        print("❌ ERREUR CRITIQUE : Aucune recette n'a d'embedding !")
        print("👉 Solution : Ouvrez src/recommender/vectorizer.py")
        print("   Changez la ligne: .filter(Recipe.embedding == None)")
        print("   Par: .filter(Recipe.id > 0) # Pour forcer la mise à jour")
        return

    print(f"📚 Index chargé : {len(valid_recipes)} recettes vectorisées.")

    # 2. Vectorisation de la requête (Query)
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_vector = model.encode([query_text]) # Forme (1, 384)

    # 3. Préparation de la matrice des recettes
    # On empile tous les vecteurs dans une grosse matrice Numpy
    # Cela permet de faire le calcul de similarité en une seule opération matricielle
    corpus_embeddings = np.array([np.array(r.embedding) for r in valid_recipes])
    
    # 4. Calcul de similarité (Cosine Similarity)
    # Résultat : tableau de scores entre -1 et 1 pour chaque recette
    similarities = cosine_similarity(query_vector, corpus_embeddings)[0]
    
    # 5. Tri et Affichage des meilleurs résultats
    # On récupère les indices des top_k scores
    top_indices = np.argsort(similarities)[::-1][:top_k]
    
    print(f"\n🏆 Top {top_k} Recettes recommandées :")
    print("-" * 50)
    for idx in top_indices:
        score = similarities[idx]
        recipe = valid_recipes[idx]
        print(f"[{score:.4f}] {recipe.name} (⏱️ {recipe.minutes}m)")
        # Affiche les tags pour vérifier pourquoi c'est pertinent
        print(f"   Tags: {recipe.tags[:5]}...") 

if __name__ == "__main__":
    # Testez avec une requête qui n'est pas un mot-clé exact pour voir la puissance de l'IA
    # Ex: "Something spicy for a party" trouvera des tacos même sans le mot "party" si le contexte s'y prête.
    search_recipes("healthy breakfast with fruit", top_k=5)