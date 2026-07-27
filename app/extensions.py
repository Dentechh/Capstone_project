from flask_mail import Mail
from flask import Flask

mail = Mail()


def init_extensions(app: Flask) -> None:
    mail.init_app(app)
