from typing import List, Optional
from datetime import datetime
from sqlalchemy import String, Integer, Float, ForeignKey, JSON, DateTime, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Base de déclaration pour SQLAlchemy 2.0+
class Base(DeclarativeBase):
    pass

class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Métadonnées brutes (Food.com)
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Données structurées pour le Solveur (Contraintes)
    minutes: Mapped[int] = mapped_column(Integer)  # Pour la contrainte "Temps de prépa"
    n_steps: Mapped[int] = mapped_column(Integer)
    calories: Mapped[float] = mapped_column(Float, nullable=True) # Pour la contrainte "Calories"
    
    # Nutrition détaillée (stockée en JSON pour flexibilité : {fat: 10, sugar: 5...})
    nutrition_info: Mapped[dict] = mapped_column(JSON, default={})
    
    # Contenu pour l'affichage et le NLP
    steps: Mapped[list] = mapped_column(JSON)       # Liste des étapes
    ingredients: Mapped[list] = mapped_column(JSON) # Liste des ingrédients (ex: ['tomate', 'sel'])
    tags: Mapped[list] = mapped_column(JSON)        # Catégories (ex: ['vegan', '15-minutes'])
    
    # Vecteur d'Embedding (Prévision pour la Phase 2 - Hybrid Filtering)
    # On stocke ici le vecteur généré par Sentence-BERT (liste de floats)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Relations
    interactions: Mapped[List["Interaction"]] = relationship(back_populates="recipe")

    def __repr__(self):
        return f"<Recipe(id={self.id}, name='{self.name}')>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    
    # Profilage pour le Simulateur & Recommandation
    # Ex: {"italian": 0.8, "spicy": 0.2}
    preferences: Mapped[dict] = mapped_column(JSON, default={}) 
    
    # Contraintes strictes pour le Solveur
    # Ex: ["peanut-free", "vegetarian"]
    dietary_restrictions: Mapped[list] = mapped_column(JSON, default=[])
    
    # Objectifs Nutritionnels (Optionnel pour l'optimisation)
    # Ex: {"target_calories": 2000}
    goals: Mapped[dict] = mapped_column(JSON, default={})

    interactions: Mapped[List["Interaction"]] = relationship(back_populates="user")


class Interaction(Base):
    """
    Table centrale pour l'entraînement du modèle IA.
    Enregistre QUAND un utilisateur a aimé QUOI, et dans QUEL CONTEXTE.
    """
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    
    # Le signal (Target variable)
    rating: Mapped[int] = mapped_column(Integer) # 1 à 5
    
    # Le Contexte Temporel & Environnemental [cite: 14, 39]
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Stockage du contexte au moment de l'action (ex: {"weather": "rainy", "season": "winter"})
    # Crucial pour apprendre que "Pluie" -> "Raclette"
    context_snapshot: Mapped[dict] = mapped_column(JSON, default={})

    # Relations
    user: Mapped["User"] = relationship(back_populates="interactions")
    recipe: Mapped["Recipe"] = relationship(back_populates="interactions")

# Note : Pas besoin de table "MenuPlan" pour l'instant, 
# car c'est un output temporaire du solveur, mais on pourra l'ajouter si on veut sauvegarder les historiques de menus.