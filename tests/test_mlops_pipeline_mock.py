
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from src.mlops.train_model import train, train_svd, calculate_context_penalty
from src.mlops.optimize_svd import optimize_svd as run_optimize_svd
from src.database.models import Recipe

# --- FIXTURES ---

@pytest.fixture
def mock_session():
    with patch("src.mlops.train_model.Session") as mock_sess_cls:
        mock_sess = mock_sess_cls.return_value.__enter__.return_value
        yield mock_sess

@pytest.fixture
def mock_mlflow():
    with patch("src.mlops.train_model.mlflow") as mock_ml:
        yield mock_ml

@pytest.fixture
def mock_surprise_cv():
    with patch("src.mlops.optimize_svd.GridSearchCV") as mock_gscv:
        yield mock_gscv

# --- TESTS FOR train_model.py ---

def test_calculate_context_penalty():
    # Setup a mock recipe
    mock_recipe = MagicMock(spec=Recipe)
    mock_recipe.name = "Pancakes"
    mock_recipe.tags = "['breakfast', 'sweet']"
    mock_recipe.minutes = 15
    
    # 1. Breakfast context + Breakfast item -> No Penalty (or small)
    # Meal 0=Morning. Params: recipe, meal_type, season
    p1 = calculate_context_penalty(mock_recipe, meal_type=0, season=0)
    assert p1 >= -0.5 # Should be reasonable
    
    # 2. Dinner context (meal=1) + Breakfast item -> Penalty
    p2 = calculate_context_penalty(mock_recipe, meal_type=1, season=0)
    assert p2 < 0 # Should be penalized
    
    # 3. Snack context (meal=2) + Breakfast item -> Small penalty or neutral
    p3 = calculate_context_penalty(mock_recipe, meal_type=2, season=0)
    
def test_train_rf_success(mock_session, mock_mlflow):
    """Test standard Random Forest training path with mocks"""
    
    # Use context managers to avoid decorator ordering confusion
    with patch("src.mlops.train_model.engine") as mock_engine, \
         patch("src.mlops.train_model.os.makedirs") as mock_makedirs, \
         patch("joblib.dump") as mock_joblib_dump:
             
        # Mock Database Query Results
        # We need to mock: 1. check for embeddings, 2. fetch interactions
        
        # query().filter().count() -> 0 (No missing embeddings)
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        
        # query().join().all() -> List of (Interaction, Recipe)
        mock_interaction = MagicMock()
        mock_interaction.user_id = 1
        mock_interaction.rating = 5.0
        
        mock_recipe = MagicMock()
        mock_recipe.id = 101
        mock_recipe.embedding = str([0.1] * 384) # Simplified vector
        mock_recipe.name = "Test Recipe"
        mock_recipe.tags = "['dinner']"
        mock_recipe.minutes = 30
        
        mock_session.query.return_value.join.return_value.all.return_value = [
            (mock_interaction, mock_recipe)
        ]

        # Run Train
        train()
        
        # Verify MLflow calls
        mock_mlflow.set_tracking_uri.assert_called()
        mock_mlflow.start_run.assert_called()
        mock_mlflow.sklearn.log_model.assert_called()
        
        # Verify joblib called (fallback save)
        mock_joblib_dump.assert_called()

@patch("src.mlops.train_model.engine")
def test_train_rf_no_data(mock_engine, mock_session, mock_mlflow):
    """Test RF training stops gracefully if no data"""
    mock_session.query.return_value.filter.return_value.count.return_value = 0
    mock_session.query.return_value.join.return_value.all.return_value = [] # Empty
    
    train()
    
    mock_mlflow.start_run.assert_not_called()

@patch("src.mlops.train_model.engine")
def test_train_svd_success(mock_engine, mock_session, mock_mlflow):
    """Test SVD training path with mocks"""
    # Mock Data
    mock_interaction = MagicMock()
    mock_interaction.user_id = 1
    mock_interaction.rating = 4.0
    
    mock_recipe = MagicMock()
    mock_recipe.id = 202
    
    mock_session.query.return_value.join.return_value.all.return_value = [
        (mock_interaction, mock_recipe)
    ]
    
    # Mock SVD & Dataset from surprise (imported inside function or module level)
    with patch("src.mlops.train_model.SVD") as mock_svd_cls, \
         patch("src.mlops.train_model.Dataset") as mock_dataset, \
         patch("src.mlops.train_model.surprise_train_test_split") as mock_tts, \
         patch("src.mlops.train_model.surprise.dump.dump") as mock_dump:
             
        mock_tts.return_value = (MagicMock(), MagicMock()) # trainset, testset
        
        train_svd()
        
        mock_mlflow.start_run.assert_called()
        mock_svd_cls.return_value.fit.assert_called()
        # Ensure model artifact logging is attempted
        mock_mlflow.log_artifact.assert_called()
        mock_dump.assert_called()

# --- TESTS FOR optimize_svd.py ---

@patch("src.mlops.optimize_svd.engine")
@patch("src.mlops.optimize_svd.Session")
def test_optimize_svd_run(mock_sess_cls, mock_engine, mock_surprise_cv):
    """Test SVD Optimization script execution"""
    mock_sess = mock_sess_cls.return_value.__enter__.return_value
    
    # Data
    mock_int = MagicMock()
    mock_int.user_id = 1
    mock_int.rating = 3.0
    mock_rec = MagicMock()
    mock_rec.id = 500
    
    mock_sess.query.return_value.join.return_value.all.return_value = [(mock_int, mock_rec)]
    
    # Mock GridSearchCV behavior
    mock_gs_instance = mock_surprise_cv.return_value
    mock_gs_instance.best_score = {"rmse": 0.99}
    mock_gs_instance.best_params = {"rmse": {"n_factors": 10}}
    
    # Run
    with patch("builtins.open", new_callable=MagicMock) as mock_open, \
         patch("json.dump") as mock_json_dump:
        run_optimize_svd()
        
        # Verify it ran fit
        mock_gs_instance.fit.assert_called()
        # Verify it tried to save json
        mock_json_dump.assert_called()

