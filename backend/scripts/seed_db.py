"""
Seed MongoDB with the downloaded EPL matches.

Run AFTER `python -m ml.download_data`:
    python -m scripts.seed_db

Loads ml/data/epl_matches.csv into the `matches` collection (wiping any
existing documents) and creates the indexes used by the API.
"""

import os

import pandas as pd
from pymongo import MongoClient

from config import Config

DATA_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "data", "epl_matches.csv")


def seed():
    if not os.path.exists(DATA_CSV):
        raise FileNotFoundError(
            f"{DATA_CSV} not found. Run `python -m ml.download_data` first."
        )

    df = pd.read_csv(DATA_CSV, parse_dates=["date"])
    docs = []
    for _, r in df.iterrows():
        docs.append({
            "season": r["season"],
            "date": r["date"].to_pydatetime(),
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "home_goals": int(r["home_goals"]),
            "away_goals": int(r["away_goals"]),
            "result": r["result"],
        })

    client = MongoClient(Config.MONGO_URI)
    db = client.get_default_database()

    db.matches.delete_many({})
    db.matches.insert_many(docs)

    db.matches.create_index([("season", 1), ("home_team", 1)])
    db.matches.create_index([("season", 1), ("away_team", 1)])
    db.matches.create_index([("date", 1)])

    print(f"[DONE] Inserted {len(docs)} matches into '{db.name}.matches'.")
    client.close()


if __name__ == "__main__":
    seed()
