import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

basedir = os.path.abspath(os.path.dirname(__file__))
key_path = os.path.normpath(os.path.join(basedir, "..", "..", "dentech_key.json"))

db = None


def init_firebase() -> None:
    global db
    if not firebase_admin._apps:
        try:
            if not os.path.exists(key_path):
                raise FileNotFoundError(f"Firebase key not found at: {key_path}")
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
            db = firestore.client()
            print(" Firebase initialized successfully")
        except Exception as e:
            print(" Firebase initialization failed:", e)
            db = None
    else:
        db = firestore.client()
        print(" Firebase already initialized")


def get_db():
    if db is None:
        raise RuntimeError("Firebase is not initialized. Check dentech_key.json")
    return db
