from flask import Flask, abort, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, UTC
import bleach
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import sys
sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)
import os
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)  # Secure session key
from datetime import timedelta
import random

import os
import firebase_admin
from firebase_admin import credentials, firestore

basedir = os.path.abspath(os.path.dirname(__file__))
key_path = os.path.join(basedir, "dentech_key.json")

# Check service account file
if not os.path.exists(key_path):
    raise FileNotFoundError(
        f"Firebase key not found at: {key_path}"
    )

# Prevent re-initialization during Flask debug reload
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(key_path)

        firebase_admin.initialize_app(cred, {
            "projectId": "dentech-c2ee0"
        })

        db = firestore.client()

        print("✅ Firebase initialized successfully")

    except Exception as e:
        print("❌ Firebase initialization failed:", e)
        raise

else:
    db = firestore.client()
    print("♻️ Firebase already initialized")

Account_clients = "manual_create_account"
Appointment_cliets = "appointments"
Doc_Patients = "Patients"



# Paymongo api keys
pay_mongo_secret_key = "sk_test_CYiQMSXw2cHHhtF564gZ3mMx"
pay_mongo_public_key = "pk_test_m4rG4iv4L9S5MC8d4dxq39ko"

import requests
import base64

@app.route("/create_gcash_payment", methods=["POST"])
def create_gcash_payment():

    data = request.json

    amount = int(float(data["amount"]) * 100)

    auth = base64.b64encode(
        f"{pay_mongo_secret_key}:".encode()
    ).decode()

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Basic {auth}"
    }

    payload = {
        "data": {
            "attributes": {
                "billing": {
                    "name": "Dental Patient",
                    "email": "patient@example.com"
                },
                "line_items": [{
                    "currency": "PHP",
                    "amount": amount,
                    "name": data["procedure"],
                    "quantity": 1
                }],
                "payment_method_types": ["gcash"],
                "success_url": "https://yourdomain.com/payment-success",
                "cancel_url": "https://yourdomain.com/payment-cancel"
            }
        }
    }

    r = requests.post(
        "https://api.paymongo.com/v1/checkout_sessions",
        headers=headers,
        json=payload
    )

    result = r.json()

    return {
        "checkout_url": result["data"]["attributes"]["checkout_url"]
    }


# makita nisa sa diri https://console.cloud.google.com/auth/clients?project=dentech-c2ee0
CLIENT_ID = "921529543911-okjlt4tgb56admos6msdlho9c6ibive8.apps.googleusercontent.com"



#PAYMENTS 
#Still working palang payment the butangi lng cho if maka tapos ka sa need  mo  taposon
# add kalng button for payment



#notification for gmail ni client

app.permanent_session_lifetime = timedelta(minutes=10)

@app.before_request
def refresh_session():
    session.permanent = True
    session.modified = True

@app.route("/", methods=["GET"])
def index():
    uid = session.get('uid', '')
    name = session.get('name', 'Guest')
    email = session.get('email', '')

    return render_template("index.html",uid=uid,name=name,email=email)



@app.route("/google_index", methods=["GET"])
def google_index():
    uid = session.get ('uid', '')
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("google_index.html",uid = uid, name=name, email=email)

@app.route("/login", methods=["POST"])
def login_manual():

    email = bleach.clean(request.form.get("email", "").strip())
    password = bleach.clean(request.form.get("Password", "").strip())

    user_query = db.collection(Account_clients).where("email", "==", email).get()

    if user_query:

        user_data = user_query[0].to_dict()

        if check_password_hash(user_data["password"], password):

            # Check if email is verified
            if not user_data.get("verified", False):
                flash("Please verify your email first.", "error")
                return redirect(url_for("verify_otp", uid=user_query[0].id))

            session["name"] = user_data.get("firstname", "")
            session["email"] = user_data.get("email", "")
            session["uid"] = user_query[0].id

            flash(f"Welcome back, {user_data['firstname']}!", "success")
            return redirect(url_for("index"))

    flash("Invalid email or password!", "error")
    return redirect("/")

#  GOOGLE AUTH ROUTE

@app.route("/google-auth", methods=["POST"])
def login_g_auth():
    token = request.form["token"]
    try:
        google_account = id_token.verify_oauth2_token(token, google_requests.Request(), CLIENT_ID)
        
        # Store user info in session
        session['uid'] = google_account["sub"]
        session['email'] = google_account["email"]
        session['name'] = google_account.get("name", "User")

        db.collection("google_create_account").document(session['uid']).set({
            "uid": session['uid'],
            "email": session['email'],
            "name": session['name'],
            "provider": "google",
            "last_login": datetime.now(UTC).isoformat()
        }, merge=True)

        return redirect(url_for("google_index")) 
    except ValueError:
        return render_template("error.html", message="Invalid Google token")


