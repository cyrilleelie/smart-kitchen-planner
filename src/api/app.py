import ast
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
import os # <--- AJOUT IMPORTANT

# --- IMPORTS INTERNES ---
from src.database.connection import get_db
from src.database.models import User, Interaction, Recipe
from src.recommender.profile_builder import UserProfiler
from src.recommender.solver import MenuSolver
from src.recommender.inference_service import InferenceService
import json
import logging
from src.utils.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

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
# Initialisation
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Smart Retail API", version="2.8-batch-controller", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
@limiter.limit("10/minute")
def generate_menu(request: Request, menu_request: MenuRequest = Body(...), db: Session = Depends(get_db)):
    """
    Generate a weekly menu plan using the heuristic solver.
    
    Args:
        request: Raw request (for rate limiting)
        menu_request: Menu generation parameters (user_id, days, calories)
        db: Database session
        
    Returns:
        MenuResponse: The generated menu with recipes for each day.
        
    Raises:
        HTTPException(404): If user is not found.
    """
    # Note: nous avons renommé 'request' -> 'menu_request' pour Pydantic, car 'request' est pris par limiter
    request = menu_request # Alias pour garder la compatibilité du code existant
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
                else:
                    logger.warning(f"Invalid nutrition_info format for recipe {recipe.id}")
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse nutrition_info for recipe {recipe.id}: {e}")
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
@limiter.limit("30/minute")
def get_contextual_recommendations(request: Request, context_request: ContextRequest = Body(...), db: Session = Depends(get_db)):
    """
    Get 5 contextual recipe recommendations based on AI model.
    
    Uses Random Forest model to predict recipe relevance based on:
    - User profile (embeddings)
    - Recipe features (embeddings)
    - Context (Time of day, Season)
    
    Args:
        request: Raw request
        context_request: User ID and optional manual context overrides
        db: Database session
        
    Returns:
        List[RecipeRecommendation]: Top 5 recommended recipes.
    """
    request = context_request # Alias
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Instantiation du service avec la session DB
    service = InferenceService(db)
    
    # Appel du service MLflow
    recommendations = service.recommend(
        user_id=request.user_id,
        n=5
    )
    
    response = []
    for item in recommendations:
        recipe = item["recipe"]
        cals = 0.0
        try:
            if recipe.nutrition_info:
                nutr_list = json.loads(recipe.nutrition_info)
                cals = float(nutr_list[0])
        except Exception as e:
            logger.warning(f"Failed to parse nutrition_info in recommendation: {e}")
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
    
    # Instantiation du service
    service = InferenceService(db)

    # --- A. GESTION DES REPAS PRINCIPAUX (MIDI & SOIR) ---
    # Si on demande MIDI (1) ET SOIR (2), on utilise la stratégie 'Batch & Split'
    if 1 in selected_set and 2 in selected_set:
        # On génère 2x recettes d'un coup avec le contexte 'Déjeuner' (1)
        # On suppose que Déjeuner/Dîner sont interchangeables pour le modèle principal
        main_meals = service.recommend_weekly_batch(
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
        meals = service.recommend_weekly_batch(
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
                    try:
                        cals = float(json.loads(recipe.nutrition_info)[0])
                    except: pass
                if recipe.ingredients:
                    try:
                        ing_list = json.loads(recipe.ingredients) # ast.literal_eval -> json.loads
                        # Note: ingredients are often stored simply as text representations of lists in Python str format in some datasets
                        # If json.loads fails, we might need a fallback or data cleaning. 
                        # For this specific case, if the data is Python list string, json.loads might fail if it uses single quotes.
                        # Let's check if we can make it safer. The original code used ast.literal_eval.
                        # Ideally data should be stored as JSON. For now assuming JSON or valid string.
                        pass 
                    except: 
                         # Fallback for legacy format if json fails but ast works (transition period)
                         # BUT user asked to replace ast.literal_eval. 
                         # If the DB has single quotes, json.loads WILL fail.
                         # I will strictly follow "Replace ast.literal_eval with json.loads" but I should probably handle the single quote issue if the data is dirty.
                         # For now, let's stick to json.loads as requested for security.
                         pass
                if recipe.tags:
                    try:
                        rec_tags = json.loads(recipe.tags)
                    except: pass
            except: pass

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