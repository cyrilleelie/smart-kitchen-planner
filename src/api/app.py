from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from collections import Counter

# Imports du projet
from src.database.connection import get_db
from src.database.models import User, Recipe, Interaction
from src.recommender.profile_builder import UserProfiler
from src.recommender.solver import MenuSolver

app = FastAPI(title="SmartRetail RecSys API")

# --- Modèles de Données (Pydantic) ---
class MenuRequest(BaseModel):
    user_id: int
    days: int = 1
    target_calories: int = 2000

# --- Nouveau Modèle de Données ---
class FeedbackRequest(BaseModel):
    user_id: int
    recipe_id: int
    rating: int  # 5 = J'aime, 1 = Je n'aime pas

TAG_BLACKLIST = {
    # Méta-catégories techniques (ce que vous voyiez)
    "main-ingredient", "low-in-something", "dietary", "occasion", "course", 
    "preparation", "equipment", "technique", "number-of-servings", "meat", 
    "vegetables", "fruit", # Ces 3 derniers sont souvent des catégories parentes trop vagues
    
    # Temps et difficulté
    "time-to-make", "easy", "beginner-cook", "inexpensive", "healthy", "healthy-2",
    "5-minutes-or-less", "15-minutes-or-less", "30-minutes-or-less", 
    "60-minutes-or-less", "4-hours-or-less", "less-thans",
    
    # Infos nutritionnelles génériques (sauf si vous voulez tracker le régime)
    "low-sodium", "low-cholesterol", "low-saturated-fat", "low-calorie", 
    "low-protein", "low-carb", "high-calcium", "high-in-something"
}

# --- Endpoints ---

@app.get("/")
def root():
    """Route de vérification de santé"""
    return {"status": "online", "message": "SmartRetail API is running 🚀"}

@app.get("/user/{user_id}/profile")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """
    Analyse l'historique en filtrant agressivement les tags techniques.
    """
    liked_interactions = db.query(Interaction).join(Recipe).filter(
        Interaction.user_id == user_id,
        Interaction.rating >= 4
    ).all()

    if not liked_interactions:
        return {"status": "empty", "message": "Pas assez de données"}

    tag_counter = Counter()
    total_likes = len(liked_interactions)
    
    for interaction in liked_interactions:
        raw_tags = interaction.recipe.tags
        if isinstance(raw_tags, str):
            clean_tags = raw_tags.replace('[', '').replace(']', '').replace("'", "").split(',')
            clean_tags = [t.strip() for t in clean_tags if t.strip()]
        else:
            clean_tags = raw_tags
        
        # Filtrage
        filtered_tags = [t for t in clean_tags if t not in TAG_BLACKLIST]
        tag_counter.update(filtered_tags)

    # On prend le top 10
    top_tags = tag_counter.most_common(10)
    
    return {
        "user_id": user_id,
        "total_likes": total_likes,
        "favorite_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "last_interaction": liked_interactions[-1].date if liked_interactions else None
    }

# --- Nouvelle Route ---
@app.post("/feedback")
def log_feedback(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """
    Enregistre une interaction utilisateur (Like/Dislike)
    pour affiner les futures recommandations.
    """
    # 1. On vérifie si l'interaction existe déjà (pour éviter les doublons)
    existing_interaction = db.query(Interaction).filter(
        Interaction.user_id == feedback.user_id,
        Interaction.recipe_id == feedback.recipe_id
    ).first()

    if existing_interaction:
        # Mise à jour de l'avis existant
        existing_interaction.rating = feedback.rating
        existing_interaction.date = datetime.utcnow()
        action = "mis à jour"
    else:
        # Création d'un nouvel avis
        new_interaction = Interaction(
            user_id=feedback.user_id,
            recipe_id=feedback.recipe_id,
            rating=feedback.rating,
            date=datetime.utcnow()
        )
        db.add(new_interaction)
        action = "créé"
    
    db.commit()
    print(f"💾 Feedback {action} : User {feedback.user_id} -> Recipe {feedback.recipe_id} ({feedback.rating}/5)")
    return {"status": "success", "message": "Préférence enregistrée"}

@app.post("/generate-menu")
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    """
    Génère un menu optimisé.
    """
    # 1. Vérification de l'utilisateur
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Utilisateur {request.user_id} introuvable.")
    
    # 2. Récupération des candidats (IA)
    print(f"🔍 Recherche de candidats pour User {user.id}...")
    
    # CORRECTION ICI : On instancie le profileur AVEC la session de la requête
    profiler = UserProfiler(db) 
    
    candidates_pool = profiler.recommend_candidates(user.id, limit=100)
    
    if not candidates_pool:
        return {
            "menu": [], 
            "meta": {"status": "error", "message": "Pas assez de données pour recommander."}
        }

    # 3. Optimisation Mathématique (Solveur)
    print(f"🧮 Optimisation pour {request.target_calories} kcal sur {request.days} jours...")
    solver = MenuSolver()
    final_menu = solver.solve(
        candidates=candidates_pool,
        target_calories=request.target_calories,
        days=request.days
    )
    
    # 4. Calcul des métadonnées
    total_cals = sum([item['calories'] for item in final_menu if item['calories']])
    
    return {
        "menu": final_menu,
        "meta": {
            "total_calories": total_cals,
            "days": request.days,
            "target": request.target_calories * request.days,
            "count": len(final_menu)
        }
    }
