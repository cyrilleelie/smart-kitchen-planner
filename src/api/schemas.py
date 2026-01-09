from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# MODÈLES POUR LE GÉNÉRATEUR DE MENUS
# ==========================================
class MenuRequest(BaseModel):
    user_id: int = Field(..., description="ID de l'utilisateur en base")
    days: int = Field(7, ge=1, le=14, description="Durée du planning (jours)")
    meals_per_day: int = Field(2, ge=1, le=3, description="Nombre de repas par jour")
    max_prep_time: int = Field(45, description="Temps max en cuisine (min)")
    target_calories_min: int = Field(400, description="Minimum calorique par repas")
    target_calories_max: int = Field(1200, description="Maximum calorique par repas")
    preferences: Optional[List[str]] = Field(default=[], description="Tags déclaratifs (ex: ['indian', 'vegetarian'])")

class MealItem(BaseModel):
    day: int
    recipe_name: str
    calories: float
    time: int
    match_score: float
    tags: List[str] = [] # Contiendra uniquement ["Découverte"] si applicable
    ingredients: List[str] = []  # Liste brute des ingrédients
    recipe_tags: List[str] = []  # Tags métadata de la recette (ex: "dessert", "winter")

class MenuResponse(BaseModel):
    status: str
    user: str
    plan: List[MealItem]
    stats: dict # Pour renvoyer la moyenne cal/score

class FeedbackRequest(BaseModel):
    user_id: int
    recipe_id: int
    rating: int

# ==========================================
# RECOMMANDATION CONTEXTUELLE (ENDPOINT SIMPLE)
# ==========================================
class ContextRequest(BaseModel):
    user_id: int
    meal_type: int = Field(..., description="0=Matin, 1=Midi, 2=Soir, 3=Snack")
    season: int = Field(..., description="0=Hiver, 1=Printemps, 2=Ete, 3=Automne")

class RecipeRecommendation(BaseModel):
    id: int
    name: str
    minutes: int
    score: float
    calories: float

# Nouveau modèle pour /generate-planning
class PlanningRequest(BaseModel):
    user_id: int = Field(..., description="ID Utilisateur")
    days: int = Field(7, description="Durée du planning")
    # Liste des IDs de repas (0, 1, 2, 3)
    selected_meals: List[int] = Field(..., description="0=Matin, 1=Midi, 2=Soir, 3=Snack") 
    season: int = Field(..., description="0=Hiver, 1=Printemps, 2=Ete, 3=Automne")
    target_calories: int = Field(600, description="Cible calorique par repas (ex: 500 kcal)")