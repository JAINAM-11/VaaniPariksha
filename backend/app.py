"""
VaaniPariksha - Flask Application Factory
"""
import os
import logging
from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()


def create_app(config_name: str = "default") -> Flask:
    from backend.config.settings import config
    from backend.database.db import init_db
    from backend.routes.upload import upload_bp
    from backend.routes.exam import exam_bp
    from backend.routes.admin import download_bp, admin_bp

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "static"),
    )

    # Load config
    app.config.from_object(config[config_name])

    # CORS
    CORS(app, origins=app.config.get("CORS_ORIGINS", ["*"]))

    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Register blueprints
    app.register_blueprint(upload_bp, url_prefix="/api")
    app.register_blueprint(exam_bp, url_prefix="/api")
    app.register_blueprint(download_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")

    # Initialize DB
    try:
        init_db(app)
        logging.getLogger(__name__).info("Database initialized.")
    except Exception as e:
        logging.getLogger(__name__).warning(f"DB init warning: {e}")

    # Serve frontend pages
    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")

    @app.route("/exam")
    def exam_page():
        from flask import render_template
        return render_template("exam.html")

    @app.route("/admin")
    def admin_page():
        from flask import render_template
        return render_template("admin.html")

    # Health check
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "VaaniPariksha"}

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Internal server error"}, 500

    return app


if __name__ == "__main__":
    app = create_app()
    from backend.config.settings import Config
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )
