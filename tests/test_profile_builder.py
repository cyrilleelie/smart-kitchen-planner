import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import text
import src.utils.translations

# --- SETUP DES MOCKS ---
with patch.dict(
    "sys.modules", {"src.database.models": Mock(), "sqlalchemy.orm": Mock()}
):
    from src.recommender.profile_builder import UserProfiler

# --- CONFIG SQLALCHEMY ---
dummy_sql = text("1=1")
MOCK_TAGS_MAP = {"Végétarien": "vegetarian", "Rapide": "15-minutes-or-less"}


@pytest.fixture
def mock_profiler():
    mock_db = Mock()
    return UserProfiler(mock_db)


# --- TESTS UTILITAIRES ---
def test_get_converted_tags_nominal(mock_profiler):
    input_tags = ["Végétarien", "Rapide"]
    with patch.dict(
        src.utils.translations.PREFERENCE_TAGS_MAP, MOCK_TAGS_MAP, clear=True
    ):
        res = mock_profiler.get_converted_tags(input_tags)
    assert "vegetarian" in res


def test_get_converted_tags_empty(mock_profiler):
    assert mock_profiler.get_converted_tags([]) == []


def test_parse_embedding_profiler(mock_profiler):
    assert mock_profiler._parse_embedding("[0.1, 0.2]") == [0.1, 0.2]
    assert mock_profiler._parse_embedding(None) == []


# --- TESTS LOGIQUE METIER ---


@patch("src.recommender.profile_builder.or_")
def test_get_weighted_profile_full_flow(mock_or, mock_profiler):
    """Teste la construction complète d'un profil"""
    mock_or.return_value = dummy_sql

    # 1. Objets FIXES pour les retours BDD
    fixed_user = MagicMock()
    fixed_user.preferences = ["Végétarien"]

    fixed_recipe = Mock()
    fixed_recipe.embedding = "[1.0, 0.0]"

    fixed_interaction = Mock()
    fixed_interaction.recipe.embedding = "[0.0, 1.0]"

    # 2. Side Effect ROBUSTE
    def query_side_effect(model):
        m = Mock()
        # On compare le NOM de la classe pour éviter les soucis d'import
        model_name = getattr(model, "__name__", str(model))

        if "Recipe" in model_name:
            m.filter.return_value.filter.return_value.limit.return_value.all.return_value = [
                fixed_recipe
            ]
            m.filter.return_value.all.return_value = [fixed_recipe]
        elif "Interaction" in model_name:
            m.filter.return_value.all.return_value = [fixed_interaction]
        elif "User" in model_name:
            m.filter.return_value.first.return_value = fixed_user
        return m

    mock_profiler.db.query.side_effect = query_side_effect

    # 3. PATCH DES CLASSES (La Correction Clé)
    from src.recommender import profile_builder as pb_module

    # On crée des faux attributs qui acceptent .ilike()
    mock_col = MagicMock()
    mock_col.ilike.return_value = dummy_sql

    # On utilise setattr pour REMPLACER la colonne protégée par notre Mock
    if hasattr(pb_module, "Recipe"):
        setattr(pb_module.Recipe, "tags", mock_col)
        setattr(pb_module.Recipe, "name", mock_col)

        mock_emb = MagicMock()
        mock_emb.__ne__.return_value = dummy_sql
        setattr(pb_module.Recipe, "embedding", mock_emb)

    if hasattr(pb_module, "Interaction"):
        mock_rating = MagicMock()
        mock_rating.__ge__.return_value = dummy_sql
        setattr(pb_module.Interaction, "rating", mock_rating)

    # Exécution du test
    with patch.dict(
        src.utils.translations.PREFERENCE_TAGS_MAP, MOCK_TAGS_MAP, clear=True
    ):
        profile_vec = mock_profiler.get_weighted_profile(1, request_tags=["Rapide"])

    assert profile_vec is not None
    assert len(profile_vec) == 2
    assert profile_vec[0] > 0


@patch("src.recommender.profile_builder.or_")
def test_get_weighted_profile_cold_start(mock_or, mock_profiler):
    """Teste le cas 'Cold Start'"""
    mock_or.return_value = dummy_sql

    def empty_side_effect(model):
        m = Mock()
        m.filter.return_value.first.return_value = None
        m.filter.return_value.all.return_value = []
        m.filter.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )
        return m

    mock_profiler.db.query.side_effect = empty_side_effect

    res = mock_profiler.get_weighted_profile(999, request_tags=[])
    assert res is None


@patch("src.recommender.profile_builder.or_")
def test_get_weighted_profile_tag_not_found(mock_or, mock_profiler):
    """Vérifie le cas où un tag utilisateur ne correspond à aucune recette en base"""
    mock_or.return_value = dummy_sql

    # 1. User avec le tag "Inexistant"
    mock_user = MagicMock()
    mock_user.preferences = ["Inexistant"]

    # 2. Configuration du Mock DB pour renvoyer VIDE pour les recettes
    def query_side_effect(model):
        m = Mock()
        # On compare le nom de la classe
        model_name = getattr(model, "__name__", str(model))

        if "Recipe" in model_name:
            # Aucune recette trouvée !
            m.filter.return_value.filter.return_value.limit.return_value.all.return_value = (
                []
            )
            m.filter.return_value.all.return_value = []
        elif "User" in model_name:
            m.filter.return_value.first.return_value = mock_user
        elif "Interaction" in model_name:
            m.filter.return_value.all.return_value = []
        return m

    mock_profiler.db.query.side_effect = query_side_effect

    # On lance. Le code doit gérer la liste vide sans planter et renvoyer None (car aucun vecteur)
    # (ou un vecteur vide si d'autres tags marchaient, mais ici on a qu'un seul tag qui échoue)
    with patch.dict(src.utils.translations.PREFERENCE_TAGS_MAP, {}, clear=True):
        res = mock_profiler.get_weighted_profile(1, request_tags=[])

    # Comme le seul tag n'a rien donné, le profil est vide -> None
    assert res is None
