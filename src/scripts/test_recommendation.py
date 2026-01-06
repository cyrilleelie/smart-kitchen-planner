from src.recommender.content_engine import ContentEngine
from src.database.connection import engine
from sqlalchemy.orm import Session
from src.database.models import Recipe

def get_recipe_details(recipe_ids):
    """Petite fonction utilitaire pour afficher les noms des recettes trouvées"""
    with Session(engine) as db:
        recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
        # On remet dans l'ordre de la recommandation
        recipe_map = {r.id: r.name for r in recipes}
        return [recipe_map.get(rid, "Unknown") for rid in recipe_ids]

def test():
    print("--- 🧪 TEST DU MOTEUR DE RECOMMANDATION ---")
    
    # 1. Initialisation
    recsys = ContentEngine()
    
    # 2. Scénarios de test
    scenarios = [
        ["chicken", "rice", "salt", "pepper"], # Cas classique (salt/pepper doivent être ignorés)
        ["chocolate", "cake", "party"],        # Cas dessert (party doit être ignoré)
        ["tomato", "pasta", "italian"],        # Cas italien
        ["absurd", "word", "chicken"]          # Cas bruit
    ]
    
    for ingredients in scenarios:
        print(f"\n👤 Utilisateur demande : {ingredients}")
        ids = recsys.recommend(ingredients, top_k=3)
        
        if ids:
            names = get_recipe_details(ids)
            for name in names:
                print(f"   🍲 Recommandation : {name}")
        else:
            print("   ❌ Aucune recommandation trouvée.")

if __name__ == "__main__":
    test()