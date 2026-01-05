import ast
import sys
import os

# Ajout du chemin racine pour trouver les modules src
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import Recipe
from src.recommender.cleaner import TagCleaner

def clean_database_tags():
    print("🧹 Démarrage du Grand Nettoyage des Tags...")
    
    with Session(engine) as session:
        recipes = session.query(Recipe).all()
        total = len(recipes)
        print(f"   📉 {total} recettes à traiter.")
        
        modified_count = 0
        
        for i, recipe in enumerate(recipes):
            original_tags_str = recipe.tags
            try:
                # 1. Conversion String -> Liste
                tags_list = ast.literal_eval(original_tags_str) if isinstance(original_tags_str, str) else []
                
                # 2. Filtrage
                # On GARDE : Goût, Type (Dessert...), Diète (Vegan...)
                # On JETTE : Bruit (Preparation, Time, Equipment...)
                clean_list = []
                for tag in tags_list:
                    category = TagCleaner.get_tag_category(tag)
                    if category != "NOISE": # On supprime uniquement le bruit
                        clean_list.append(tag)
                
                # 3. Vérification si changement
                if len(clean_list) != len(tags_list):
                    # 4. Sauvegarde (Retour en String)
                    recipe.tags = str(clean_list)
                    modified_count += 1
            
            except Exception as e:
                print(f"⚠️ Erreur ID {recipe.id}: {e}")
                continue
            
            # Barre de progression simple
            if i % 500 == 0:
                print(f"      -> {i}/{total} traités...")

        print("   💾 Validation des modifications en base...")
        session.commit()
        
    print(f"✅ Terminé ! {modified_count} recettes ont été nettoyées.")
    print("   Les tags techniques (bruit) ont été supprimés définitivement.")

if __name__ == "__main__":
    clean_database_tags()