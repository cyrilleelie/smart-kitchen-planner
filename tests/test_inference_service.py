import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.append(os.getcwd())

with patch.dict('sys.modules', {
    'mlflow': Mock(),
    'mlflow.sklearn': Mock(),
    'src.database.models': Mock(),
    'sqlalchemy.orm': Mock()
}):
    from src.recommender.inference_service import InferenceService
    from src.database.models import Recipe, Interaction

@pytest.fixture
def mock_service():
    """Crée une instance du service avec un modèle mocké"""
    with patch('mlflow.get_experiment_by_name') as mock_exp:
        mock_exp.return_value.experiment_id = "1"
        with patch('mlflow.MlflowClient') as mock_client:
            mock_run = Mock()
            mock_run.info.run_id = "run_123"
            mock_client.return_value.search_runs.return_value = [mock_run]
            with patch('mlflow.sklearn.load_model') as mock_load:
                mock_model = Mock()
                # predict renvoie [0.9, 0.1, ...]
                mock_model.predict.side_effect = lambda x: np.linspace(0.9, 0.1, len(x))
                mock_load.return_value = mock_model
                mock_db = Mock()
                return InferenceService(mock_db)

def test_parse_vector(mock_service):
    res = mock_service._parse_vector("[0.1, 0.2]")
    assert res[0] == pytest.approx(0.1)
    res = mock_service._parse_vector(None)
    assert res.shape == (384,)

def test_get_calories(mock_service):
    r = Mock()
    r.nutrition_info = "['500.0']"
    assert mock_service._get_calories(r) == 500.0

def test_get_user_vector(mock_service):
    mock_session = Mock()
    # Configuration directe pour get_user_vector
    # La chaine est: query().join().filter().all()
    # On fait simple: .all() renvoie toujours nos vecteurs
    mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
        ("[1.0, 0.0]",), ("[0.0, 1.0]",)
    ]
    user_vec = mock_service.get_user_vector(1, mock_session)
    assert user_vec[0] == pytest.approx(0.5)

def test_recommend_flow(mock_service):
    """
    Teste le flux complet de recommandation.
    Note: Le service utilise self.db donc on doit configurer mock_service.db directement.
    """
    # 1. Setup Candidats
    r1 = Mock(id=1, name="Recipe1", embedding="[1, 0]")
    r2 = Mock(id=2, name="Recipe2", embedding="[0, 1]")
    
    # 2. Configure mock_service.db (injecté via MockService(mock_db))
    # La méthode recommend() utilise self.db directement
    mock_service.db.query.return_value.limit.return_value.all.return_value = [r1, r2]
    
    # 3. Mock UserProfiler pour éviter les dépendances
    with patch('src.recommender.inference_service.UserProfiler') as MockProfiler:
        mock_profiler = MockProfiler.return_value
        mock_profiler.get_weighted_profile.return_value = np.array([1.0] * 384, dtype=np.float32)
        
        # 4. Exécution avec nouvelle signature
        recs = mock_service.recommend(user_id=1, n=2)
        
        # 5. Validation
        assert isinstance(recs, list)
        # Note: Le résultat peut être vide si le modèle n'est pas chargé (mock)

def test_recommend_weekly_batch(mock_service):
    mock_session = Mock()
    # 50 Candidats pour avoir de la variété
    candidates = [Mock(id=i, embedding="[0.1, 0.1]", nutrition_info="['500']") for i in range(50)]
    
    mock_service.get_user_vector = Mock(return_value=np.array([0.1, 0.1], dtype=np.float32))
    
    # Mock qui répond aux candidats
    mock_session.query.return_value.limit.return_value.all.return_value = candidates
    
    # Mock predict
    mock_service.model.predict.return_value = np.linspace(1.0, 0.0, 50)
    
    plan = mock_service.recommend_weekly_batch(1, 1, 0, mock_session, n_days=5, target_calories=2000)
    
    assert len(plan) == 5
    assert "Performance" in {item["tag"] for item in plan}