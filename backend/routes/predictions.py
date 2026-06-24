"""
Prediction routes.

POST /api/predictions/predict  -> runs the trained PyTorch model for a matchup
                                  (home vs away) and returns outcome probabilities
                                  + expected/most-likely exact score. If the caller
                                  is authenticated, the prediction is stored.
GET  /api/predictions/teams    -> list of teams known to the model
GET  /api/predictions/history  -> (JWT) the current user's saved predictions
"""

from datetime import datetime, timezone
import json

from bson import ObjectId
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from database import mongo

predictions_bp = Blueprint("predictions", __name__, url_prefix="/api/predictions")


def _predictor():
    # Imported lazily so the app can start even before the model is trained.
    from ml.predict import get_predictor
    return get_predictor()


@predictions_bp.get("/teams")
def teams():
    try:
        return jsonify(_predictor().known_teams), 200
    except Exception as exc:
        return jsonify({"error": f"Model not available: {exc}"}), 503


@predictions_bp.post("/simulate")
@jwt_required(optional=True)
def simulate():
    """Run a full-season Monte-Carlo simulation (different every call)."""
    data = request.get_json(silent=True) or {}
    seed = data.get("seed")
    season = (data.get("season") or "").strip() or None
    try:
        seed = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        seed = None

    try:
        predictor = _predictor()
    except Exception as exc:
        return jsonify({"error": f"Model not available: {exc}"}), 503

    next_seasons = predictor.next_seasons
    if season in next_seasons:
        result = predictor.simulate_next_season(season=season, seed=seed)
    else:
        result = predictor.simulate_season(season=season, seed=seed)
    # Upcoming real-fixture seasons first, then the most recent historical ones.
    result["available_seasons"] = next_seasons + predictor.seasons[-10:]
    result["next_seasons"] = next_seasons

    # Persist for authenticated users (each run is a distinct random outcome).
    user_id = get_jwt_identity()
    if user_id:
        claims = get_jwt()
        standings = result.get("standings", [])
        champion = standings[0]["team"] if standings else None
        mongo.db.user_simulations.insert_one({
            "user_id": user_id,
            "user_name": claims.get("name"),
            "season": result.get("season"),
            "champion": champion,
            "standings": standings,
            "timestamp": datetime.now(timezone.utc),
        })

    return jsonify(result), 200


@predictions_bp.post("/simulate-batch")
@jwt_required(optional=True)
def simulate_batch():
    """Run many full-season simulations and aggregate title / top-N / relegation odds."""
    data = request.get_json(silent=True) or {}
    season = (data.get("season") or "").strip() or None
    seed = data.get("seed")
    runs = data.get("runs", 1000)
    try:
        seed = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        seed = None
    try:
        runs = int(runs)
    except (TypeError, ValueError):
        runs = 1000

    try:
        predictor = _predictor()
    except Exception as exc:
        return jsonify({"error": f"Model not available: {exc}"}), 503

    result = predictor.simulate_batch(season=season, runs=runs, seed=seed)
    next_seasons = predictor.next_seasons
    result["available_seasons"] = next_seasons + predictor.seasons[-10:]
    result["next_seasons"] = next_seasons

    # Persist for authenticated users.
    user_id = get_jwt_identity()
    if user_id:
        claims = get_jwt()
        table = result.get("table", [])
        # The favourite is the team that won the title most often.
        favourite = max(
            table, key=lambda r: r.get("title_count", 0), default=None
        )
        mongo.db.user_forecasts.insert_one({
            "user_id": user_id,
            "user_name": claims.get("name"),
            "season": result.get("season"),
            "runs": result.get("runs"),
            "favourite": favourite["team"] if favourite else None,
            "table": table,
            "timestamp": datetime.now(timezone.utc),
        })

    return jsonify(result), 200


