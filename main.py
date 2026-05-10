from flask import Flask, abort, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, UTC
import bleach
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"  # required for flash messages and session

# -----------------------------
# Initialize Firebase safely
# -----------------------------
cred = credentials.Certificate("dentech_key.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

Account_clients = "manual_create_account"
Appointment_cliets = "appointments"
Doc_Patients = "Patients"



# Paymongo api keys

pay_mongo_secret_key = "sk_test_CYiQMSXw2cHHhtF564gZ3mMx"
pay_mongo_public_key = "pk_test_m4rG4iv4L9S5MC8d4dxq39ko"



# makita nisa sa diri https://console.cloud.google.com/auth/clients?project=dentech-c2ee0
CLIENT_ID = "921529543911-okjlt4tgb56admos6msdlho9c6ibive8.apps.googleusercontent.com"



#PAYMENTS 
#Still working palang payment the butangi lng cho if maka tapos ka sa need  mo  taposon
# add kalng button for payment
import requests

url = "https://api.paymongo.com/v1/checkout_sessions"

payload = { "data": { "attributes": {
            "billing": { "email": "Email information" },
            "send_email_receipt": True,
            "show_description": True,
            "show_line_items": True,
            "payment_method_types": ["gcash", "brankas_metrobank", "paymaya"],
            "reference_number": "reference_number",
            "cancel_url": "cancel url",
            "description": "Description details of the checkout.",
            "line_items": [
                {
                    "currency": "PHP",
                    "images": ["image ka checkout"],
                    "amount": 200,
                    "description": "description ka checkout",
                    "name": "name ka checkout",
                    "quantity": 112
                },
                {
                    "currency": "PHP",
                    "images": ["second image"],
                    "amount": 1000,
                    "description": "second  description",
                    "name": "second name ",
                    "quantity": 200
                }
            ]
        } } }
headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "authorization": "Basic c2tfdGVzdF9DWWlRTVNYdzJjSEhodEY1NjRnWjNtTXg6cGtfdGVzdF9tNHJHNGl2NEw5UzVNQzhkNGR4cTM5a28="
}

response = requests.post(url, json=payload, headers=headers)

print(response.text)



#------------------------------------------------------------------------------------------------------------------------------------------------
#notification for gmail ni client



#------------------------------------------------------------------------------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    uid = session.get ('uid', '')
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("index.html",uid = uid, name=name, email=email)


@app.route("/google_index", methods=["GET"])
def google_index():
    uid = session.get ('uid', '')
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("google_index.html",uid = uid, name=name, email=email)


@app.route("/login", methods=["POST"])
def login_manual():
    email = bleach.clean(request.form.get("email",''))
    password = bleach.clean(request.form.get("Password"))

    # Search for user in Firestore
    user_query = db.collection(Account_clients).where("email", "==", email).get()

    if user_query:
        user_data = user_query[0].to_dict()
        # Verify the hashed password
        if check_password_hash(user_data['password'], password):
            session['name'] = user_data.get('firstname', '')
            session['email'] = user_data.get('email', '')
            session['uid'] = user_query[0].id           # ✅ ADD THIS

            flash(f"Welcome back, {user_data['firstname']}!", "success")
            return redirect(url_for("index"))
    
    flash("Invalid username or password!", "error") # Added error category
    return redirect("/") # Redirect to the root route


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
            flash("Username already taken!")
            return redirect(url_for("sign_up"))

        hashed_password = generate_password_hash(password)


        doc_ref = db.collection(Account_clients).document()
        uid = doc_ref.id

        doc_ref.set({
            "uid": uid,
            "firstname": firstname,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.now(UTC).isoformat(),
            "contact_number":contact_number,
            "lastname":lastname
        })

        return redirect(url_for("index"))

    return render_template("index.html")

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



app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='yourgmail@gmail.com',
    MAIL_PASSWORD='slrm eyqa pciv flky'
)

mail = Mail(app)


def send_appointment_email(to_email, first_name, appointment_date, service):
    msg = Message(
        subject="Dental Appointment Reminder",
        sender=app.config['MAIL_USERNAME'],
        recipients=[to_email]
    )

    msg.body = f"""
Hello {first_name},

This is a reminder for your dental appointment:

📅 Date: {appointment_date}
🦷 Service: {service}

Please arrive 10–15 minutes early.

Thank you!
"""

    mail.send(msg)





