"""
MongoDB connection module.

Exposes a single shared PyMongo instance. Collections are accessed via
`mongo.db.<collection>` after `init_db(app)` has run. Indexes used by the API
are created on startup (idempotent).
"""

from flask_pymongo import PyMongo

mongo = PyMongo()


def init_db(app):
    """Attach PyMongo to the Flask app and ensure indexes exist."""
    mongo.init_app(app)
    try:
        # Trigger a connection and report the server version.
        info = mongo.cx.server_info()
        print(f"[DB] MongoDB connected (v{info.get('version', '?')}).")
        _ensure_indexes()
    except Exception as exc:  # pragma: no cover - startup diagnostics
        print(f"[DB] WARNING: could not connect to MongoDB: {exc}")


def _ensure_indexes():
    """Create indexes used by the read-heavy endpoints (idempotent)."""
    matches = mongo.db.matches
    matches.create_index([("season", 1), ("home_team", 1)])
    matches.create_index([("season", 1), ("away_team", 1)])
    matches.create_index([("date", 1)])

    mongo.db.users.create_index("email", unique=True)
    mongo.db.user_predictions.create_index([("user_id", 1), ("timestamp", -1)])
