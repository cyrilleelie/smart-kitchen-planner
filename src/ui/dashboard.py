import streamlit as st
import requests
import pandas as pd

# --- CONFIGURATION ---
API_URL = "http://127.0.0.1:8000"
st.set_page_config(page_title="SmartRetail Planner", layout="wide", page_icon="🍽️")

# --- CSS CUSTOM (Pour un look un peu plus 'Luxury') ---
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px; text-align: center;}
    .recipe-card {border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; margin-bottom: 10px; background: white;}
    .day-header {color: #FF4B4B; font-weight: bold; font-size: 1.1em;}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR : CONTRÔLES ---
st.sidebar.title("🎛️ Paramètres")
st.sidebar.markdown("Configurez vos contraintes pour générer le planning idéal.")

# Simulation du login (Pour l'instant ID 1)
user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)

st.sidebar.divider()

# Contraintes
days = st.sidebar.slider("Durée (Jours)", 1, 7, 7)
time_max = st.sidebar.slider("Temps max cuisine (min)", 10, 120, 45, step=5)
cal_range = st.sidebar.slider("Cible Calories / Repas", 300, 1500, (400, 1000), step=50)

generate_btn = st.sidebar.button("🚀 Générer le Menu", type="primary")

# --- MAIN : AFFICHAGE ---
st.title("🍽️ SmartRetail Menu Planner")
st.markdown(f"Bienvenue. Conception de menu optimisée pour l'utilisateur **#{user_id}**.")

if generate_btn:
    with st.spinner("L'IA analyse vos goûts et optimise le planning..."):
        try:
            # Appel à VOTRE API
            payload = {
                "user_id": user_id,
                "days": days,
                "max_prep_time": time_max,
                "target_calories_min": cal_range[0],
                "target_calories_max": cal_range[1]
            }
            response = requests.post(f"{API_URL}/generate-menu", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # 1. Affichage des KPIs
                stats = data['stats']
                col1, col2, col3 = st.columns(3)
                col1.metric("Satisfaction IA", f"{stats['avg_satisfaction']}/100", delta_color="normal")
                col2.metric("Moyenne Calories", f"{stats['avg_calories']} kcal")
                col3.metric("Recettes Uniques", f"{len(data['plan'])}")
                
                st.divider()
                
                # 2. Affichage du Planning (Grille)
                # On divise l'écran en 3 ou 4 colonnes selon la largeur
                cols = st.columns(4)
                
                for idx, meal in enumerate(data['plan']):
                    # Modulo pour revenir à la ligne
                    with cols[idx % 4]:
                        st.markdown(f"""
                        <div class="recipe-card">
                            <div class="day-header">JOUR {meal['day']}</div>
                            <h3>{meal['recipe_name'].title()}</h3>
                            <p>⏱️ {meal['time']} min | 🔥 {meal['calories']} kcal</p>
                            <progress value="{meal['match_score']}" max="100"></progress>
                            <small>Match IA: {meal['match_score']}%</small>
                        </div>
                        """, unsafe_allow_html=True)
                        
            else:
                st.error(f"Erreur du solveur : {response.json().get('detail')}")
                
        except requests.exceptions.ConnectionError:
            st.error("🚨 Impossible de contacter l'API. Vérifiez que 'src.api.app' tourne bien dans un autre terminal !")

# --- FOOTER ---
st.markdown("---")
st.caption("Architecture: Database SQL • Sentence-BERT NLP • OR-Tools Solver • FastAPI • Streamlit")