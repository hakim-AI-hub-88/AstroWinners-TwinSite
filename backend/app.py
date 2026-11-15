#############################################################################
# FLASK APPLICATION ENTRY POINT
#
# Why this file exists:
#   Creates the web server: serves the single-page interface
#   (templates/index.html + static/), registers the API blueprint and loads
#   the harmonized datasets once at start-up.
#
# Run (from the app/ folder):
#   python backend/app.py            -> http://127.0.0.1:5050
#   APP_PORT=8000 python backend/app.py
#
# Future extension:
#   - production server: gunicorn "app:create_app()" --chdir backend
#   - more blueprints (e.g. /api/maps) registered in create_app()
#############################################################################
from __future__ import annotations

import logging
import sys
from pathlib import Path

# The TwinSite platform package (backend/twinsite) imports `contracts` from the repository root.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "backend"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, jsonify, render_template

from routes.assistant_routes import bp as assistant_bp
from routes.ml_routes import bp as ml_bp
from routes.platform_routes import bp as platform_bp
from routes.report_routes import bp as report_bp
from routes.similarity_routes import bp as similarity_bp
from routes.twin_routes import bp as twin_bp
from services import data_loader, ml_models
from utils import config


#############################################
# APPLICATION FACTORY
# Output: configured Flask app
# preload=True reads the three datasets now (~10-20 s for Mars) so the first
# user request is fast; tests can pass preload=False.
#############################################
def create_app(preload: bool = True) -> Flask:
    app = Flask(__name__, template_folder=str(config.TEMPLATE_DIR), static_folder=str(config.STATIC_DIR))
    app.json.sort_keys = False
    app.register_blueprint(similarity_bp)
    app.register_blueprint(assistant_bp)      # AI Mission Assistant (Groq)
    app.register_blueprint(ml_bp)             # machine-learning models (PCA, K-means)
    app.register_blueprint(report_bp)         # TWINSITE mission report (AI narrative + map images)
    app.register_blueprint(twin_bp)           # TWINSITE interactive globes (data layers, region check)
    app.register_blueprint(platform_bp)       # pages, sitemap, React console, /v1 platform API proxy

    # ----------------------------------------------------------------------
    # PAGE ROUTES
    #   /     TWINSITE home page (hero, call to action)
    #   /app  the analysis dashboard (one Jinja2 template, 4 client-side pages)
    # ----------------------------------------------------------------------
    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/app")
    def index():
        return render_template("index.html", targets=config.TARGETS, features=config.FEATURES,
                               zones=config.EARTH_ZONES, default_zone=config.DEFAULT_ZONE)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"status": "error", "message": "Not found"}), 404

    if preload:
        try:
            data_loader.load_all()
            ml_models.models()                 # train the unsupervised models once (~5 s)
        except ImportError:
            app.logger.warning("scikit-learn missing: the machine-learning section is disabled")
        except (FileNotFoundError, ValueError) as exc:
            # The server still starts; /api/status reports the problem.
            app.logger.error("Datasets not loaded: %s", exc)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    create_app().run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
