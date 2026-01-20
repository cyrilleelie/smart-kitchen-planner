from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import Recipe
from dotenv import load_dotenv

load_dotenv()
import logging  # noqa: E402
from src.utils.logging_config import setup_logging  # noqa: E402

setup_logging()
logger = logging.getLogger(__name__)


def generate_recipe_embeddings():
    logger.info("🧠 Chargement du modèle NLP (Sentence-BERT)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    with Session(engine) as session:
        # --- ÉTAPE 1 : DIAGNOSTIC VÉRITÉ ---
        # On regarde la première recette brute pour voir comment Python voit le champ embedding
        sample = session.query(Recipe).first()
        if sample:
            logger.debug(f"🕵️ [DEBUG] Recette '{sample.name}' (ID: {sample.id})")
            logger.debug(f"   Valeur actuelle embedding (Python): {sample.embedding}")
            logger.debug(f"   Type de la donnée: {type(sample.embedding)}")

        # --- ÉTAPE 2 : SÉLECTION ---
        # On cherche ceux qui sont None
        recipes = session.query(Recipe).filter(Recipe.embedding == None).all()

        total = len(recipes)
        print(f"👉 {total} recettes à traiter (NULL détectés).")

        if total == 0:
            logger.warning("⚠️ Aucune recette détectée via le filtre ORM standard.")
            logger.warning(
                "🛑 FORCE UPDATE : On prend les 10 premières pour tester l'écriture."
            )
            recipes = session.query(Recipe).limit(10).all()
            total = len(recipes)

        logger.info("🔄 Démarrage de la vectorisation...")

        count = 0
        for recipe in recipes:
            try:
                # Gestion sécurisée des champs
                r_name = recipe.name if recipe.name else "Sans nom"
                r_desc = recipe.description if recipe.description else ""
                r_tags = recipe.tags if recipe.tags else ""
                r_ingredients = recipe.ingredients if recipe.ingredients else ""

                combined_text = f"{r_name}. {r_desc}. {r_tags}. {r_ingredients}"

                # --- CORRECTION CRITIQUE ICI ---
                # On génère le vecteur (c'est une liste de floats)
                vector = model.encode(combined_text).tolist()

                # ON N'UTILISE PAS json.dumps() !
                # Le modèle est Column(JSON), donc on lui donne directement la liste.
                recipe.embedding = vector
                # -------------------------------

                count += 1
                if count % 10 == 0:
                    session.commit()
                    logger.info(f"   [{count}/{total}] Traité : {r_name[:30]}...")

            except Exception as e:
                logger.error(f"❌ Erreur ID {recipe.id}: {e}")
                continue

        session.commit()
        session.commit()
        logger.info("✅ Terminé ! Base de données mise à jour.")


if __name__ == "__main__":
    generate_recipe_embeddings()