#  MANUAL SIGN UP

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp(email, otp):

    msg = Message(
        subject="Verify Your Email",
        recipients=[email]
    )

    msg.body = f"""
Hello,

Thank you for creating an account.

Your verification code is:

{otp}

This code expires in 10 minutes.

If you didn't request this account, ignore this email.

Dentech Dental Clinic
"""

    mail.send(msg)



@app.route("/sign-up", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":

        firstname = bleach.clean(request.form["FirstName"].strip())
        lastname = bleach.clean(request.form["LastName"].strip())
        email = bleach.clean(request.form["UserName"].strip())
        password = bleach.clean(request.form["Password"].strip())
        contact_number = bleach.clean(request.form["MobileNumber"].strip())

        check_account = db.collection(Account_clients).where("email", "==", email).get()

        if check_account:
            flash("Email already exists!", "error")
            return redirect(url_for("sign_up"))

        hashed_password = generate_password_hash(password)

        otp = generate_otp()

        doc_ref = db.collection(Account_clients).document()
        uid = doc_ref.id

        doc_ref.set({
            "uid": uid,
            "firstname": firstname,
            "lastname": lastname,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.now(UTC).isoformat(),
            "contact_number": contact_number,

            # OTP Verification
            "verified": False,
            "otp": otp
        })

        send_otp(email, otp)

        flash("A verification code has been sent to your email.", "success")

        return redirect(url_for("verify_otp", uid=uid))

    return render_template("index.html")


@app.route("/verify_otp/<uid>", methods=["GET", "POST"])
def verify_otp(uid):

    doc_ref = db.collection(Account_clients).document(uid)
    doc = doc_ref.get()

    if not doc.exists:
        flash("Account not found.", "error")
        return redirect(url_for("index"))

    user = doc.to_dict()

    if request.method == "POST":

        code = request.form["otp"].strip()

        if code == user.get("otp"):

            doc_ref.update({
                "verified": True,
                "otp": firestore.DELETE_FIELD
            })

            flash("Email verified successfully!", "success")

            return redirect(url_for("index"))

        flash("Invalid OTP.", "error")

    return render_template("verify_otp.html", email=user["email"])



@app.route("/resend_otp/<uid>")
def resend_otp(uid):

    doc_ref = db.collection(Account_clients).document(uid)
    doc = doc_ref.get()

    if not doc.exists:
        flash("User not found.", "error")
        return redirect(url_for("index"))

    user = doc.to_dict()

    otp = generate_otp()

    doc_ref.update({
        "otp": otp
    })

    send_otp(user["email"], otp)

    flash("A new OTP has been sent.", "success")

    return redirect(url_for("verify_otp", uid=uid))

#  LOGOUT

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/patient_forms")
def p_forms():
    return render_template("patientForms.html")

@app.route("/about")
def about_customer():
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("about.html", name=name, email=email)









@app.route("/google_booked_customer", methods=["POST"])
def google_bookedCustomer():
    uid = session.get('uid')
    email = session.get('email')

        # Personal Info
    FirstName = bleach.clean(request.form.get("First_Name", ""))
    MiddleName = bleach.clean(request.form.get("Middle_Name", ""))
    LastName = bleach.clean(request.form.get("Last_Name", ""))
    HouseNo = bleach.clean(request.form.get("House_No", ""))
    Street = bleach.clean(request.form.get("Street", ""))
    Brgy = bleach.clean(request.form.get("Brgy", ""))
    Municipality = bleach.clean(request.form.get("Municipality", ""))
    City = bleach.clean(request.form.get("City", ""))
    Nationality = bleach.clean(request.form.get("Nationality", ""))
    Religion = bleach.clean(request.form.get("Religion", ""))
    Age = bleach.clean(request.form.get("Age", ""))
    Sex = bleach.clean(request.form.get("Sex", ""))
    ContactNumber = bleach.clean(request.form.get("Contact_number", ""))
    Birthday = bleach.clean(request.form.get("Birthday", ""))
    Occupation = bleach.clean(request.form.get("Occupation", ""))
    CivilStatus = bleach.clean(request.form.get("Civil_Status", ""))
    Service = bleach.clean(request.form.get("Service", ""))
    appointment_date = bleach.clean(request.form.get("appointment_date", ""))
    q1 = bleach.clean(request.form.get("q1", ""))
    q2 = bleach.clean(request.form.get("q2", ""))
    q3 = bleach.clean(request.form.get("q3", ""))
    q4 = bleach.clean(request.form.get("q4", ""))
    q5 = bleach.clean(request.form.get("q5", ""))
    q6 = bleach.clean(request.form.get("q6", ""))
    q7 = bleach.clean(request.form.get("q7", ""))
    q9 = bleach.clean(request.form.get("q9", ""))
    q2_spec = bleach.clean(request.form.get("q2_spec", ""))
    q3_spec = bleach.clean(request.form.get("q3_spec", ""))
    q4_spec = bleach.clean(request.form.get("q4_spec", ""))
    q5_spec = bleach.clean(request.form.get("q5_spec", ""))
    q7_spec = bleach.clean(request.form.get("q7_spec", ""))
    q9_spec = bleach.clean(request.form.get("q9_spec", ""))
    w_preg = request.form.get("w_preg")
    w_nurse = request.form.get("w_nurse")
    w_pill = request.form.get("w_pill")
    try:
        db.collection("google_create_account").document(uid).collection(Appointment_cliets).add({
            "uid": uid,
            "email":email,
            "FirstName": FirstName,
            "MiddleName": MiddleName,
            "LastName": LastName,

            "HouseNo": HouseNo,
            "Street": Street,
            "Brgy": Brgy,
            "Municipality": Municipality,
            "City": City,

            "ContactNumber": ContactNumber,
            "Nationality": Nationality,
            "Religion": Religion,
            "Age": Age,
            "Sex": Sex,
            "Birthday": Birthday,
            "Occupation": Occupation,
            "CivilStatus": CivilStatus,

            "Service": Service,
            "appointment_date": appointment_date,

            "q1": q1,
            "q2": q2,
            "q3": q3,
            "q4": q4,
            "q5": q5,
            "q6": q6,
            "q7": q7,
            "q9": q9,

            "q2_spec": q2_spec,
            "q3_spec": q3_spec,
            "q4_spec": q4_spec,
            "q5_spec": q5_spec,
            "q7_spec": q7_spec,
            "q9_spec": q9_spec,

            "w_preg": w_preg,
            "w_nurse": w_nurse,
            "w_pill": w_pill
        })

        flash("Appointment successfully booked!", "success")

    except Exception as e:
        print(f"Error adding appointment: {e}")
        flash("There was an error booking your appointment.", "error")

    return redirect(url_for("index"))



@app.route("/booked_customer", methods=["POST"])
def bookedCustomer():
    uid = session.get('uid')
    email = session.get('email')
    FirstName = bleach.clean(request.form.get("First_Name", ""))
    MiddleName = bleach.clean(request.form.get("Middle_Name", ""))
    LastName = bleach.clean(request.form.get("Last_Name", ""))
    HouseNo = bleach.clean(request.form.get("House_No", ""))
    Street = bleach.clean(request.form.get("Street", ""))
    Brgy = bleach.clean(request.form.get("Brgy", ""))
    Municipality = bleach.clean(request.form.get("Municipality", ""))
    City = bleach.clean(request.form.get("City", ""))
    Nationality = bleach.clean(request.form.get("Nationality", ""))
    Religion = bleach.clean(request.form.get("Religion", ""))
    Age = bleach.clean(request.form.get("Age", ""))
    Sex = bleach.clean(request.form.get("Sex", ""))
    ContactNumber = bleach.clean(request.form.get("Contact_number", ""))
    Birthday = bleach.clean(request.form.get("Birthday", ""))
    Occupation = bleach.clean(request.form.get("Occupation", ""))
    CivilStatus = bleach.clean(request.form.get("Civil_Status", ""))
    Service = bleach.clean(request.form.get("Service", ""))
    appointment_date = bleach.clean(request.form.get("appointment_date", ""))
    q1 = bleach.clean(request.form.get("q1", ""))
    q2 = bleach.clean(request.form.get("q2", ""))
    q3 = bleach.clean(request.form.get("q3", ""))
    q4 = bleach.clean(request.form.get("q4", ""))
    q5 = bleach.clean(request.form.get("q5", ""))
    q6 = bleach.clean(request.form.get("q6", ""))
    q7 = bleach.clean(request.form.get("q7", ""))
    q9 = bleach.clean(request.form.get("q9", ""))
    q2_spec = bleach.clean(request.form.get("q2_spec", ""))
    q3_spec = bleach.clean(request.form.get("q3_spec", ""))
    q4_spec = bleach.clean(request.form.get("q4_spec", ""))
    q5_spec = bleach.clean(request.form.get("q5_spec", ""))
    q7_spec = bleach.clean(request.form.get("q7_spec", ""))
    q9_spec = bleach.clean(request.form.get("q9_spec", ""))
    w_preg = request.form.get("w_preg")
    w_nurse = request.form.get("w_nurse")
    w_pill = request.form.get("w_pill")
    try:
        db.collection(Account_clients).document(uid).collection(Appointment_cliets).add({
            "uid": uid,
            "email": email,
            "FirstName": FirstName,
            "MiddleName": MiddleName,
            "LastName": LastName,

            "HouseNo": HouseNo,
            "Street": Street,
            "Brgy": Brgy,
            "Municipality": Municipality,
            "City": City,

            "ContactNumber": ContactNumber,
            "Nationality": Nationality,
            "Religion": Religion,
            "Age": Age,
            "Sex": Sex,
            "Birthday": Birthday,
            "Occupation": Occupation,
            "CivilStatus": CivilStatus,

            "Service": Service,
            "appointment_date": appointment_date,

            "q1": q1,
            "q2": q2,
            "q3": q3,
            "q4": q4,
            "q5": q5,
            "q6": q6,
            "q7": q7,
            "q9": q9,

            "q2_spec": q2_spec,
            "q3_spec": q3_spec,
            "q4_spec": q4_spec,
            "q5_spec": q5_spec,
            "q7_spec": q7_spec,
            "q9_spec": q9_spec,

            "w_preg": w_preg,
            "w_nurse": w_nurse,
            "w_pill": w_pill
        })

        flash("Appointment successfully booked!", "success")

    except Exception as e:
        print(f"Error adding appointment: {e}")
        flash("There was an error booking your appointment.", "error")

    return redirect(url_for("index"))


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'jayr.bonitillo.ui@phinmaed.com'
app.config['MAIL_PASSWORD'] = 'htal wzrv wyai rgsi'
app.config['MAIL_DEFAULT_SENDER'] = 'jayr.bonitillo.ui@phinmaed.com'

mail = Mail(app)


def send_email(recipient, fullname, status):
    msg = Message(
        subject=f"Appointment {status}",
        recipients=[recipient]
    )

    msg.body = f"""
Hello {fullname},

Your appointment has been {status}.

Thank you,
Dental Clinic
"""

    mail.send(msg)



def send_email(recipient, fullname, status):

    msg = Message(
        subject=f"Appointment {status.capitalize()}",
        recipients=[recipient]
    )

    if status == "accepted":
        msg.body = f"""
Hello {fullname},

Good news!

Your dental appointment has been ACCEPTED.

Please arrive at the clinic on your scheduled date and time.

Thank you,
Dental Clinic
"""

    elif status == "declined":
        msg.body = f"""
Hello {fullname},

We regret to inform you that your appointment request has been declined.

Please log in to the Dental Clinic system and schedule another appointment at your convenience.

Thank you for your understanding.

Dental Clinic
"""

    mail.send(msg)


@app.route("/approve", methods=["POST"])
def approve():

    uid = request.form.get("user_id")
    DentistName = bleach.clean(request.form.get("dentist_name", ""))
    appointment_id = request.form.get("appointment_id")
    action = request.form.get("action")
    email = session.get("email")

    data = {
        "status": action,
        "Patient_unq_id": appointment_id,
        "uid": uid,
        "email": email,
        "DentistName": DentistName,
        "FirstName": request.form.get("firstname"),
        "MiddleName": request.form.get("middlename"),
        "LastName": request.form.get("lastname"),

        "HouseNo": request.form.get("houseno"),
        "Street": request.form.get("street"),
        "Brgy": request.form.get("brgy"),
        "Municipality": request.form.get("municipality"),
        "City": request.form.get("city"),

        "ContactNumber": request.form.get("contactnumber"),
        "Nationality": request.form.get("nationality"),
        "Religion": request.form.get("religion"),

        "Age": request.form.get("age"),
        "Sex": request.form.get("sex"),
        "Birthday": request.form.get("birthday"),

        "Occupation": request.form.get("occupation"),
        "CivilStatus": request.form.get("civilstatus"),
        "Service": request.form.get("service"),
    }

    # Find user
    if db.collection("google_create_account").document(uid).get().exists:
        main_collection = "google_create_account"

    elif db.collection(Account_clients).document(uid).get().exists:
        main_collection = Account_clients

    else:
        return "User not found", 404

    user_ref = db.collection(main_collection).document(uid)

    # Get email
    user_doc = user_ref.get()
    patient_email = None

    if user_doc.exists:
        patient_email = user_doc.to_dict().get("email")

    fullname = f"{data['FirstName']} {data['LastName']}"

    # ==========================
    # ACCEPT
    # ==========================
    if action == "accept":

        user_ref.collection("Approve").document(appointment_id).set(data)

        user_ref.collection(Appointment_cliets).document(appointment_id).delete()

        if patient_email:
            send_email(patient_email, fullname, "accepted")

        return "Appointment accepted"

    # ==========================
    # DECLINE
    # ==========================
    elif action == "decline":

        # Delete appointment only
        user_ref.collection(Appointment_cliets).document(appointment_id).delete()

        if patient_email:
            send_email(patient_email, fullname, "declined")

        return "Appointment declined"

    return "Invalid action", 400


@app.route("/test-email")
def test_email():

    msg = Message(
        subject="SMTP Test",
        recipients=["jayr.bonitillo.ui@phinmaed.com"]
    )

    msg.body = "SMTP is working!"

    mail.send(msg)

    return "Email sent!"






@app.route("/patient-profile")
def p_profile():
    name = session.get('name')
    email = session.get('email')
    user_data = {}

    # 1. Try to find in manual accounts
    user_query = db.collection(Account_clients).where("username", "==", session.get('username')).get()
    
    # 2. If not found/empty, try Google accounts
    if not user_query:
        user_query = db.collection("google_create_account").where("email", "==", email).get()

    if user_query:
        user_data = user_query[0].to_dict()
        user_data['id'] = user_query[0].id # Store ID for updates
    
    return render_template("patient-profile.html", name=session.get('name'), user=user_data)






#---------------------------------------------------
#Admin routes
#---------------------------------------------------



@app.route("/admin_dashboard")
def adminDashboard():


    # APPOINTMENTS COLLECTION

    docs = db.collection_group("appointments").get()

    appointment_list = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["user_uid"] = doc.reference.parent.parent.id
        data["source"] = "appointment"
        appointment_list.append(data)

    # APPROVE SUBCOLLECTION

    approve_docs = db.collection_group("Approve").get()

    approve_list = []

    for doc in approve_docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["appointment_id"] = doc.reference.parent.parent.id
        data["user_uid"] = doc.reference.parent.parent.parent.id
        data["source"] = "approve"
        approve_list.append(data)

    # ACCOUNTS

    google_docs = db.collection("google_create_account").stream()
    manual_docs = db.collection(Account_clients).stream()

    accounts = []

    # GOOGLE ACCOUNTS

    for doc in google_docs:

        data = doc.to_dict()

        data["uid"] = doc.id
        data["account_type"] = "Google"
        data["source"] = "account"

        first = data.get("firstname") or data.get("first_name") or ""
        last = data.get("lastname") or data.get("last_name") or ""

        data["first_name"] = first
        data["last_name"] = last
        data["full_name"] = data.get("name") or f"{first} {last}".strip()

        # DONE PROCEDURE

        done_doc = (
            db.collection("google_create_account")
            .document(doc.id)
            .collection("Done_procedure")
            .document(doc.id)
            .get()
        )

        data["Done_procedure"] = (
            done_doc.to_dict() if done_doc.exists else {}
        )

        accounts.append(data)


    # MANUAL ACCOUNTS

    for doc in manual_docs:

        data = doc.to_dict()

        data["uid"] = doc.id
        data["account_type"] = "Manual"
        data["source"] = "account"

        first = data.get("firstname") or ""
        last = data.get("lastname") or ""

        data["first_name"] = first
        data["last_name"] = last
        data["full_name"] = f"{first} {last}".strip()

        # DONE PROCEDURE
  
        done_doc = (
            db.collection(Account_clients)
            .document(doc.id)
            .collection("Done_procedure")
            .document(doc.id)
            .get()
        )

        data["Done_procedure"] = (
            done_doc.to_dict() if done_doc.exists else {}
        )

        accounts.append(data)

    # =========================
    # SEND ALL TO TEMPLATE
    # =========================
    return render_template(
        "admin_dashboard.html",
        Appointment_clients=appointment_list,
        Approve=approve_list,
        accounts=accounts,
        
    )


@app.route("/get_patient/<uid>")
def get_patient(uid):

    # =========================
    # TRY GOOGLE ACCOUNT FIRST
    # =========================
    doc_ref = db.collection("google_create_account").document(uid)
    doc = doc_ref.get()

    account_type = "Google"

    # =========================
    # TRY MANUAL ACCOUNT
    # =========================
    if not doc.exists:
        doc_ref = db.collection(Account_clients).document(uid)
        doc = doc_ref.get()
        account_type = "Manual"

    if not doc.exists:
        return {"error": "Patient not found"}

    # =========================
    # ACCOUNT INFORMATION
    # =========================
    data = doc.to_dict()

    data["uid"] = doc.id
    data["account_type"] = account_type

    first = data.get("firstname") or data.get("first_name") or ""
    last = data.get("lastname") or data.get("last_name") or ""

    data["first_name"] = first
    data["last_name"] = last
    data["full_name"] = data.get("name") or f"{first} {last}".strip()

    # =========================
    # LOAD DONE PROCEDURE
    # =========================
    visit_history = []

    done_docs = doc_ref.collection("Done_procedure").stream()

    for done in done_docs:

        done_data = done.to_dict()

        procedures = done_data.get("procedures", [])

        for p in procedures:
            visit_history.append({
                "dentist": p.get("dentist", ""),
                "uid": p.get("uid", ""),
                "date": p.get("date", ""),
                "procedure": p.get("procedure", ""),
                "paid": p.get("paid", 0),
                "balance": p.get("balance", 0),
                "tooth": p.get("tooth", ""),
                "value": p.get("value", 0),
                "status": p.get("status", ""),   # <-- ADD THIS
                "next_appointment": p.get("next_appointment", ""),
                "status": p.get("status", ""),
                "medicine": p.get("medicine", "")
            })

    data["Done_procedure"] = visit_history

    return data

@app.route("/admin_login", methods=["GET", "POST"])  # ← Add methods=["GET", "POST"]
def adminLogin():
    if request.method == "POST":
        email = bleach.clean(request.form.get("email", "").strip().lower())
        password = request.form.get("password", "")
        
        # Query your admins collection
        admin_query = db.collection("admins").where("email", "==", email).get()
        
        if admin_query and admin_query[0].exists:
            admin_data = admin_query[0].to_dict()
            if admin_data.get("is_active", True) and check_password_hash(admin_data["password_hash"], password):
                # Set admin session
                session['admin_logged_in'] = True
                session['admin_email'] = email
                session['admin_name'] = admin_data.get("name", "Admin")
                flash(f"Welcome back, Dr. {admin_data.get('name')}!", "success")
                return redirect(url_for("adminDashboard"))
        
        flash("Invalid credentials. Please try again.", "error")
        return redirect(url_for("adminLogin"))
    
    # GET request - show login page
    if session.get('admin_logged_in'):
        return redirect(url_for("adminDashboard"))
    
    return render_template("admin_login.html")  # ✅ This now works!


from flask import abort, render_template

SERVICES_DATA = {
    "cleaning": {
        "title": "Oral Prophylaxis (Cleaning)",
        "short_desc": "Keep your gums healthy and your smile bright.",
        "full_desc": "Oral prophylaxis is a thorough dental cleaning procedure performed by our professionals. It involves the removal of dental plaque and tartar to prevent cavities, gingivitis, and gum disease.",
        "benefits": [
            "Prevents tooth decay and gum disease",
            "Removes stubborn stains for a whiter smile",
            "Eliminates bad breath",
            "Early detection of dental issues"
        ],
        "image": "cleaning.jpg"
    },
    "root-canal": {
        "title": "Root Canal Treatment",
        "short_desc": "Save your natural tooth and relieve severe pain.",
        "full_desc": "A root canal is a treatment to repair and save a badly damaged or infected tooth instead of removing it. The procedure involves removing the damaged area of the tooth (the pulp) and cleaning and disinfecting it.",
        "benefits": [
            "Stops the spread of infection",
            "Relieves severe toothache",
            "Preserves your natural tooth structure",
            "Highly successful and long-lasting"
        ],
        "image": "root-canal.jpg"
    },
    "consultation": {
        "title": "Dental Consultation",
        "short_desc": "Start your journey to a healthier smile with a professional check-up.",
        "full_desc": "A comprehensive dental examination where our dentists assess your overall oral health. This includes checking for cavities, gum disease, and oral cancer, followed by a personalized treatment plan.",
        "benefits": [
            "Comprehensive oral health assessment",
            "Personalized treatment planning",
            "Professional advice on oral hygiene",
            "Early detection of potential dental problems"
        ],
        "image": "consultation.jpg"
    },
    "pasta": {
        "title": "Tooth Restoration (Pasta)",
        "short_desc": "Restore the strength and beauty of your teeth.",
        "full_desc": "Commonly known as 'Pasta,' this procedure uses tooth-colored composite resins to fill cavities or repair chipped teeth, restoring their natural function and appearance.",
        "benefits": [
            "Matches your natural tooth color",
            "Prevents further tooth decay",
            "Restores tooth strength and function",
            "Quick and minimally invasive procedure"
        ],
        "image": "pasta.jpg"
    },
    "extraction": {
        "title": "Tooth Extraction",
        "short_desc": "Safe and gentle removal of problematic teeth.",
        "full_desc": "When a tooth is too damaged to be saved by a filling or crown, a professional extraction is performed. We ensure the process is as comfortable and pain-free as possible.",
        "benefits": [
            "Eliminates severe dental pain",
            "Prevents the spread of infection to other teeth",
            "Prepares for orthodontic or denture treatment",
            "Fast relief from overcrowded teeth"
        ],
        "image": "extraction.jpg"
    },
    "dentures": {
        "title": "Dentures",
        "short_desc": "Regain your smile and confidence with custom-fit dentures.",
        "full_desc": "Custom-made removable replacements for missing teeth and surrounding tissues. We offer both full and partial dentures designed to look natural and fit comfortably.",
        "benefits": [
            "Restores ability to chew and speak clearly",
            "Supports facial muscles for a younger look",
            "Customized for a natural appearance",
            "Cost-effective solution for missing teeth"
        ],
        "image": "dentures.jpg"
    },
    "crowns-bridges": {
        "title": "Crowns and Bridges",
        "short_desc": "Permanent solutions for broken or missing teeth.",
        "full_desc": "Dental crowns cover a damaged tooth to restore its shape, while bridges fill the gap created by one or more missing teeth, anchored by healthy teeth on either side.",
        "benefits": [
            "Long-lasting and durable restoration",
            "Restores the natural shape and size of teeth",
            "Prevents remaining teeth from shifting",
            "Enhances overall smile aesthetics"
        ],
        "image": "crowns-bridges.jpg"
    },
    "whitening": {
        "title": "Teeth Whitening",
        "short_desc": "Brighten your smile by several shades in one visit.",
        "full_desc": "A professional cosmetic procedure that uses high-quality whitening agents to remove deep-seated stains caused by coffee, tea, or aging, giving you a radiant smile.",
        "benefits": [
            "Immediate and noticeable results",
            "Safe and professionally supervised",
            "Boosts self-confidence",
            "Removes tough stains that toothpaste can't"
        ],
        "image": "whitening.jpg"
    },
    "fluoride": {
        "title": "Fluoride Treatment",
        "short_desc": "Strengthen your tooth enamel against decay.",
        "full_desc": "A quick preventive treatment where a high concentration of fluoride is applied to the teeth. This mineral helps rebuild weakened tooth enamel and reverses early signs of cavities.",
        "benefits": [
            "Significantly reduces risk of cavities",
            "Strengthens tooth enamel",
            "Especially effective for children's developing teeth",
            "Protects teeth from acid and bacteria"
        ],
        "image": "fluoride.jpg"
    },
    "sealant": {
        "title": "Pit and Fissure Sealant",
        "short_desc": "An invisible shield for your molars.",
        "full_desc": "A thin, protective coating applied to the chewing surfaces of the back teeth (molars). It seals the deep grooves where food and bacteria often get trapped.",
        "benefits": [
            "Highly effective at preventing molar cavities",
            "Painless and non-invasive application",
            "Long-lasting protection for many years",
            "Ideal for children and teenagers"
        ],
        "image": "sealant.jpg"
    },
    "wisdom-tooth": {
        "title": "Wisdom Teeth Removal",
        "short_desc": "Prevent pain and crowding caused by impacted wisdom teeth.",
        "full_desc": "A surgical procedure to remove one or more wisdom teeth—the four permanent adult teeth located at the back corners of your mouth—that don't have enough room to grow.",
        "benefits": [
            "Prevents overcrowding and shifting of teeth",
            "Relieves jaw pain and gum swelling",
            "Reduces risk of infection and cysts",
            "Protects adjacent healthy molars"
        ],
        "image": "wisdom-tooth.jpg"
    },
    "xray": {
        "title": "Periapical X-ray",
        "short_desc": "Detailed imaging to see what's happening beneath the surface.",
        "full_desc": "A focused X-ray that shows the entire tooth, from the crown to the end of the root where it anchors into the jaw. Essential for detecting abscesses and deep-seated issues.",
        "benefits": [
            "Accurate diagnosis of root-level problems",
            "Detects infections and cysts early",
            "Shows the exact position of impacted teeth",
            "Critical for successful root canal planning"
        ],
        "image": "xray.jpg"
    }
}

@app.route('/services/<service_id>')
def service_detail(service_id):
    # Check if the requested service exists in our dictionary
    service = SERVICES_DATA.get(service_id)
    
    if not service:
        abort(404) # Show a 404 page if they type a wrong URL
        
    return render_template('service.html', service=service)

@app.route("/location")
def dental_location():
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("location.html",name=name, email=email)

@app.route("/prac")
def prac():
    return render_template("prac.html")

@app.route("/medical_records")
def medical_records():
    return render_template("medical_records.html")




def safe_float(value):
    try:
        return float(value)
    except:
        return 0



import os
import base64
from datetime import datetime
from flask import request, jsonify
from firebase_admin import firestore


app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB


@app.route("/save_dental_record", methods=["POST"])
def save_dental_record():

    try:
        uid = request.form.get("uid")

        if not uid:
            return jsonify({
                "success": False,
                "message": "UID is required"
            }), 400

        if db.collection("google_create_account").document(uid).get().exists:
            main_collection = "google_create_account"

        elif db.collection(Account_clients).document(uid).get().exists:
            main_collection = Account_clients

        else:
            return jsonify({
                "success": False,
                "message": "User not found"
            }), 404

        user_ref = db.collection(main_collection).document(uid)

        # =========================
        # DENTAL CHART JSON
        # =========================
        dental_chart = {}

        for key in request.form:
            if key.startswith("tooth_"):
                dental_chart[key] = request.form.get(key)

        image_url = ""

        image_file = request.files.get("dental_chart_image")

        if image_file:
            try:
                save_folder = os.path.join("static", "dental_charts")
                os.makedirs(save_folder, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{uid}_{timestamp}.jpg"
                filepath = os.path.join(save_folder, filename)

                image_file.save(filepath)

                image_url = f"/static/dental_charts/{filename}"

            except Exception as img_error:
                print("IMAGE SAVE ERROR:", img_error)

        # =========================
        # TREATMENT TABLE
        # =========================
        dates = request.form.getlist("date[]")
        teeth = request.form.getlist("tooth[]")
        procedures = request.form.getlist("procedure[]")
        dentists = request.form.getlist("dentist[]")
        values = request.form.getlist("value[]")
        paids = request.form.getlist("paid[]")
        balances = request.form.getlist("balance[]")
        next_appts = request.form.getlist("next_appointment[]")
        medicines = request.form.getlist("medicine[]")
        statuses = request.form.getlist("status[]")

        length = min(
            len(dates),
            len(teeth),
            len(procedures),
            len(dentists),
            len(values),
            len(paids),
            len(balances),
            len(next_appts),
            len(medicines),
            len(statuses)
        )

        done_procedures = []

        for i in range(length):

            if not procedures[i] and not teeth[i]:
                continue

            done_procedures.append({
                "date": dates[i],
                "tooth": teeth[i],
                "procedure": procedures[i],
                "dentist": dentists[i],
                "value": safe_float(values[i]),
                "paid": safe_float(paids[i]),
                "balance": safe_float(balances[i]),
                "next_appointment": next_appts[i],
                "medicine": medicines[i],
                "status": statuses[i]
            })

        # =========================
        # SAVE TO FIRESTORE
        # =========================
        user_ref.collection("Done_procedure").add({
            "uid": uid,
            "chart": dental_chart,
            "chart_image": image_url,
            "procedures": done_procedures,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

        # =========================
        # DELETE APPROVED RECORD
        # =========================
        Patient_unq_id = request.form.get("Patient_unq_id")

        print("Received Patient_unq_id:", Patient_unq_id)

        if Patient_unq_id:
            try:
                user_ref.collection("Approve").document(Patient_unq_id).delete()
                print("Deleted Approve document:", Patient_unq_id)

            except Exception as del_error:
                print("DELETE APPROVE ERROR:", del_error)

        return jsonify({
            "success": True,
            "message": "Dental record saved successfully",
            "chart_image": image_url
        })

    except Exception as e:
        print("ERROR:", e)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500



@app.route("/get_treatment_info/<uid>")
def get_treatment_info(uid):

    # Find the patient
    if db.collection("google_create_account").document(uid).get().exists:
        user_ref = db.collection("google_create_account").document(uid)

    elif db.collection(Account_clients).document(uid).get().exists:
        user_ref = db.collection(Account_clients).document(uid)

    else:
        return jsonify({
            "success": False,
            "message": "Patient not found"
        }), 404

    procedures = []

    # Read all Done_procedure documents
    for doc in user_ref.collection("Done_procedure").stream():

        data = doc.to_dict()

        for p in data.get("procedures", []):
            procedures.append({
                "dentist": p.get("dentist", ""),
                "medicine": p.get("medicine", ""),
                "date": p.get("date", ""),
                "procedure": p.get("procedure", ""),
                "paid": p.get("paid", 0),
                "next_appointment": p.get("next_appointment", ""),
                "status": p.get("status", ""),
                "balance": p.get("balance", 0),
                "value": p.get("value", 0),
                "tooth": p.get("tooth", "")
            })

    return jsonify({
        "success": True,
        "procedures": procedures
    })


@app.route("/get_approve/<uid>")
def get_approve(uid):
    try:
        approve_docs = (
            db.collection("google_create_account")
            .document(uid)
            .collection("Approve")
            .stream()
        )

        approve_list = []

        for doc in approve_docs:
            data = doc.to_dict()
            data["id"] = doc.id
            approve_list.append(data)

        return jsonify(approve_list)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


    
if __name__ == "__main__":
    print("🦷 Capizonda Dental Clinic Server Starting...")
    app.run(debug=True, port=5000)



# pip install google-auth firebase-admin
# pip install flask firebase-admin google-auth
# pip install firebase-admin
# pip install google-auth
# pip install flask
#pip install --upgrade google-auth google-api-core


#✅ Correct way to think about it
#🔹 1. .strip() → use for almost all text inputs
#Login
#Signup
#Forms
#Search fields

#🔹 2. bleach.clean() → use only when displaying user content in HTML
#NOT for storing or comparing data.
#Use it for things like:
#Comments
#Blog posts
#User bios
#Chat messages

#Argon2 for security

#CRUD


#Update code in github
#git status
#git add .
#git commit -m "Describe your changes here"
#git push origin main

#sa unto
#pip install flask requests

#new~
#added