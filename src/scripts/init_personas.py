import sys
import os
import glob
import argparse

# Add project root to path
sys.path.append(os.getcwd())

from src.scripts.inject_persona import inject_data


def init_all_personas(persona_dir="data/personas"):
    """
    Finds all JSON files in the persona directory and injects them one by one.
    """
    print(f"🚀 Initializing ALL personas from '{persona_dir}'...")

    pattern = os.path.join(persona_dir, "*.json")
    files = glob.glob(pattern)

    if not files:
        print(f"⚠️ No persona files found in {persona_dir}")
        return

    print(f"📂 Found {len(files)} persona files.")

    for i, f_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing {os.path.basename(f_path)}...")
        try:
            inject_data(f_path)
        except Exception as e:
            print(f"❌ Error processing {f_path}: {e}")

    print("\n✅ All personas processed!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Initialize users for ALL persona files in data/personas."
    )
    parser.add_argument(
        "--dir",
        type=str,
        default="data/personas",
        help="Directory containing persona JSON files",
    )

    args = parser.parse_args()
    init_all_personas(args.dir)
