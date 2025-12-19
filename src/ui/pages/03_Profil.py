import streamlit as st
import requests
import pandas as pd
import sys

# Fix Docker Path
sys.path.append("/app")

st.set_page_config(page_title="Mon Profil Gustatif", page_icon="🧠", layout="wide")
API_URL = "http://localhost:8000"

def main():
    st.title("🧠 Mon ADN Culinaire")
    st.markdown("Analyse de vos préférences basée sur vos interactions.")
    
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = 1
    user_id = st.session_state['user_id']

    st.divider()

    try:
        response = requests.get(f"{API_URL}/user/{user_id}/profile")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("status") == "empty":
                st.info("Données insuffisantes. Allez noter quelques recettes !")
                if st.button("Démarrer l'exploration ➡️"):
                    st.switch_page("pages/02_Exploration.py")
            
            else:
                # --- HEADER ---
                col1, col2, col3 = st.columns(3)
                col1.metric("Plats Analysés", data['total_likes'])
                
                # Récupération des top tags
                top_tags_list = data.get('favorite_tags', [])
                
                if top_tags_list:
                    # Le N°1
                    top_1 = top_tags_list[0]['tag'].replace('-', ' ').title()
                    col2.metric("Dominante N°1", top_1)
                    
                    # Le N°2 (s'il existe)
                    if len(top_tags_list) > 1:
                        top_2 = top_tags_list[1]['tag'].replace('-', ' ').title()
                        col3.metric("Dominante N°2", top_2)

                st.markdown("---")

                # --- GRAPHIQUE AMÉLIORÉ ---
                st.subheader("📊 Vos marqueurs de goût")
                
                if top_tags_list:
                    # Transformation en DataFrame propre
                    df = pd.DataFrame(top_tags_list)
                    # Nettoyage des noms pour l'affichage (ex: "main-dish" -> "Main Dish")
                    df['tag'] = df['tag'].str.replace('-', ' ').str.title()
                    df = df.set_index('tag')
                    # On trie pour avoir le plus grand en haut
                    df = df.sort_values(by='count', ascending=True)

                    # Affichage en Barres Horizontales (plus lisible pour du texte)
                    st.bar_chart(df, color="#FF4B4B", horizontal=True)
                
                # --- ANALYSE TEXTUELLE NEUTRE ---
                # st.success(f"🔎 **Analyse :** Vos choix montrent une préférence marquée pour **{top_1}**.")

        else:
            st.error(f"Erreur API : {response.text}")

    except Exception as e:
        st.error(f"Erreur technique : {e}")

if __name__ == "__main__":
    main()