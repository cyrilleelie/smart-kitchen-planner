import sys
import os
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.getcwd())
from src.database.connection import engine
from src.database.models import User, Interaction


def delete_user(username):
    with Session(engine) as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"User '{username}' not found.")
            return

        print(f"Found user '{username}' (ID: {user.id}). Deleting...")

        # Delete interactions first
        deleted_interactions = (
            session.query(Interaction).filter(Interaction.user_id == user.id).delete()
        )
        print(f"   - Deleted {deleted_interactions} interactions.")

        # Delete user
        session.delete(user)
        session.commit()
        print(f"   - User '{username}' deleted successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/scripts/reset_persona.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    delete_user(username)
