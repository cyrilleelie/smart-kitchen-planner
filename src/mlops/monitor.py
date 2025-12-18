from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session
from src.database.models import Interaction
import statistics

# Seuil d'alerte : Si la satisfaction moyenne tombe sous 2.5/5, c'est critique.
DRIFT_THRESHOLD = 2.5 

def check_model_health(user_id: int):
    print(f"🔍 MONITORING : Analyse de santé pour User #{user_id}...")
    
    engine = create_engine("sqlite:///smartretail.db")
    with Session(engine) as session:
        # On récupère les 20 dernières interactions (les plus récentes)
        recent_interactions = session.query(Interaction)\
            .filter(Interaction.user_id == user_id)\
            .order_by(desc(Interaction.timestamp))\
            .limit(20)\
            .all()
        
        if not recent_interactions:
            print("   Pas assez de données récentes.")
            return True

        # Calcul de la moyenne mobile
        ratings = [i.rating for i in recent_interactions]
        avg_rating = statistics.mean(ratings)
        
        print(f"   Derniers ratings : {ratings}")
        print(f"   Satisfaction Moyenne (Rolling Window) : {avg_rating:.2f} / 5.0")
        
        if avg_rating < DRIFT_THRESHOLD:
            print("🚨 ALERTE DRIFT DÉTECTÉE ! L'utilisateur rejette les recommandations actuelles.")
            print("👉 Action requise : Réentraînement immédiat du profil.")
            return False # Santé KO
        else:
            print("✅ Le modèle est sain. L'utilisateur est satisfait.")
            return True # Santé OK

if __name__ == "__main__":
    check_model_health(user_id=1)