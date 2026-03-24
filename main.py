from flask import Flask, abort, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token
from google.auth.transport import requests
from datetime import datetime, UTC
import bleach
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"  # required for flash messages

# -----------------------------
# Initialize Firebase safely
# -----------------------------
cred = credentials.Certificate("dentech_key.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

Account_clients = "manual_create_account"
Appointment_cliets = "Booked"


# makita nisa sa diri https://console.cloud.google.com/auth/clients
CLIENT_ID = "921529543911-okjlt4tgb56admos6msdlho9c6ibive8.apps.googleusercontent.com"


@app.route("/", methods=["GET"])
def index():
    name = session.get('name', 'Guest')
    email = session.get('email', '')
    return render_template("index.html", name=name, email=email)


@app.route("/login", methods=["POST"])
def login_manual():
    username = bleach.clean(request.form.get("UserName"))
    password = bleach.clean (request.form.get("Password"))

    # Search for user in Firestore
    user_query = db.collection(Account_clients).where("username", "==", username).get()

    if user_query:
        user_data = user_query[0].to_dict()
        # Verify the hashed password
        if check_password_hash(user_data['password'], password):
            session['name'] = user_data['firstname']
            session['email'] = user_data.get('email', '') 
            return redirect(url_for("index"))
    
    flash("Invalid username or password!")
    return redirect(url_for("/"))


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
        username = bleach.clean(request.form["UserName"].strip())
        password = bleach.clean(request.form["Password"].strip())

        check_account = db.collection(Account_clients).where("username", "==", username).get()

        if check_account:
            flash("Username already taken!")
            return redirect(url_for("sign_up"))

        hashed_password = generate_password_hash(password)


        db.collection(Account_clients).add({
            "firstname": firstname,
            "username": username,
            "password": hashed_password,
            "created_at": datetime.now(UTC).isoformat()
        })

        session['name'] = firstname
        return render_template(url_for("index"))

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

    FullName = bleach.clean(request.form["Full_Name"])
    EmailAddress = bleach.clean(request.form["Email_Address"])
    ContactNumber = bleach.clean(request.form["Contact_number"])
    SelectAppointDate = bleach.clean(request.form["Appointment_date"])
    Clientconcers = bleach.clean(request.form["Client_Concern"])

    try:
        # Attempt to add to Firestore
        db.collection("Appointment_clients").add({
            "FullName": FullName,
            "EmailAddress": EmailAddress,
            "ContactNumber": ContactNumber,
            "SelectAppointDate": SelectAppointDate,
            "Client_concers": Clientconcers
        })
        flash("Appointment successfully booked!", "success")

    except Exception as e:
        # Log the error or flash a message
        print(f"Error adding appointment: {e}")
        flash("There was an error booking your appointment. Please try again.", "error")

    return redirect(url_for("index"))

@app.route("/patient-profile")
def p_profile():
    if 'email' not in session:
        flash("Please login to view your profile")
        return redirect(url_for("index"))

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
    if 'email' not in session: 
        return redirect(url_for("index"))

    email = request.form.get("email_id")
    new_name = bleach.clean(request.form.get("new_name").strip())
    new_phone = bleach.clean(request.form.get("new_phone").strip())
    new_password = request.form.get("new_password")
    
    # Determine which collection to update based on session provider
    provider = session.get('provider', 'manual')
    collection = "google_create_account" if provider == 'google' else Account_clients
    
    update_data = {
        "firstname": new_name,
        "phone": new_phone
    }

    # If it's a manual user and they typed a new password
    if provider != 'google' and new_password and len(new_password.strip()) > 0:
        update_data["password"] = generate_password_hash(new_password.strip())

    try:
        # 1. Update Firestore
        # We find the document by the email field
        user_docs = db.collection(collection).where("email", "==", email).get()
        
        if user_docs:
            for doc in user_docs:
                db.collection(collection).document(doc.id).update(update_data)
            
            # 2. Update the session so the UI updates immediately
            session['name'] = new_name
            flash("Profile updated successfully!", "success")
        else:
            flash("User document not found.", "error")

    except Exception as e:
        print(f"Update Error: {e}")
        flash("Error updating profile.", "error")

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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
    return render_template("location.html")



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