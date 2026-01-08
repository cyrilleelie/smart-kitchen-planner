import streamlit as st
import requests
from src.ui.config import API_URL

st.set_page_config(page_title="Planner", page_icon="📅", layout="wide")

def main():
    st.title("📅 Générateur de Menu")
    st.caption("Laissez l'IA organiser votre semaine culinaire.")

    # --- BARRE LATÉRALE (Specifique au Planner) ---
    with st.sidebar:
        st.header("Paramètres")
        user_id = st.number_input("ID Utilisateur", min_value=1, value=1)
        days = st.slider("Durée (Jours)", 2, 14, 7)
        calories = st.slider("Cible Kcal/repas", 300, 1200, 600, step=50)
        meals_count = st.radio("Repas/jour", [1, 2, 3], index=1, horizontal=True)
        prep_time = st.slider("Temps max cuisine (min)", 15, 120, 45, step=15)
        generate_btn = st.button("✨ Générer", type="primary")

    # --- LOGIQUE ---
    if generate_btn:
        with st.spinner("🤖 Calcul de l'itinéraire gourmand..."):
            try:
                payload = {
                    "user_id": user_id,
                    "days": days,
                    "meals_per_day": meals_count,
                    "max_prep_time": prep_time,
                    "target_calories_min": calories - 50, 
                    "target_calories_max": calories + 150 
                }
                
                response = requests.post(f"{API_URL}/generate-menu", json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    plan = data.get("plan", [])
                    stats = data.get("stats", {})
                    
                    if not plan:
                        st.warning("⚠️ Aucun menu trouvé. Élargissez vos critères.")
                    else:
                        st.success("✅ Menu prêt !")
                        
                        # KPIs
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Moyenne Kcal", f"{int(stats.get('average_calories', 0))}")
                        k2.metric("Score Match", f"{int(stats.get('average_match_score', 0)*100)}%")
                        k3.metric("Recettes", len(plan))
                        
                        st.divider()
                        
                        # Affichage
                        schedule = {}
                        for item in plan:
                            schedule.setdefault(item['day'], []).append(item)

                        cols = st.columns(len(schedule))
                        labels = ["☀️ Midi", "🌙 Soir", "🍏 Snack"] if meals_count > 1 else ["🍽️ Repas"]

                        for idx, day in enumerate(sorted(schedule.keys())):
                            with cols[idx]:
                                st.markdown(f"<div style='text-align:center; background:#f0f2f6; padding:5px; border-radius:5px;'><b>J{day}</b></div>", unsafe_allow_html=True)
                                for m_idx, meal in enumerate(schedule[day]):
                                    label = labels[min(m_idx, len(labels)-1)]
                                    st.caption(label)
                                    st.markdown(f"**{meal['recipe_name']}**")
                                    st.write(f"🔥 {int(meal['calories'])} | ⏱️ {meal['time']}m")
                                    
                                    if "Découverte" in meal.get("tags", []):
                                        st.markdown("🎲 <span style='color:#6f42c1'><b>Découverte</b></span>", unsafe_allow_html=True)
                                    else:
                                        st.markdown(f"⭐ {meal['match_score']:.2f}")
                                    st.divider()
                else:
                    st.error(f"Erreur API: {response.status_code}")
            
            except Exception as e:
                st.error(f"Erreur technique: {e}")

if __name__ == "__main__":
    main()