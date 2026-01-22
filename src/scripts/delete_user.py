import sys
import os
import argparse
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.getcwd())
from src.database.connection import engine
from src.database.models import User, Interaction, PredictionLog


def delete_user_data(username):
    with Session(engine) as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User '{username}' not found.")
            return

        print(f"🗑️  Found user '{username}' (ID: {user.id}). Deleting...")

        # Delete interactions
        deleted_interactions = (
            session.query(Interaction).filter(Interaction.user_id == user.id).delete()
        )
        print(f"   - Deleted {deleted_interactions} interactions.")

        # Delete prediction logs (New requirement)
        deleted_logs = (
            session.query(PredictionLog)
            .filter(PredictionLog.user_id == user.id)
            .delete()
        )
        print(f"   - Deleted {deleted_logs} prediction logs.")

        # Delete user
        session.delete(user)
        session.commit()
        print(f"✅ User '{username}' and all associated data deleted successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete a user and all their history (interactions & logs)."
    )
    parser.add_argument("username", help="Username of the user to delete")
    args = parser.parse_args()

    delete_user_data(args.username)
