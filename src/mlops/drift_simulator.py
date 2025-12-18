import random
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models import User, Recipe, Interaction

def simulate_meat_crisis(user_id: int, n_interactions=20):
    print(f"🚨 DÉBUT DE LA SIMULATION : CONVERSION VÉGÉTARIENNE...")
    
    engine = create_engine("sqlite:///smartretail.db")
    with Session(engine) as session:
        user = session.get(User, user_id)
        all_recipes = session.query(Recipe).all()
        
        # 1. IDENTIFICATION DES GROUPES
        meat_keywords = ['chicken', 'beef', 'pork', 'steak', 'bacon']
        veg_keywords = ['vegetarian', 'tofu', 'salad', 'vegetable', 'bean', 'lentil']
        
        meat_recipes = []
        veg_recipes = []
        
        for r in all_recipes:
            text = (r.name + " " + str(r.tags)).lower()
            if any(k in text for k in meat_keywords):
                meat_recipes.append(r)
            if any(k in text for k in veg_keywords) and not any(k in text for k in meat_keywords):
                veg_recipes.append(r)
        
        print(f"   🎯 Cibles : {len(meat_recipes)} carnées vs {len(veg_recipes)} végétariennes.")
        
        interactions = []
        simulation_date = datetime.now() # C'est arrivé "maintenant"

        # 2. ACTION A : Rejet de la viande (Note 1/5)
        # Cela sert au Monitor (baisse de la moyenne)
        sample_meat = random.sample(meat_recipes, min(len(meat_recipes), n_interactions))
        for recipe in sample_meat:
            interactions.append(Interaction(
                user_id=user.id, recipe_id=recipe.id, rating=1, 
                timestamp=simulation_date, context_snapshot={"event": "hate_meat"}
            ))

        # 3. ACTION B : Adoption Végétarienne (Note 5/5)
        # Cela sert au Retrain (Nouveau vecteur positif)
        sample_veg = random.sample(veg_recipes, min(len(veg_recipes), n_interactions))
        for recipe in sample_veg:
            interactions.append(Interaction(
                user_id=user.id, recipe_id=recipe.id, rating=5, 
                timestamp=simulation_date, context_snapshot={"event": "love_veggie"}
            ))
            print(f"   🥗 User a noté 5/5 : {recipe.name}")

        session.add_all(interactions)
        session.commit()
        print(f"✅ Injection massive : {len(interactions)} interactions (Rejet Viande + Love Veggie).")

if __name__ == "__main__":
    simulate_meat_crisis(user_id=1)