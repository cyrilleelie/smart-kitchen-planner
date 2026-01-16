from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.database.connection import engine
from src.database.models import Recipe
import os
import logging
from dotenv import load_dotenv
from src.utils.logging_config import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

def generate_recipe_embeddings(model_name: str = 'all-MiniLM-L6-v2', batch_size: int = 10) -> int:
    """
    Generate and persist embeddings for recipes in the database.
    
    Loads the sentence-transformer model and processes recipes that either
    lack an embedding or are forced to update. Uses the recipe name, description,
    tags, and ingredients to build a semantic vector.
    
    Args:
        model_name: Name of the NLP model to load (default: 'all-MiniLM-L6-v2')
        batch_size: Number of recipes to process before committing (default: 10)
        
    Returns:
        Number of recipes processed.
    """
    logger.info(f"🧠 Loading NLP model ({model_name})...")
    try:
        model = SentenceTransformer(model_name)
    except Exception as e:
        logger.error(f"❌ Failed to load model {model_name}: {e}")
        return 0
    
    with Session(engine) as session:
        # Check for recipes needing embeddings
        recipes = session.query(Recipe).filter(Recipe.embedding == None).all()
        total = len(recipes)
        logger.info(f"👉 Found {total} recipes needing embeddings.")

        if total == 0:
            logger.warning("⚠️ No recipes found with missing embeddings.")
            # Optional: logic to force update could be added here via flag
            return 0

        logger.info(f"🔄 Starting vectorization for {total} recipes...")
        
        count = 0
        success_count = 0
        for recipe in recipes:
            try:
                # Safe field access
                r_name = recipe.name or "Sans nom"
                r_desc = recipe.description or ""
                r_tags = recipe.tags or ""
                r_ingredients = recipe.ingredients or ""

                combined_text = f"{r_name}. {r_desc}. {r_tags}. {r_ingredients}"
                
                # Generate vector
                vector = model.encode(combined_text).tolist()
                
                # Update model
                recipe.embedding = vector 
                
                count += 1
                success_count += 1
                
                if count % batch_size == 0:
                    session.commit()
                    logger.info(f"   [{count}/{total}] Processed: {r_name[:30]}...")
            
            except Exception as e:
                logger.error(f"❌ Error processing recipe ID {recipe.id}: {e}")
                continue

        # Final commit
        try:
            session.commit()
            logger.info(f"✅ Finished! Updated {success_count} recipes.")
        except Exception as e:
            logger.error(f"❌ Database commit failed: {e}")
            session.rollback()

    return success_count

if __name__ == "__main__":
    generate_recipe_embeddings()