import sys
import os

# Ajout du root au path pour les imports
sys.path.append(os.getcwd())

from src.database.connection import engine
from sqlalchemy.orm import Session
from src.data_engineering.processor import DataPipeline

def main():
    with Session(engine) as db:
        pipeline = DataPipeline(db)
        pipeline.run_pipeline()

if __name__ == "__main__":
    main()