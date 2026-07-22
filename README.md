# 🦷 Capizonda Dental Clinic Management System

A comprehensive web-based dental clinic management system built with **Flask**, **Firebase Firestore**, and **vanilla JavaScript**. It handles patient records, appointment scheduling, dental charting, treatment notes, and administrative workflows with a modern, responsive UI.

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Environment Variables](#environment-variables)
- [Database Schema](#database-schema)
- [Pages & Routes](#pages--routes)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [About](#about)

## ✨ Features

### 👤 Patient Portal
- **User Registration & Email Verification** — OTP-based email verification via Gmail SMTP
- **Google Sign-In / Sign-Up** — OAuth2 integration for fast account creation
- **Dark Mode / Light Mode Toggle** — Persistent theme preference per user
- **Appointment Booking** — Full medical history form (heart disease, diabetes, allergies, women's health, etc.)
- **Patient Profile** — View and update personal information
- **Service Catalog** — Browse dental services with detailed descriptions and benefits
- **Responsive Design** — Mobile-first layout with hamburger navigation and optimized layouts

### 🦷 Dental Charting
- **Interactive Odontogram** — Visual dental record chart with temporary and permanent teeth grids
- **Treatment Action Palette** — Select tools: Healthy, Caries, Filling, Crown, Root Canal, Missing Tooth, Extraction, Check
- **Chart Image Upload** — Attach dental chart images to patient records
- **PDF Export** — Generate downloadable PDF of the dental record chart using jsPDF + html2canvas
- **Mobile Chart Modal** — Opens dental chart in fullscreen landscape mode on phone screens

### 🩺 Patient Dashboard (Admin)
- **Patient Information Panel** — View patient demographics, medical history, and women's health info
- **Visit History Table** — Track assigned dentist, procedures, fees paid, balance, and next appointments
- **Treatment Notes** — 10-column treatment log with date, tooth#, procedure, dentist, value, amount paid, balance, next appointment, medicine, and status
- **Dental Record Chart** — Interactive tooth chart with status tracking (healthy, caries, filling, etc.)
- **PDF Download** — Export dental charts as landscape A4 PDFs

### 📊 Admin Dashboard
- **Appointment Requests** — View, approve, or decline incoming appointments with status badges
- **My Weekly Clients** — Track weekly client visits and appointments
- **My Patients** — Patient database with profile cards and quick stats
- **Appointment Management** — Assign dentists, update status, and send email notifications
- **Responsive Admin Panel** — Collapsible sidebar with hamburger menu on mobile

### 🔐 Authentication & Security
- **Manual Account Registration** — Email/password with hashed passwords (Werkzeug)
- **Google OAuth2 Integration** — Secure token verification via Google identity services
- **Email Verification** — 6-digit OTP codes with 10-minute expiration
- **Session Management** — Secure Flask sessions with permanent session lifetime
- **Input Sanitization** — Bleach library for XSS prevention on all form inputs

### 📧 Notifications
- **Appointment Status Emails** — Automated Gmail SMTP notifications for approved/declined appointments
- **OTP Verification Emails** — Secure email verification codes

## 🛠 Tech Stack

| Category | Technology |
|----------|-----------|
| **Backend** | Flask (Python) |
| **Database** | Firebase Firestore |
| **Authentication** | Firebase Admin SDK, Google OAuth2 |
| **Email** | Flask-Mail (Gmail SMTP) |
| **Frontend** | HTML5, CSS3, JavaScript (ES6+) |
| **Icons** | Material Symbols Rounded |
| **PDF Generation** | jsPDF, html2canvas |
| **Security** | Werkzeug password hashing, Bleach sanitization |
| **Deployment** | Flask development server (port 5000) |

## 📁 Project Structure

```
Capstone_project/
├── main.py                      # Flask application entry point
├── dentech_key.json             # Firebase service account key
├── templates/
│   ├── index.html               # Home page
│   ├── about.html               # About page
│   ├── service.html             # Services catalog
│   ├── location.html            # Clinic location page
│   ├── patient-profile.html     # Patient profile view
│   ├── admin_dashboard.html     # Admin dashboard (single-page app)
│   ├── admin_login.html         # Admin authentication
│   ├── verify_otp.html          # Email OTP verification
│   ├── view_dental_record.html  # Dental record viewer
│   ├── medical_records.html     # Medical history view
│   └── prac.html                # Practice/test page
├── static/
│   ├── css/
│   │   ├── index-s.css          # Home page styles
│   │   ├── about.css            # About page styles
│   │   ├── service.css          # Services page styles
│   │   ├── location.css         # Location page styles
│   │   ├── admin.css            # Admin dashboard styles
│   │   ├── chart-style.css      # Dental chart styles
│   │   └── verify_otp.css       # OTP verification styles
│   ├── img/                     # Images, logos, icons
│   ├── dental_charts/           # Saved dental chart images
│   └── services/                # Service-related images
├── archive/
│   └── main.py                  # Archived version of main.py
└── README.md                    # Project documentation
```

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8+
- Firebase project with Firestore enabled
- Gmail account (for SMTP)
- Google Cloud project (for OAuth2)

### 1. Clone the Repository
```bash
git clone <repository-url>
cd Capstone_project
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install flask firebase-admin google-auth flask-mail bleach requests pyjwt
```

### 4. Firebase Setup
1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Generate a service account key and save it as `dentech_key.json` in the project root
3. Enable Firestore database in your Firebase project
4. Update the Firebase project ID in `main.py` (line 38: `"projectId": "dentech-c2ee0"`)

### 5. Google OAuth2 Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/auth/clients)
2. Create an OAuth2 Client ID for Web application
3. Add authorized JavaScript origins and redirect URIs
4. Update `CLIENT_ID` in `main.py` (line 116) with your client ID

### 6. Email (SMTP) Configuration
Update the Flask-Mail configuration in `main.py` (lines 561-566):
```python
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'
```

**Note:** For Gmail, use an [App Password](https://myaccount.google.com/apppasswords) if 2FA is enabled.

### 7. Run the Application
```bash
python main.py
```

The server will start at `http://localhost:5000`

- **Home Page:** http://localhost:5000/
- **Admin Login:** http://localhost:5000/admin_login
- **Admin Dashboard:** http://localhost:5000/admin_dashboard

## 🔑 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Flask session secret key | No (auto-generated if missing) |

## 🗄️ Database Schema

### Collections

| Collection | Description |
|------------|-------------|
| `manual_create_account` | Patient accounts created via email/password |
| `google_create_account` | Patient accounts created via Google OAuth |
| `appointments` | Appointment requests from patients |
| `Approve` | Approved appointments (subcollection of user documents) |
| `Done_procedure` | Completed treatment records (subcollection of user documents) |
| `admins` | Admin user accounts |

### Subcollections

Each user document (in `manual_create_account` or `google_create_account`) contains:
- `appointments` — Pending appointment requests
- `Approve` — Approved appointments
- `Done_procedure` — Completed dental procedures

## 📱 Pages & Routes

### Public Pages
| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Landing page with clinic info and service highlights |
| `/about` | About | Clinic information and doctor profile |
| `/services/<id>` | Services | Individual service details (consultation, cleaning, extraction, etc.) |
| `/location` | Location | Clinic address and Google Maps embed |

### Patient Pages
| Route | Page | Description |
|-------|------|-------------|
| `/sign-up` | Register | Patient registration form |
| `/verify_otp/<uid>` | OTP Verification | Email verification code entry |
| `/resend_otp/<uid>` | Resend OTP | Resend verification code |
| `/login` | Login | Manual email/password login |
| `/google-auth` | Google Auth | Google OAuth callback |
| `/logout` | Logout | Clear session |
| `/patient-profile` | Profile | View patient profile |
| `/booked_customer` | Book Appointment | Submit appointment booking |
| `/google_booked_customer` | Google Book | Submit appointment via Google |

### Admin Pages
| Route | Page | Description |
|-------|------|-------------|
| `/admin_login` | Admin Login | Admin authentication |
| `/admin_dashboard` | Admin Dashboard | Main admin panel |
| `/approve` | Approve Action | Approve/decline appointments |
| `/save_dental_record` | Save Record | Save dental chart and treatment notes |
| `/get_patient/<uid>` | Get Patient | Fetch patient data (JSON) |
| `/get_treatment_info/<uid>` | Get Treatment | Fetch treatment history (JSON) |
| `/get_approve/<uid>` | Get Approve | Fetch approved appointments (JSON) |

## 🎨 Design Features

- **Responsive Layout** — Mobile-first CSS with hamburger navigation
- **Dark Mode Support** — Toggle between light and dark themes
- **Navy/Gold Theme** — Professional dental clinic color scheme
- **Material Icons** — Consistent iconography throughout the app
- **Smooth Animations** — CSS transitions and view-transition API
- **Kumbh Sans Font** — Clean, modern typography

## 🔒 Security Features

- Password hashing with Werkzeug
- Input sanitization with Bleach
- Firebase service account authentication
- Google OAuth2 token verification
- Session-based authentication
- Email verification before account activation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -m 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Open a Pull Request

## 📄 License

This project is developed as a capstone project for educational purposes.

## 👨‍⚕️ About

**Capizonda Dental Clinic** — Located at 231 Lopez Jaena St, Molo, Iloilo City.  
Providing quality dental care since 2024.

**Contact:** capizondadental@gmail.com | **Phone:** 0962 687 6076

---

Built with ❤️ using Flask, Firebase, and modern web technologies.

## 🧪 Testing

### Running the Application
1. Start the Flask server:
   ```bash
   python main.py
   ```
2. Open your browser and navigate to `http://localhost:5000`
3. To log in as admin: navigate to `http://localhost:5000/admin_login`
4. To register as a patient: go to `http://localhost:5000/sign-up`

### Manual Test Checklist
- ✅ User registration with email verification (OTP)
- ✅ Google Sign-In / Sign-Up flow
- ✅ Email/password login and logout
- ✅ Appointment booking with medical history form
- ✅ Admin can view, approve, and decline appointments
- ✅ Admin can save dental chart and treatment notes
- ✅ Dental chart interaction (clicking teeth to assign status)
- ✅ PDF generation of dental chart
- ✅ Dark mode / Light mode toggle
- ✅ Responsive design on mobile and desktop

## 📦 API Reference

### Authentication Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/sign-up` | Register a new patient account |
| POST | `/login` | Login with email and password |
| POST | `/google-auth` | Google OAuth2 callback |
| GET | `/logout` | Logout and clear session |
| GET | `/verify_otp/<uid>` | Verify OTP code |
| GET | `/resend_otp/<uid>` | Resend OTP code |

### Appointment Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/booked_customer` | Submit appointment booking (email/password users) |
| POST | `/google_booked_customer` | Submit appointment booking (Google users) |
| POST | `/approve` | Approve or decline an appointment |
| GET | `/get_approve/<uid>` | Fetch approved appointments for a patient |

### Patient & Treatment Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/save_dental_record` | Save dental chart and treatment notes |
| GET | `/get_patient/<uid>` | Fetch patient data (JSON) |
| GET | `/get_treatment_info/<uid>` | Fetch treatment history (JSON) |
| GET | `/patient-profile` | View patient profile page |
| GET | `/medical_records/<uid>` | View patient medical records |

## 🚢 Deployment

### Prerequisites
- Python 3.8+ installed on the server
- Firebase project configured
- A production-ready WSGI server (Gunicorn, uWSGI, etc.)

### Deployment Steps
1. **Set Environment Variables**
   ```bash
   export SECRET_KEY="your-secret-key-here"
   export MAIL_USERNAME="your-email@gmail.com"
   export MAIL_PASSWORD="your-app-password"
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run with Gunicorn**
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 main:app
   ```

4. **Using Nginx as Reverse Proxy** (Recommended)
   ```bash
   # /etc/nginx/sites-available/capizonda
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       location /static {
           alias /path/to/Capstone_project/static;
       }
   }
   ```

## 🐛 Troubleshooting

### Common Issues

**Firebase Connection Error**
- Ensure `dentech_key.json` is in the project root
- Verify the Firebase project ID matches in `main.py`

**Email Not Sending**
- Use Gmail App Password if 2FA is enabled
- Check SMTP credentials in `main.py`
- Ensure port 587 is not blocked by firewall

**Google Sign-In Not Working**
- Verify `CLIENT_ID` is correctly set in `main.py`
- Check authorized origins in Google Cloud Console
- Ensure redirect URIs are properly configured

**Port Already in Use**
- Change the port in `main.py`: `app.run(debug=True, port=5001)`

## 📝 License

This project is developed as a capstone project for educational purposes.

## 👨‍⚕️ About

**Capizonda Dental Clinic** — Located at 231 Lopez Jaena St, Molo, Iloilo City.  
Providing quality dental care since 2024.

**Contact:** capizondadental@gmail.com | **Phone:** 0962 687 6076

---

Built with ❤️ using Flask, Firebase, and modern web technologies.
