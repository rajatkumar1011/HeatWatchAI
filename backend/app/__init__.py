"""HeatWatch AI — Flask application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.extensions import db, jwt, migrate
from config import get_config


def create_app(config_object=None) -> Flask:
    app = Flask(__name__)
    config = config_object or get_config()
    app.config.from_object(config)

    Path(app.config["REPORT_OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / "migrations"))
    jwt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, supports_credentials=False)

    _configure_logging(app)
    _register_models(app)
    _register_jwt_handlers(app)
    _register_error_handlers(app)
    _register_blueprints(app)
    _register_cli(app)

    @app.get("/api/v1/health")
    def health_root():  # public liveness probe
        return jsonify({"status": "ok", "app": app.config["APP_NAME"], "data_mode_hint": app.config["DATA_MODE"]})

    @app.get("/")
    def index():
        return jsonify({"app": app.config["APP_NAME"], "tagline": app.config["APP_TAGLINE"], "api": "/api/v1"})

    # Hard cap JSON body size (FR-10 input validation)
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_JSON_BODY_BYTES"]

    return app


def _configure_logging(app: Flask) -> None:
    logging.basicConfig(
        level=logging.DEBUG if app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _register_models(app: Flask) -> None:
    import app.models  # noqa: F401  (registers all tables)


def _register_jwt_handlers(app: Flask) -> None:
    from app.models import User

    @jwt.user_identity_loader
    def user_identity_lookup(user):  # JWT subject must be a string
        return str(user)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_payload):
        identity = jwt_payload["sub"]
        try:
            user_id = int(identity)
        except (TypeError, ValueError):
            return None
        user = db.session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user

    @jwt.expired_token_loader
    def expired_token_callback(_jwt_header, _jwt_payload):
        from app.utils.responses import error_response
        return error_response(401, "Your session has expired. Please log in again.", code="token_expired")

    @jwt.invalid_token_loader
    def invalid_token_callback(_reason):
        from app.utils.responses import error_response
        return error_response(401, "Invalid authentication token.", code="token_invalid")

    @jwt.unauthorized_loader
    def missing_token_callback(_reason):
        from app.utils.responses import error_response
        return error_response(401, "Authentication required.", code="token_missing")


def _register_error_handlers(app: Flask) -> None:
    from app.utils.responses import ApiError, error_response, log_event

    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        return error_response(err.status, err.message, err.details, err.code)

    @app.errorhandler(404)
    def handle_404(_err):
        return error_response(404, "The requested resource was not found.")

    @app.errorhandler(405)
    def handle_405(_err):
        return error_response(405, "Method not allowed for this endpoint.")

    @app.errorhandler(413)
    def handle_413(_err):
        return error_response(413, "Request body too large.")

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        app.logger.exception("unhandled exception on %s %s", request.method, request.path)
        try:
            log_event("system", f"Unhandled exception: {err}", level="error",
                      details={"path": request.path, "method": request.method})
        except Exception:
            pass
        # Always respond with a safe JSON envelope; internal details stay in
        # the log (SRS FR-10: no stack traces or credentials to clients).
        return error_response(500, "An unexpected internal error occurred. The incident has been logged.")


def _register_blueprints(app: Flask) -> None:
    from app.api import ALL_BLUEPRINTS

    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)


def _register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin_command():  # pragma: no cover - interactive command
        """Secure initial administrator setup (never via public registration)."""
        import click
        from app.models import ROLE_ADMIN, User

        username = click.prompt("Admin username")
        email = click.prompt("Admin email")
        password = click.prompt("Admin password", hide_input=True, confirmation_prompt=True)
        if db.session.query(User).filter((User.username == username) | (User.email == email)).first():
            click.echo("A user with that username or email already exists.")
            raise SystemExit(1)
        user = User(username=username, email=email, role=ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator '{username}' created.")