@app.route("/google_booked_customer", methods=["POST"])
def google_bookedCustomer():
    uid = session.get('uid')

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


@app.route("/approve", methods=["POST"])
def approve():

    uid = request.form.get("user_id")
    appointment_id = request.form.get("appointment_id")
    action = request.form.get("action")
    email = session.get('email')
    


    data = {
        "status": action,
        "uid": uid,
        "email": email,
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

        "q1": request.form.get("q1"),
        "q2": request.form.get("q2"),
        "q3": request.form.get("q3"),
        "q4": request.form.get("q4"),
        "q5": request.form.get("q5"),
        "q6": request.form.get("q6"),
        "q7": request.form.get("q7"),
        "q9": request.form.get("q9"),

        "q2_spec": request.form.get("q2_spec"),
        "q3_spec": request.form.get("q3_spec"),
        "q4_spec": request.form.get("q4_spec"),
        "q5_spec": request.form.get("q5_spec"),
        "q7_spec": request.form.get("q7_spec"),
        "q9_spec": request.form.get("q9_spec"),

        "w_preg": request.form.get("w_preg"),
        "w_nurse": request.form.get("w_nurse"),
        "w_pill": request.form.get("w_pill"),
    }

    # check where uid exists
    if db.collection("google_create_account").document(uid).get().exists:
        main_collection = "google_create_account"
    
    elif db.collection(Account_clients).document(uid).get().exists:
        main_collection = Account_clients

    else:
        return "User not found", 404

    # save approved data
    db.collection(main_collection) \
        .document(uid) \
        .collection("Approve") \
        .document(appointment_id) \
        .set(data)

    # delete pending appointment
    db.collection(main_collection) \
        .document(uid) \
        .collection("appointments") \
        .document(appointment_id) \
        .delete()

    return "Approved successfully"


                                                                                   
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


@app.route("/update-profile", methods=["POST"])
def update_profile():

    user_id = session.get("uid")

    if not user_id:
        flash("User not logged in", "error")
        return redirect(url_for("p_profile"))

    new_name = bleach.clean(request.form.get("new_name", "").strip())
    new_lastname = bleach.clean(request.form.get("new_last", "").strip())
    new_username = bleach.clean(request.form.get("new_username", "").strip())
    new_phone = bleach.clean(request.form.get("new_phone", "").strip())
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if new_password and new_password != confirm_password:
        flash("Passwords do not match!")
        return redirect(url_for("p_profile"))

    update_data = {
        "firstname": new_name,
        "username": new_username,
        "phone": new_phone,
        "updated_at": datetime.utcnow().isoformat(),
        
    }

    if new_password:
        update_data["password"] = generate_password_hash(new_password)

    try:
        db.collection(Account_clients).document(user_id).update(update_data)
        session['username'] = new_username
        session['name'] = new_name
        
        flash("Profile updated successfully!")
    except Exception as e:
        print("Error:", e)
        flash("Update failed")

    return redirect(url_for("p_profile"))

#---------------------------------------------------
#Admin routes
#---------------------------------------------------



@app.route("/admin_dashboard")
def adminDashboard():

    # =========================
    # APPOINTMENTS COLLECTION
    # =========================
    docs = db.collection_group("appointments").get()

    appointment_list = []

    for doc in docs:
        appointment_data = doc.to_dict()
        appointment_data["id"] = doc.id
        appointment_data["user_uid"] = doc.reference.parent.parent.id
        appointment_list.append(appointment_data)

    # =========================
    # APPROVE SUBCOLLECTION
    # =========================
    approve_docs = db.collection_group("Approve").get()

    approve_list = []

    for doc in approve_docs:
        data = doc.to_dict()

        data["id"] = doc.id
        data["appointment_id"] = doc.reference.parent.parent.id
        data["user_uid"] = doc.reference.parent.parent.parent.id

        approve_list.append(data)

    # =========================
    # SEND BOTH TO TEMPLATE
    # =========================
    return render_template(
        "admin_dashboard.html",
        Appointment_clients=appointment_list,
        Approve=approve_list
    )


@app.route("/admin_login")
def adminLogin():
    return render_template("admin_login.html")


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



if __name__ == "__main__":
    app.run(debug=True)





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