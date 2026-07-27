import threading
from datetime import datetime, UTC
from flask import flash, redirect, url_for, session
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.utils.firebase import get_db
from app.config import config
from firebase_admin import auth as firebase_auth
from app.utils.validators import sanitize_input
import bleach
from werkzeug.security import check_password_hash


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
        self.google_client_id = config.get("GOOGLE_CLIENT_ID")

    def login_manual(self, email: str, password: str):
        email = sanitize_input(email)
        password = sanitize_input(password)
        user = self.user_repo.find_by_email(email)
        if not user:
            flash("Incorrect email.", "error")
            return redirect(url_for("public.index"))
        if not check_password_hash(user.password_hash, password):
            flash("Incorrect password.", "error")
            return redirect(url_for("public.index"))
        firebase_user = firebase_auth.get_user(user.uid)
        if not firebase_user.email_verified:
            flash("Please verify your email first.", "error")
            return redirect(url_for("public.index"))
        session["name"] = user.firstname
        session["email"] = user.email
        session["uid"] = user.uid
        flash(f"Welcome back, {user.firstname}!", "success")
        return redirect(url_for("public.index"))

    def login_google(self, token: str):
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        try:
            google_account = id_token.verify_oauth2_token(
                token, google_requests.Request(), self.google_client_id
            )
            session["uid"] = google_account["sub"]
            session["email"] = google_account["email"]
            session["name"] = google_account.get("name", "User")
            user = User(
                uid=session["uid"],
                email=session["email"],
                name=session["name"],
                account_type="Google",
                created_at=datetime.now(UTC).isoformat(),
            )
            self.user_repo.create_google(user)
            return redirect(url_for("public.google_index"))
        except ValueError:
            from flask import render_template
            return render_template("error.html", message="Invalid Google token"), 401

    def sign_up(self, form_data: dict):
        from app.utils.validators import sanitize_form
        cleaned = sanitize_form(form_data)
        try:
            firebase_user = firebase_auth.get_user_by_email(cleaned["email"])
            uid = firebase_user.uid
            doc_ref = get_db().collection("manual_create_account").document(uid)
            if doc_ref.get().exists:
                return "OK", 200
            doc_ref.set({
                "uid": uid,
                "firstname": cleaned["firstname"],
                "lastname": cleaned["lastname"],
                "email": cleaned["email"],
                "contact_number": cleaned["contact_number"],
                "password": "" if not cleaned["password"] else "",
                "verified": firebase_user.email_verified,
                "created_at": datetime.now(UTC).isoformat(),
            })
            return "OK", 200
        except Exception as e:
            print("SIGNUP ERROR:", e)
            return str(e), 500

    def logout(self):
        session.clear()
        return redirect(url_for("public.index"))

    def update_profile(self, uid: str, updates: dict) -> bool:
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return False
            doc_ref = get_db().collection(user_collection).document(uid)
            doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error updating profile: {e}")
            return False
