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
                return InferenceService()

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
    """Teste le flux complet de recommandation"""
    mock_session = Mock()
    
    # 1. Setup Candidats
    r1 = Mock(id=1, embedding="[1, 0]")
    r2 = Mock(id=2, embedding="[0, 1]")
    
    # 2. Configuration du Mock Query avec Side Effect
    # On doit différencier:
    # A. query(Recipe) -> Candidats
    # B. query(Recipe.embedding) -> User Vector
    
    # On prépare les Mocks de retour
    candidates_query_mock = Mock()
    candidates_query_mock.limit.return_value.all.return_value = [r1, r2]
    
    user_vector_query_mock = Mock()
    user_vector_query_mock.join.return_value.filter.return_value.all.return_value = [("[1.0, 0.0]",)]

    def query_side_effect(*args):
        # Si query() est appelé sans argument ou avec Recipe (qui est un Mock)
        # C'est difficile à distinguer.
        # ASTUCE : On regarde si l'argument a un attribut 'embedding' (cas Recipe.embedding)
        # Ou s'il est utilisé pour join/filter.
        
        # Le plus simple : on renvoie un mock polyvalent qui change de comportement selon ce qu'on appelle dessus
        m = Mock()
        
        # Si on appelle .limit().all(), c'est les candidats
        m.limit.return_value.all.return_value = [r1, r2]
        
        # Si on appelle .join().filter().all(), c'est le user vector
        m.join.return_value.filter.return_value.all.return_value = [("[1.0, 0.0]",)]
        
        return m

    mock_session.query.side_effect = query_side_effect

    # 3. Exécution
    recs = mock_service.recommend(1, 1, 0, mock_session, top_k=2)
    
    # 4. Validation
    assert len(recs) == 2
    # predict renvoie [0.9, 0.1], donc r1 est premier
    assert recs[0]["recipe"].id == 1

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