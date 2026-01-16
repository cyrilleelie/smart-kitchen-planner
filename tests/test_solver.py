import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import text

# --- SETUP DES MOCKS ---
with patch.dict(
    "sys.modules", {"src.database.models": Mock(), "sqlalchemy.orm": Mock()}
):
    from src.recommender.solver import MenuSolver, Recipe

# --- CORRECTIF CRITIQUE POUR SQLALCHEMY ---
# 1. On crée un "faux" objet SQL valide
dummy_sql = text("1=1")

# 2. On REMPLACE les attributs de la classe par des MagicMocks
# Cela contourne la protection "read-only" de SQLAlchemy
Recipe.minutes = MagicMock()
Recipe.embedding = MagicMock()

# 3. On configure ces nouveaux Mocks pour renvoyer du SQL valide
Recipe.minutes.__le__.return_value = dummy_sql
Recipe.embedding.__ne__.return_value = dummy_sql

# --- TESTS ---


def test_similarity_maths():
    """Vérifie le calcul de similarité cosinus"""
    solver = MenuSolver(Mock(), [1, 0], 1, 2000, 1)

    # Identique -> 1.0
    assert solver._calculate_similarity([1, 0]) == pytest.approx(1.0)
    # Opposé -> 0.0
    assert solver._calculate_similarity([-1, 0]) == pytest.approx(0.0)
    # Orthogonal -> 0.5
    assert solver._calculate_similarity([0, 1]) == pytest.approx(0.5)


def test_solve_nominal_flow():
    """Test complet de la génération de menu"""
    mock_db = Mock()

    # On génère 10 fausses recettes
    mock_candidates = []
    for i in range(10):
        # Alterne vecteurs proches et loin
        emb = "[1, 0]" if i % 2 == 0 else "[0, 1]"
        mock_candidates.append((i, emb, 500))

    # Configuration du chaînage SQL : query().filter().all()
    q = mock_db.query.return_value
    f = q.filter.return_value
    f.all.return_value = mock_candidates
    # Astuce : si le code fait filter().filter(), on renvoie le même objet
    f.filter.return_value = f

    solver = MenuSolver(
        db=mock_db,
        user_vector=[1.0, 0.0],  # User aligné sur [1, 0]
        days=2,
        target_calories=2000,
        meals_per_day=2,
    )

    menu = solver.solve()

    # On attend 2 jours * 2 repas = 4 slots
    assert len(menu) == 4
    # On vérifie qu'on a bien des types définis
    assert "algo_type" in menu[0]
    assert menu[0]["score"] > 0


def test_solve_empty_database():
    """Si la base ne renvoie rien, le menu est vide"""
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    solver = MenuSolver(mock_db, [1, 0], 1, 2000, 1)
    assert solver.solve() == []


def test_solve_fallback_rescue():
    """Si algorithme trop restrictif, le mode RESCUE prend le relais"""
    mock_db = Mock()
    # 5 Recettes identiques -> Les percentiles seront écrasés
    mock_candidates = [(i, "[1, 0]", 500) for i in range(5)]

    q = mock_db.query.return_value
    f = q.filter.return_value
    f.all.return_value = mock_candidates
    f.filter.return_value = f

    solver = MenuSolver(mock_db, [1, 0], days=1, target_calories=2000, meals_per_day=2)
    menu = solver.solve()

    assert len(menu) == 2
