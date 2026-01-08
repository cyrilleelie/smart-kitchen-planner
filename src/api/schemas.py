from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# PARTIE 1 : GÉNÉRATEUR DE MENUS (Existant)
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
# PARTIE 2 : MOTEUR DE RECOMMANDATION (Nouveau)
# ==========================================
class UserRequest(BaseModel):
    """Ce que l'utilisateur envoie pour une recherche par ingrédients"""
    ingredients: List[str] = Field(..., description="Liste d'ingrédients (ex: ['chicken', 'rice'])")

class RecipeResponse(BaseModel):
    """Ce que l'API renvoie pour afficher une recette"""
    id: int
    name: str
    minutes: int
    tags: str 
    ingredients: str 
    description: Optional[str] = None
    
    class Config:
        from_attributes = True # Permet de convertir directement depuis l'objet SQLAlchemy