import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.services.email_service import EmailService
from app.services.treatment_service import TreatmentService
from app.services.dashboard_service import DashboardService
from app.services.payment_service import PaymentService
from app.utils.repos import get_user_repo, get_appointment_repo, get_procedure_repo
from app.utils.validators import sanitize_input

bp = Blueprint("admin", __name__)


@bp.route("/admin_dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    dashboard_service = DashboardService(get_appointment_repo(), get_user_repo(), get_procedure_repo())
    data = dashboard_service.get_admin_dashboard_data()
    return render_template("admin_dashboard.html", **data)


@bp.route("/admin_login", methods=["GET", "POST"])
def login():
    from werkzeug.security import check_password_hash
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        from app.utils.firebase import get_db
        admin_query = get_db().collection("admins").where("email", "==", email).get()
        if admin_query and admin_query[0].exists:
            admin_data = admin_query[0].to_dict()
            if admin_data.get("is_active", True) and check_password_hash(admin_data["password_hash"], password):
                session["admin_logged_in"] = True
                session["admin_email"] = email
                session["admin_name"] = admin_data.get("name", "Admin")
                flash(f"Welcome back, Dr. {admin_data.get('name')}!", "success")
                return redirect(url_for("admin.admin_dashboard"))
        flash("Invalid credentials. Please try again.", "error")
        return redirect(url_for("admin.login"))
    if session.get("admin_logged_in"):
        return redirect(url_for("admin.admin_dashboard"))
    return render_template("admin_login.html")


@bp.route("/approve", methods=["POST"])
def approve():
    from app.models.approve import Approve
    user_repo = get_user_repo()
    appointment_repo = get_appointment_repo()
    email_service = EmailService()

    uid = request.form.get("user_id", "").strip()
    appointment_id = request.form.get("appointment_id", "").strip()
    action = request.form.get("action", "").strip().lower()
    dentist_name = sanitize_input(request.form.get("dentist_name", ""))

    if not uid or not appointment_id:
        return "Missing user_id or appointment_id", 400
    if action not in ("accept", "decline"):
        return "Invalid action", 400

    approve = Approve(
        appointment_id=appointment_id,
        patient_unq_id=appointment_id,
        uid=uid,
        email=request.form.get("email", ""),
        first_name=request.form.get("firstname", ""),
        middle_name=request.form.get("middlename", ""),
        last_name=request.form.get("lastname", ""),
        house_no=request.form.get("houseno", ""),
        street=request.form.get("street", ""),
        brgy=request.form.get("brgy", ""),
        municipality=request.form.get("municipality", ""),
        city=request.form.get("city", ""),
        contact_number=request.form.get("contactnumber", ""),
        nationality=request.form.get("nationality", ""),
        religion=request.form.get("religion", ""),
        age=request.form.get("age", ""),
        sex=request.form.get("sex", ""),
        birthday=request.form.get("birthday", ""),
        occupation=request.form.get("occupation", ""),
        civil_status=request.form.get("civilstatus", ""),
        urgency_level=request.form.get("UrgencyLevel", ""),
        service=request.form.get("service", ""),
        dentist_name=dentist_name,
        status=action,
    )

    user = user_repo.find_by_uid(uid) or user_repo.find_google_by_uid(uid)
    patient_email = user.email if user else None
    fullname = f"{approve.first_name} {approve.last_name}"

    if action == "accept":
        success = appointment_repo.move_to_approve(uid, appointment_id, approve)
    else:
        success = appointment_repo.delete_appointment(uid, appointment_id)

    if success:
        email_service.send_async(patient_email, fullname, action, approve.to_dict())
        return f"Appointment {action}ed"

    return f"Failed to {action} appointment", 500


@bp.route("/get_treatment_info/<uid>")
def get_treatment_info(uid):
    procedure_repo = get_procedure_repo()
    treatment_service = TreatmentService(procedure_repo)
    procedures = treatment_service.get_treatment_info(uid)
    return jsonify({"success": True, "procedures": procedures})


@bp.route("/payment-success")
def payment_success():
    checkout_session_id = request.args.get("checkout_session_id")
    patient_uid = request.args.get("uid", "")
    procedure = request.args.get("procedure", "")
    if checkout_session_id:
        payment_service = PaymentService()
        result = payment_service.verify_payment(checkout_session_id)
        if result.get("success"):
            procedure_repo = get_procedure_repo()
            treatment_service = TreatmentService(procedure_repo)
            procedures = treatment_service.get_treatment_info(patient_uid)
            for proc in procedures:
                if proc.get("procedure") == procedure and proc.get("status") != "Paid":
                    proc["status"] = "Paid"
                    proc["paid"] = proc.get("balance", proc.get("paid", 0))
                    proc["balance"] = 0
            flash("Payment successful! Your appointment is now confirmed.", "success")
        else:
            flash("Payment received and is being processed. Your status will update shortly.", "info")
    return redirect(url_for("public.index"))


@bp.route("/payment-cancel")
def payment_cancel():
    flash("Payment was cancelled or expired.", "error")
    return redirect(url_for("public.index"))


@bp.route("/webhook/paymongo", methods=["POST"])
def paymongo_webhook():
    try:
        event = request.json
        attributes = event.get("data", {}).get("attributes", {})
        event_type = attributes.get("type", "")
        if event_type == "checkout.session.completed":
            session_attrs = attributes.get("data", {}).get("attributes", {})
            metadata = session_attrs.get("metadata", {})
            patient_uid = metadata.get("patient_uid", "")
            procedure = metadata.get("procedure", "")
            payment_status = session_attrs.get("payment_status", "")
            if payment_status == "paid" and patient_uid and procedure:
                procedure_repo = get_procedure_repo()
                treatment_service = TreatmentService(procedure_repo)
                procedures = treatment_service.get_treatment_info(patient_uid)
                for proc in procedures:
                    if proc.get("procedure") == procedure and proc.get("status") != "Paid":
                        proc["status"] = "Paid"
                        proc["paid"] = proc.get("balance", proc.get("paid", 0))
                        proc["balance"] = 0
    except Exception as e:
        print(f"Webhook error: {e}")
    return "", 200
