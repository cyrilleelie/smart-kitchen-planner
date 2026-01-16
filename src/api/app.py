import json
import logging
import ast
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timezone # <--- AJOUT IMPORTANT

# --- IMPORTS INTERNES ---
from src.database.connection import get_db
from src.database.models import User, Interaction, Recipe
from src.recommender.profile_builder import UserProfiler
from src.recommender.solver import MenuSolver
from src.recommender.inference_service import recommender_service

# --- SCHEMAS (Pydantic) ---
from src.api.schemas import (
    MenuRequest, MenuResponse, MealItem,
    FeedbackRequest,
    ContextRequest, RecipeRecommendation,
    PlanningRequest
)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌍 Démarrage de l'API Smart Retail...")
    yield
    print("🛑 Arrêt de l'API...")

# Initialisation
app = FastAPI(title="Smart Retail API", version="2.7-batch-controller", lifespan=lifespan)


# ==========================================
# 1. GESTION DES PRÉFÉRENCES
# ==========================================
@app.put("/user/{user_id}/preferences")
def update_user_preferences(user_id: int, preferences: List[str] = Body(...), db: Session = Depends(get_db)):
    """Met à jour les préférences déclarées de l'utilisateur."""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.preferences = preferences 
    db.commit()
    db.refresh(user)
    
    return {"status": "success", "preferences": user.preferences}


# ==========================================
# 2. GÉNÉRATEUR DE MENUS (Legacy Solver)
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
                nutr_list = json.loads(recipe.nutrition_info)
                if isinstance(nutr_list, list) and len(nutr_list) > 0:
                    cals = float(nutr_list[0])
        except (json.JSONDecodeError, ValueError, TypeError):
            cals = 0.0

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

    # CORRECTION : Utilisation de timezone-aware datetime
    now_utc = datetime.now(timezone.utc)

    if interaction:
        interaction.rating = feedback.rating
        interaction.date = now_utc
    else:
        new_interaction = Interaction(
            user_id=feedback.user_id,
            recipe_id=feedback.recipe_id,
            rating=feedback.rating,
            date=now_utc
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

# ==========================================
# 5. RECOMMANDATION CONTEXTUELLE (AI POWERED)
# ==========================================
@app.post("/recommend", response_model=List[RecipeRecommendation])
def get_contextual_recommendations(request: ContextRequest, db: Session = Depends(get_db)):
    """
    Recommande 5 recettes basées sur le profil vectoriel et le contexte (Heure/Saison).
    """
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    recommendations = recommender_service.recommend(
        user_id=request.user_id,
        meal_type=request.meal_type,
        season=request.season,
        session=db,
        top_k=5
    )
    
    response = []
    for item in recommendations:
        recipe = item["recipe"]
        cals = 0.0
        try:
            if recipe.nutrition_info:
                nutr_list = json.loads(recipe.nutrition_info)
                if isinstance(nutr_list, list) and len(nutr_list) > 0:
                    cals = float(nutr_list[0])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        response.append(RecipeRecommendation(
            id=recipe.id,
            name=recipe.name,
            minutes=recipe.minutes,
            score=round(item["score"], 2),
            calories=cals
        ))
        
    return response

# ==========================================
# 6. PLANIFICATEUR CONTEXTUEL (BATCH & SPLIT)
# ==========================================
@app.post("/generate-planning", response_model=MenuResponse)
def generate_planning_batch(request: PlanningRequest, db: Session = Depends(get_db)):
    """
    Génère un planning en appelant recommend_weekly_batch.
    Implémente le 'Batch & Split' pour éviter les doublons Midi/Soir.
    """
    selected_set = set(request.selected_meals)
    
    # Structure temporaire pour stocker les résultats par jour
    # daily_menus[jour] = {type_repas_id: item_data, ...}
    daily_menus = {d: {} for d in range(1, request.days + 1)}

    # --- A. GESTION DES REPAS PRINCIPAUX (MIDI & SOIR) ---
    # Si on demande MIDI (1) ET SOIR (2), on utilise la stratégie 'Batch & Split'
    if 1 in selected_set and 2 in selected_set:
        # On génère 2x recettes d'un coup avec le contexte 'Déjeuner' (1)
        # On suppose que Déjeuner/Dîner sont interchangeables pour le modèle principal
        main_meals = recommender_service.recommend_weekly_batch(
            user_id=request.user_id,
            meal_type=1, # On utilise 1 (Midi) comme contexte générique "Plat"
            season=request.season,
            session=db,
            n_days=request.days * 2, # Double dose
            target_calories=request.target_calories
        )
        
        # Split : Première moitié pour midi, seconde pour le soir
        lunches = main_meals[:request.days]
        dinners = main_meals[request.days:]
        
        for i in range(request.days):
            if i < len(lunches): daily_menus[i+1][1] = lunches[i]
            if i < len(dinners): daily_menus[i+1][2] = dinners[i]
            
        # On marque comme traités pour ne pas les refaire individuellement
        processed_meals = {1, 2}
    else:
        processed_meals = set()

    # --- B. GESTION DES AUTRES REPAS (PETIT DEJ, SNACK, OU ISOLES) ---
    for m_id in selected_set:
        if m_id in processed_meals:
            continue
            
        # Appel standard pour 1 type de repas
        meals = recommender_service.recommend_weekly_batch(
            user_id=request.user_id,
            meal_type=m_id, # C'est ici qu'on passe le meal_type requis !
            season=request.season,
            session=db,
            n_days=request.days,
            target_calories=request.target_calories
        )
        
        for i in range(request.days):
            if i < len(meals):
                daily_menus[i+1][m_id] = meals[i]

    # --- C. FORMATAGE DE LA RÉPONSE ---
    plan_items = []
    total_score = 0
    total_calories = 0
    items_count = 0

    for day_num, meals_dict in daily_menus.items():
        for m_id, item_data in meals_dict.items():
            
            recipe = item_data["recipe"]
            score = item_data["score"]
            tag = item_data["tag"]

            # Parsing sécurisé
            cals = 0.0
            ing_list = []
            rec_tags = []
            try:
                if recipe.nutrition_info:
                    parsed = json.loads(recipe.nutrition_info)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        cals = float(parsed[0])
                if recipe.ingredients:
                    parsed = json.loads(recipe.ingredients)
                    if isinstance(parsed, list):
                        ing_list = parsed
                if recipe.tags:
                    parsed = json.loads(recipe.tags)
                    if isinstance(parsed, list):
                        rec_tags = parsed
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

            total_score += score
            total_calories += cals
            items_count += 1

            plan_items.append(MealItem(
                day=day_num,
                recipe_name=recipe.name,
                calories=cals,
                time=recipe.minutes,
                match_score=round(score, 2),
                tags=[tag] if tag == "Découverte" else [],
                ingredients=ing_list,
                recipe_tags=rec_tags
            ))

    avg_score = total_score / items_count if items_count else 0
    avg_cals = total_calories / items_count if items_count else 0

    return MenuResponse(
        status="success",
        user=f"User {request.user_id}",
        plan=plan_items,
        stats={
            "average_match_score": round(avg_score, 2),
            "average_calories": round(avg_cals, 0)
        }
    )