import streamlit as st
import requests

# Configuration de la page
st.set_page_config(
    page_title="Smart Retail - Home",
    page_icon="🏠",
    layout="wide"
)

# URL de l'API (Interne Docker)
API_URL = "http://localhost:8000"

# --- EN-TÊTE ---
st.title("🥗 Smart Kitchen Planner")
st.markdown("""
Bienvenue dans votre assistant culinaire intelligent.
Générez un planning de repas optimisé pour **vos goûts** et **votre santé**.
""")

# --- 1. BARRE LATÉRALE (Contrôles) ---
with st.sidebar:
    st.header("⚙️ Paramètres du Menu")
    
    # Simulation de l'utilisateur connecté
    user_id = st.number_input("ID Utilisateur", min_value=1, value=1, help="Simule l'utilisateur connecté")
    
    st.divider()
    
    # Critères
    days = st.slider("Durée du planning (Jours)", 2, 14, 7)
    calories = st.slider("Cible Calorique (par repas)", 300, 1200, 600, step=50)
    meals_count = st.radio("Repas par jour", [1, 2, 3], index=1, horizontal=True)
    prep_time = st.slider("Temps max en cuisine (min)", 15, 120, 45, step=15)
    generate_btn = st.button("✨ Générer le Planning", type="primary")

# --- 2. LOGIQUE PRINCIPALE ---
if generate_btn:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.info(f"🎯 Objectif : {calories} kcal/repas")
    with col2:
        st.info(f"📅 Durée : {days} jours")

    with st.spinner("🤖 L'IA analyse vos préférences et calcule les apports nutritionnels..."):
        try:
            # Construction du Payload (Conforme au schema MenuRequest)
            payload = {
                "user_id": user_id,
                "days": days,
                "meals_per_day": meals_count,
                "max_prep_time": prep_time,
                "target_calories_min": calories - 50, 
                "target_calories_max": calories + 150 
            }
            
            # Appel API
            response = requests.post(f"{API_URL}/generate-menu", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # Récupération des données
                plan = data.get("plan", [])
                stats = data.get("stats", {})
                
                if not plan:
                    st.warning("⚠️ Aucun menu trouvé correspondant exactement à ces critères. Essayez d'élargir la fourchette calorique.")
                else:
                    st.success("✅ Menu généré avec succès !")
                    
                    # --- 3. AFFICHAGE DES STATISTIQUES ---
                    st.markdown("### 📊 Analyse Nutritionnelle")
                    kpi1, kpi2, kpi3 = st.columns(3)
                    
                    avg_cal = stats.get('average_calories', 0)
                    avg_score = stats.get('average_match_score', 0) * 100
                    
                    kpi1.metric("Calories Moyennes", f"{int(avg_cal)} kcal", delta=f"{int(avg_cal - calories)}")
                    kpi2.metric("Score de Compatibilité", f"{int(avg_score)}%", help="Basé sur vos historiques de likes")
                    kpi3.metric("Recettes Uniques", len(plan))
                    
                    st.divider()
                    
                    # --- 4. AFFICHAGE DYNAMIQUE ---
                    st.markdown("### 🗓️ Votre Semaine")

                    # Groupement par jour
                    schedule = {}
                    for item in plan:
                        d = item['day']
                        if d not in schedule: schedule[d] = []
                        schedule[d].append(item)

                    cols = st.columns(len(schedule))
                    
                    # Labels dynamiques
                    if meals_count == 1:
                        labels = ["🍽️ Repas Unique"]
                    elif meals_count == 2:
                        labels = ["☀️ Midi", "🌙 Soir"]
                    else:
                        labels = ["☀️ Midi", "🌙 Soir", "🍏 Snack/Autre"]

                    for idx, day_num in enumerate(sorted(schedule.keys())):
                        with cols[idx]:
                            # En-tête du jour stylisé
                            st.markdown(f"<div style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 5px; border-radius: 5px; margin-bottom: 10px;'>JOUR {day_num}</div>", unsafe_allow_html=True)
                            
                            day_meals = schedule[day_num]
                            
                            for meal_idx, meal in enumerate(day_meals):
                                label = labels[meal_idx] if meal_idx < len(labels) else f"Repas {meal_idx+1}"
                                
                                with st.container():
                                    st.caption(label)
                                    st.markdown(f"**{meal['recipe_name']}**")
                                    st.write(f"🔥 `{int(meal['calories'])} kcal` | ⏱️ `{meal['time']} min`")
                                    
                                    # --- MODIFICATION ICI : Gestion Découverte vs Étoiles ---
                                    tags = meal.get("tags", [])
                                    
                                    if "Découverte" in tags:
                                        # Badge spécial pour la découverte (Violet)
                                        st.markdown("""
                                            <span style='background-color: #6f42c1; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; font-weight: bold;'>
                                                🎲 Découverte
                                            </span>
                                        """, unsafe_allow_html=True)
                                    else:
                                        # Affichage classique des étoiles
                                        score = meal.get('match_score', 0)
                                        stars_count = int(round(score * 5))
                                        stars = "★" * stars_count
                                        # (Optionnel) Ajout d'étoiles vides pour un meilleur rendu visuel
                                        empty = "☆" * (5 - stars_count)
                                        st.markdown(f"<small style='color:orange'>{stars}{empty}</small>", unsafe_allow_html=True)
                                    # -------------------------------------------------------
                                    
                                    st.divider()

            else:
                st.error(f"❌ Erreur API : {response.status_code}")
                with st.expander("Détails techniques"):
                    st.json(response.json())

        except requests.exceptions.ConnectionError:
            st.error("🚨 Impossible de se connecter au Backend. Vérifiez que le conteneur Docker 'app' tourne bien.")
        except Exception as e:
            st.error(f"Une erreur inattendue est survenue : {e}")

else:
    # État initial
    st.info("👈 Ajustez les paramètres dans la barre latérale et cliquez sur 'Générer' pour commencer.")
    
    st.markdown("---")
    st.markdown("#### Pourquoi utiliser ce planner ?")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("* **Personnalisé :** Apprend de vos goûts.")
        st.markdown("* **Sain :** Respecte vos objectifs caloriques.")
    with c2:
        st.markdown("* **Rapide :** Filtre par temps de préparation.")
        st.markdown("* **Exploration :** Vous propose de nouvelles saveurs.")