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

app = FastAPI(title="Smart Retail API")

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
    "low-saturated-fat", "low-calorie", "low-protein", "low-carb", 
    "high-calcium", "high-in-something"
}

# --- Événement de démarrage ---
@app.on_event("startup")
def on_startup():
    init_database()

# --- Routes ---

@app.get("/")
def read_root():
    return {"message": "Welcome to Smart Retail API 🥦"}

@app.post("/feedback")
def log_feedback(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """Enregistre un Like/Dislike"""
    existing = db.query(Interaction).filter(
        Interaction.user_id == feedback.user_id,
        Interaction.recipe_id == feedback.recipe_id
    ).first()

    if existing:
        existing.rating = feedback.rating
        existing.date = datetime.utcnow()
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

@app.get("/user/{user_id}/profile")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Statistiques du profil utilisateur"""
    liked = db.query(Interaction).join(Recipe).filter(
        Interaction.user_id == user_id,
        Interaction.rating >= 4
    ).all()

    if not liked:
        return {"status": "empty"}

    tag_counter = Counter()
    for interaction in liked:
        raw = interaction.recipe.tags
        if isinstance(raw, str):
            clean = raw.replace('[', '').replace(']', '').replace("'", "").split(',')
            clean = [t.strip() for t in clean if t.strip()]
        else:
            clean = raw
        
        filtered = [t for t in clean if t not in TAG_BLACKLIST]
        tag_counter.update(filtered)

    return {
        "user_id": user_id,
        "total_likes": len(liked),
        "favorite_tags": [{"tag": t, "count": c} for t, c in tag_counter.most_common(10)]
    }

@app.post("/generate-menu")
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    # 1. Récupération User
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        user = User(id=request.user_id, username=f"User {request.user_id}")
        db.add(user)
        db.commit()

    # 2. Profiling (IA)
    profiler = UserProfiler(db)
    # Variable unifiée : 'candidates'
    candidates = profiler.recommend_candidates(request.user_id, limit=200)

    if not candidates:
        return {"menu": [], "meta": {"total_calories": 0}}

    # 3. Optimisation (Solver)
    # On passe bien 'candidates' ici
    solver = MenuSolver(candidates, days=request.days, target_calories=request.target_calories)
    
    final_menu_objects = solver.solve(fridge_ingredients=request.fridge_items)

    # 4. Formatage réponse
    menu_response = []
    total_cals = 0
    
    for recipe in final_menu_objects:
        # On retrouve le score original via l'ID
        original_score = next((s for r, s in candidates if r.id == recipe.id), 0)
        
        # Accès par attribut (.) car ce sont des objets SQLAlchemy
        total_cals += recipe.calories
        
        menu_response.append({
            "id": recipe.id,
            "name": recipe.name,
            "calories": recipe.calories,
            "minutes": recipe.minutes,
            "tags": str(recipe.tags),
            "ingredients": str(recipe.ingredients),
            "score": original_score
        })

    return {
        "menu": menu_response,
        "meta": {
            "total_calories": total_cals,
            "days": request.days
        }
    }

@app.get("/user/{user_id}/interactions")
def get_user_interactions(user_id: int, db: Session = Depends(get_db)):
    """Récupère l'historique complet des notes de l'utilisateur"""
    interactions = db.query(Interaction).filter(Interaction.user_id == user_id).all()
    # On renvoie un dictionnaire simple : {recipe_id: note}
    return {i.recipe_id: i.rating for i in interactions}

@app.get("/explore")
def explore_recipes(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """
    Renvoie des recettes aléatoires que l'utilisateur n'a JAMAIS notées.
    """
    # 1. Sous-requête : Les IDs déjà notés par l'utilisateur
    rated_subquery = db.query(Interaction.recipe_id).filter(
        Interaction.user_id == user_id
    )

    # 2. Requête principale : Recettes NOT IN (déjà notés)
    # On trie aléatoirement (func.random() pour Postgres)
    candidates = db.query(Recipe).filter(
        Recipe.id.notin_(rated_subquery)
    ).order_by(func.random()).limit(limit).all()

    # 3. Formatage
    results = []
    for r in candidates:
        results.append({
            "id": r.id,
            "name": r.name,
            "calories": r.calories,
            "minutes": r.minutes,
            "tags": str(r.tags),
            "ingredients": str(r.ingredients)
        })

    return results