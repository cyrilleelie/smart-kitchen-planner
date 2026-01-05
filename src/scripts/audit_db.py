import ast
import sys
import os
from collections import Counter

# Setup des imports
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import Recipe

def audit_database():
    print("🕵️‍♂️ Audit DIRECT de la Base de Données (PostgreSQL)...")
    
    tag_counter = Counter()
    
    with Session(engine) as session:
        # On récupère tous les tags de la base
        recipes = session.query(Recipe.tags).all()
        print(f"   📊 Analyse de {len(recipes)} recettes en base...")
        
        for (tags_str,) in recipes:
            try:
                if isinstance(tags_str, str):
                    tags_list = ast.literal_eval(tags_str)
                    tag_counter.update(tags_list)
            except:
                continue

    print(f"\n✅ Total de tags uniques en base : {len(tag_counter)}")
    
    print("\n🏆 TOP 50 des Tags en Base (Après Nettoyage) :")
    print("-" * 60)
    for i, (tag, count) in enumerate(tag_counter.most_common(50), 1):
        print(f"{i:>2}. {tag:<35} : {count}")
    print("-" * 60)

if __name__ == "__main__":
    audit_database()