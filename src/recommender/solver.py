from ortools.linear_solver import pywraplp

class MenuSolver:
    def __init__(self):
        # Création du solveur
        self.solver = pywraplp.Solver.CreateSolver('SCIP')

    def solve(self, candidates, target_calories, days=1, meals_per_day=3):
        if not candidates or not self.solver:
            return []

        # --- 1. VARIABLES & NETTOYAGE ---
        x = {}
        clean_candidates = []
        
        # BOUCLE SCANNER INTELLIGENTE
        # On ne présume plus de la position (0 ou 1), on scanne le contenu.
        for i, entry in enumerate(candidates):
            recipe = None
            score = 0.0 # Score par défaut si introuvable
            
            # Si entry n'est pas une liste/tuple (ex: juste un objet Recipe), on le traite comme une liste de 1 item
            iterable_entry = entry if isinstance(entry, (list, tuple)) else [entry]

            for item in iterable_entry:
                try:
                    # Est-ce un Score (Nombre) ?
                    if isinstance(item, (int, float)):
                        # On suppose que le score est petit (ex: < 100). 
                        # Si c'est énorme (ex: 500), c'est peut-être des calories qui trainent.
                        if item < 1000: 
                            score = float(item)
                    
                    # Est-ce une Recette (Objet avec attributs) ?
                    # On vérifie la présence de 'calories' et 'name'
                    elif hasattr(item, 'calories') and hasattr(item, 'name'):
                        recipe = item
                except:
                    continue
            
            # Si on a trouvé une recette valide dans ce bazar, on la garde
            if recipe:
                clean_candidates.append((recipe, score))
                # On crée la variable de décision pour le solveur
                idx = len(clean_candidates) - 1
                x[idx] = self.solver.BoolVar(f'x_{idx}')

        total_meals = days * meals_per_day
        
        # Sécurité : Si après nettoyage on a moins de recettes que de repas, on renvoie tout
        if len(clean_candidates) < total_meals:
            print(f"⚠️ Pas assez de candidats valides ({len(clean_candidates)}/{total_meals})")
            return [{"id": r.id, "name": r.name, "calories": r.calories, "score": s} for r, s in clean_candidates]

        # --- 2. CONTRAINTES ---
        
        # Tolérance calorique (+/- 10%)
        total_target = target_calories * days
        min_cal = total_target * 0.9
        max_cal = total_target * 1.1

        # Contrainte A : Nombre exact de repas
        self.solver.Add(self.solver.Sum([x[i] for i in range(len(clean_candidates))]) == total_meals)

        # Contrainte B : Calories
        calories_expr = self.solver.Sum([x[i] * (recipe.calories or 0) for i, (recipe, _) in enumerate(clean_candidates)])
        self.solver.Add(calories_expr >= min_cal)
        self.solver.Add(calories_expr <= max_cal)

        # --- 3. OBJECTIF ---
        # Maximiser le score
        objective = self.solver.Objective()
        for i, (recipe, score) in enumerate(clean_candidates):
            objective.SetCoefficient(x[i], score)
        objective.SetMaximization()

        # --- 4. RÉSOLUTION ---
        status = self.solver.Solve()

        solution = []
        if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
            for i, (recipe, score) in enumerate(clean_candidates):
                if x[i].solution_value() > 0.5:
                    solution.append({
                        "id": recipe.id,
                        "name": recipe.name,
                        "calories": recipe.calories,
                        "score": round(score, 2),
                        "tags": recipe.tags
                    })
        else:
            print("⚠️ Optimisation échouée (contraintes trop strictes ?), retour par défaut.")
            return [{"id": r.id, "name": r.name, "calories": r.calories, "score": s} for r, s in clean_candidates[:total_meals]]

        return solution