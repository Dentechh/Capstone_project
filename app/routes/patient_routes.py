from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.payment_service import PaymentService
from app.services.treatment_service import TreatmentService
from app.services.dashboard_service import DashboardService
from app.utils.repos import get_user_repo, get_appointment_repo, get_procedure_repo

bp = Blueprint("patient", __name__)


def _get_current_user(from_repo=None):
    email = session.get("email")
    if not email:
        return None
    repo = from_repo or get_user_repo()
    return repo.find_by_email(email) or repo.find_google_by_email(email)


@bp.route("/patient-profile")
def profile():
    user = _get_current_user()
    if not user:
        return redirect(url_for("public.index"))
    return render_template("patient-profile.html", name=session.get("name", "Guest"), user=user.to_dict())


@bp.route("/update-profile", methods=["POST"])
def update_profile():
    user = _get_current_user()
    if not user:
        return redirect(url_for("public.index"))
    user_repo = get_user_repo()
    auth_service = AuthService(user_repo)
    firstname = request.form.get("new_name", user.firstname)
    lastname = ""
    if " " in firstname:
        parts = firstname.split(" ", 1)
        firstname = parts[0]
        lastname = parts[1]
    result = auth_service.update_profile(user.uid, {
        "firstname": firstname,
        "lastname": lastname,
    })
    if result:
        flash("Profile updated successfully!", "success")
    else:
        flash("Failed to update profile.", "error")
    return redirect(url_for("patient.profile"))


@bp.route("/patient_forms")
def patient_forms():
    return render_template("patientForms.html")


@bp.route("/booked_customer", methods=["POST"])
def booked_customer():
    from app.models.appointment import Appointment
    user_repo = get_user_repo()
    appointment_repo = get_appointment_repo()
    uid = session.get("uid")
    email = session.get("email")
    appointment = Appointment(
        uid=uid,
        email=email,
        first_name=request.form.get("First_Name", ""),
        middle_name=request.form.get("Middle_Name", ""),
        last_name=request.form.get("Last_Name", ""),
        house_no=request.form.get("House_No", ""),
        street=request.form.get("Street", ""),
        brgy=request.form.get("Brgy", ""),
        municipality=request.form.get("Municipality", ""),
        city=request.form.get("City", ""),
        contact_number=request.form.get("Contact_number", ""),
        nationality=request.form.get("Nationality", ""),
        religion=request.form.get("Religion", ""),
        age=request.form.get("Age", ""),
        sex=request.form.get("Sex", ""),
        birthday=request.form.get("Birthday", ""),
        occupation=request.form.get("Occupation", ""),
        civil_status=request.form.get("Civil_Status", ""),
        service=request.form.get("Service", ""),
        urgency_level=request.form.get("Urgency_Level", ""),
        appointment_date=request.form.get("appointment_date", ""),
        q1=request.form.get("q1", ""),
        q2=request.form.get("q2", ""),
        q3=request.form.get("q3", ""),
        q4=request.form.get("q4", ""),
        q5=request.form.get("q5", ""),
        q6=request.form.get("q6", ""),
        q7=request.form.get("q7", ""),
        q9=request.form.get("q9", ""),
        q2_spec=request.form.get("q2_spec", ""),
        q3_spec=request.form.get("q3_spec", ""),
        q4_spec=request.form.get("q4_spec", ""),
        q5_spec=request.form.get("q5_spec", ""),
        q7_spec=request.form.get("q7_spec", ""),
        q9_spec=request.form.get("q9_spec", ""),
        w_preg=request.form.get("w_preg"),
        w_nurse=request.form.get("w_nurse"),
        w_pill=request.form.get("w_pill"),
    )
    result = appointment_repo.add_appointment(uid, appointment)
    if result:
        flash("Appointment successfully booked!", "success")
    else:
        flash("There was an error booking your appointment.", "error")
    return redirect(url_for("public.index"))


@bp.route("/google_booked_customer", methods=["POST"])
def google_booked_customer():
    return booked_customer()


@bp.route("/get_patient/<uid>")
def get_patient(uid):
    user_repo = get_user_repo()
    procedure_repo = get_procedure_repo()
    user = user_repo.find_by_uid(uid) or user_repo.find_google_by_uid(uid)
    if not user:
        return {"error": "Patient not found"}
    data = user.to_dict()
    data["uid"] = user.uid
    data["account_type"] = user.account_type
    visit_history = procedure_repo.get_history(uid)
    data["Done_procedure"] = {"procedures": visit_history}
    return data


@bp.route("/get_approve/<uid>")
def get_approve(uid):
    appointment_repo = get_appointment_repo()
    approvals = appointment_repo.get_approvals_by_uid(uid)
    return jsonify(approvals)


@bp.route("/save_dental_record", methods=["POST"])
def save_dental_record():
    user = _get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    procedure_repo = get_procedure_repo()
    treatment_service = TreatmentService(procedure_repo)
    result = treatment_service.save_dental_record(user.uid, request.form, request.files)
    return jsonify(result)


@bp.route("/create_gcash_payment", methods=["POST"])
def create_gcash_payment():
    payment_service = PaymentService()
    data = request.json
    amount = float(data.get("amount", 0))
    procedure = data.get("procedure", "")
    patient_uid = data.get("uid", "")
    base_url = request.host_url.rstrip("/")
    return payment_service.create_gcash_payment(amount, procedure, patient_uid, base_url)
