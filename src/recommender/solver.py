from ortools.linear_solver import pywraplp

class MenuSolver:
    def __init__(self, candidates, days=1, target_calories=2000):
        self.candidates = candidates
        self.days = days
        self.target_calories = target_calories
        self.meals_per_day = 3 # Simplification pour le planning (Midi/Soir)

    def solve(self, fridge_ingredients=None):
        """
        Résout le problème d'optimisation avec contraintes.
        """
        solver = pywraplp.Solver.CreateSolver('SCIP')
        if not solver:
            return []

        # Variables : x[i] = 1 si la recette i est choisie, 0 sinon
        x = {}
        for i in range(len(self.candidates)):
            x[i] = solver.BoolVar(f'recipe_{i}')

        # --- 1. IDENTIFICATION DES RECETTES "FRIGO" ---
        fridge_indices = [] # On stocke les indices des recettes qui matchent
        
        if fridge_ingredients:
            for i, (recipe, score) in enumerate(self.candidates):
                ing_str = str(recipe.ingredients).lower()
                # Si un des ingrédients du frigo est dans la recette
                if any(item.lower() in ing_str for item in fridge_ingredients):
                    fridge_indices.append(i)

        # --- 2. CONTRAINTES DE BASE ---
        
        # A. Nombre de repas exact (ex: 5 jours * 2 repas = 10 recettes)
        total_meals = self.days * self.meals_per_day
        solver.Add(solver.Sum([x[i] for i in range(len(self.candidates))]) == total_meals)

        # B. Calories (Moyenne sur la période) +/- 10%
        total_target = self.target_calories * self.days
        calories_sum = solver.Sum([x[i] * self.candidates[i][0].calories for i in range(len(self.candidates))])
        solver.Add(calories_sum >= total_target * 0.9)
        solver.Add(calories_sum <= total_target * 1.1)

        # --- 3. CONTRAINTE INTELLIGENTE "VIDE-FRIGO" ---
        if fridge_indices:
            # RÈGLE : On veut utiliser le frigo, mais pas à tous les repas !
            # On impose : Au moins 1 fois, mais au maximum 2 fois.
            
            # 1. Au moins une recette du frigo (si possible)
            solver.Add(solver.Sum([x[i] for i in fridge_indices]) >= 1)
            
            # 2. Pas plus de 2 recettes du frigo (pour la variété)
            solver.Add(solver.Sum([x[i] for i in fridge_indices]) <= 2)

        # --- 4. OBJECTIF : MAXIMISER LE SCORE ---
        objective = solver.Objective()
        
        for i, (recipe, score) in enumerate(self.candidates):
            # Le score de base (Goûts IA)
            final_weight = score
            
            # Si c'est une recette frigo, on ajoute un petit bonus
            # pour qu'elle soit choisie en priorité parmi les slots disponibles (1 ou 2)
            if i in fridge_indices:
                final_weight += 0.5 

            objective.SetCoefficient(x[i], final_weight)
            
        objective.SetMaximization()

        # --- RÉSOLUTION ---
        status = solver.Solve()

        if status == pywraplp.Solver.OPTIMAL:
            selected_indices = [i for i in range(len(self.candidates)) if x[i].solution_value() > 0.5]
            return [self.candidates[i][0] for i in selected_indices]
        else:
            print("⚠️ Aucune solution optimale. Relaxez les contraintes.")
            return []