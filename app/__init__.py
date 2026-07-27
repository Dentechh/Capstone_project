from flask import Flask
from app.config import config
from app.extensions import init_extensions
from app.utils.firebase import init_firebase
from app.routes.public_routes import bp as public_bp
from app.routes.auth_routes import bp as auth_bp
from app.routes.patient_routes import bp as patient_bp
from app.routes.admin_routes import bp as admin_bp


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    init_extensions(app)
    init_firebase()

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(admin_bp)

    return app
