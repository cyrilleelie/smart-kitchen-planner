from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Body, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
import os  # <--- AJOUT IMPORTANT

# --- IMPORTS INTERNES ---
from src.database.connection import get_db, SessionLocal
from src.database.models import User, Interaction, Recipe, PredictionLog

import json
import logging
import ast
from src.utils.logging_config import setup_logging

# Setup logging
# --- SCHEMAS (Pydantic) ---
from src.api.schemas import (
    MenuResponse,
    MealItem,
    FeedbackRequest,
    ContextRequest,
    RecipeRecommendation,
    PlanningRequest,
)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌍 Démarrage de l'API Smart Retail...")
    yield
    print("🛑 Arrêt de l'API...")


# Initialisation
# Initialisation
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="Smart Retail API", version="2.8-batch-controller", lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def log_batch_predictions(entries: List[dict]):
    """
    Enregistre un lot de prédictions en base (granularité : item).
    """
    db = SessionLocal()
    try:
        logs = []
        for entry in entries:
            log = PredictionLog(
                user_id=entry["user_id"],
                input_features=json.dumps(entry["input_features"], default=str),
                prediction_result=json.dumps(entry["prediction_result"], default=str),
                model_version=entry["model_version"],
                timestamp=datetime.utcnow(),
            )
            logs.append(log)

        db.add_all(logs)
        db.commit()
        logger.info(f"📝 Logged {len(logs)} predictions.")
    except Exception as e:
        logger.error(f"❌ Failed to log batch: {e}")
    finally:
        db.close()


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
def update_user_preferences(
    user_id: int, preferences: List[str] = Body(...), db: Session = Depends(get_db)
):
    """Met à jour les préférences déclarées de l'utilisateur."""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.preferences = preferences
    db.commit()
    db.refresh(user)

    return {"status": "success", "preferences": user.preferences}


