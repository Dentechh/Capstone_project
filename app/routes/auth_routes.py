from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.services.auth_service import AuthService
from app.utils.repos import get_user_repo

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["POST"])
def login():
    user_repo = get_user_repo()
    auth_service = AuthService(user_repo)
    email = request.form.get("email", "")
    password = request.form.get("Password", "")
    return auth_service.login_manual(email, password)


@bp.route("/google-auth", methods=["POST"])
def google_auth():
    user_repo = get_user_repo()
    auth_service = AuthService(user_repo)
    token = request.form["token"]
    return auth_service.login_google(token)


@bp.route("/sign-up", methods=["POST"])
def sign_up():
    user_repo = get_user_repo()
    auth_service = AuthService(user_repo)
    result, status = auth_service.sign_up(request.form.to_dict())
    if status == 200:
        flash("Account created successfully!", "success")
    else:
        flash(result, "error")
    return result, status


@bp.route("/logout")
def logout():
    user_repo = get_user_repo()
    auth_service = AuthService(user_repo)
    return auth_service.logout()
