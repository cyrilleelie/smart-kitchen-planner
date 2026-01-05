import streamlit as st
import requests
import pandas as pd
import altair as alt # <--- Import nécessaire

st.set_page_config(page_title="Mon Profil", page_icon="👤", layout="wide")

API_URL = "http://app:8000"

def main():
    st.title("👤 Profil du Chef")
    
    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)
    
    if st.button("Actualiser les données"):
        st.rerun()

    try:
        response = requests.get(f"{API_URL}/user/{user_id}/profile")
        
        if response.status_code == 200:
            data = response.json()
            
            # 1. KPIs
            c1, c2 = st.columns(2)
            c1.metric("Interactions Totales", data.get("total_likes", 0))
            flavors = data.get("favorite_tags", [])
            c2.metric("Goûts identifiés", len(flavors))
            
            st.divider()
            
            # 2. Graphique Altair (Barres Horizontales)
            if flavors:
                st.subheader("📊 ADN Culinaire")
                st.caption("Vos préférences triées par importance.")
                
                df = pd.DataFrame(flavors)
                df = df.rename(columns={"tag": "Saveur", "count": "Intérêt"})
                
                # Construction du graphique Altair explicite
                chart = alt.Chart(df).mark_bar().encode(
                    x=alt.X('Intérêt', title='Score d\'intérêt'),
                    y=alt.Y('Saveur', sort='-x', title='Saveur'), # Tri descendant
                    color=alt.value("#4CAF50"),
                    tooltip=['Saveur', 'Intérêt']
                ).properties(
                    height=max(400, len(df) * 30) # Hauteur dynamique selon le nb de barres
                )
                
                st.altair_chart(chart, use_container_width=True)
                
                with st.expander("Voir les données brutes"):
                    st.dataframe(df, use_container_width=True)
            else:
                st.info("Profil vide. Allez dans 'Exploration' pour noter des plats !")
                
        else:
            st.warning("Impossible de récupérer le profil.")
            
    except Exception as e:
        st.error(f"Erreur de connexion : {e}")

if __name__ == "__main__":
    main()