@predictions_bp.post("/simulate-batch-stream")
@jwt_required(optional=True)
def simulate_batch_stream():
    """
    Same as /simulate-batch but streams newline-delimited JSON so the client
    can show real progress (seasons completed) instead of a time estimate.

    Each line is one JSON object:
      {"type": "progress", "done": 103, "total": 1000}
      ...
      {"type": "result", "result": { ...full aggregate... }}
    """
    data = request.get_json(silent=True) or {}
    season = (data.get("season") or "").strip() or None
    seed = data.get("seed")
    runs = data.get("runs", 1000)
    try:
        seed = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        seed = None
    try:
        runs = int(runs)
    except (TypeError, ValueError):
        runs = 1000
    runs = max(1, min(runs, 10000))

    try:
        predictor = _predictor()
    except Exception as exc:
        return jsonify({"error": f"Model not available: {exc}"}), 503

    # Capture auth context now — the generator runs while streaming.
    user_id = get_jwt_identity()
    claims = get_jwt() if user_id else None
    # ~100 progress updates regardless of run count.
    every = max(1, runs // 100)

    def sse(obj):
        return f"data: {json.dumps(obj)}\n\n"

    def generate():
        # Large initial comment defeats byte-threshold buffering in proxies/CDNs
        # (Cloudflare/Render) so progress events flush immediately.
        yield ": " + (" " * 2048) + "\n\n"

        result = None
        for kind, payload in predictor.iter_simulate_batch(
            season=season, runs=runs, seed=seed, progress_every=every
        ):
            if kind == "progress":
                yield sse({"type": "progress", "done": payload, "total": runs})
            else:
                result = payload

        next_seasons = predictor.next_seasons
        result["available_seasons"] = next_seasons + predictor.seasons[-10:]
        result["next_seasons"] = next_seasons

        if user_id:
            table = result.get("table", [])
            favourite = max(
                table, key=lambda r: r.get("title_count", 0), default=None
            )
            mongo.db.user_forecasts.insert_one({
                "user_id": user_id,
                "user_name": claims.get("name") if claims else None,
                "season": result.get("season"),
                "runs": result.get("runs"),
                "favourite": favourite["team"] if favourite else None,
                "table": table,
                "timestamp": datetime.now(timezone.utc),
            })

        yield sse({"type": "result", "result": result})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@predictions_bp.post("/predict")
@jwt_required(optional=True)
def predict():
    data = request.get_json() or {}
    home = (data.get("home_team") or "").strip()
    away = (data.get("away_team") or "").strip()

    if not home or not away:
        return jsonify({"error": "home_team and away_team are required."}), 400
    if home == away:
        return jsonify({"error": "Teams must be different."}), 400

    try:
        predictor = _predictor()
    except Exception as exc:
        return jsonify({"error": f"Model not available: {exc}"}), 503

    if home not in predictor.known_teams or away not in predictor.known_teams:
        return jsonify({"error": "Unknown team(s) for the trained model."}), 400

    result = predictor.predict(home, away)

    # Persist for authenticated users. Upsert on (user, home, away) so the same
    # matchup is stored once (the model is deterministic) instead of duplicated.
    user_id = get_jwt_identity()
    if user_id:
        claims = get_jwt()
        mongo.db.user_predictions.update_one(
            {"user_id": user_id, "home_team": home, "away_team": away},
            {"$set": {
                "user_id": user_id,
                "user_name": claims.get("name"),
                "home_team": home,
                "away_team": away,
                "predicted_result": result["predicted_result"],
                "probabilities": result["probabilities"],
                "predicted_score": result["predicted_score"],
                "timestamp": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

    return jsonify(result), 200


@predictions_bp.get("/history")
@jwt_required()
def history():
    user_id = get_jwt_identity()
    cursor = (
        mongo.db.user_predictions.find({"user_id": user_id})
        .sort("timestamp", -1)
        .limit(50)
    )
    items = [{
        "id": str(d["_id"]),
        "home_team": d["home_team"],
        "away_team": d["away_team"],
        "predicted_result": d["predicted_result"],
        "probabilities": d["probabilities"],
        "predicted_score": d.get("predicted_score"),
        "timestamp": d["timestamp"].isoformat(),
    } for d in cursor]
    return jsonify(items), 200


@predictions_bp.get("/history/simulations")
@jwt_required()
def history_simulations():
    user_id = get_jwt_identity()
    cursor = (
        mongo.db.user_simulations.find({"user_id": user_id})
        .sort("timestamp", -1)
        .limit(50)
    )
    items = [{
        "id": str(d["_id"]),
        "season": d.get("season"),
        "champion": d.get("champion"),
        "standings": d.get("standings", []),
        "timestamp": d["timestamp"].isoformat(),
    } for d in cursor]
    return jsonify(items), 200


@predictions_bp.get("/history/forecasts")
@jwt_required()
def history_forecasts():
    user_id = get_jwt_identity()
    cursor = (
        mongo.db.user_forecasts.find({"user_id": user_id})
        .sort("timestamp", -1)
        .limit(50)
    )
    items = [{
        "id": str(d["_id"]),
        "season": d.get("season"),
        "runs": d.get("runs"),
        "favourite": d.get("favourite"),
        "table": d.get("table", []),
        "timestamp": d["timestamp"].isoformat(),
    } for d in cursor]
    return jsonify(items), 200
