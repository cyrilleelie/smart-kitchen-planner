import streamlit as st
import requests
from src.ui.config import API_URL

st.set_page_config(page_title="Accueil - Smart Retail", page_icon="🏠", layout="wide")

def main():
    st.title("🥗 Smart Kitchen Hub")
    
    # Hero Section
    st.markdown("""
    ### Bienvenue Chef ! 👩‍🍳👨‍🍳
    Votre assistant culinaire est prêt. Que voulez-vous faire aujourd'hui ?
    """)
    
    # KPI Rapides (Appel API pour voir si le backend répond)
    col1, col2, col3 = st.columns(3)
    
    try:
        # On tente de récupérer quelques stats basiques via l'utilisateur par défaut (1)
        user_id = 1 
        resp = requests.get(f"{API_URL}/user/{user_id}/interactions", timeout=2)
        count_interactions = len(resp.json()) if resp.status_code == 200 else 0
        status_api = "🟢 En ligne"
    except:
        count_interactions = "-"
        status_api = "🔴 Hors ligne"

    col1.metric("État du Backend", status_api)
    col2.metric("Recettes notées", count_interactions)
    col3.metric("Version App", "2.4-Lite")
    
    st.divider()

    # Navigation Visuelle (Cartes)
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.info("📅 **Planifier la semaine**\nGénérez des menus équilibrés en un clic.")
    with c2:
        st.info("🔥 **Explorer**\nDécouvrez de nouvelles recettes et affinez vos goûts.")
    with c3:
        st.info("👤 **Mon Profil**\nGérez vos régimes et préférences alimentaires.")

    st.markdown("---")
    st.caption("👈 Utilisez la barre latérale pour naviguer.")

if __name__ == "__main__":
    main()