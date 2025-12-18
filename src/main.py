from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import User
from src.recommender.profile_builder import UserProfiler
from src.optimization.menu_solver import MenuSolver

def main():
    # --- 1. Initialisation ---
    print("\n🚀 Démarrage de SmartRetail RecSys...")
    engine = create_engine("sqlite:///smartretail.db")
    session = Session(engine)
    
    # On prend notre user de test (généré par init_db)
    user = session.query(User).filter(User.username == "test_user_01").first()
    if not user:
        print("❌ Erreur : User de test introuvable.")
        return

    print(f"👤 Client identifié : {user.username}")
    print(f"   Préférences déclarées : {user.preferences}")

    # --- 2. IA : Recommandation (Ciblage) ---
    print("\n🧠 Analyse des goûts (Profiling)...")
    profiler = UserProfiler(session)
    
    # MODIFICATION ICI : On passe de 50 à 200 candidats pour avoir du stock après filtrage
    candidates, scores = profiler.recommend_candidates(user.id, limit=200)
    
    print(f"✅ {len(candidates)} recettes présélectionnées par l'IA.")
    print(f"   Top candidat : {candidates[0].name} (Match: {scores[0]:.1f}%)")

    # --- 3. OR : Optimisation (Planning) ---
    print("\n🧩 Génération du planning optimal (sous contraintes)...")
    solver = MenuSolver(candidates, scores)
    
    # Contraintes : Max 45 min de cuisine, Repas entre 500 et 1000 kcal
    weekly_menu = solver.solve(days=7, max_prep_time=45, max_calories_per_day=1200)

    # --- 4. Rendu Final ---
    if weekly_menu:
        print("\n" + "="*40)
        print(f"  MENU PERSONNALISÉ POUR {user.username.upper()}")
        print("="*40)
        
        total_score = 0
        total_cals = 0
        
        for day in weekly_menu:
            print(f"J{day['day']} | 🍽️ {day['recipe']}")
            print(f"     | Score IA: {day['score_match']:.1f}/10  🔥 {day['calories']} kcal  ⏱️ {day['time']} min")
            print("-" * 40)
            total_score += day['score_match']
            total_cals += day['calories']
            
        avg_score = total_score / 7
        avg_cals = total_cals / 7
        print(f"\n📊 Bilan :")
        print(f"   - Satisfaction Moyenne : {avg_score:.1f}/100")
        print(f"   - Apport Calorique Moyen : {avg_cals:.0f} kcal")
    else:
        print("❌ Impossible de générer un menu avec ces contraintes.")

if __name__ == "__main__":
    main()