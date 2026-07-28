import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the adminLogin method
old_admin_login = '''    def adminLogin(self):
        if request.method == "POST":
            email = bleach.clean(request.form.get("email", "").strip().lower())
            password = request.form.get("password", "")
            
            # Query your admins collection
            admin_query = self.db.collection("admins").where("email", "==", email).get()
            
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
        
        return render_template("admin_login.html")  # ✅ This now works!'''

new_admin_login = '''    def adminLogin(self):
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
        
        return render_template("admin_login.html")'''

content = content.replace(old_admin_login, new_admin_login)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated adminLogin method')
