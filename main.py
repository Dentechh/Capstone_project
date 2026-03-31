from flask import Flask, abort, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token
from google.auth.transport import requests
from datetime import datetime, UTC
import bleach
import uuid
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
Appointment_cliets = "Booked"
Doc_Patients = "Patients"



# makita nisa sa diri https://console.cloud.google.com/auth/clients?project=dentech-c2ee0
CLIENT_ID = "921529543911-okjlt4tgb56admos6msdlho9c6ibive8.apps.googleusercontent.com"


@app.route("/", methods=["GET"])
def index():
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("index.html", name=name, email=email)


@app.route("/login", methods=["POST"])
def login_manual():
    username = bleach.clean(request.form.get("UserName"))
    password = bleach.clean(request.form.get("Password"))

    # Search for user in Firestore
    user_query = db.collection(Account_clients).where("username", "==", username).get()

    if user_query:
        user_data = user_query[0].to_dict()
        # Verify the hashed password
        if check_password_hash(user_data['password'], password):
            session['name'] = user_data['firstname']
            session['email'] = user_data.get('email', '')
            session['username'] = user_data['username']   # ✅ ADD THIS
            session['uid'] = user_query[0].id             # ✅ ADD THIS

            flash(f"Welcome back, {user_data['firstname']}!", "success")
            return redirect(url_for("index"))
    
    flash("Invalid username or password!", "error") # Added error category
    return redirect("/") # Redirect to the root route


#  GOOGLE AUTH ROUTE

@app.route("/google-auth", methods=["POST"])
def login_g_auth():
    token = request.form["token"]
    try:
        google_account = id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)
        
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

        return redirect(url_for("index")) 
    except ValueError:
        return render_template("error.html", message="Invalid Google token")


#  MANUAL SIGN UP



@app.route("/sign-up", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":

        firstname = bleach.clean(request.form["FirstName"].strip())
        lastname = bleach.clean(request.form["LastName"].strip())
        username = bleach.clean(request.form["UserName"].strip())
        password = bleach.clean(request.form["Password"].strip())
        contact_number = bleach.clean(request.form["MobileNumber"].strip())
        

        check_account = db.collection(Account_clients).where("username", "==", username).get()

        if check_account:
            flash("Username already taken!")
            return redirect(url_for("sign_up"))

        hashed_password = generate_password_hash(password)


        doc_ref = db.collection(Account_clients).document()
        uid = doc_ref.id

        doc_ref.set({
            "uid": uid,
            "firstname": firstname,
            "username": username,
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






@app.route("/booked_customer", methods=["POST"])
def bookedCustomer():

    FullName = bleach.clean(request.form.get("Full_Name", ""))
    EmailAddress = bleach.clean(request.form.get("Email_Address", ""))
    ContactNumber = bleach.clean(request.form.get("Contact_number", ""))
    Nationality_appointment = bleach.clean(request.form.get("Nationality", ""))
    Age_appointment = bleach.clean(request.form.get("Age", ""))
    Sex_appointment = bleach.clean(request.form.get("Sex", ""))
    Birthday_appointment = bleach.clean(request.form.get("Birthday", ""))
    Occupation_appointment = bleach.clean(request.form.get("Occupation", ""))
    Civil_Status_appointment = bleach.clean(request.form.get("Civil_Status", ""))
    Service_appointment = bleach.clean(request.form.get("Service", ""))
    

    q1_appointment = bleach.clean(request.form.get("q1", ""))
    q2_appointment = bleach.clean(request.form.get("q2", ""))
    q3_appointment = bleach.clean(request.form.get("q3", ""))
    q4_appointment = bleach.clean(request.form.get("q4", ""))
    q5_appointment = bleach.clean(request.form.get("q5", ""))
    q6_appointment = bleach.clean(request.form.get("q6", ""))
    q7_appointment = bleach.clean(request.form.get("q7", ""))
    q9_appointment = bleach.clean(request.form.get("q9", ""))

    q2_spec_appointment = bleach.clean(request.form.get("q2_spec", ""))
    q3_spec_appointment = bleach.clean(request.form.get("q3_spec", ""))
    q4_spec_appointment = bleach.clean(request.form.get("q4_spec", ""))
    q5_spec_appointment = bleach.clean(request.form.get("q5_spec", ""))
    q7_spec_appointment = bleach.clean(request.form.get("q7_spec", ""))
    q9_spec_appointment = bleach.clean(request.form.get("q9_spec", ""))

    w_nurse_appointment = request.form.get("w_nurse")
    w_preg_appointment = request.form.get("w_preg")
    w_pill_appointment = request.form.get("w_pill")
    uid = str(uuid.uuid4())
    try:
        db.collection("Appointment_clients").document(uid).set({
            "uid": uid,
            "FullName": FullName,
            "EmailAddress": EmailAddress,
            "ContactNumber": ContactNumber,
            "Nationality": Nationality_appointment,
            "Age": Age_appointment,
            "Sex": Sex_appointment,
            "Birthday": Birthday_appointment,
            "Occupation": Occupation_appointment,
            "Civil_Status": Civil_Status_appointment,
            "q1": q1_appointment,
            "q2": q2_appointment,
            "q3": q3_appointment,
            "q4": q4_appointment,
            "q5": q5_appointment,
            "q6": q6_appointment,
            "q7": q7_appointment,
            "q9": q9_appointment,
            "q2_spec": q2_spec_appointment,
            "q3_spec": q3_spec_appointment,
            "q4_spec": q4_spec_appointment,
            "q5_spec": q5_spec_appointment,
            "q7_spec": q7_spec_appointment,
            "q9_spec": q9_spec_appointment,

            "w_nurse": w_nurse_appointment,
            "w_preg": w_preg_appointment,
            "w_pill": w_pill_appointment,
            "Service_appointment":Service_appointment

        })

        flash("Appointment successfully booked!", "success")

    except Exception as e:
        print(f"Error adding appointment: {e}")
        flash("There was an error booking your appointment.", "error")

    return redirect(url_for("index"))


                                                                                   
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
    ref = db.collection("Appointment_clients")
    docs = ref.get()

    Appointment_clients = []

    for doc in docs:
        appointment = doc.to_dict()
        appointment["id"] = doc.id
        Appointment_clients.append(appointment)

    return render_template(
        "admin_dashboard.html",
        Appointment_clients=Appointment_clients
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