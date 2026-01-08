import random
import json
import numpy as np
from sqlalchemy.orm import Session
from src.database.models import Recipe

class MenuSolver:
    def __init__(self, db: Session, user_vector: list, days: int, target_calories: int, meals_per_day: int):
        self.db = db
        self.user_vector = np.array(user_vector) if user_vector is not None and len(user_vector) > 0 else None
        self.days = days
        self.target_calories = target_calories
        self.meals_per_day = meals_per_day
        self.cal_max = target_calories * 1.5

    def solve(self):
        print(f"\n🔧 [SOLVER] Stratégie : Quantiles Dynamiques (Calibration Auto)")
        
        # 1. CHARGEMENT
        candidates = self.db.query(Recipe.id, Recipe.embedding, Recipe.calories).filter(
            Recipe.embedding != None,
            Recipe.minutes <= 120
        ).all()

        scored_items = []
        scores_list = []
        
        for r_id, r_emb, r_cal in candidates:
            if r_cal is None: continue
            score = self._calculate_similarity(r_emb)
            scored_items.append({"id": r_id, "score": score, "calories": r_cal})
            scores_list.append(score)

        if not scores_list: return []

        # 2. CALIBRATION STATISTIQUE (Le coeur de la correction)
        # On calcule les seuils basés sur la RÉALITÉ des données actuelles
        
        # Seuil Performance : Le Top 20% (80e percentile)
        thresh_perf = np.percentile(scores_list, 80)
        
        # Zone Découverte : Entre le bas du classement (10%) et un peu en dessous de la moyenne (40%)
        # Cela garantit qu'on est loin des goûts (Perfs) mais pas dans les déchets (0%)
        thresh_disco_high = np.percentile(scores_list, 40)
        thresh_disco_low = np.percentile(scores_list, 5) 

        print(f"📊 Calibration : PERF > {thresh_perf:.4f} | DISCO entre {thresh_disco_low:.4f} et {thresh_disco_high:.4f}")

        # 3. BUCKETING
        bucket_perf = []
        bucket_disco = []
        
        for item in scored_items:
            s = item["score"]
            if s >= thresh_perf:
                item["type"] = "PERF"
                bucket_perf.append(item)
            elif thresh_disco_low <= s <= thresh_disco_high:
                item["type"] = "DISCO"
                bucket_disco.append(item)
            else:
                item["type"] = "NEUTRAL" # Zone grise (40% - 80%) qu'on ignore pour trancher
        
        print(f"📦 Buckets : {len(bucket_perf)} Perf | {len(bucket_disco)} Disco")

        # 4. SÉLECTION
        total_slots = self.days * self.meals_per_day
        nb_discovery = max(1, int(total_slots * 0.20))
        nb_performance = total_slots - nb_discovery

        final_selection = []
        used_ids = set()

        # A. Remplissage PERFORMANCE (Top Scores mélangés)
        bucket_perf.sort(key=lambda x: x["score"], reverse=True) # On garde les meilleurs des meilleurs
        top_perf = bucket_perf[:150] # Vivier large
        random.shuffle(top_perf)
        
        for item in top_perf:
            if len(final_selection) >= nb_performance: break
            final_selection.append(item)
            used_ids.add(item["id"])

        # B. Remplissage DÉCOUVERTE (Shuffle total)
        random.shuffle(bucket_disco)
        for item in bucket_disco:
            if len(final_selection) >= total_slots: break
            final_selection.append(item)
            used_ids.add(item["id"])

        # C. Fallback (Si buckets vides, très rare avec les percentiles)
        if len(final_selection) < total_slots:
            print("⚠️ Fallback activé (Buckets insuffisants)")
            remaining_pool = [x for x in scored_items if x["id"] not in used_ids]
            remaining_pool.sort(key=lambda x: x["score"], reverse=True) # On prend les meilleurs restants
            for item in remaining_pool:
                if len(final_selection) >= total_slots: break
                item["type"] = "RESCUE"
                final_selection.append(item)

        # 5. FINALISATION
        random.shuffle(final_selection)
        menu = []
        
        print("\n🕵️ [AUDIT MENU]")
        print(f"{'Jour':<5} | {'ID':<6} | {'Score':<8} | {'Type':<8}")
        print("-" * 35)
        
        for i, item in enumerate(final_selection):
            day_num = (i // self.meals_per_day) + 1
            
            # On renvoie un objet complet pour que l'API sache si c'est de la découverte
            menu.append({
                "day": day_num,
                "recipe_id": item["id"],
                "algo_type": item.get("type", "PERF"), # "PERF", "DISCO", "RESCUE"
                "score": item["score"]
            })

            print(f"J{day_num:<4} | {item['id']:<6} | {item['score']:.4f}   | {item['type']:<8}")
        print("-" * 35 + "\n")
            
        return menu

    def calculate_score(self, recipe):
        return self._calculate_similarity(recipe.embedding)

    def _calculate_similarity(self, embedding_data):
        if self.user_vector is None or embedding_data is None: return 0.5
        try:
            if isinstance(embedding_data, str):
                vec = np.array(json.loads(embedding_data))
            else:
                vec = np.array(embedding_data)
            norm_u = np.linalg.norm(self.user_vector)
            norm_r = np.linalg.norm(vec)
            if norm_u == 0 or norm_r == 0: return 0.5
            dot = np.dot(self.user_vector, vec)
            sim = dot / (norm_u * norm_r)
            return (sim + 1) / 2
        except:
            return 0.5