from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from flask import abort

bp = Blueprint("public", __name__)


@bp.route("/", methods=["GET"])
def index():
    uid = session.get("uid", "")
    name = session.get("name", "Guest")
    email = session.get("email", "")
    return render_template("index.html", uid=uid, name=name, email=email)


@bp.route("/google_index", methods=["GET"])
def google_index():
    uid = session.get("uid", "")
    name = session.get("name", "Guest")
    email = session.get("email", "")
    return render_template("google_index.html", uid=uid, name=name, email=email)


@bp.route("/about")
def about():
    name = session.get("name", "Guest")
    email = session.get("email", "")
    return render_template("about.html", name=name, email=email)


@bp.route("/location")
def location():
    name = session.get("name", "Guest")
    email = session.get("email", "")
    return render_template("location.html", name=name, email=email)


@bp.route("/services/<service_id>")
def service_detail(service_id):
    from app.models.service import Service
    service = Service.get_by_id(service_id)
    if not service:
        abort(404)
    name = session.get("name", "Guest")
    email = session.get("email", "")
    uid = session.get("uid", "")
    return render_template("service.html", service=service, name=name, email=email, uid=uid)


@bp.route("/medical_records")
def medical_records():
    return render_template("medical_records.html")


@bp.route("/prac")
def prac():
    return render_template("prac.html")
