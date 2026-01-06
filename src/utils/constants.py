# Fichier: src/utils/constants.py

STOP_WORDS_METIER = {
    # --- 1. Ingrédients "Utilitaires" ---
    "salt", "pepper", "oil", "water", "sugar", "flour", "butter", 
    "vegetable", "olive", "virgin", "extra", 
    "extract", "leavening",
    "absolut", # Marque (Votre ajout)
    
    # --- 2. Unités, Contenants & Formes ---
    "cup", "teaspoon", "tablespoon", "ounce", "pound", "gram", "tbsp", "tsp", "oz", "lb",
    "half", "can", "jar", "bag", "box", "package", "spray",
    "cube", "bar", "drop", "slice", "piece", "pinch",
    
    # --- 3. Verbes & Actions ---
    "chop", "dice", "mince", "peel", "cut", "add", "use", "make", "cook", "prepare",
    "whip", "mix", "freeze", "rise", "grind", "rub", "spread", "dress", "reduce", "serve",
    "hand", "active", # "Active yeast" (Votre ajout)
    
    # --- 4. Adjectifs & États ---
    "ground", "powder", "fresh", "freshly", "dry", "dried", 
    "large", "small", "medium", "long", "flat", "hard", "soft",
    "hot", "cold", "warm", "high", "low",
    "quick", "instant", "easy", "simple", "old", "new",
    "friendly", "healthy", "light", "skinless", "boneless",
    "free", "saturate", "calorie", "lean", "plain", "heavy", "pure", "raw",
    "semi", "condense", "confectioner", "evaporate",
    "self", "non", 
    
    # --- 5. Styles, Marketing & Marques ---
    "copycat", "novelty", "historical", "comfort", "scratch", "oamc", "ahead",
    "ranch", "a.1", 
    "preserve",
    
    # --- 6. Structure & Métadonnées ---
    "dish", "main", "recipe", "ingredient", "instruction", "time", "minute", "hour", "year",
    "taste", "mood", "texture", "flavor", "style", "casserole",
    "food", "meal", "cooking", "appliance", "purpose", "etc",
    
    # --- 7. Géographie (Bruitée) ---
    "north", "south", "east", "west", "northeastern", "eastern", "middle", "central",
    "states", "united", "unite", "state",
    
    # --- 8. Occasions ---
    "holiday", "event", "party", "celebration", "gift", "superbowl",
    "christmas", "thanksgive", "thanksgiving", "valentine", "independence", "picnic",
    "summer", "winter", "fall", "autumn", "spring", "seasonal",
    "weeknight", "weekend",
    "dinner", "lunch", "breakfast", "brunch", "snack", "appetizer", "beverage", "supper", "side",
    "kid", "toddler", "baby",
    "romantic", 
    
    # --- 9. Divers ---
    "leaf", "flake", "refrigerator", "freezer"
}