from sqlalchemy import Column, Integer, String, Float, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    preferences = Column(JSON, default=list)

    # Relation inverse (facultatif mais pratique)
    interactions = relationship("Interaction", back_populates="user")

class Recipe(Base):
    __tablename__ = "recipes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(Text)
    minutes = Column(Integer)
    tags = Column(String)
    calories = Column(Float)
    n_steps = Column(Integer, nullable=True)
    steps = Column(Text)
    nutrition_info = Column(JSON, nullable=True)
    ingredients = Column(Text) # Stocké comme string "['chicken', 'salt']"
    
    # AJOUT CRUCIAL 1 : La colonne pour stocker le vecteur IA
    embedding = Column(JSON, nullable=True)

class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, index=True)
    
    # AJOUT CRUCIAL 2 : Définition propre des clés étrangères
    user_id = Column(Integer, ForeignKey("users.id"))
    recipe_id = Column(Integer, ForeignKey("recipes.id"))
    
    rating = Column(Integer)
    date = Column(DateTime, default=datetime.utcnow)

    # AJOUT CRUCIAL 3 : Les ponts relationnels
    user = relationship("User", back_populates="interactions")
    recipe = relationship("Recipe")  # <-- C'est ça qui manquait pour 'interaction.recipe' !