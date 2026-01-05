import pandas as pd
import ast
from collections import Counter

def audit_tags():
    print("🕵️‍♂️ Audit des Tags en cours...")
    
    # On lit juste la colonne tags pour aller vite
    df = pd.read_csv("data/raw/RAW_recipes.csv", usecols=['tags'])
    
    tag_counter = Counter()
    
    for raw_tags in df['tags']:
        try:
            # Conversion de la string "['a', 'b']" en liste réelle
            tags_list = ast.literal_eval(raw_tags)
            tag_counter.update(tags_list)
        except:
            continue

    print(f"\n📊 Total de tags uniques trouvés : {len(tag_counter)}")
    
    print("\n🏆 TOP 50 des Tags les plus fréquents (Bruit probable) :")
    print("-" * 50)
    for tag, count in tag_counter.most_common(50):
        print(f"{tag:<30} : {count}")

    print("-" * 50)
    
    # On regarde aussi des tags spécifiques pour voir leur fréquence
    targets = ["chicken", "french", "spicy", "chocolate"]
    print("\n🧐 Fréquence de quelques tags 'Goût' :")
    for t in targets:
        print(f"{t:<30} : {tag_counter[t]}")

if __name__ == "__main__":
    audit_tags()