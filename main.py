from flask import Flask, render_template, request, redirect, url_for, flash, session
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
    return redirect(url_for("index"))


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