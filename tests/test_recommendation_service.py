from unittest.mock import MagicMock, patch
import pytest
from src.domain.recommendation_service import (
    generate_recommendations,
    SVDSurpriseStrategy,
    RandomForestStrategy,
    _apply_constraints,
)
from src.database.models import Recipe


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


@pytest.fixture
def mock_recipes():
    r1 = Recipe(id=1, name="R1", tags="['vegetarian']", minutes=20)
    r2 = Recipe(id=2, name="R2", tags="['meat']", minutes=40)
    return [r1, r2]


def test_apply_constraints(mock_db, mock_recipes):
    # Setup mock query
    mock_query = mock_db.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [(1,), (2,)]

    constraints = {"vegetarian": True, "max_time": 30}
    ids = _apply_constraints(mock_db, constraints)

    assert ids == [
        1,
        2,
    ]  # Mock returns 1, 2 regardless of filter implementation, just checking flow
    # Verification of filter calls
    assert mock_db.query.call_count == 1


@patch("src.domain.recommendation_service.InferenceService")
def test_random_forest_strategy(mock_inference_cls, mock_db):
    mock_service = mock_inference_cls.return_value
    # Service returns list of dicts with 'id' and 'score'
    mock_service.recommend.return_value = [
        {"id": 1, "score": 0.9},
        {"id": 2, "score": 0.5},
        {"id": 3, "score": 0.1},
    ]

    strategy = RandomForestStrategy(mock_db)
    # Testing for candidate_ids=[1, 3], so 2 should be filtered out
    ranked = strategy.rank(user_id=1, candidate_ids=[1, 3], top_n=2)

    assert len(ranked) == 2
    assert ranked[0] == (1, 0.9)
    assert ranked[1] == (3, 0.1)


@patch("src.domain.recommendation_service.surprise.dump.load")
def test_svd_surprise_strategy(mock_dump_load, mock_db):
    # Mock the algorithm
    mock_algo = MagicMock()
    # Mock predict: returns an object with .est attribute
    start_prediction = MagicMock()
    start_prediction.est = 3.5
    mock_algo.predict.side_effect = lambda uid, iid: start_prediction

    mock_dump_load.return_value = {"algo": mock_algo}

    strategy = SVDSurpriseStrategy(mock_db)
    ranked = strategy.rank(user_id=1, candidate_ids=[10, 20], top_n=2)

    assert len(ranked) == 2
    assert ranked[0] == (10, 3.5)
    assert ranked[1] == (20, 3.5)


@patch("src.domain.recommendation_service.surprise.dump.load")
def test_svd_surprise_strategy_fallback(mock_dump_load, mock_db):
    mock_algo = MagicMock()
    # Simulate a NaN return from surprise (unknown user/item)
    nan_prediction = MagicMock()
    nan_prediction.est = float("nan")
    mock_algo.predict.return_value = nan_prediction

    mock_dump_load.return_value = {"algo": mock_algo}

    # Mock global average query
    # db.query().filter().scalar()
    mock_db.query.return_value.filter.return_value.scalar.return_value = 4.2

    strategy = SVDSurpriseStrategy(mock_db)
    ranked = strategy.rank(user_id=999, candidate_ids=[5], top_n=1)

    assert len(ranked) == 1
    assert ranked[0] == (5, 4.2)


@patch("src.domain.recommendation_service.RandomForestStrategy")
@patch("src.domain.recommendation_service.SVDSurpriseStrategy")
@patch("src.domain.recommendation_service._apply_constraints")
def test_generate_recommendations_content_based(
    mock_constraints, mock_svd, mock_rf, mock_db, mock_recipes
):
    mock_constraints.return_value = [1, 2]
    mock_rf_instance = mock_rf.return_value
    mock_rf_instance.rank.return_value = [(1, 0.9), (2, 0.8)]

    # Mock DB query for final recipe retrieval
    mock_query = mock_db.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = mock_recipes  # [r1(1), r2(2)]

    res = generate_recommendations(mock_db, user_id=1, model_type="content_based")

    assert len(res) == 2
    assert res[0].id == 1
    assert res[1].id == 2
    mock_rf.assert_called_once()
    mock_svd.assert_not_called()


@patch("src.domain.recommendation_service.RandomForestStrategy")
@patch("src.domain.recommendation_service.SVDSurpriseStrategy")
@patch("src.domain.recommendation_service._apply_constraints")
def test_generate_recommendations_collaborative(
    mock_constraints, mock_svd, mock_rf, mock_db, mock_recipes
):
    mock_constraints.return_value = [2]
    mock_svd_instance = mock_svd.return_value
    mock_svd_instance.rank.return_value = [(2, 4.5)]

    mock_query = mock_db.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [mock_recipes[1]]  # r2 only

    res = generate_recommendations(mock_db, user_id=1, model_type="collaborative")

    assert len(res) == 1
    assert res[0].id == 2
    mock_svd.assert_called_once()
    mock_rf.assert_not_called()
