"""
Standings route — computes the EPL table dynamically from the `matches`
collection for a given season.
"""

from flask import Blueprint, jsonify, request

from database import mongo

standings_bp = Blueprint("standings", __name__, url_prefix="/api/standings")


def _latest_season():
    seasons = mongo.db.matches.distinct("season")
    return sorted(seasons, reverse=True)[0] if seasons else None


def _compute_table(season):
    table = {}

    def row(team):
        return table.setdefault(team, {
            "team": team, "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "gf": 0, "ga": 0, "gd": 0, "points": 0,
        })

    for m in mongo.db.matches.find({"season": season}):
        h, a = row(m["home_team"]), row(m["away_team"])
        hg, ag = m["home_goals"], m["away_goals"]
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hg
        h["ga"] += ag
        a["gf"] += ag
        a["ga"] += hg
        if hg > ag:
            h["won"] += 1
            h["points"] += 3
            a["lost"] += 1
        elif hg < ag:
            a["won"] += 1
            a["points"] += 3
            h["lost"] += 1
        else:
            h["drawn"] += 1
            a["drawn"] += 1
            h["points"] += 1
            a["points"] += 1

    for r in table.values():
        r["gd"] = r["gf"] - r["ga"]

    ordered = sorted(table.values(),
                     key=lambda r: (r["points"], r["gd"], r["gf"]), reverse=True)
    for pos, r in enumerate(ordered, start=1):
        r["pos"] = pos
    return ordered


@standings_bp.get("/")
def get_standings():
    season = request.args.get("season") or _latest_season()
    if not season:
        return jsonify({"season": None, "standings": []}), 200
    return jsonify({"season": season, "standings": _compute_table(season)}), 200
