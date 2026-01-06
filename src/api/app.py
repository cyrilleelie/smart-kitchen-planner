from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, not_
from typing import List, Optional
from datetime import datetime
from collections import Counter

# Imports internes
from src.database.connection import get_db
from src.database.init_db import init_database
from src.database.models import User, Interaction, Recipe
from src.recommender.profile_builder import UserProfiler
from src.recommender.solver import MenuSolver

# --- NOUVEAUX IMPORTS (Moteur de Recommandation) ---
from src.recommender.content_engine import ContentEngine
from src.api.schemas import UserRequest, RecipeResponse

# --- LIFESPAN (Gestion du cycle de vie) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌍 Démarrage de l'API Smart Retail...")
    
    # 1. Chargement du ContentEngine (Lourd)
    # On le stocke dans app.state pour qu'il soit accessible partout
    try:
        app.state.recsys = ContentEngine()
    except Exception as e:
        print(f"⚠️ Erreur chargement ContentEngine: {e}")
        app.state.recsys = None
    
    yield
    print("🛑 Arrêt de l'API...")

# Initialisation de l'app avec le lifespan
app = FastAPI(title="Smart Retail API", lifespan=lifespan)

# --- Modèles Pydantic ---
class MenuRequest(BaseModel):
    user_id: int
    days: int
    target_calories: int
    fridge_items: Optional[List[str]] = None

class FeedbackRequest(BaseModel):
    user_id: int
    recipe_id: int
    rating: int 

# --- Constantes ---
TAG_BLACKLIST = {
    "main-ingredient", "low-in-something", "dietary", "occasion", "course", 
    "preparation", "equipment", "technique", "number-of-servings", "meat", 
    "vegetables", "fruit", "time-to-make", "easy", "beginner-cook", 
    "inexpensive", "healthy", "healthy-2", "5-minutes-or-less", 
    "15-minutes-or-less", "30-minutes-or-less", "60-minutes-or-less", 
    "4-hours-or-less", "less-thans", "low-sodium", "low-cholesterol", 
}

# ==========================================
# 🚀 ROUTE 1 : RECOMMANDATION IA (Ingrédients)
# ==========================================
@app.post("/recommend", response_model=List[RecipeResponse])
def get_recommendations(request: UserRequest, db: Session = Depends(get_db)):
    """
    Moteur de recommandation basé sur le contenu (Ingrédients).
    Utilise le ContentEngine chargé au démarrage.
    """
    if not hasattr(app.state, 'recsys') or app.state.recsys is None:
        raise HTTPException(status_code=503, detail="Moteur de recommandation non chargé.")

    # 1. Appel au moteur (via app.state)
    recipe_ids = app.state.recsys.recommend(request.ingredients, top_k=5)
    
    if not recipe_ids:
        return []

    # 2. Récupération des infos en BDD
    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
    
    # 3. Réordonnancement (SQL ne garantit pas l'ordre)
    recipe_map = {r.id: r for r in recipes}
    ordered_recipes = [recipe_map[rid] for rid in recipe_ids if rid in recipe_map]
    
    return ordered_recipes

# ==========================================
# 🚀 ROUTE 2 : FEEDBACK UTILISATEUR
# ==========================================
@app.post("/feedback")
def submit_feedback(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """Enregistre ou met à jour la note d'un utilisateur pour une recette."""
    # Vérifier si l'interaction existe déjà
    interaction = db.query(Interaction).filter(
        Interaction.user_id == feedback.user_id,
        Interaction.recipe_id == feedback.recipe_id
    ).first()

    if interaction:
        interaction.rating = feedback.rating
        interaction.timestamp = datetime.utcnow()
    else:
        new_interaction = Interaction(
            user_id=feedback.user_id,
            recipe_id=feedback.recipe_id,
            rating=feedback.rating,
            timestamp=datetime.utcnow()
        )
        db.add(new_interaction)
    
    db.commit()
    return {"status": "success", "message": "Feedback enregistré"}

# ==========================================
# 🚀 ROUTE 3 : PROFIL UTILISATEUR
# ==========================================
@app.get("/user/{user_id}/profile")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Génère le profil culinaire de l'utilisateur basé sur ses notes."""
    profiler = UserProfiler(db)
    profile = profiler.get_profile(user_id)
    
    if not profile:
        raise HTTPException(status_code=404, detail="Utilisateur ou interactions introuvables")
        
    return profile

# ==========================================
# 🚀 ROUTE 4 : GÉNÉRATEUR DE MENU
# ==========================================
@app.post("/generate_menu")
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    profiler = UserProfiler(db)
    user_profile = profiler.get_profile(request.user_id)
    
    # Instanciation du solveur
    solver = MenuSolver(
        db=db,
        user_profile=user_profile,
        days=request.days,
        target_calories=request.target_calories
    )
    
    # Génération
    menu = solver.solve()
    
    # Formatage de la réponse
    menu_response = []
    total_cals = 0
    
    for day, recipe_id in enumerate(menu):
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        score = solver.calculate_score(recipe)
        
        # Calcul précis des calories (si dispo)
        try:
            nutr = eval(recipe.nutrition) # [cal, fat, sugar...]
            cals = nutr[0]
        except:
            cals = 500 # Valeur par défaut
            
        total_cals += cals
        
        menu_response.append({
            "day": day + 1,
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "calories": cals,
            "match_score": score
        })

    return {
        "menu": menu_response,
        "meta": {
            "total_calories": total_cals,
            "days": request.days
        }
    }

# ==========================================
# 🚀 ROUTE 5 : INTERACTIONS & EXPLORATION
# ==========================================
@app.get("/user/{user_id}/interactions")
def get_user_interactions(user_id: int, db: Session = Depends(get_db)):
    """Récupère l'historique complet des notes de l'utilisateur"""
    interactions = db.query(Interaction).filter(Interaction.user_id == user_id).all()
    return {i.recipe_id: i.rating for i in interactions}

@app.get("/explore")
def explore_recipes(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """Renvoie des recettes aléatoires que l'utilisateur n'a JAMAIS notées."""
    rated_subquery = db.query(Interaction.recipe_id).filter(
        Interaction.user_id == user_id
    )
    candidates = db.query(Recipe).filter(
        Recipe.id.notin_(rated_subquery)
    ).order_by(func.random()).limit(limit).all()
    
    return candidates