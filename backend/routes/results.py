"""
Match results routes backed by MongoDB.

Reads from the `matches` collection (seeded with `python -m scripts.seed_db`).
Supports filtering by season / team and pagination.
"""

from flask import Blueprint, jsonify, request

from database import mongo

results_bp = Blueprint("results", __name__, url_prefix="/api/results")


def _serialize(doc):
    return {
        "id": str(doc["_id"]),
        "season": doc.get("season"),
        "date": doc["date"].strftime("%Y-%m-%d") if doc.get("date") else None,
        "home_team": doc.get("home_team"),
        "away_team": doc.get("away_team"),
        "home_goals": doc.get("home_goals"),
        "away_goals": doc.get("away_goals"),
        "result": doc.get("result"),
    }


@results_bp.get("/")
def get_results():
    season = request.args.get("season")
    team = request.args.get("team", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    limit = min(int(request.args.get("limit", 20)), 100)

    query = {}
    if season:
        query["season"] = season
    if team:
        regex = {"$regex": team, "$options": "i"}
        query["$or"] = [{"home_team": regex}, {"away_team": regex}]

    total = mongo.db.matches.count_documents(query)
    cursor = (
        mongo.db.matches.find(query)
        .sort("date", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    return jsonify({
        "total": total,
        "page": page,
        "results": [_serialize(d) for d in cursor],
    }), 200


@results_bp.get("/seasons")
def get_seasons():
    seasons = mongo.db.matches.distinct("season")
    return jsonify(sorted(seasons, reverse=True)), 200
