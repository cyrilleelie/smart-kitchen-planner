from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager

# Imports de vos modules
from src.database.models import User, Recipe
from src.recommender.profile_builder import UserProfiler
from src.optimization.menu_solver import MenuSolver
from src.api.schemas import MenuRequest, MenuResponse, MealItem

# Configuration DB
DB_URL = "sqlite:///smartretail.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

def get_db():
    """Dépendance pour gérer la session DB proprement"""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()

# Initialisation de l'App
app = FastAPI(
    title="SmartRetail RecSys API",
    description="API de génération de menus intelligents (IA + OR)",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message": "SmartRetail API is running 🚀"}

@app.post("/generate-menu", response_model=MenuResponse)
def generate_menu(request: MenuRequest, db: Session = Depends(get_db)):
    """
    Génère un menu optimisé pour un utilisateur donné.
    """
    # 1. Récupération User
    user = db.get(User, request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    # 2. IA : Profiling & Candidats (On élargit à 200 comme validé précédemment)
    profiler = UserProfiler(db)
    candidates, scores = profiler.recommend_candidates(user.id, limit=200)
    
    if not candidates:
        raise HTTPException(status_code=400, detail="Pas assez de données pour recommander.")

    # 3. OR : Résolution
    solver = MenuSolver(candidates, scores)
    
    # On passe les paramètres dynamiques de la requête API au solveur
    # Note : Le solveur utilise déjà votre filtre anti-dessert codé en dur
    solution = solver.solve(
        days=request.days,
        max_prep_time=request.max_prep_time,
        max_calories_per_day=request.target_calories_max 
        # Note: on pourrait aussi passer le min_cal au solveur si on modifie sa signature,
        # pour l'instant il utilise son défaut (400) ou celui codé en dur.
    )

    if not solution:
        raise HTTPException(status_code=422, detail="Impossible de générer un menu avec ces contraintes strictes.")

    # 4. Formatting de la réponse
    meal_items = []
    total_score = 0
    total_cals = 0
    
    for item in solution:
        meal_items.append(MealItem(
            day=item['day'],
            recipe_name=item['recipe'],
            calories=item['calories'],
            time=item['time'],
            match_score=round(item['score_match'], 1)
        ))
        total_score += item['score_match']
        total_cals += item['calories']

    return MenuResponse(
        status="success",
        user=user.username,
        plan=meal_items,
        stats={
            "avg_satisfaction": round(total_score / request.days, 1),
            "avg_calories": int(total_cals / request.days)
        }
    )