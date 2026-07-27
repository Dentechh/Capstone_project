import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24)
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_USERNAME")
    MAIL_TIMEOUT = 10
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    PAYMONGO_SECRET_KEY = "sk_test_CYiQMSXw2cHHhtF564gZ3mMx"
    PAYMONGO_PUBLIC_KEY = "pk_test_m4rG4iv4L9S5MC8d4dxq39ko"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
