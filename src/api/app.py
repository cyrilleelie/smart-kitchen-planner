import ast
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

# --- IMPORTS INTERNES ---
from src.database.connection import get_db
from src.database.models import User, Interaction, Recipe
from src.recommender.profile_builder import UserProfiler
from src.recommender.solver import MenuSolver

# --- SCHEMAS (Pydantic) ---
# Note : UserRequest et RecipeResponse ont été supprimés car inutiles
from src.api.schemas import (
    MenuRequest, MenuResponse, MealItem,
    FeedbackRequest
)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌍 Démarrage de l'API Smart Retail...")
    yield
    print("🛑 Arrêt de l'API...")

# Initialisation
app = FastAPI(title="Smart Retail API", version="2.4-lite", lifespan=lifespan)


# ==========================================
# 1. GESTION DES PRÉFÉRENCES
# ==========================================
@app.put("/user/{user_id}/preferences")
def update_user_preferences(user_id: int, preferences: List[str] = Body(...), db: Session = Depends(get_db)):
    """
    Met à jour les préférences déclarées de l'utilisateur.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.preferences = preferences 
    db.commit()
    db.refresh(user)
    
    return {"status": "success", "preferences": user.preferences}


# ==========================================
# 2. GÉNÉRATEUR DE MENUS (Core Feature)
# ==========================================
@app.post("/generate-menu", response_model=MenuResponse)
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    # A. Profiling
    profiler = UserProfiler(db)
    user_vector = profiler.get_weighted_profile(
        request.user_id, 
        request.preferences
    )

    # B. Solving
    solver = MenuSolver(
        db=db,
        user_vector=user_vector, 
        days=request.days,
        target_calories=request.target_calories_min,
        meals_per_day=request.meals_per_day
    )
    
    recommended_menu = solver.solve()
    
    # C. Construction de la réponse
    plan_items = []
    total_score = 0
    total_cals_accumulated = 0
    
    for item in recommended_menu:
        day_num = item["day"]
        recipe_id = item["recipe_id"]
        algo_type = item["algo_type"] # "PERF", "DISCO", "RESCUE"
        raw_score = item["score"]

        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe: continue
            
        # Parsing Calories
        cals = 0.0
        try:
            if recipe.nutrition_info:
                nutr_list = ast.literal_eval(recipe.nutrition_info)
                cals = float(nutr_list[0])
        except: cals = 0.0

        total_score += raw_score
        total_cals_accumulated += cals

        # Gestion des Tags UI
        current_tags = []
        if algo_type == "DISCO":
            current_tags.append("Découverte")
        
        plan_items.append(MealItem(
            day=day_num, 
            recipe_name=recipe.name,
            calories=cals,
            time=recipe.minutes,
            match_score=round(raw_score, 2),
            tags=current_tags 
        ))

    nb_items = len(recommended_menu)
    avg_score = total_score / nb_items if nb_items else 0
    avg_cals = total_cals_accumulated / nb_items if nb_items else 0

    return MenuResponse(
        status="success",
        user=f"User {request.user_id}",
        plan=plan_items,
        stats={
            "average_match_score": round(avg_score, 2),
            "average_calories": round(avg_cals, 0)
        }
    )

# ==========================================
# 3. FEEDBACK & INTERACTIONS
# ==========================================
@app.post("/feedback")
def submit_feedback(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """Enregistre une note utilisateur (1-5)"""
    interaction = db.query(Interaction).filter(
        Interaction.user_id == feedback.user_id,
        Interaction.recipe_id == feedback.recipe_id
    ).first()

    if interaction:
        interaction.rating = feedback.rating
        interaction.date = datetime.utcnow()
    else:
        new_interaction = Interaction(
            user_id=feedback.user_id,
            recipe_id=feedback.recipe_id,
            rating=feedback.rating,
            date=datetime.utcnow()
        )
        db.add(new_interaction)
    
    db.commit()
    return {"status": "success"}

@app.get("/user/{user_id}/interactions")
def get_user_interactions(user_id: int, db: Session = Depends(get_db)):
    """Récupère l'historique complet des notes"""
    interactions = db.query(Interaction).filter(Interaction.user_id == user_id).all()
    return {i.recipe_id: i.rating for i in interactions}

@app.get("/user/{user_id}/profile")
def get_user_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Récupère ou crée le profil utilisateur"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        new_user = User(id=user_id, username=f"user_{user_id}", preferences=[])
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user

    return {
        "id": user.id,
        "username": user.username,
        "preferences": user.preferences
    }

# ==========================================
# 4. EXPLORATION
# ==========================================
@app.get("/explore")
def explore_recipes(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """Recettes aléatoires jamais notées"""
    rated_subquery = db.query(Interaction.recipe_id).filter(
        Interaction.user_id == user_id
    )
    candidates = db.query(Recipe).filter(
        Recipe.id.notin_(rated_subquery)
    ).order_by(func.random()).limit(limit).all()
    return candidates