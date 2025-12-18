import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import User, Recipe
from src.recommender.profile_builder import UserProfiler
from sklearn.metrics.pairwise import cosine_similarity

def retrain_user_profile(user_id: int):
    print(f"🛠️ MLOps PIPELINE : Recalibrage du profil User #{user_id}...")
    
    engine = create_engine("sqlite:///smartretail.db")
    with Session(engine) as session:
        profiler = UserProfiler(session)
        
        # 1. L'Ancien Monde (Sans Time Decay)
        old_vector = profiler.get_user_vector(user_id, use_decay=False)
        if old_vector is None:
            print("❌ Erreur : Pas assez de données pour recalculer.")
            return

        # 2. Le Nouveau Monde (Avec Time Decay - Réentraînement)
        new_vector = profiler.get_user_vector(user_id, use_decay=True)
        
        # 3. Mesure du changement (Distance entre les deux vecteurs)
        # Si similarity < 0.99, c'est que le profil a significativement bougé
        shift = cosine_similarity(old_vector.reshape(1, -1), new_vector.reshape(1, -1))[0][0]
        distance = 1 - shift
        
        print(f"   📊 Distance de Drift corrigée : {distance:.4f}")
        
        if distance > 0.001:
            print("✅ SUCCÈS : Le profil a été mis à jour pour ignorer le passé obsolète.")
        else:
            print("⚠️ AVERTISSEMENT : Le profil n'a pas beaucoup bougé (Peut-être pas assez de nouvelles données ?)")

        # 4. Vérification Sémantique (Qu'est-ce qu'on recommande maintenant ?)
        print("\n🔎 VÉRIFICATION DES RECOMMANDATIONS (Top 3) :")
        
        print("--- AVANT (Obsolète) ---")
        # Simulation manuelle de recherche avec l'ancien vecteur
        all_recipes = session.query(Recipe).filter(Recipe.embedding != None).all()
        recipe_vectors = np.array([np.array(r.embedding) for r in all_recipes])
        
        sim_old = cosine_similarity(old_vector.reshape(1, -1), recipe_vectors)[0]
        top_old = np.argsort(sim_old)[::-1][:3]
        for idx in top_old:
            print(f"   - {all_recipes[idx].name}")

        print("\n--- APRÈS (Recalibré) ---")
        sim_new = cosine_similarity(new_vector.reshape(1, -1), recipe_vectors)[0]
        top_new = np.argsort(sim_new)[::-1][:3]
        for idx in top_new:
            print(f"   - {all_recipes[idx].name}")

if __name__ == "__main__":
    retrain_user_profile(user_id=1)