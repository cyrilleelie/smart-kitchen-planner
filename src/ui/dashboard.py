import streamlit as st
import requests

# Imports pour la connexion directe (lecture de l'historique)
from src.database.connection import get_db
from src.recommender.profile_builder import UserProfiler

# 1. Configuration de la page
st.set_page_config(
    page_title="Smart Retail AI",
    page_icon="🥗",
    layout="wide"
)

API_URL = "http://localhost:8000"

def main():
    # --- GESTION ÉTAT (SESSION STATE) ---
    if 'generated_data' not in st.session_state:
        st.session_state['generated_data'] = None
    
    # Initialisation de l'ID utilisateur dans le state s'il n'existe pas
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = 1

    # --- BARRE LATÉRALE ---
    with st.sidebar:
        st.header("🎛️ Paramètres")
        
        # On lie l'input directement au session_state via la clé 'user_id'
        user_id = st.number_input("ID Utilisateur", min_value=1, value=1, step=1, key='user_id')
        
        days = st.slider("Nombre de jours", min_value=1, max_value=5, value=2)
        target_cal = st.number_input("Objectif Calories", min_value=1200, max_value=4000, value=2000, step=100)
        
        st.markdown("---")
        generate_btn = st.button("🚀 Générer Planning", type="primary", use_container_width=True)

    # --- CHARGEMENT DE L'HISTORIQUE (Live) ---
    # On récupère ce que l'utilisateur a déjà noté pour afficher l'état correct
    try:
        db = next(get_db())
        profiler = UserProfiler(db)
        # Retourne un dictionnaire : {recipe_id: note, ...} ex: {10: 5, 24: 1}
        user_history = profiler.get_user_ratings(user_id)
    except Exception as e:
        st.error(f"Erreur de connexion BDD : {e}")
        user_history = {}

    # --- LOGIQUE DE GÉNÉRATION ---
    if generate_btn:
        with st.spinner("🧠 L'IA cuisine les données..."):
            try:
                payload = {"user_id": user_id, "days": days, "target_calories": target_cal}
                response = requests.post(f"{API_URL}/generate-menu", json=payload)
                
                if response.status_code == 200:
                    st.session_state['generated_data'] = response.json()
                    st.toast("Nouveau menu prêt !", icon="✅")
                else:
                    st.error(f"Erreur API : {response.text}")
            except Exception as e:
                st.error(f"Erreur connexion : {e}")

    # --- AFFICHAGE DU PLANNING ---
    if st.session_state['generated_data']:
        data = st.session_state['generated_data']
        menu = data.get("menu", [])
        meta = data.get("meta", {})
        
        st.title("🥗 Smart Kitchen AI")
        total_cals = meta.get('total_calories', 0)
        st.info(f"📊 **Total : {total_cals:.0f} kcal** (Moyenne : {total_cals/days:.0f} kcal/jour)")

        if not menu:
            st.warning("Aucun menu généré.")
        else:
            meals_per_day = 3
            day_cols = st.columns(days)
            
            for day_idx in range(days):
                with day_cols[day_idx]:
                    st.markdown(f"### 📅 Jour {day_idx + 1}")
                    st.markdown("---")
                    
                    start = day_idx * meals_per_day
                    end = start + meals_per_day
                    daily_menu = menu[start:end]
                    
                    for item in daily_menu:
                        with st.container(border=True):
                            st.markdown(f"**{item['name'].title()}**")
                            
                            # Tags
                            tags_raw = item.get('tags', [])
                            tags_clean = tags_raw.replace('[','').replace(']','').replace("'", "").split(',') if isinstance(tags_raw, str) else tags_raw
                            st.caption(f"🏷️ {', '.join(tags_clean[:2])}")
                            
                            # Metrics
                            c1, c2 = st.columns(2)
                            with c1: st.markdown(f"🔥 **{item.get('calories', 0):.0f}**")
                            with c2: st.markdown(f"match **{int(item.get('score', 0)*100)}%**")
                            
                            st.divider()
                            
                            # --- SYSTÈME DE NOTATION ÉTOILES ---
                            rec_id = item['id']
                            existing_rating = user_history.get(rec_id)

                            if existing_rating:
                                # Cas 1 : Déjà noté -> Affichage statique
                                st.markdown(f"Votre avis : {'⭐' * existing_rating}")
                            else:
                                # Cas 2 : Pas encore noté -> Widget interactif
                                # Fonction de callback interne
                                def submit_rating(rid=rec_id):
                                    # On récupère la valeur du widget (0-4)
                                    val = st.session_state.get(f"star_{rid}")
                                    if val is not None:
                                        final_score = val + 1 # Conversion vers 1-5
                                        try:
                                            requests.post(f"{API_URL}/feedback", json={
                                                "user_id": user_id,
                                                "recipe_id": rid,
                                                "rating": final_score
                                            })
                                            st.toast(f"Note enregistrée : {final_score}/5 ⭐", icon="😍")
                                            # Mise à jour locale forcée pour l'UI immédiate (hack visuel optionnel)
                                            # user_history[rid] = final_score 
                                        except Exception as e:
                                            st.error(f"Erreur sauvegarde : {e}")

                                st.write("Notez ce plat :")
                                st.feedback(
                                    "stars", 
                                    key=f"star_{rec_id}", 
                                    on_change=submit_rating,
                                    kwargs={"rid": rec_id}
                                )

    elif not generate_btn:
        st.title("🥗 Smart Kitchen AI")
        st.info("👈 Lancez une génération pour commencer.")

if __name__ == "__main__":
    main()