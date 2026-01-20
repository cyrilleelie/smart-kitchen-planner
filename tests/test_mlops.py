import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Ajout du dossier courant
sys.path.append(os.getcwd())

# --- MOCKS SYSTÈME ---
# Plus besoin de mocker xgboost ici si tu ne l'utilises pas
with patch.dict(
    "sys.modules",
    {
        "src.database.connection": Mock(),
        "src.database.models": Mock(),
        "sqlalchemy.orm": MagicMock(),
        "mlflow": Mock(),
        "mlflow.sklearn": Mock(),
    },
):
    from src.mlops.train_model import (
        calculate_context_penalty,
        parse_list,
        parse_vector,
    )


# --- TESTS UTILITAIRES ---
def test_parse_list_logic():
    assert parse_list(["a"]) == ["a"]
    assert parse_list("['a']") == ["a"]
    assert parse_list(None) == []


def test_parse_vector_logic():
    vec_str = "[0.1, 0.5, 0.9]"
    res = parse_vector(vec_str)
    assert res[0] == pytest.approx(0.1, abs=1e-5)
    assert parse_vector(None).shape == (384,)


def test_context_logic_mocks():
    mock_recipe = Mock()
    mock_recipe.tags = ["heavy", "winter", "raclette"]
    mock_recipe.name = "Raclette"
    # Raclette (Main Meal) + Hiver = Bonus ou Neutre (>= 0)
    assert calculate_context_penalty(mock_recipe, 1, 0) >= 0.0


# --- TESTS PIPELINE ---

# @patch('src.mlops.train_model.Session')
# def test_train_pipeline_nominal(mock_session_cls):
#     """Test avec VRAI DataFrame Pandas (via Mock DB)"""

#     # 1. Config Session
#     mock_session = MagicMock()
#     mock_session_cls.return_value = mock_session
#     mock_session.__enter__.return_value = mock_session

#     # 2. Mock Data BDD
#     interaction = Mock()
#     interaction.user_id = 1
#     interaction.recipe_id = 101
#     interaction.rating = 5.0
#     interaction.date = datetime.now()

#     recipe = Mock()
#     recipe.id = 101
#     recipe.embedding = "[0.1, 0.2]"
#     recipe.tags = "['italian']"
#     recipe.name = "Pizza"
#     recipe.minutes = 15
#     recipe.nutrition_info = "['500']"

#     # Configuration du retour DB
#     mock_session.query.return_value.join.return_value.all.return_value = [
#         (interaction, recipe)
#     ]

#     # 3. Patch Sklearn
#     # On mocke train_test_split pour éviter les soucis de dimensions
#     with patch('sklearn.model_selection.train_test_split') as mock_split:
#         empty_df = pd.DataFrame()
#         mock_split.return_value = (empty_df, empty_df, np.array([]), np.array([]))

#         # CORRECTION : On mocke RandomForestRegressor au lieu de XGBoost
#         with patch('sklearn.ensemble.RandomForestRegressor'):
#              try:
#                 train()
#              except Exception as e:
#                 pytest.fail(f"Le script d'entraînement a planté : {e}")

#     assert mlflow.start_run.called
#     assert mlflow.sklearn.log_model.called

# @patch('src.mlops.train_model.Session')
# def test_train_pipeline_no_data(mock_session_cls):
#     """Test base vide sans mocker Pandas"""
#     mock_session = MagicMock()
#     mock_session_cls.return_value = mock_session
#     mock_session.__enter__.return_value = mock_session

#     # Retour vide
#     mock_session.query.return_value.join.return_value.all.return_value = []

#     train()

#     assert not mlflow.start_run.called


# --- TESTS LOGIQUE METIER DETAILLEE ---
def create_mock_recipe(name, tags, minutes=15):
    r = Mock()
    r.name = name
    r.tags = str(tags)
    r.minutes = minutes
    return r


def test_logic_penalty_breakfast_steak():
    r = create_mock_recipe("Steak", ["beef", "main_meal"])
    assert calculate_context_penalty(r, meal_type=0, season=0) < 0.0


def test_logic_bonus_winter_soup():
    r = create_mock_recipe("Soup", ["soup", "winter"])
    assert calculate_context_penalty(r, meal_type=1, season=0) >= 0.0


def test_logic_penalty_summer_soup():
    r = create_mock_recipe("Soup", ["soup", "winter"])
    # Pénalité saison (-1.5) + Bonus Main Meal (+0.5) = -1.0
    assert calculate_context_penalty(r, meal_type=1, season=2) <= -0.5


def test_logic_snack_timing():
    r = create_mock_recipe("Cake", ["snack"], minutes=60)
    assert calculate_context_penalty(r, meal_type=2, season=1) < 0.0
