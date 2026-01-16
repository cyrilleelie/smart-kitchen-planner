import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.append(os.getcwd())

with patch.dict('sys.modules', {
    'sentence_transformers': Mock(),
    'src.database.connection': Mock(),
    'src.database.models': Mock(),
    'sqlalchemy.orm': MagicMock(),
}):
    from src.recommender.vectorizer import generate_recipe_embeddings
    from src.database.models import Recipe

@patch('src.recommender.vectorizer.Session')
@patch('src.recommender.vectorizer.SentenceTransformer')
@patch('src.recommender.vectorizer.setup_logging')
def test_generate_recipe_embeddings_flow(mock_logging, mock_transformer_cls, mock_session_cls):
    """Teste le flux de vectorisation"""
    # 1. Config NLP
    mock_model = mock_transformer_cls.return_value
    mock_model.encode.return_value.tolist.return_value = [0.1, 0.2]

    # 2. Config Session
    mock_session = mock_session_cls.return_value.__enter__.return_value
    
    # Recette Test
    r1 = Mock(id=1, name="Pasta", embedding=None)
    
    # 3. Config Query "Bulldozer"
    # On crée un objet Mock pour la Query
    mock_query = MagicMock()
    mock_session.query.side_effect = lambda *args: mock_query
    
    # CRITIQUE : On configure toutes les méthodes de chaînage pour renvoyer self
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    
    # On force le retour de .all() via side_effect pour être sûr
    mock_query.all.side_effect = lambda: [r1]
    
    # On force aussi le retour de .first()
    mock_query.first.return_value = r1

    # 4. Exécution
    generate_recipe_embeddings()
    
    # 5. Assertions
    assert mock_model.encode.called
    # Comme r1 est un Mock, on vérifie l'assignation de l'attribut
    assert r1.embedding == [0.1, 0.2]
    assert mock_session.commit.called

@patch('src.recommender.vectorizer.Session')
@patch('src.recommender.vectorizer.SentenceTransformer')
def test_generate_embeddings_empty_db(mock_transformer_cls, mock_session_cls):
    """Vérifie le cas vide"""
    mock_session = mock_session_cls.return_value.__enter__.return_value
    mock_query = mock_session.query.return_value
    
    # Config vide
    mock_query.first.return_value = None
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    # side_effect renvoie liste vide
    mock_query.all.side_effect = lambda: []
    
    generate_recipe_embeddings()
    
    mock_model = mock_transformer_cls.return_value
    assert not mock_model.encode.called