# ==========================================
# 2. FEEDBACK & INTERACTIONS
# ==========================================
@app.post("/feedback")
def submit_feedback(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """Enregistre une note utilisateur (1-5)"""
    interaction = (
        db.query(Interaction)
        .filter(
            Interaction.user_id == feedback.user_id,
            Interaction.recipe_id == feedback.recipe_id,
        )
        .first()
    )

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
            date=now_utc,
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

    return {"id": user.id, "username": user.username, "preferences": user.preferences}


# ==========================================
# 4. EXPLORATION
# ==========================================
@app.get("/explore")
def explore_recipes(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """Recettes aléatoires jamais notées"""
    rated_subquery = db.query(Interaction.recipe_id).filter(
        Interaction.user_id == user_id
    )
    candidates = (
        db.query(Recipe)
        .filter(Recipe.id.notin_(rated_subquery))
        .order_by(func.random())
        .limit(limit)
        .all()
    )
    return candidates


# ==========================================
# 5. RECOMMANDATION CONTEXTUELLE (AI POWERED)
# ==========================================
@app.post("/recommend", response_model=List[RecipeRecommendation])
@limiter.limit("30/minute")
def get_contextual_recommendations(
    request: Request,
    context_request: ContextRequest = Body(...),
    db: Session = Depends(get_db),
    model_type: str = "collaborative",
):
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
    request = context_request  # Alias
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Use the new multi‑model recommendation service
    from src.domain.recommendation_service import generate_recommendations

    # Build constraints dict from the request (example fields)
    constraints = {}
    if hasattr(context_request, "vegetarian"):
        constraints["vegetarian"] = context_request.vegetarian
    if hasattr(context_request, "max_time"):
        constraints["max_time"] = context_request.max_time

    # Generate recommendations using selected model type
    # Returns List[Tuple[Recipe, float]]
    results = generate_recommendations(
        db=db,
        user_id=context_request.user_id,
        constraints=constraints,
        top_n=5,
        model_type=model_type,
    )

    response = []
    for recipe, score in results:
        cals = 0.0
        try:
            if recipe.nutrition_info:
                nutr_list = json.loads(recipe.nutrition_info)
                cals = float(nutr_list[0])
        except Exception as e:
            logger.warning(f"Failed to parse nutrition_info in recommendation: {e}")
            pass
        response.append(
            RecipeRecommendation(
                id=recipe.id,
                name=recipe.name,
                minutes=recipe.minutes,
                score=round(score, 2),  # Use the actual model score
                calories=cals,
            )
        )

    return response


# ==========================================
# 6. PLANIFICATEUR CONTEXTUEL (BATCH & SPLIT)
# ==========================================
@app.post("/generate-planning", response_model=MenuResponse)
@limiter.limit("10/minute")
def generate_planning_batch(
    request: Request,
    planning_request: PlanningRequest = Body(...),
    background_tasks: BackgroundTasks = None,  # Injection BackgroundTasks
    db: Session = Depends(get_db),
):
    """
    Génère un planning en appelant recommend_weekly_batch.
    Génère un planning en appelant recommend_weekly_batch.
    Implémente le 'Batch & Split' pour éviter les doublons Midi/Soir.
    """
    # Alias pour compatibilité interne (request désignait le Pydantic model avant)
    request = planning_request
    selected_set = set(request.selected_meals)

    # Structure temporaire pour stocker les résultats par jour
    # daily_menus[jour] = {type_repas_id: item_data, ...}
    daily_menus = {d: {} for d in range(1, request.days + 1)}

    # Instantiation du service
    # service = InferenceService(db) # REMPLACÉ par generate_weekly_plan
    from src.domain.recommendation_service import generate_weekly_plan

    # --- A. GESTION DES REPAS PRINCIPAUX (MIDI & SOIR) ---
    # Si on demande MIDI (1) ET SOIR (2), on utilise la stratégie 'Batch & Split'
    if 1 in selected_set and 2 in selected_set:
        # On génère 2x recettes d'un coup avec le contexte 'Déjeuner' (1)
        # On suppose que Déjeuner/Dîner sont interchangeables pour le modèle principal
        main_meals = generate_weekly_plan(
            db=db,
            user_id=request.user_id,
            meal_type=1,  # On utilise 1 (Midi) comme contexte générique "Plat"
            season=request.season,
            n_days=request.days * 2,  # Double dose
            target_calories=request.target_calories,
            model_type=request.model_type,  # <--- Nouveau paramètre
        )

        # Split : Première moitié pour midi, seconde pour le soir
        lunches = main_meals[: request.days]
        dinners = main_meals[request.days :]

        for i in range(request.days):
            if i < len(lunches):
                daily_menus[i + 1][1] = lunches[i]
            if i < len(dinners):
                daily_menus[i + 1][2] = dinners[i]

        # On marque comme traités pour ne pas les refaire individuellement
        processed_meals = {1, 2}
    else:
        processed_meals = set()

    # --- B. GESTION DES AUTRES REPAS (PETIT DEJ, SNACK, OU ISOLES) ---
    for m_id in selected_set:
        if m_id in processed_meals:
            continue

        # Appel standard pour 1 type de repas
        meals = generate_weekly_plan(
            db=db,
            user_id=request.user_id,
            meal_type=m_id,
            season=request.season,
            n_days=request.days,
            target_calories=request.target_calories,
            model_type=request.model_type,  # <--- Nouveau paramètre
        )

        for i in range(request.days):
            if i < len(meals):
                daily_menus[i + 1][m_id] = meals[i]

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

            # Parsing sécurisé (compatible JSON et Python list repr)
            cals = 0.0
            ing_list = []
            rec_tags = []
            try:
                if recipe.nutrition_info:
                    try:
                        # Try JSON first, fallback to eval
                        raw = recipe.nutrition_info
                        try:
                            parsed = json.loads(raw)
                        except Exception:
                            parsed = ast.literal_eval(raw)
                        cals = float(parsed[0])
                    except Exception:
                        pass

                if recipe.ingredients:
                    try:
                        raw = recipe.ingredients
                        try:
                            ing_list = json.loads(raw)
                        except Exception:
                            ing_list = ast.literal_eval(raw)
                    except Exception:
                        pass

                if recipe.tags:
                    try:
                        raw = recipe.tags
                        try:
                            rec_tags = json.loads(raw)
                        except Exception:
                            rec_tags = ast.literal_eval(raw)
                    except Exception:
                        pass
            except Exception:
                pass

            total_score += score
            total_calories += cals
            items_count += 1

            plan_items.append(
                MealItem(
                    day=day_num,
                    recipe_name=recipe.name,
                    calories=cals,
                    time=recipe.minutes,
                    match_score=round(score, 2),
                    tags=[tag] if tag == "Découverte" else [],
                    ingredients=ing_list,
                    recipe_tags=rec_tags,
                )
            )

    avg_score = total_score / items_count if items_count else 0
    avg_cals = total_calories / items_count if items_count else 0

    response_payload = MenuResponse(
        status="success",
        user=f"User {request.user_id}",
        plan=plan_items,
        stats={
            "average_match_score": round(avg_score, 2),
            "average_calories": round(avg_cals, 0),
        },
    )

    if background_tasks:
        log_entries = []

        # On parcourt ce qui a été généré
        for day_num, meals_dict in daily_menus.items():
            for m_id, item_data in meals_dict.items():
                rec_id = item_data["recipe"].id
                rec_score = item_data["score"]

                log_entries.append(
                    {
                        "user_id": request.user_id,
                        "model_version": "v2.8",
                        "input_features": {
                            "recipe_id": rec_id,
                            "meal_type": m_id,
                            "season": request.season,
                        },
                        "prediction_result": {"score": round(rec_score, 4)},
                    }
                )

        background_tasks.add_task(log_batch_predictions, log_entries)

    return response_payload
