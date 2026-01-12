import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from sqlalchemy.orm import Session
from types import SimpleNamespace # <--- L'astuce pour éviter la RecursionError

# Ajout du path
sys.path.append(os.getcwd())

from src.api.app import app, get_db

# --- FIXTURES ---

@pytest.fixture
def mock_db_session():
    """Crée une fausse session SQLAlchemy"""
    session = MagicMock(spec=Session)
    return session

@pytest.fixture
def client(mock_db_session):
    """Client de test avec injection de dépendances"""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    # On patch le service pour éviter tout appel réseau
    with patch('src.api.app.recommender_service') as mock_service:
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()

# --- TESTS ---

def test_update_user_preferences(client, mock_db_session):
    """PUT /user/{id}/preferences"""
    mock_user = Mock()
    mock_user.id = 1
    mock_user.preferences = []
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user

    response = client.put("/user/1/preferences", json=["vegetarien"])
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_update_preferences_user_not_found(client, mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    response = client.put("/user/999/preferences", json=["veg"])
    assert response.status_code == 404

def test_get_user_profile(client, mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/user/10/profile")
    assert response.status_code == 200
    assert response.json()["id"] == 10

def test_submit_feedback(client, mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    response = client.post("/feedback", json={"user_id": 1, "recipe_id": 100, "rating": 5})
    assert response.status_code == 200

def test_explore_recipes(client, mock_db_session):
    """GET /explore"""
    # CORRECTION : Utiliser SimpleNamespace au lieu de Mock
    mock_recipe = SimpleNamespace(id=101, name="Pizza", minutes=15, nutrition_info="['500']", ingredients="[]", tags="[]")
    
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_recipe]
    
    response = client.get("/explore?user_id=1&limit=5")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Pizza"

# --- TESTS SERVICES ---

@patch('src.api.app.UserProfiler')
@patch('src.api.app.MenuSolver')
def test_generate_menu_legacy(mock_solver_cls, mock_profiler_cls, client, mock_db_session):
    """POST /generate-menu"""
    mock_profiler_instance = mock_profiler_cls.return_value
    mock_profiler_instance.get_weighted_profile.return_value = [0.1, 0.2]
    
    mock_solver_instance = mock_solver_cls.return_value
    mock_solver_instance.solve.return_value = [
        {"day": 1, "recipe_id": 50, "algo_type": "PERF", "score": 0.95}
    ]
    
    # CORRECTION : SimpleNamespace
    mock_recipe = SimpleNamespace(id=50, name="Super Pasta", minutes=15, nutrition_info="['500']", ingredients="[]", tags="[]")
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_recipe
    
    response = client.post("/generate-menu", json={
        "user_id": 1, "preferences": ["italian"], "days": 1, 
        "target_calories_min": 1800, "meals_per_day": 1
    })
    
    assert response.status_code == 200
    assert response.json()["plan"][0]["recipe_name"] == "Super Pasta"

def test_contextual_recommendation(client, mock_db_session):
    """POST /recommend"""
    from src.api.app import recommender_service as mock_service
    
    mock_db_session.query.return_value.filter.return_value.first.return_value = Mock()
    
    # CORRECTION : SimpleNamespace
    mock_recipe = SimpleNamespace(id=200, name="Salad", minutes=10, nutrition_info="['200']", ingredients="[]", tags="[]")
    mock_service.recommend.return_value = [{"recipe": mock_recipe, "score": 0.88}]
    
    response = client.post("/recommend", json={"user_id": 1, "meal_type": 1, "season": 2})
    
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Salad"

def test_generate_planning_batch_split(client, mock_db_session):
    """POST /generate-planning"""
    from src.api.app import recommender_service as mock_service
    
    # CORRECTION : SimpleNamespace pour éviter ValidationError de Pydantic
    r1 = SimpleNamespace(id=1, name="Lunch", minutes=20, nutrition_info="['600']", ingredients="[]", tags="[]")
    r2 = SimpleNamespace(id=2, name="Dinner", minutes=30, nutrition_info="['400']", ingredients="[]", tags="[]")
    
    mock_service.recommend_weekly_batch.return_value = [
        {"recipe": r1, "score": 0.9, "tag": "Perf"},
        {"recipe": r2, "score": 0.8, "tag": "Disco"}
    ]
    
    response = client.post("/generate-planning", json={
        "user_id": 1, "days": 1, "target_calories": 2000, "selected_meals": [1, 2], "season": 0
    })
    
    assert response.status_code == 200
    assert len(response.json()["plan"]) == 2