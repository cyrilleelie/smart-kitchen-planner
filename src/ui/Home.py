import streamlit as st
import requests

st.set_page_config(page_title="Générateur de Menus", page_icon="🍳", layout="wide")

API_URL = "http://app:8000"

def main():
    st.title("🍳 Générateur de Menus")
    st.markdown("---")

    with st.sidebar:
        st.header("Paramètres")
        user_id = st.number_input("ID Chef", value=1, step=1)
        days = st.slider("Jours", 1, 5, 3)
        target_cal = st.number_input("Calories/jour", 1200, 4000, 2000, 100)
        
        st.subheader("🥦 Vide-Frigo")
        fridge_input = st.text_input("Ingrédients à passer", placeholder="Ex: chicken, tomato")
        fridge_list = [item.strip() for item in fridge_input.split(',')] if fridge_input else []
        
        generate_btn = st.button("🚀 Lancer la Génération", type="primary", use_container_width=True)

    # --- CHARGEMENT HISTORIQUE ---
    # On récupère ce que l'user a déjà noté pour ne pas lui redemander
    user_history = {}
    try:
        hist_resp = requests.get(f"{API_URL}/user/{user_id}/interactions")
        if hist_resp.status_code == 200:
            # Conversion des clés en int (le JSON renvoie des strings pour les clés)
            raw_hist = hist_resp.json()
            user_history = {int(k): v for k, v in raw_hist.items()}
    except:
        pass # Pas grave si l'API échoue, on fera sans

    # --- LOGIQUE DE GENERATION ---
    if generate_btn:
        with st.spinner("🧠 L'IA cuisine les données..."):
            try:
                payload = {
                    "user_id": user_id, 
                    "days": days, 
                    "target_calories": target_cal,
                    "fridge_items": fridge_list
                }
                response = requests.post(f"{API_URL}/generate-menu", json=payload)
                if response.status_code == 200:
                    st.session_state['generated_data'] = response.json()
                else:
                    st.error(f"Erreur API : {response.text}")
            except Exception as e:
                st.error(f"Erreur connexion : {e}")

    # --- AFFICHAGE ---
    if 'generated_data' in st.session_state and st.session_state['generated_data']:
        data = st.session_state['generated_data']
        menu = data.get("menu", [])
        
        if not menu:
            st.warning("Aucun menu trouvé.")
            return

        total_recipes = len(menu)
        meals_per_day = max(1, total_recipes // days)
        cols = st.columns(days)
        
        for day_idx in range(days):
            with cols[day_idx]:
                # 1. Découpage du menu pour ce jour précis
                start = day_idx * meals_per_day
                end = start + meals_per_day
                daily_menu = menu[start:end]
                
                # 2. CALCUL : Somme des calories du jour
                day_cals = sum(item.get('calories', 0) for item in daily_menu)
                
                # 3. Affichage du Header avec le Total Journalier
                # On utilise une couleur (vert/rouge) visuelle si on est proche de la cible ou non
                delta = day_cals - target_cal
                color = "green" if abs(delta) < 200 else "orange"
                
                st.markdown(f"### 📅 Jour {day_idx + 1}")
                st.markdown(f"**Total : :{color}[{int(day_cals)} kcal]**")
                st.markdown("---")
                
                for i, item in enumerate(daily_menu):
                    # Labels
                    labels = ["☕ Matin", "☀️ Midi", "🌙 Soir"] if len(daily_menu) == 3 else ["☀️ Midi", "🌙 Soir"]
                    moment = labels[i] if i < len(labels) else f"Repas {i+1}"

                    st.caption(moment)
                    with st.container(border=True):
                        st.markdown(f"**{item['name']}**")
                        
                        tags_clean = item.get('tags', '').replace('[','').replace(']','').replace("'", "").split(',')
                        st.caption(f"🏷️ {', '.join(tags_clean[:2])}")
                        
                        # --- MODIFICATION : Affichage clair des calories par repas ---
                        st.markdown(f"🔥 **{int(item.get('calories', 0))} kcal**")
                        
                        with st.expander("🛒 Ingrédients"):
                            ing_raw = item.get('ingredients', '[]')
                            if isinstance(ing_raw, str):
                                ing_clean = ing_raw.replace('[','').replace(']','').replace("'", "").split(',')
                                for ing in ing_clean: st.markdown(f"- {ing.strip()}")

                        if item.get('score', 0) > 1.0:
                            st.success("🎯 Vide-Frigo")
                        
                        st.divider()
                        
                        # --- VERIFICATION HISTORIQUE ---
                        existing_rating = user_history.get(item['id'])
                        
                        if existing_rating:
                            st.write(f"✅ Noté : **{existing_rating}/5** ⭐")
                        else:
                            def submit_rating(rid=item['id'], key_id=f"{day_idx}_{i}"):
                                stars_idx = st.session_state[f"star_{key_id}"]
                                if stars_idx is not None:
                                    rating_val = stars_idx + 1
                                    try:
                                        requests.post(f"{API_URL}/feedback", json={
                                            "user_id": user_id, "recipe_id": rid, "rating": rating_val
                                        })
                                        st.toast(f"Noté {rating_val}/5 ⭐")
                                    except:
                                        st.error("Erreur save")

                            st.write("Votre avis ?")
                            st.feedback("stars", key=f"star_{day_idx}_{i}", on_change=submit_rating)

if __name__ == "__main__":
    main()