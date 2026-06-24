"""
Authentication routes backed by MongoDB.

Passwords are hashed with bcrypt and never stored in clear text. On successful
login a signed JWT access token (24h expiry, configured in Config) is returned.
"""

import bcrypt
from bson import ObjectId
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from database import mongo

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/register")
def register():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()

    if not email or not password or not name:
        return jsonify({"error": "All fields are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    if mongo.db.users.find_one({"email": email}):
        return jsonify({"error": "Email already registered."}), 409

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    result = mongo.db.users.insert_one({
        "email": email,
        "name": name,
        "password_hash": pw_hash,
    })

    token = create_access_token(identity=str(result.inserted_id),
                                additional_claims={"name": name, "email": email})
    return jsonify({"message": "Registered successfully.", "token": token, "name": name}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = mongo.db.users.find_one({"email": email})
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
        return jsonify({"error": "Invalid credentials."}), 401

    token = create_access_token(identity=str(user["_id"]),
                                additional_claims={"name": user["name"], "email": email})
    return jsonify({"message": "Login successful.", "token": token, "name": user["name"]}), 200


@auth_bp.get("/me")
@jwt_required()
def me():
    user = mongo.db.users.find_one({"_id": ObjectId(get_jwt_identity())})
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"email": user["email"], "name": user["name"]}), 200


@auth_bp.post("/logout")
def logout():
    # JWT is stateless; the client simply drops the token.
    return jsonify({"message": "Logged out."}), 200
