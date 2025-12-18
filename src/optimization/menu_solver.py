from ortools.sat.python import cp_model
from typing import List
from src.database.models import Recipe

class MenuSolver:
    def __init__(self, recipes: List[Recipe], scores: List[float]):
        self.recipes = recipes
        self.scores = [int(s * 10) for s in scores] # Conversion en entiers pour le solveur
        self.model = cp_model.CpModel()
        self.vars = {} 

    def solve(self, days=7, max_calories_per_day=2500, max_prep_time=60):
        print(f"🧩 Démarrage du solveur pour {days} jours (Filtre Dessert/Apéro ACTIF)...")
        
        # 1. Variables de décision
        for d in range(days):
            for r_idx, recipe in enumerate(self.recipes):
                self.vars[(d, r_idx)] = self.model.NewBoolVar(f'day_{d}_recipe_{r_idx}')

        # 2. CONTRAINTES

        # A. Unique : Exactement 1 recette par jour
        for d in range(days):
            self.model.Add(sum(self.vars[(d, r)] for r in range(len(self.recipes))) == 1)

        # B. Diversité : Une recette ne peut être mangée qu'une seule fois
        for r in range(len(self.recipes)):
            self.model.Add(sum(self.vars[(d, r)] for d in range(days)) <= 1)

        # C. Temps : Pas de recette trop longue
        for d in range(days):
            for r_idx, recipe in enumerate(self.recipes):
                if recipe.minutes > max_prep_time:
                    self.model.Add(self.vars[(d, r_idx)] == 0)

        # D. Budget Calories (Range pour un vrai repas)
        min_cal_per_meal = 400  
        for d in range(days):
            daily_cals = sum(self.vars[(d, r)] * int(self.recipes[r].calories or 0) 
                             for r in range(len(self.recipes)))
            self.model.Add(daily_cals <= max_calories_per_day)
            self.model.Add(daily_cals >= min_cal_per_meal)

        # E. NOUVEAU : Filtre "Vrai Repas" (Anti-Dessert/Apéro)
        # Liste noire de mots-clés trouvés couramment dans les tags Food.com
        forbidden_keywords = [
            'dessert', 'cookie', 'brownie', 'cake', 'pie', 'ice-cream', 'pudding', # Sucré
            'appetizer', 'dip', 'spread', 'finger-food', 'snack',                 # Grignotage
            'beverage', 'cocktail', 'shake', 'smoothie', 'drink'                  # Boissons
        ]

        skipped_count = 0
        for r_idx, recipe in enumerate(self.recipes):
            # On vérifie si un mot interdit est présent dans les tags de la recette
            is_forbidden = False
            if recipe.tags:
                # On check si un tag contient un mot interdit (ex: tag "desserts-fruit" contient "dessert")
                for tag in recipe.tags:
                    for keyword in forbidden_keywords:
                        if keyword in tag:
                            is_forbidden = True
                            break
                    if is_forbidden: break
            
            # Si interdit, on force la variable à 0 pour tous les jours
            if is_forbidden:
                skipped_count += 1
                for d in range(days):
                    self.model.Add(self.vars[(d, r_idx)] == 0)
        
        if skipped_count > 0:
            print(f"   🚫 {skipped_count} recettes ignorées (Desserts/Apéros/Boissons).")

        # 3. OBJECTIF : Maximiser le score total
        total_score = []
        for d in range(days):
            for r_idx, score in enumerate(self.scores):
                total_score.append(self.vars[(d, r_idx)] * score)
        
        self.model.Maximize(sum(total_score))

        # 4. RÉSOLUTION
        solver = cp_model.CpSolver()
        status = solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            return self._format_solution(solver, days)
        else:
            print("❌ Aucune solution trouvée (Trop de filtres ? Essayez d'augmenter le temps max ou les calories).")
            return None

    def _format_solution(self, solver, days):
        plan = []
        for d in range(days):
            for r_idx, recipe in enumerate(self.recipes):
                if solver.Value(self.vars[(d, r_idx)]) == 1:
                    plan.append({
                        "day": d + 1,
                        "recipe": recipe.name,
                        "calories": recipe.calories,
                        "time": recipe.minutes,
                        "score_match": self.scores[r_idx] / 10
                    })
        return plan