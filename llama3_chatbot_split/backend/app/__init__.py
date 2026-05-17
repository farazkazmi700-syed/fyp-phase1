from flask import Flask
from flask_cors import CORS
from .config import Config, FRONTEND_DIR
from .database import init_db, close_db
from .auth import auth_bp
from .chat import chat_bp
from .feedback import feedback_bp
from .analytics import analytics_bp


def create_app():
    app = Flask(
        __name__,
        template_folder=f"{FRONTEND_DIR}/templates",
        static_folder=f"{FRONTEND_DIR}/static",
    )
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    CORS(app, supports_credentials=True)

    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(analytics_bp)

    with app.app_context():
        init_db()

    return app
