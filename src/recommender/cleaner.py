class TagCleaner:
    # 1. BRUIT : Tout ce qui est technique, temps, difficulté ou générique
    # On utilise des mots-clés pour attraper "60-minutes", "preparation", etc.
    NOISE_PATTERNS = [
        "preparation", "time-to-make", "course", "main-ingredient", "dietary",
        "occasion", "equipment", "cuisine", "number-of-servings", "technique",
        "minutes", "hours", "steps", "easy", "beginner", "inexpensive",
        "oven", "stove", "microwave", "pot", "pan", "blender",
        "presentation", "served", "guide", "for-1-or-2", "for-large-groups",
        "healthy-2", "low-in-something" # Ajouts basés sur votre audit
    ]

    # 2. DIÈTE : On garde (utile pour filtrer)
    DIET_KEYWORDS = [
        "low-", "free", "healthy", "vegan", "vegetarian", "diet", "light"
    ]

    # 3. TYPE DE REPAS : On garde (utile pour le contexte)
    MEAL_KEYWORDS = [
        "main-dish", "side-dish", "dessert", "lunch", "dinner", "breakfast",
        "salad", "soup", "stew", "appetizer", "snack", "drink", "beverage"
    ]

    @staticmethod
    def get_tag_category(tag):
        tag = tag.lower().strip()
        
        # Vérification Bruit
        for noise in TagCleaner.NOISE_PATTERNS:
            if noise in tag:
                return "NOISE"
                
        # Vérification Diète
        for diet in TagCleaner.DIET_KEYWORDS:
            if diet in tag:
                return "DIET"
                
        # Vérification Type
        for meal in TagCleaner.MEAL_KEYWORDS:
            if meal in tag:
                return "MEAL"
        
        # Si ça passe tous les filtres, c'est probablement un INGRÉDIENT ou une SAVEUR
        return "FLAVOR"