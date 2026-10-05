import os
from firebase_admin import credentials

key_path = "/etc/secrets/dentech_key.json"
if not os.path.exists(key_path):
    key_path = "dentech_key.json"  # local development

cred = credentials.Certificate(key_path)