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
from src.recommender.content_engine import ContentEngine

# --- SCHEMAS (Pydantic) ---
from src.api.schemas import (
    UserRequest, RecipeResponse, 
    MenuRequest, MenuResponse, MealItem,
    FeedbackRequest
)

# --- NOUVEAU SCHEMA LOCAL (Pour la sauvegarde des préférences) ---
class PreferencesRequest(BaseModel):
    preferences: List[str]

# --- LIFESPAN (Le Cerveau IA) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌍 Démarrage de l'API Smart Retail...")
    
    # Chargement du moteur de recommandation
    try:
        app.state.recsys = ContentEngine()
    except Exception as e:
        print(f"⚠️ Erreur critique chargement IA: {e}")
        app.state.recsys = None
    
    yield
    print("🛑 Arrêt de l'API...")

# Initialisation
app = FastAPI(title="Smart Retail API", version="2.2", lifespan=lifespan)


# ==========================================
# 1. GESTION DES PRÉFÉRENCES (NOUVEAU) ⚙️
# ==========================================
@app.put("/user/{user_id}/preferences")
def update_user_preferences(user_id: int, preferences: List[str] = Body(...), db: Session = Depends(get_db)):
    """
    Met à jour les préférences déclarées de l'utilisateur.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Mise à jour du champ JSON dans la base de données
    # Note: Nécessite que la colonne 'preferences' existe dans models.py
    user.preferences = preferences 
    
    db.commit()
    db.refresh(user) # Recharge l'objet depuis la DB pour confirmer
    
    print(f"✅ Préférences sauvegardées pour User {user_id} : {preferences}")
    
    return {"status": "success", "preferences": user.preferences}


# ==========================================
# 2. GÉNÉRATEUR DE MENUS (Optimisation) 📅
# ==========================================
@app.post("/generate-menu", response_model=MenuResponse)
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    # 1. Profiling
    profiler = UserProfiler(db)
    user_vector = profiler.get_weighted_profile(
        request.user_id, 
        request.preferences
    )

    # On convertit les tags du Front (ex: "Italienne") en tags de BDD (ex: "italian")
    active_tags = profiler.get_converted_tags(request.preferences)
    print(f"🚀 API envoie au Solveur les tags : {active_tags}")

    # --- DEBUG LOGS ---
    print(f"\n🔍 [DEBUG] User {request.user_id} Vector: {user_vector}")
    if not user_vector:
        print("⚠️ [WARN] Le vecteur utilisateur est VIDE ! C'est pour ça que tout est à 0.5.")
    # ------------------

    # 2. Solving Probabiliste
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
        # 1. Extraction des données enrichies du Solver
        day_num = item["day"]
        recipe_id = item["recipe_id"]
        algo_type = item["algo_type"] # "PERF" ou "DISCO"
        raw_score = item["score"]

        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe: continue
            
        # 2. Parsing Calories
        cals = 0.0
        try:
            if recipe.nutrition_info:
                nutr_list = ast.literal_eval(recipe.nutrition_info)
                cals = float(nutr_list[0])
        except: cals = 0.0

        total_score += raw_score
        total_cals_accumulated += cals

        # 3. Logique Minimaliste : Tag "Découverte" uniquement
        current_tags = []
        if algo_type == "DISCO":
            current_tags.append("Découverte")
        
        # 4. Création de l'objet réponse
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
# 3. RECOMMANDATION IA (Ingrédients) 🧠
# ==========================================
@app.post("/recommend", response_model=List[RecipeResponse])
def get_recommendations_by_ingredients(request: UserRequest, db: Session = Depends(get_db)):
    """Trouve des recettes basées sur une liste d'ingrédients."""
    if not hasattr(app.state, 'recsys') or app.state.recsys is None:
        raise HTTPException(status_code=503, detail="IA non chargée.")

    recipe_ids = app.state.recsys.recommend(request.ingredients, top_k=5)
    
    if not recipe_ids:
        return []

    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
    recipe_map = {r.id: r for r in recipes}
    ordered_recipes = [recipe_map[rid] for rid in recipe_ids if rid in recipe_map]
    
    return ordered_recipes

# ==========================================
# 4. FEEDBACK & INTERACTIONS ⭐
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
    """Récupère l'historique complet des notes de l'utilisateur {recipe_id: note}"""
    interactions = db.query(Interaction).filter(Interaction.user_id == user_id).all()
    return {i.recipe_id: i.rating for i in interactions}

@app.get("/user/{user_id}/profile")
def get_user_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Récupère le profil. Si l'utilisateur n'existe pas, on le crée à la volée (Lazy Creation).
    Cela permet au Frontend d'avoir toujours une réponse '200 OK' et d'afficher des préférences vides.
    """
    # 1. On cherche l'utilisateur
    user = db.query(User).filter(User.id == user_id).first()
    
    # 2. S'il n'existe pas, on le crée immédiatement
    if not user:
        print(f"🆕 Création automatique de l'utilisateur {user_id}")
        new_user = User(id=user_id, username=f"user_{user_id}", preferences=[])
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user

    # 3. On calcule son profil vecteur (optionnel pour l'affichage, mais utile pour le debug)
    profiler = UserProfiler(db)
    # On renvoie l'objet user brut pour que le front affiche les préférences cochées (JSON)
    return {
        "id": user.id,
        "username": user.username,
        "preferences": user.preferences  # C'est ça que le Front doit lire pour reset les checkbox
    }

# ==========================================
# 5. EXPLORATION 🧭
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