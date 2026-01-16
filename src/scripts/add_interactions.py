import sys
import os
import argparse
import random
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.database.connection import engine
from src.database.models import User, Recipe, Interaction
from src.scripts.inject_persona import analyze_recipe_taste, load_persona

def add_interactions(username: str, count: int, persona_path: str):
    print(f"🚀 Adding {count} new interactions for user '{username}' using rules from '{persona_path}'")
    
    # 1. Load Persona Rules
    try:
        persona = load_persona(persona_path)
        rules = persona["behavior_rules"]
    except Exception as e:
        print(f"❌ Error loading persona file: {e}")
        return

    with Session(engine) as session:
        # 2. Get User
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User '{username}' not found in database.")
            return

        print(f"   👤 User found: ID {user.id}")

        # 3. Identify Unrated Recipes
        # Get all recipe IDs
        all_recipe_ids = {r.id for r in session.query(Recipe.id).all()}
        
        # Get rated recipe IDs
        rated_recipe_ids = {i.recipe_id for i in session.query(Interaction.recipe_id).filter(Interaction.user_id == user.id).all()}
        
        # Determine candidates
        candidate_ids = list(all_recipe_ids - rated_recipe_ids)
        
        if not candidate_ids:
            print("   ⚠️ This user has already rated ALL recipes available!")
            return

        # 4. Select Random Recipes
        sample_size = min(count, len(candidate_ids))
        selected_ids = random.sample(candidate_ids, sample_size)
        
        print(f"   🎲 Selected {sample_size} new recipes to rate (out of {len(candidate_ids)} available).")

        # 5. Generate Interactions
        new_interactions = []
        # Pre-fetch recipe objects for selected IDs to avoid N queries
        selected_recipes = session.query(Recipe).filter(Recipe.id.in_(selected_ids)).all()
        
        for recipe in selected_recipes:
            rating = analyze_recipe_taste(recipe, rules)
            
            interaction = Interaction(
                user_id=user.id,
                recipe_id=recipe.id,
                rating=rating,
                # Use current UTC time (timezone aware if needed, currently datetime.utcnow handles it as naive UTC)
                date=datetime.utcnow() 
            )
            new_interactions.append(interaction)

        # 6. Batch Insert
        session.add_all(new_interactions)
        session.commit()
        
        print(f"✅ Successfully added {len(new_interactions)} new interactions for '{username}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add random interactions to an existing user based on persona rules.")
    parser.add_argument("username", type=str, help="Username of the existing user")
    parser.add_argument("count", type=int, help="Number of new interactions to generate")
    parser.add_argument("persona_file", type=str, help="Path to the JSON persona file containing behavior rules")

    args = parser.parse_args()
    
    add_interactions(args.username, args.count, args.persona_file)
