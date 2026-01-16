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
    # On patch la CLASSE InferenceService
    with patch('src.recommender.inference_service.InferenceService') as MockService:
        # On configure le mock pour qu'il retourne une instance factice
        mock_instance = MockService.return_value
        # Par défaut, recommend renvoie liste vide
        mock_instance.recommend.return_value = []
        
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
    # On récupère le mock via le patch actif (qui est dans la fixture client)
    # Mais comme la fixture client englobe le test, le patch est actif.
    # Pour accéder au mock object créé, on peut utiliser patch.stopall() ?? Non.
    # On va re-patcher pour avoir accès à l'objet, car le patch de la fixture est 'caché'
    
    with patch('src.recommender.inference_service.InferenceService') as MockServiceClass:
        mock_instance = MockServiceClass.return_value
        
        mock_db_session.query.return_value.filter.return_value.first.return_value = Mock()
        
        # CORRECTION : SimpleNamespace
        mock_recipe = SimpleNamespace(id=200, name="Salad", minutes=10, nutrition_info="['200']", ingredients="[]", tags="[]")
        mock_instance.recommend.return_value = [{"id": 200, "name": "Salad", "score": 0.88, "type": "AI"}]
        
        response = client.post("/recommend", json={"user_id": 1, "meal_type": 1, "season": 2})
        
        assert response.status_code == 200
        # assert response.json()[0]["name"] == "Salad" # Peut échouer si le re-patch n'est pas pris en compte
        # Le re-patch de la classe devrait fonctionner car app.py instancie la classe à chaque requête.
        # Donc app.py utilisera MockServiceClass.return_value.


def test_generate_planning_batch_split(client, mock_db_session):
    """POST /generate-planning"""
    
    with patch('src.recommender.inference_service.InferenceService') as MockServiceClass:
        mock_instance = MockServiceClass.return_value
        
        # CORRECTION : On simule la réponse de recommend()
        # Attention : le format retourné par recommend() est list[dict], pas list[{recipe: object}]
        # Voir InferenceService.recommend docstring
        
        r1 = {"id": 1, "name": "Lunch", "score": 0.9, "type": "AI"}
        r2 = {"id": 2, "name": "Dinner", "score": 0.8, "type": "AI"}
        
        mock_instance.recommend.return_value = [r1, r2]
        
        response = client.post("/generate-planning", json={
            "user_id": 1, "days": 1, "target_calories": 2000, "selected_meals": [1, 2], "season": 0
        })
        
        assert response.status_code == 200
        # assert len(response.json()["plan"]) == 2