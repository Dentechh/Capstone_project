from flask import Flask, abort, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, UTC
import bleach
from flask_mail import Mail, Message
from flask import jsonify
import sys
import os
import threading
import smtplib
from email.message import EmailMessage
import requests
import base64
from datetime import timedelta
import random
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


class BaseFlaskApp:
    """Base class demonstrating Inheritance"""
    def __init__(self):
        self._app = None
        self._db = None
        self._mail = None

    @property
    def app(self):
        return self._app

    @property
    def db(self):
        return self._db

    @property
    def mail(self):
        return self._mail

    def render_page(self, template, **kwargs):
        return self._app.render_template(template, **kwargs)


class DentalClinicApp(BaseFlaskApp):
    """
    4 Pillars of OOP:
    1. Encapsulation - State and behavior in one class
    2. Abstraction - Setup hidden in _setup_* methods
    3. Inheritance - Inherits from BaseFlaskApp
    4. Polymorphism - Overridable methods
    """
    
    def __init__(self):
        super().__init__()
        self._setup_app()
        self._setup_config()
        self._setup_mail()
        self._setup_firebase()
        self._setup_constants()
        self._setup_paymongo()
        self._setup_session()
        self._register_routes()
        print("🦷 Capizonda Dental Clinic Initialized")

    def _setup_app(self):
        self._app = Flask(__name__)

    def _setup_config(self):
        self.app.config["MAIL_SERVER"] = "smtp.gmail.com"
        self.app.config["MAIL_PORT"] = 587
        self.app.config["MAIL_USE_TLS"] = True
        self.app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
        self.app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
        self.app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")
        self.app.config["MAIL_TIMEOUT"] = 10
        self.app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)
        self.app.permanent_session_lifetime = timedelta(minutes=10)
        self.app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

    def _setup_mail(self):
        self._mail = Mail(self.app)
        print("MAIL USER:", self.app.config["MAIL_USERNAME"])
        print("MAIL PASS:", "Loaded" if self.app.config["MAIL_PASSWORD"] else "Missing")

    def _setup_firebase(self):
        basedir = os.path.abspath(os.path.dirname(__file__))
        key_path = os.path.join(basedir, "dentech_key.json")
        if not firebase_admin._apps:
            try:
                if not os.path.exists(key_path):
                    raise FileNotFoundError(f"Firebase key not found at: {key_path}")
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
                self._db = firestore.client()
                print("✅ Firebase initialized successfully")
            except Exception as e:
                print("❌ Firebase initialization failed:", e)
                self._db = None
        else:
            self._db = firestore.client()
            print("♻️ Firebase already initialized")

    def _setup_constants(self):
        self.Customer_Account = "Customer_Account"
        self.Appointment_cliets = "appointments"
        self.Doc_Patients = "Patients"
        self.CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        self.firebase_api_key = "AIzaSyCpt9dnVFDvDNfnX4jQyfxxtYfnR_duUEE"
        if not self.CLIENT_ID:
            print("⚠️  GOOGLE_CLIENT_ID is missing; Google login will be disabled until it's set in .env")
        self.SERVICES_DATA = {
            "cleaning": {"title": "Oral Prophylaxis (Cleaning)", "short_desc": "Keep your gums healthy and your smile bright.", "full_desc": "Oral prophylaxis is a thorough dental cleaning procedure performed by our professionals. It involves the removal of dental plaque and tartar to prevent cavities, gingivitis, and gum disease.", "benefits": ["Prevents tooth decay and gum disease", "Removes stubborn stains for a whiter smile", "Eliminates bad breath", "Early detection of dental issues"], "image": "cleaning.jpg"},
            "root-canal": {"title": "Root Canal Treatment", "short_desc": "Save your natural tooth and relieve severe pain.", "full_desc": "A root canal is a treatment to repair and save a badly damaged or infected tooth instead of removing it. The procedure involves removing the damaged area of the tooth (the pulp) and cleaning and disinfecting it.", "benefits": ["Stops the spread of infection", "Relieves severe toothache", "Preserves your natural tooth structure", "Highly successful and long-lasting"], "image": "root-canal.jpg"},
            "consultation": {"title": "Dental Consultation", "short_desc": "Start your journey to a healthier smile with a professional check-up.", "full_desc": "A comprehensive dental examination where our dentists assess your overall oral health. This includes checking for cavities, gum disease, and oral cancer, followed by a personalized treatment plan.", "benefits": ["Comprehensive oral health assessment", "Personalized treatment planning", "Professional advice on oral hygiene", "Early detection of potential dental problems"], "image": "consultation.jpg"},
            "pasta": {"title": "Tooth Restoration (Pasta)", "short_desc": "Restore the strength and beauty of your teeth.", "full_desc": "Commonly known as 'Pasta,' this procedure uses tooth-colored composite resins to fill cavities or repair chipped teeth, restoring their natural function and appearance.", "benefits": ["Matches your natural tooth color", "Prevents further tooth decay", "Restores tooth strength and function", "Quick and minimally invasive procedure"], "image": "pasta.jpg"},
            "extraction": {"title": "Tooth Extraction", "short_desc": "Safe and gentle removal of problematic teeth.", "full_desc": "When a tooth is too damaged to be saved by a filling or crown, a professional extraction is performed. We ensure the process is as comfortable and pain-free as possible.", "benefits": ["Eliminates severe dental pain", "Prevents the spread of infection to other teeth", "Prepares for orthodontic or denture treatment", "Fast relief from overcrowded teeth"], "image": "extraction.jpg"},
            "dentures": {"title": "Dentures", "short_desc": "Regain your smile and confidence with custom-fit dentures.", "full_desc": "Custom-made removable replacements for missing teeth and surrounding tissues. We offer both full and partial dentures designed to look natural and fit comfortably.", "benefits": ["Restores ability to chew and speak clearly", "Supports facial muscles for a younger look", "Customized for a natural appearance", "Cost-effective solution for missing teeth"], "image": "dentures.jpg"},
            "crowns-bridges": {"title": "Crowns and Bridges", "short_desc": "Permanent solutions for broken or missing teeth.", "full_desc": "Dental crowns cover a damaged tooth to restore its shape, while bridges fill the gap created by one or more missing teeth, anchored by healthy teeth on either side.", "benefits": ["Long-lasting and durable restoration", "Restores the natural shape and size of teeth", "Prevents remaining teeth from shifting", "Enhances overall smile aesthetics"], "image": "crowns-bridges.jpg"},
            "whitening": {"title": "Teeth Whitening", "short_desc": "Brighten your smile by several shades in one visit.", "full_desc": "A professional cosmetic procedure that uses high-quality whitening agents to remove deep-seated stains caused by coffee, tea, or aging, giving you a radiant smile.", "benefits": ["Immediate and noticeable results", "Safe and professionally supervised", "Boosts self-confidence", "Removes tough stains that toothpaste can't"], "image": "whitening.jpg"},
            "fluoride": {"title": "Fluoride Treatment", "short_desc": "Strengthen your tooth enamel against decay.", "full_desc": "A quick preventive treatment where a high concentration of fluoride is applied to the teeth. This mineral helps rebuild weakened tooth enamel and reverses early signs of cavities.", "benefits": ["Significantly reduces risk of cavities", "Strengthens tooth enamel", "Especially effective for children's developing teeth", "Protects teeth from acid and bacteria"], "image": "fluoride.jpg"},
            "sealant": {"title": "Pit and Fissure Sealant", "short_desc": "An invisible shield for your molars.", "full_desc": "A thin, protective coating applied to the chewing surfaces of the back teeth (molars). It seals the deep grooves where food and bacteria often get trapped.", "benefits": ["Highly effective at preventing molar cavities", "Painless and non-invasive application", "Long-lasting protection for many years", "Ideal for children and teenagers"], "image": "sealant.jpg"},
            "wisdom-tooth": {"title": "Wisdom Teeth Removal", "short_desc": "Prevent pain and crowding caused by impacted wisdom teeth.", "full_desc": "A surgical procedure to remove one or more wisdom teeth—the four permanent adult teeth located at the back corners of your mouth—that don't have enough room to grow.", "benefits": ["Prevents overcrowding and shifting of teeth", "Relieves jaw pain and gum swelling", "Reduces risk of infection and cysts", "Protects adjacent healthy molars"], "image": "wisdom-tooth.jpg"},
            "xray": {"title": "Periapical X-ray", "short_desc": "Detailed imaging to see what's happening beneath the surface.", "full_desc": "A focused X-ray that shows the entire tooth, from the crown to the end of the root where it anchors into the jaw. Essential for detecting abscesses and deep-seated issues.", "benefits": ["Accurate diagnosis of root-level problems", "Detects infections and cysts early", "Shows the exact position of impacted teeth", "Critical for successful root canal planning"], "image": "xray.jpg"}
        }
        if not self.CLIENT_ID:
            print("⚠️  GOOGLE_CLIENT_ID is missing; Google login will be disabled until it's set in .env")

    def _setup_paymongo(self):
        self.pay_mongo_secret_key = "sk_test_CYiQMSXw2cHHhtF564gZ3mMx"
        self.pay_mongo_public_key = "pk_test_m4rG4iv4L9S5MC8d4dxq39ko"

    def _setup_session(self):
        @self.app.before_request
        def refresh_session():
            session.permanent = True
            session.modified = True

    def _register_routes(self):
        """Polymorphism: Register all routes"""
        pass


    def require_firebase(self):
        if db is None:
            raise RuntimeError("Firebase is not initialized. Check dentech_key.json")
    

    def update_payment_status(self, patient_uid, procedure):
        try:
            patient_collection = None
            if self.db.collection(self.Customer_Account).document(patient_uid).get().exists:
                patient_collection = self.Customer_Account
            elif self.db.collection(self.Customer_Account).document(patient_uid).get().exists:
                patient_collection = self.Customer_Account
    
            if patient_collection:
                user_ref = self.db.collection(patient_collection).document(patient_uid)
                done_procedures = user_ref.collection("Done_procedure").stream()
    
                updated = False
                for proc_doc in done_procedures:
                    if updated:
                        break
    
                    proc_data = proc_doc.to_dict()
                    procedures = proc_data.get("procedures", [])
    
                    for p in procedures:
                        if p.get("procedure") == procedure and p.get("status") != "Paid":
                            p["status"] = "Paid"
                            p["paid"] = p.get("balance", p.get("paid", 0))
                            p["balance"] = 0
                            proc_doc.reference.update({"procedures": procedures})
                            updated = True
                            break
    
        except Exception as e:
            print(f"Error updating payment status: {e}")
    
    

    def payment_success(self):
        checkout_session_id = request.args.get("checkout_session_id")
        patient_uid = request.args.get("uid", "")
        procedure = request.args.get("procedure", "")
    
        if checkout_session_id:
            try:
                auth = base64.b64encode(f"{self.pay_mongo_secret_key}:".encode()).decode()
                headers = {
                    "accept": "application/json",
                    "authorization": f"Basic {auth}"
                }
    
                r = requests.get(
                    f"https://api.paymongo.com/v1/checkout_sessions/{checkout_session_id}",
                    headers=headers,
                    timeout=30
                )
    
                result = r.json()
                session_data = result.get("data", {}).get("attributes", {})
                payment_status = session_data.get("payment_status", "")
    
                if payment_status == "paid":
                    self.update_payment_status(patient_uid, procedure)
                    flash("Payment successful! Your appointment is now confirmed.", "success")
                else:
                    flash("Payment received and is being processed. Your status will update shortly.", "info")
    
            except Exception as e:
                print(f"Error verifying payment: {e}")
                flash("Could not verify payment status. Please contact support.", "error")
    
        return redirect(url_for("index"))
    
    

    def payment_cancel(self):
        flash("Payment was cancelled or expired.", "error")
        return redirect(url_for("index"))
    
    

    def paymongo_webhook(self):
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
                    self.update_payment_status(patient_uid, procedure)
    
        except Exception as e:
            print(f"Webhook error: {e}")
    
        return "", 200
    
    

    def create_gcash_payment(self):
        try:
            data = request.json
            amount = int(float(data.get("amount", 0)) * 100)
            procedure = data.get("procedure", "")
            patient_uid = data.get("uid", "")
    
            patient_email = session.get("email", "patient@example.com")
            patient_name = session.get("name", "Dental Patient")
    
            base_url = request.host_url.rstrip('/')
            success_url = f"{base_url}/payment-success?uid={patient_uid}&procedure={procedure}"
            cancel_url = f"{base_url}/payment-cancel"
    
            auth = base64.b64encode(f"{self.pay_mongo_secret_key}:".encode()).decode()
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Basic {auth}"
            }
    
            payload = {
                "data": {
                    "attributes": {
                        "billing": {
                            "name": patient_name,
                            "email": patient_email
                        },
                        "line_items": [{
                            "currency": "PHP",
                            "amount": amount,
                            "name": procedure,
                            "quantity": 1
                        }],
                        "payment_method_types": ["gcash"],
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                        "metadata": {
                            "patient_uid": patient_uid,
                            "procedure": procedure
                        }
                    }
                }
            }
    
            r = requests.post(
                "https://api.paymongo.com/v1/checkout_sessions",
                headers=headers,
                json=payload,
                timeout=30
            )
    
            result = r.json()
    
            if "data" in result:
                return {
                    "checkout_url": result["data"]["attributes"]["checkout_url"]
                }
            else:
                return {
                    "error": result.get("error", {}).get("message", "Failed to create payment session")
                }
    
        except Exception as e:
            return {"error": str(e)}
    
    

    def refresh_session(self):
        session.permanent = True
        session.modified = True
    

    def index(self):
        uid = session.get('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
    
        return render_template("index.html",uid=uid,name=name,email=email)
    
    
    

    def google_index(self):
        uid = session.get ('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        return render_template("google_index.html",uid = uid, name=name, email=email)
    
    

    def login_manual(self):
        email = bleach.clean(request.form.get("email", "").strip())
        password = request.form.get("Password", "")

        # Verify credentials with Firebase Auth REST API
        resp = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + self.firebase_api_key,
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True
            }
        )

        if resp.status_code != 200:
            flash("Incorrect email or password.", "error")
            return redirect(url_for("index"))

        data = resp.json()

        # Get the ID token returned after successful sign-in
        id_token = data["idToken"]

        # Look up the user's account information
        lookup_resp = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={self.firebase_api_key}",
            json={
                "idToken": id_token
            }
        )

        if lookup_resp.status_code != 200:
            flash("Unable to verify your account.", "error")
            return redirect(url_for("index"))

        lookup_data = lookup_resp.json()

        verified = lookup_data["users"][0]["emailVerified"]

        if not verified:
            flash("Please verify your email first.", "error")
            return redirect(url_for("index"))

        uid = lookup_data["users"][0]["localId"]

        # Get user data from Firestore
        user_doc = self.db.collection(self.Customer_Account).document(uid).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}

        session["name"] = user_data.get("firstname", "")
        session["email"] = email
        session["uid"] = uid

        flash(f"Welcome back, {user_data.get('firstname', '')}!", "success")
        return redirect(url_for("index"))

    


    def login_g_auth(self):
        token = request.form["token"]
        try:
            google_account = id_token.verify_oauth2_token(token, google_requests.Request(), self.CLIENT_ID)
            
            # Store user info in session
            session['uid'] = google_account["sub"]
            session['email'] = google_account["email"]
            session['name'] = google_account.get("name", "User")
    
            self.db.collection(self.Customer_Account).document(session['uid']).set({
                "uid": session['uid'],
                "email": session['email'],
                "name": session['name'],
                "provider": "google",
                "last_login": datetime.now(UTC).isoformat()
            }, merge=True)
    
            return redirect(url_for("google_index")) 
        except ValueError:
            return render_template("error.html", message="Invalid Google token")
    
    

    def sign_up(self):
        try:
            firstname = bleach.clean(request.form["FirstName"].strip())
            lastname = bleach.clean(request.form["LastName"].strip())
            email = bleach.clean(request.form["UserName"].strip())
            contact_number = bleach.clean(request.form["MobileNumber"].strip())
            password = request.form.get("Password", "")

            # Create Firebase Auth user server-side
            try:
                user = auth.create_user(
                    email=email,
                    password=password,
                    display_name=f"{firstname} {lastname}"
                )
                uid = user.uid
            except auth.EmailAlreadyExistsError:
                user = auth.get_user_by_email(email)
                uid = user.uid

            # Sign in to get idToken for sending verification email
            sign_in_resp = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + self.firebase_api_key,
                json={
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }
            )

            id_token = sign_in_resp.json().get("idToken", "")

            # Send verification email via Firebase Auth REST API (requires idToken)
            oob_resp = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key=" + self.firebase_api_key,
                json={
                    "requestType": "VERIFY_EMAIL",
                    "idToken": id_token
                }
            )

            if oob_resp.status_code != 200:
                print("Verification email error:", oob_resp.text)

            # Save to Firestore (no password stored - Firebase Auth handles it)
            doc_ref = self.db.collection(self.Customer_Account).document(uid)
            if not doc_ref.get().exists:
                doc_ref.set({
                    "uid": uid,
                    "firstname": firstname,
                    "lastname": lastname,
                    "email": email,
                    "contact_number": contact_number,
                    "provider": "password",
                    "created_at": datetime.now(UTC).isoformat()
                })

            print("User created:", uid)
            return "OK", 200

        except Exception as e:
            print("Signup error:", e)
            return str(e), 500


    def logout(self):
        session.clear()
        return redirect(url_for("index"))
    

    def logoutadmin(self):
        session.clear()
        return redirect(url_for("adminLogin"))
    

    def p_forms(self):
        return render_template("patientForms.html")
    

    def about_customer(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        return render_template("about.html", name=name, email=email)
    
    
    
    
    
    
    
    
    

    def google_bookedCustomer(self):
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
        UrgencyLevel = bleach.clean(request.form.get("Urgency_Level", ""))
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
            self.db.collection(self.Customer_Account).document(uid).collection(self.Appointment_cliets).add({
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
                "UrgencyLevel": UrgencyLevel,
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
    
    
    

    def bookedCustomer(self):
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
        UrgencyLevel = bleach.clean(request.form.get("Urgency_Level", ""))
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
            self.db.collection(self.Customer_Account).document(uid).collection(self.Appointment_cliets).add({
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
                "UrgencyLevel": UrgencyLevel,
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
    
    

    def send_appointment_email(self, patient_email, fullname, action, appointment_data):
        try:
            if not patient_email:
                return None
    
            service = appointment_data.get("Service", "your appointment")
            dentist = appointment_data.get("DentistName", "our dentist")
            appointment_date = appointment_data.get("appointment_date", "")
    
            if action == "accept":
                subject = "Appointment Accepted - Capizonda Dental Clinic"
                body = f"""
    Hello {fullname},
    
    Good news! Your appointment for {service} has been accepted by Dr. {dentist}.
    {f'Appointment Date: {appointment_date}' if appointment_date else ''}
    
    Please arrive 10 minutes before your scheduled time.
    If you have any questions, feel free to contact us.
    
    Best regards,
    Capizonda Dental Clinic Team
    """
            else:
                subject = "Appointment Declined - Capizonda Dental Clinic"
                body = f"""
    Hello {fullname},
    
    We regret to inform you that your appointment request for {service} has been declined by Dr. {dentist}.
    {f'Your previously scheduled appointment date was: {appointment_date}' if appointment_date else ''}
    
    Please feel free to book another appointment at your convenience.
    We apologize for any inconvenience this may have caused.
    
    Best regards,
    Capizonda Dental Clinic Team
    """
    
            msg = Message(
                subject=subject,
                sender=self.app.config["MAIL_DEFAULT_SENDER"],
                recipients=[patient_email]
            )
            msg.body = body
            self.mail.send(msg)
            return True
    
        except Exception as e:
            print(f"EMAIL SEND ERROR: {e}")
            return False
    
    


    def approve(self):

        uid = request.form.get("user_id", "").strip()
        appointment_id = request.form.get("appointment_id", "").strip()
        action = request.form.get("action", "").strip().lower()
        dentist_name = bleach.clean(request.form.get("dentist_name", ""))

        if not uid or not appointment_id:
            return "Missing user_id or appointment_id", 400

        if action not in ("accept", "decline"):
            return "Invalid action", 400


        # FIND USER COLLECTION
        main_collection = None

        if self.db.collection("google_create_account").document(uid).get().exists:
            main_collection = "google_create_account"

        elif self.db.collection(self.Customer_Account).document(uid).get().exists:
            main_collection = self.Customer_Account

        if not main_collection:
            return "User not found", 404


        user_ref = self.db.collection(main_collection).document(uid)


        # GET EXISTING APPOINTMENT DATA BEFORE DELETE
        appt_ref = (
            user_ref
            .collection(self.Appointment_cliets)
            .document(appointment_id)
        )

        appt_doc = appt_ref.get()

        if appt_doc.exists:
            appointment_data = appt_doc.to_dict()
        else:
            appointment_data = {}


        data = {
            "status": action,
            "Patient_unq_id": appointment_id,
            "uid": uid,
            "DentistName": dentist_name,

            # KEEP APPOINTMENT DETAILS
            "appointment_date": appointment_data.get("appointment_date", ""),
            "Service": appointment_data.get("Service", ""),
            "UrgencyLevel": appointment_data.get("UrgencyLevel", ""),

            "FirstName": appointment_data.get("FirstName", ""),
            "MiddleName": appointment_data.get("MiddleName", ""),
            "LastName": appointment_data.get("LastName", ""),

            "HouseNo": appointment_data.get("HouseNo", ""),
            "Street": appointment_data.get("Street", ""),
            "Brgy": appointment_data.get("Brgy", ""),
            "Municipality": appointment_data.get("Municipality", ""),
            "City": appointment_data.get("City", ""),

            "ContactNumber": appointment_data.get("ContactNumber", ""),
            "Nationality": appointment_data.get("Nationality", ""),
            "Religion": appointment_data.get("Religion", ""),

            "Age": appointment_data.get("Age", ""),
            "Sex": appointment_data.get("Sex", ""),
            "Birthday": appointment_data.get("Birthday", ""),

            "Occupation": appointment_data.get("Occupation", ""),
            "CivilStatus": appointment_data.get("CivilStatus", ""),

            # MEDICAL HISTORY
            "q1": appointment_data.get("q1", ""),
            "q2": appointment_data.get("q2", ""),
            "q3": appointment_data.get("q3", ""),
            "q4": appointment_data.get("q4", ""),
            "q5": appointment_data.get("q5", ""),
            "q6": appointment_data.get("q6", ""),
            "q7": appointment_data.get("q7", ""),
            "q9": appointment_data.get("q9", ""),

            "q2_spec": appointment_data.get("q2_spec", ""),
            "q3_spec": appointment_data.get("q3_spec", ""),
            "q4_spec": appointment_data.get("q4_spec", ""),
            "q5_spec": appointment_data.get("q5_spec", ""),
            "q7_spec": appointment_data.get("q7_spec", ""),
            "q9_spec": appointment_data.get("q9_spec", ""),

            "w_preg": appointment_data.get("w_preg", ""),
            "w_nurse": appointment_data.get("w_nurse", ""),
            "w_pill": appointment_data.get("w_pill", ""),
        }


        user_doc = user_ref.get()

        patient_email = (
            user_doc.to_dict().get("email")
            if user_doc.exists
            else None
        )

        fullname = f"{data['FirstName']} {data['LastName']}"


        try:

            if action == "accept":

                approve_ref = (
                    user_ref
                    .collection("Approve")
                    .document(appointment_id)
                )

                batch = self.db.batch()

                # COPY APPOINTMENT TO APPROVE
                batch.set(approve_ref, data)

                # REMOVE FROM APPOINTMENTS
                batch.delete(appt_ref)

                batch.commit()


            elif action == "decline":

                batch = self.db.batch()

                # ONLY DELETE APPOINTMENT
                batch.delete(appt_ref)

                batch.commit()


            threading.Thread(
                target=self.send_appointment_email,
                args=(patient_email, fullname, action, data),
                daemon=True
            ).start()


            return f"Appointment {action}ed"


        except Exception as e:

            print(f"{action.capitalize()} error: {e}")

            return f"Failed to {action} appointment: {e}", 500
    
    
    
    
    
    
    

    def p_profile(self):
        name = session.get('name')
        email = session.get('email')
        user_data = {}
    
        if email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            
            if user_query:
                user_data = user_query[0].to_dict()
                user_data['id'] = user_query[0].id
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    user_data = user_query[0].to_dict()
                    user_data['id'] = user_query[0].id
    
            if user_data:
                user_data.setdefault('uid', user_data.get('id', ''))
        
        return render_template("patient-profile.html", name=name, user=user_data)
    
    
    
    
    
    

    def adminDashboard(self):

        # =========================
        # APPOINTMENTS COLLECTION
        # =========================

        docs = self.db.collection_group("appointments").get()

        appointment_list = []

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["user_uid"] = doc.reference.parent.parent.id
            data["source"] = "appointment"
            appointment_list.append(data)

        # =========================
        # APPROVED APPOINTMENTS
        # =========================

        approve_docs = self.db.collection_group("Approve").get()

        approve_list = []

        for doc in approve_docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["appointment_id"] = doc.reference.parent.parent.id
            data["user_uid"] = doc.reference.parent.parent.parent.id
            data["source"] = "approve"
            approve_list.append(data)

        # =========================
        # ACCOUNTS
        # =========================

        accounts = []

        docs = self.db.collection(self.Customer_Account).stream()

        for doc in docs:

            data = doc.to_dict()

            data["uid"] = doc.id
            data["source"] = "account"

            provider = data.get("provider", "password")
            data["account_type"] = provider.capitalize()

            first = data.get("firstname") or ""
            last = data.get("lastname") or ""

            data["first_name"] = first
            data["last_name"] = last
            data["full_name"] = data.get("name") or f"{first} {last}".strip()

            # DONE PROCEDURE
            done_doc = (
                self.db.collection(self.Customer_Account)
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
        # COUNTS
        # =========================

        pending_count = len(appointment_list)
        approved_count = len(approve_list)
        total_patients = len(accounts)

        urgency_order = {
            "Emergency": 0,
            "Urgent": 1,
            "Normal": 2
        }

        appointment_list.sort(
            key=lambda x: urgency_order.get(
                x.get("UrgencyLevel", ""),
                99
            )
        )

        # =========================
        # RENDER TEMPLATE
        # =========================

        return render_template(
            "admin_dashboard.html",
            Appointment_clients=appointment_list,
            Approve=approve_list,
            accounts=accounts,
            pending_count=pending_count,
            approved_count=approved_count,
            total_patients=total_patients,
        )
        
    

    def get_patient(self, uid):
    
        # =========================
        # TRY GOOGLE ACCOUNT FIRST
        # =========================
        doc_ref = self.db.collection(self.Customer_Account).document(uid)
        doc = doc_ref.get()
    
        account_type = "Google"
    
        # =========================
        # TRY MANUAL ACCOUNT
        # =========================
        if not doc.exists:
            doc_ref = self.db.collection(self.Customer_Account).document(uid)
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

        latest_chart = {}
        latest_chart_image = ""
        try:
            latest_query = (
                doc_ref.collection("Done_procedure")
                .order_by("updated_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            latest_docs = list(latest_query.stream())
            if latest_docs:
                latest_data = latest_docs[0].to_dict()
                latest_chart = latest_data.get("chart", {})
                latest_chart_image = latest_data.get("chart_image", "")
        except Exception as e:
            print("Error getting latest chart:", e)

        data["latest_chart"] = latest_chart
        data["latest_chart_image"] = latest_chart_image

        return data
    

    def adminLogin(self):
        # Handle Google OAuth POST
        if request.method == "POST":
            token = request.form.get("token", "")
            if not token:
                flash("Invalid authentication token.", "error")
                return redirect(url_for("adminLogin"))
            
            try:
                google_account = id_token.verify_oauth2_token(token, google_requests.Request(), self.CLIENT_ID)
                
                email = google_account.get("email", "")
                name = google_account.get("name", "Admin")
                uid = google_account.get("sub", "")
                
                if not email:
                    flash("Unable to get email from Google account.", "error")
                    return redirect(url_for("adminLogin"))
                
                # Save/update admin in "Admin" collection
                self.db.collection("Admin").document(uid).set({
                    "uid": uid,
                    "email": email,
                    "name": name,
                    "provider": "google",
                    "role": "admin",
                    "last_login": datetime.now(UTC).isoformat()
                }, merge=True)
                
                # Set admin session
                session['admin_logged_in'] = True
                session['admin_email'] = email
                session['admin_name'] = name
                session['admin_uid'] = uid
                
                flash(f"Welcome back, Dr. {name}!", "success")
                return redirect(url_for("adminDashboard"))
                
            except ValueError as e:
                print(f"Google auth error: {e}")
                flash("Invalid Google token. Please try again.", "error")
                return redirect(url_for("adminLogin"))
            except Exception as e:
                print(f"Admin login error: {e}")
                flash("Login failed. Please try again.", "error")
                return redirect(url_for("adminLogin"))
        
        # GET request - show login page
        if session.get('admin_logged_in'):
            return redirect(url_for("adminDashboard"))
        
        return render_template("admin_login.html")
    
    

    def service_detail(self, service_id):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        uid = session.get('uid', '')

        service = self.SERVICES_DATA.get(service_id)
        
        if not service:
            abort(404)
            
        return render_template('service.html', service=service, name=name, email=email, uid=uid)
    

    def dental_location(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        return render_template("location.html",name=name, email=email)
    

    def prac(self):
        return render_template("prac.html")
    

    def medical_records(self):
        return render_template("medical_records.html")
    
    
    
    

    def safe_float(self, value):
        try:
            return float(value)
        except:
            return 0
    
    
    

    def save_dental_record(self):
    
        try:
            uid = request.form.get("uid")
    
            if not uid:
                return jsonify({
                    "success": False,
                    "message": "UID is required"
                }), 400
    
            if self.db.collection(self.Customer_Account).document(uid).get().exists:
                main_collection = self.Customer_Account
    
            elif self.db.collection(self.Customer_Account).document(uid).get().exists:
                main_collection = self.Customer_Account
    
            else:
                return jsonify({
                    "success": False,
                    "message": "User not found"
                }), 404
    
            user_ref = self.db.collection(main_collection).document(uid)
    
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
                    "value": self.safe_float(values[i]),
                    "paid": self.safe_float(paids[i]),
                    "balance": self.safe_float(balances[i]),
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
    
    
    

    def get_treatment_info(self, uid):
        try:
            # Find the patient
            if self.db.collection(self.Customer_Account).document(uid).get().exists:
                user_ref = self.db.collection(self.Customer_Account).document(uid)
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
    
        except Exception as e:
            print("ERROR in get_treatment_info:", e)
            return jsonify({
                "success": False,
                "message": str(e)
            }), 500
    
    

    def get_approve(self, uid):
        try:
            print("Searching UID:", uid)

            approve_list = []

            docs = (
                self.db.collection(self.Customer_Account)
                .document(uid)
                .collection("Approve")
                .stream()
            )

            for doc in docs:
                print("Document ID:", doc.id)

                data = doc.to_dict()
                print(data)

                data["id"] = doc.id
                approve_list.append(data)

            print("Returned:", approve_list)

            return jsonify(approve_list)

        except Exception as e:
            print(e)
            return jsonify({"error": str(e)}), 500
    
    
        

    def _register_routes(self):
        """Polymorphism: Register all routes"""
        self.app.route("/payment-success")(self.payment_success)
        self.app.route("/payment-cancel")(self.payment_cancel)
        self.app.route("/webhook/paymongo", methods=["POST"])(self.paymongo_webhook)
        self.app.route("/create_gcash_payment", methods=["POST"])(self.create_gcash_payment)
        self.app.route("/", methods=["GET"])(self.index)
        self.app.route("/google_index", methods=["GET"])(self.google_index)
        self.app.route("/login", methods=["POST"])(self.login_manual)
        self.app.route("/google-auth", methods=["POST"])(self.login_g_auth)
        self.app.route("/sign-up", methods=["POST"])(self.sign_up)
        self.app.route("/logout")(self.logout)
        self.app.route("/logoutadmin")(self.logoutadmin)
        self.app.route("/patient_forms")(self.p_forms)
        self.app.route("/about")(self.about_customer)
        self.app.route("/google_booked_customer", methods=["POST"])(self.google_bookedCustomer)
        self.app.route("/booked_customer", methods=["POST"])(self.bookedCustomer)
        self.app.route("/approve", methods=["POST"])(self.approve)
        self.app.route("/patient-profile")(self.p_profile)
        self.app.route("/admin_dashboard")(self.adminDashboard)
        self.app.route("/get_patient/<uid>")(self.get_patient)
        self.app.route("/admin_login", methods=["GET", "POST"])(self.adminLogin)
        self.app.route("/services/<service_id>")(self.service_detail)
        self.app.route("/location")(self.dental_location)
        self.app.route("/prac")(self.prac)
        self.app.route("/medical_records")(self.medical_records)
        self.app.route("/save_dental_record", methods=["POST"])(self.save_dental_record)
        self.app.route("/get_treatment_info/<uid>")(self.get_treatment_info)
        self.app.route("/get_approve/<uid>")(self.get_approve)



app_instance = DentalClinicApp()
app = app_instance.app

if __name__ == "__main__":
    print("🦷 Capizonda Dental Clinic Server Starting...")
    app.run(debug=True, port=5000)