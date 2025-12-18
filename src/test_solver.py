import random
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import Recipe
from src.optimization.menu_solver import MenuSolver

def test_optimization():
    # 1. Connexion DB
    engine = create_engine("sqlite:///smartretail.db")
    session = Session(engine)
    
    # 2. Récupération d'un pool de candidats (ex: 100 recettes aléatoires)
    # Dans la vraie vie, ce seraient les 100 recettes pré-sélectionnées par l'IA
    candidates = session.query(Recipe).filter(Recipe.calories > 0).limit(100).all()
    
    if not candidates:
        print("Erreur: Pas de recettes en base.")
        return

    print(f"Input : {len(candidates)} recettes candidates.")

    # 3. Simulation des scores IA (Mocking)
    # On donne un score aléatoire entre 0 et 100 à chaque recette
    scores = [random.uniform(0, 100) for _ in candidates]

    # 4. Lancement du Solveur
    solver = MenuSolver(candidates, scores)
    
    # Essai avec contrainte : Max 40 min de prépa par jour
    weekly_menu = solver.solve(days=7, max_prep_time=40, max_calories_per_day=2500)

    # 5. Affichage
    if weekly_menu:
        print("\n--- 📅 MENU DE LA SEMAINE ---")
        total_cals = 0
        for day in weekly_menu:
            print(f"Jour {day['day']}: {day['recipe']} "
                  f"(⏱️ {day['time']}m | 🔥 {day['calories']} kcal | ❤️ Score: {day['score_match']})")
            total_cals += day['calories']
        print(f"-----------------------------")
        print(f"Moyenne Calories/J : {total_cals/7:.0f}")

if __name__ == "__main__":
    test_optimization()