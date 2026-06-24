import os

from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config
from database import init_db
from routes.auth import auth_bp
from routes.results import results_bp
from routes.predictions import predictions_bp
from routes.standings import standings_bp

jwt = JWTManager()


def create_app():
    # Serve the built React app (if present) from the same origin as the API.
    frontend_dist = os.getenv(
        "FRONTEND_DIST",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist"),
    )
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}})

    init_db(app)
    jwt.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(predictions_bp)
    app.register_blueprint(standings_bp)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "Football Predictions API"}

    # Single-page-app: serve real static files when they exist, otherwise fall
    # back to index.html so client-side routing (/forecast, /history, ...) works.
    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def serve_spa(path):
        if path.startswith("api/"):
            return {"error": "Not found"}, 404
        if path:
            full = os.path.join(frontend_dist, path)
            if os.path.isfile(full):
                return send_from_directory(frontend_dist, path)
        index = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index):
            return send_from_directory(frontend_dist, "index.html")
        return {"error": "Frontend build not found"}, 404

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=Config.DEBUG, port=int(os.getenv("PORT", "5000")))

