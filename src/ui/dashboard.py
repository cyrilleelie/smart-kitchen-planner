import streamlit as st
import requests

# 1. Configuration de la page
st.set_page_config(
    page_title="Smart Retail AI",
    page_icon="🥗",
    layout="wide"
)

API_URL = "http://localhost:8000"

def main():
    # --- GESTION DE LA MÉMOIRE (SESSION STATE) ---
    # C'est ici qu'on stocke le menu pour qu'il ne disparaisse pas au clic
    if 'generated_data' not in st.session_state:
        st.session_state['generated_data'] = None

    # --- BARRE LATÉRALE ---
    with st.sidebar:
        st.header("🎛️ Paramètres")
        user_id = st.number_input("ID Utilisateur", min_value=1, value=1, step=1)
        days = st.slider("Nombre de jours", min_value=1, max_value=5, value=2)
        target_cal = st.number_input("Objectif Calories", min_value=1200, max_value=4000, value=2000, step=100)
        
        st.markdown("---")
        # Le bouton sert uniquement à LANCER le calcul
        generate_btn = st.button("🚀 Générer Planning", type="primary", use_container_width=True)

    # --- LOGIQUE DE GÉNÉRATION ---
    if generate_btn:
        with st.spinner("🧠 L'IA travaille..."):
            try:
                payload = {"user_id": user_id, "days": days, "target_calories": target_cal}
                response = requests.post(f"{API_URL}/generate-menu", json=payload)
                
                if response.status_code == 200:
                    # ### CORRECTION IMPORTANTE ###
                    # On ne traite pas les données tout de suite, on les SAUVEGARDE en mémoire
                    st.session_state['generated_data'] = response.json()
                    st.toast("Nouveau menu généré !", icon="✅")
                else:
                    st.error(f"Erreur API : {response.text}")
            except Exception as e:
                st.error(f"Erreur connexion : {e}")

    # --- LOGIQUE D'AFFICHAGE (DÉCORRELÉE) ---
    # Ce bloc s'exécute à chaque rafraichissement SI des données existent en mémoire
    if st.session_state['generated_data']:
        data = st.session_state['generated_data']
        menu = data.get("menu", [])
        meta = data.get("meta", {})
        
        # Titre et Infos
        st.title("🥗 Smart Kitchen AI")
        total_cals = meta.get('total_calories', 0)
        st.info(f"📊 **Total : {total_cals:.0f} kcal** (Moyenne : {total_cals/days:.0f} kcal/jour)")

        if not menu:
            st.warning("Menu vide.")
        else:
            # Layout Colonnes
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
                            with c2: st.markdown(f"❤️ **{int(item.get('score', 0)*100)}%**")
                            
                            st.markdown("---")
                            
                            # ### BOUTON FEEDBACK ###
                            # Maintenant que l'affichage est stable, ce bouton va fonctionner
                            btn_key = f"like_{day_idx}_{item['id']}"
                            
                            if st.button("J'aime ❤️", key=btn_key, use_container_width=True):
                                # Appel API Feedback
                                try:
                                    requests.post(f"{API_URL}/feedback", json={
                                        "user_id": user_id,
                                        "recipe_id": item['id'],
                                        "rating": 5
                                    })
                                    st.toast(f"Recette '{item['name']}' likée !", icon="😋")
                                except Exception as e:
                                    st.error("Erreur API Feedback")
    
    # Message d'accueil si rien n'est généré
    elif not generate_btn:
        st.title("🥗 Smart Kitchen AI")
        st.info("👈 Configurez vos paramètres à gauche et cliquez sur Générer pour commencer.")

if __name__ == "__main__":
    main()