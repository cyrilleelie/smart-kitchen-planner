from src.database.models import Recipe


def extract_explicit_features(recipe: Recipe) -> dict:
    """
    Extract explicit boolean features from a recipe to help the ML model
    understand context (Breakfast vs Dinner, Winter vs Summer).

    Returns a dict of features (0/1).
    """
    name = str(recipe.name).lower() if recipe.name else ""
    tags = str(recipe.tags).lower() if recipe.tags else ""

    # Combined text for search
    text = name + " " + tags

    features = {
        "is_breakfast": 0,
        "is_dishes": 0,  # Main dishes
        "is_light": 0,  # Salads, etc.
        "is_winter_comfort": 0,
        "is_summer_fresh": 0,
    }

    # 1. Breakfast Detect
    breakfast_kw = [
        "breakfast",
        "brunch",
        "pancake",
        "waffle",
        "egg",
        "omelet",
        "cereal",
        "yogurt",
        "fruit",
        "muffin",
        "toast",
        "coffee",
        "tea",
        "bread",
    ]
    if any(k in text for k in breakfast_kw):
        features["is_breakfast"] = 1

    # 2. Main Dishes (Dinner/Lunch)
    main_kw = [
        "steak",
        "chicken",
        "beef",
        "pork",
        "pasta",
        "curry",
        "roast",
        "stew",
        "burger",
        "pizza",
        "lasagna",
        "main-dish",
    ]
    if any(k in text for k in main_kw):
        features["is_dishes"] = 1

    # 3. Light / Summer
    light_kw = [
        "salad",
        "smoothie",
        "ice cream",
        "sorbet",
        "gazpacho",
        "summer",
        "fresh",
        "wrap",
    ]
    if any(k in text for k in light_kw):
        features["is_light"] = 1
        features["is_summer_fresh"] = 1

    # 4. Winter / Comfort
    winter_kw = [
        "soup",
        "stew",
        "roast",
        "chowder",
        "chili",
        "winter",
        "comfort",
        "hot",
    ]
    if any(k in text for k in winter_kw):
        features["is_winter_comfort"] = 1

    return features
