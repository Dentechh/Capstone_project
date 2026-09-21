from flask import Flask, abort, render_template, request, redirect, url_for, flash, session, jsonify
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
import firebase
import uuid
from cache_store import SimpleCache
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
        self.app.permanent_session_lifetime = timedelta(hours=8)
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
        self.Blocked_Slots = "BlockedSlots"
        self.CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        self.firebase_api_key = "7HrEnIE4fKNxmv3ctFHoNdcmqRV2"
        
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
            
        self.PATIENTS_PAGE_SIZE = 25

        # In-memory cache to cut Firestore reads on hot admin endpoints.
        # See cache_store.py for how it works and its single-process caveat.
        self.cache = SimpleCache()
        self.CACHE_TTL_SECONDS = 300  # 5 min safety-net expiry

    # ============================================================
    # CACHE HELPERS
    # ============================================================
    def _get_done_procedures_cached(self):
        """
        All Done_procedure documents across every account, used by both
        the financial and procedure charts. This used to be a fresh
        collection_group scan on every single chart request (including
        every time the admin switched the period dropdown) -- now it's
        one scan per cache window, invalidated instantly whenever a
        treatment record is created or edited.
        """
        cached = self.cache.get("done_procedures_all")
        if cached is not None:
            return cached
        docs = [doc.to_dict() for doc in self.db.collection_group("Done_procedure").stream()]
        self.cache.set("done_procedures_all", docs, ttl_seconds=self.CACHE_TTL_SECONDS)
        return docs

    def _invalidate_financial_cache(self):
        self.cache.invalidate("done_procedures_all")

    def _get_manageable_accounts_cached(self):
        """
        Raw (uid, data) pairs for every real (non-walk-in) Customer_Account.
        Powers the User Management list. This collection was being fully
        re-scanned on every admin dashboard load AND every "load more"
        click, since sorting/pagination happened in Python.
        """
        cached = self.cache.get("manageable_accounts_all")
        if cached is not None:
            return cached
        query = self.db.collection(self.Customer_Account).where("provider", "in", ["google", "password"])
        docs = [(doc.id, doc.to_dict()) for doc in query.stream()]
        self.cache.set("manageable_accounts_all", docs, ttl_seconds=self.CACHE_TTL_SECONDS)
        return docs

    def _invalidate_accounts_cache(self):
        self.cache.invalidate("manageable_accounts_all")

    def _get_patients_cached(self):
        """
        Raw (patient_id, data) pairs for every Patients doc. Powers the
        admin search box, which used to stream the ENTIRE collection on
        every keystroke (2+ chars), and also powers the account_uid ->
        patient_id lookup map below, which replaces a per-row Firestore
        query in the dashboard list pages.
        """
        cached = self.cache.get("patients_all")
        if cached is not None:
            return cached
        docs = [(doc.id, doc.to_dict()) for doc in self.db.collection(self.Doc_Patients).stream()]
        self.cache.set("patients_all", docs, ttl_seconds=self.CACHE_TTL_SECONDS)
        return docs

    def _invalidate_patients_cache(self):
        self.cache.invalidate("patients_all")

    def _get_account_to_patient_map(self):
        """account_uid -> patient_id, built from the cached patients list
        instead of firing one Firestore query per row in a table."""
        mapping = {}
        for patient_id, data in self._get_patients_cached():
            account_uid = data.get("account_uid") or ""
            if account_uid and account_uid not in mapping:
                mapping[account_uid] = patient_id
        return mapping

    # ============================================================
    # PATIENT IDENTITY MANAGEMENT
    # ============================================================

    def generate_patient_id(self):
        """
        Generate a permanent Patient ID such as:
        P-000001
        P-000002
        P-000003
        """

        counter_ref = self.db.collection("Counters").document("patients")

        @firestore.transactional
        def update_counter(transaction):
            snapshot = counter_ref.get(transaction=transaction)

            if snapshot.exists:
                last_number = snapshot.to_dict().get("last_number", 0)
            else:
                last_number = 0

            new_number = last_number + 1

            transaction.set(
                counter_ref,
                {
                    "last_number": new_number
                },
                merge=True
            )

            return new_number

        transaction = self.db.transaction()
        new_number = update_counter(transaction)

        return f"P-{new_number:06d}"


    def normalize_patient_name(self, value):
        """
        Normalize a name so searching is less affected by:
        - uppercase/lowercase
        - extra spaces
        """

        if not value:
            return ""

        return " ".join(
            str(value).strip().lower().split()
        )


    def normalize_dentist_name(self, value):
        """
        Same normalization as normalize_patient_name, used to compare
        dentist names for double-booking checks. dentist_name is a free
        text field, so this keeps "Dr. Capizonda" and " dr. capizonda "
        matching as the same dentist.
        """

        if not value:
            return ""

        return " ".join(
            str(value).strip().lower().split()
        )


    def find_appointment_conflict(self, dentist_name, appointment_date, exclude_doc_id=None):
        """
        Check whether an already-ACCEPTED appointment (Approve collection)
        exists for the same dentist at the same date/time.

        Only checks confirmed appointments, not pending requests -- two
        pending requests can compete for the same slot, and the conflict
        only matters once one of them actually gets accepted.

        NOTE: this scans the Approve collection group in Python rather
        than filtering with a Firestore .where() clause, because a
        filtered collection-group query requires a composite index to be
        created in the Firebase console first. Scanning in Python avoids
        that extra deployment step (same approach adminDashboard() already
        uses to read this same collection), at the cost of being less
        efficient at very large scale.
        """

        dentist_name = self.normalize_dentist_name(dentist_name)
        appointment_date = str(appointment_date or "").strip()

        if not dentist_name or not appointment_date:
            return None

        try:
            # Narrow to only appointments at this exact date/time instead
            # of scanning the entire Approve collection group.
            # appointment_date comes from a fixed set of UI-selected time
            # slots (flatpickr date + dropdown time), not free-typed text,
            # so it's safe to filter on directly with no normalization
            # mismatch risk -- unlike DentistName, which IS free-typed and
            # still needs the Python-side normalize+compare below.
            approve_docs = list(
                self.db.collection_group("Approve")
                .where("appointment_date", "==", appointment_date)
                .stream()
            )
        except Exception as e:
            print("FIND APPOINTMENT CONFLICT ERROR:", e)
            return None

        for doc in approve_docs:

            if exclude_doc_id and doc.id == exclude_doc_id:
                continue

            data = doc.to_dict()

            existing_dentist = self.normalize_dentist_name(
                data.get("DentistName", "")
            )
            existing_date = str(data.get("appointment_date", "")).strip()

            if existing_dentist == dentist_name and existing_date == appointment_date:
                return {
                    "appointment_id": doc.id,
                    "patient_name": f"{data.get('FirstName','')} {data.get('LastName','')}".strip(),
                    "dentist_name": data.get("DentistName", ""),
                    "appointment_date": existing_date
                }

        return None


    def find_patient(
        self,
        first_name,
        middle_name,
        last_name,
        birthday=""
    ):
        """
        Search for an existing patient using fuzzy full-name matching.
        Filipino names are split inconsistently between walk-in entry
        and patient self-entry (compound/maternal surnames end up in
        different fields), so we compare token sets across the whole
        name instead of requiring an exact last-name match.
        """
        first_name = self.normalize_patient_name(first_name)
        middle_name = self.normalize_patient_name(middle_name)
        last_name = self.normalize_patient_name(last_name)
        birthday = str(birthday or "").strip()

        query_tokens = set(
            " ".join(p for p in [first_name, middle_name, last_name] if p).split()
        )

        if not query_tokens:
            return None

        patients_ref = self.db.collection(self.Doc_Patients)

        # Narrow candidates via targeted queries instead of scanning the
        # whole collection. A genuine match must share the query's
        # first_name_normalized or last_name_normalized with SOME stored
        # patient (even if Filipino naming means a surname landed in a
        # different field on their record), so querying both and merging
        # covers the same matches the old full scan found, at a fraction
        # of the reads. Each is a single-field equality filter, which
        # Firestore indexes automatically -- no composite index needed.
        candidate_docs = {}

        if last_name:
            for doc in patients_ref.where("last_name_normalized", "==", last_name).stream():
                candidate_docs[doc.id] = doc

        if first_name:
            for doc in patients_ref.where("first_name_normalized", "==", first_name).stream():
                candidate_docs[doc.id] = doc

        best_match = None
        best_score = 0.0

        for doc in candidate_docs.values():
            data = doc.to_dict()

            existing_tokens = set(
                " ".join(p for p in [
                    data.get("first_name_normalized", ""),
                    data.get("middle_name_normalized", ""),
                    data.get("last_name_normalized", "")
                ] if p).split()
            )

            if not existing_tokens:
                continue

            existing_birthday = str(data.get("birthday", "") or "").strip()

            # If both records have a birthday, it must match exactly.
            if birthday and existing_birthday and birthday != existing_birthday:
                continue

            overlap = query_tokens & existing_tokens
            if not overlap:
                continue

            # Score = overlap relative to the shorter name, so
            # "Althea Marie Roa" fully matches inside
            # "Althea Marie Prieto Roa".
            smaller_len = min(len(query_tokens), len(existing_tokens))
            score = len(overlap) / smaller_len

            if score >= 0.6 and score > best_score:
                best_score = score
                best_match = data
                best_match["patient_id"] = doc.id

        return best_match
    
    def get_identity_from_appointments(self, uid):
        """
        Look through the user's appointments and Approve records to find
        the most complete name and birthday they've used in their forms.
        """
        account_ref = self.db.collection(self.Customer_Account).document(uid)
        print(f"--- CHECKING APPOINTMENTS FOR UID: {uid} ---")
        
        # Check both pending appointments and approved ones
        for collection_name in ["appointments", "Approve"]:
            try:
                docs = account_ref.collection(collection_name).limit(5).stream()
                for doc in docs:
                    data = doc.to_dict()
                    first = str(data.get("FirstName", "")).strip()
                    middle = str(data.get("MiddleName", "")).strip()
                    last = str(data.get("LastName", "")).strip()
                    birthday = str(data.get("Birthday", "")).strip()
                    
                    print(f"Found appointment in '{collection_name}': {first} {middle} {last} (Bday: {birthday})")
                    
                    if first and last:
                        return {
                            "first_name": first,
                            "middle_name": middle,
                            "last_name": last,
                            "birthday": birthday
                        }
            except Exception as e:
                print(f"Error fetching {collection_name}: {e}")
                
        print("No appointments found for this user.")
        return None

    def is_slot_blocked(self, appointment_date):
        """
        appointment_date format: "YYYY-MM-DD HH:MM" (matches how it's stored everywhere else).
        Returns (True, reason) if the dentist has blocked this date/time, else (False, None).
        """
        date_str = str(appointment_date or "").strip()
        if not date_str:
            return False, None

        parts = date_str.split(" ", 1)
        day = parts[0]
        time = parts[1] if len(parts) > 1 else ""

        doc = self.db.collection(self.Blocked_Slots).document(day).get()
        if not doc.exists:
            return False, None

        data = doc.to_dict()

        if data.get("full_day"):
            return True, data.get("reason", "Dentist unavailable this day")

        if time in data.get("blocked_times", []):
            return True, data.get("reason", "Dentist unavailable at this time")

        return False, None


    def get_blocked_slots(self):
        try:
            docs = self.db.collection(self.Blocked_Slots).stream()
            result = []
            for doc in docs:
                data = doc.to_dict()
                result.append({
                    "date": doc.id,
                    "full_day": bool(data.get("full_day", False)),
                    "blocked_times": data.get("blocked_times", []),
                    "reason": data.get("reason", "")
                })
            return jsonify(result)
        except Exception as e:
            print("GET BLOCKED SLOTS ERROR:", e)
            return jsonify({"error": str(e)}), 500


    def admin_block_slot(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        date = bleach.clean(request.form.get("date", "").strip())
        full_day = request.form.get("full_day", "false") == "true"
        blocked_times = request.form.getlist("blocked_times[]")
        reason = bleach.clean(request.form.get("reason", "").strip())

        if not date:
            return jsonify({"success": False, "message": "Date is required"}), 400

        if not full_day and not blocked_times:
            return jsonify({
                "success": False,
                "message": "Select full day or at least one time slot"
            }), 400

        try:
            self.db.collection(self.Blocked_Slots).document(date).set({
                "date": date,
                "full_day": full_day,
                "blocked_times": [] if full_day else blocked_times,
                "reason": reason,
                "created_by": session.get('admin_uid', ''),
                "updated_at": datetime.now(UTC).isoformat()
            })
            return jsonify({"success": True, "message": "Slot blocked successfully"})
        except Exception as e:
            print("ADMIN BLOCK SLOT ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500


    def admin_unblock_slot(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        date = bleach.clean(request.form.get("date", "").strip())
        if not date:
            return jsonify({"success": False, "message": "Date is required"}), 400

        try:
            self.db.collection(self.Blocked_Slots).document(date).delete()
            return jsonify({"success": True, "message": "Slot unblocked successfully"})
        except Exception as e:
            print("ADMIN UNBLOCK SLOT ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500

    def create_patient(
        self,
        first_name,
        middle_name,
        last_name,
        birthday="",
        account_uid=None,
        created_by="system"
    ):
        """
        Create a new canonical patient record.

        The Patient ID is permanent and is NOT the Firebase Auth UID.
        """

        patient_id = self.generate_patient_id()

        first_name = str(first_name or "").strip()
        middle_name = str(middle_name or "").strip()
        last_name = str(last_name or "").strip()
        birthday = str(birthday or "").strip()

        patient_data = {
            "patient_id": patient_id,

            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,

            "first_name_normalized":
                self.normalize_patient_name(first_name),

            "middle_name_normalized":
                self.normalize_patient_name(middle_name),

            "last_name_normalized":
                self.normalize_patient_name(last_name),

            "birthday": birthday,

            # Optional Firebase account.
            # A patient does NOT need an account.
            "account_uid": account_uid,

            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat()
        }

        self.db.collection(
            self.Doc_Patients
        ).document(patient_id).set(patient_data)

        self._invalidate_patients_cache()

        return patient_id
    
    def merge_patient_accounts(self, source_uid, target_uid):
        """
        Move a walk-in placeholder account's appointment/treatment data into
        the patient's real (logged-in) account, then delete the placeholder.

        Only ever call this with source_uid being a temporary "walkin_*"
        account — never merge two real login accounts automatically.
        """
        source_ref = self.db.collection(self.Customer_Account).document(source_uid)
        target_ref = self.db.collection(self.Customer_Account).document(target_uid)

        for sub_name in (self.Appointment_cliets, "Approve", "Done_procedure"):
            docs = list(source_ref.collection(sub_name).stream())
            for doc in docs:
                data = doc.to_dict()
                # Use .add() (new auto-ID) rather than reusing doc.id, since
                # nothing else in the app persists these subcollection doc IDs
                # outside of a single request/response cycle.
                target_ref.collection(sub_name).add(data)
                doc.reference.delete()

        # NEW: refresh the cached history flag + latest approved date on the
        # target account, since its subcollections just changed. This runs
        # once per merge (a rare event), so a few extra queries here is fine.
        has_approve = any(True for _ in target_ref.collection("Approve").limit(1).stream())
        has_done = any(True for _ in target_ref.collection("Done_procedure").limit(1).stream())

        latest_accepted = None
        for a in target_ref.collection("Approve").stream():
            accepted_at = a.to_dict().get("accepted_at", "")
            if accepted_at and (latest_accepted is None or accepted_at > latest_accepted):
                latest_accepted = accepted_at

        target_ref.update({
            "has_history": has_approve or has_done,
            "last_approved_at": latest_accepted or ""
        })

        source_ref.delete()
        self._invalidate_financial_cache()
        self._invalidate_accounts_cache()
        self._invalidate_patients_cache()
        print(f"✅ Merged walk-in account {source_uid} into {target_uid} and removed the placeholder.")


    def get_or_create_patient(
        self,
        first_name,
        middle_name,
        last_name,
        birthday="",
        account_uid=None,
        created_by="system"
    ):
        """
        Find an existing patient first.

        If the patient does not exist, create a new Patient ID.
        """

        existing_patient = self.find_patient(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            birthday=birthday
        )

        if existing_patient:
            patient_id = existing_patient["patient_id"]

            # Link Firebase account if one is now available
            # and the patient doesn't already have one.
            if account_uid and not existing_patient.get("account_uid"):
                self.db.collection(
                    self.Doc_Patients
                ).document(patient_id).update({
                    "account_uid": account_uid
                })
                self._invalidate_patients_cache()

            return patient_id

        return self.create_patient(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            birthday=birthday,
            account_uid=account_uid,
            created_by=created_by
        )

    def _setup_paymongo(self):
        self.pay_mongo_secret_key = "sk_live_FsYAsKA47Wg6HzcSzbxWWYwW"
        self.pay_mongo_public_key = "pk_live_ZaZrhPCe8d6fz7n5dZXNEebc"
        self.PAYMONGO_WEBHOOK_SECRET="whsk_SDS3prtXoFa8MCg5FPh9wfEc"

    def _setup_session(self):
        @self.app.before_request
        def refresh_session():
            # Skip static files (css, js, images) — no need to touch session
            if request.endpoint == 'static':
                return

            session.permanent = True

            # Admin timeout check
            if session.get('admin_logged_in'):
                last_activity = session.get('admin_last_activity')
                if last_activity:
                    try:
                        last_active = datetime.fromisoformat(last_activity)
                        if datetime.now(UTC) - last_active > timedelta(hours=8):
                            session.clear()
                            flash("Admin session expired. Please log in again.", "error")
                            return redirect(url_for("adminLogin"))
                    except (ValueError, TypeError):
                        session.clear()
                        return redirect(url_for("adminLogin"))

                session['admin_last_activity'] = datetime.now(UTC).isoformat()
                # No session.modified needed — assigning a value already marks it dirty

    def _register_routes(self):
        """Polymorphism: Register all routes"""
        pass


    def require_firebase(self):
        if db is None:
            raise RuntimeError("Firebase is not initialized. Check dentech_key.json")
    
    def update_payment_status(self, patient_uid, procedure):

        try:

            print("========================================")
            print("UPDATING PAYMENT STATUS")
            print("PATIENT UID:", patient_uid)
            print("PROCEDURE:", procedure)
            print("========================================")

            # -----------------------------------------------------
            # FIND PATIENT
            # -----------------------------------------------------

            user_ref = (
                self.db
                .collection(self.Customer_Account)
                .document(str(patient_uid))
            )

            user_doc = user_ref.get()

            print("PATIENT DOCUMENT PATH:", user_ref.path)
            print("PATIENT EXISTS:", user_doc.exists)

            if not user_doc.exists:

                print("❌ PATIENT NOT FOUND")
                print("UID:", patient_uid)

                return False

            # -----------------------------------------------------
            # GET DONE PROCEDURES
            # -----------------------------------------------------

            done_ref = user_ref.collection("Done_procedure")

            done_procedures = list(
                done_ref.stream()
            )

            print(
                "DONE PROCEDURE DOCUMENT COUNT:",
                len(done_procedures)
            )

            if not done_procedures:

                print("❌ NO Done_procedure DOCUMENTS FOUND")

                return False

            # -----------------------------------------------------
            # SEARCH PROCEDURES
            # -----------------------------------------------------

            target_procedure = str(
                procedure
            ).strip().lower()

            print(
                "TARGET PROCEDURE:",
                repr(target_procedure)
            )

            for proc_doc in done_procedures:

                proc_data = proc_doc.to_dict()

                print("----------------------------------------")
                print(
                    "DOCUMENT:",
                    proc_doc.id
                )

                print(
                    "DOCUMENT DATA:",
                    proc_data
                )

                procedures = proc_data.get(
                    "procedures",
                    []
                )

                print(
                    "PROCEDURES:",
                    procedures
                )

                # Make sure procedures is a list
                if not isinstance(procedures, list):

                    print(
                        "❌ 'procedures' is not a list"
                    )

                    continue

                for index, p in enumerate(procedures):

                    if not isinstance(p, dict):

                        print(
                            "❌ PROCEDURE ITEM IS NOT A DICT:",
                            p
                        )

                        continue

                    current_procedure = str(
                        p.get(
                            "procedure",
                            ""
                        )
                    ).strip().lower()

                    current_status = str(
                        p.get(
                            "status",
                            ""
                        )
                    ).strip()

                    print("----------------------------------------")
                    print(
                        "INDEX:",
                        index
                    )

                    print(
                        "STORED PROCEDURE:",
                        repr(current_procedure)
                    )

                    print(
                        "PAYMENT PROCEDURE:",
                        repr(target_procedure)
                    )

                    print(
                        "CURRENT STATUS:",
                        repr(current_status)
                    )

                    # -------------------------------------------------
                    # MATCH
                    # -------------------------------------------------

                    if current_procedure == target_procedure:

                        print("✅ PROCEDURE MATCH FOUND")

                        # Already paid
                        if current_status.lower() == "paid":

                            print(
                                "PROCEDURE IS ALREADY PAID"
                            )

                            return True

                        # -------------------------------------------------
                        # GET VALUE
                        # -------------------------------------------------

                        value = self.safe_float(
                            p.get(
                                "value",
                                0
                            )
                        )
                        
                        old_paid = self.safe_float(p.get("paid", 0))
                        old_balance = self.safe_float(p.get("balance", 0))
                        
                        print(
                            "PROCEDURE VALUE:",
                            value
                        )

                        # -------------------------------------------------
                        # UPDATE PROCEDURE
                        # -------------------------------------------------

                        procedures[index]["status"] = "Paid"

                        procedures[index]["paid"] = value

                        procedures[index]["balance"] = 0

                        # -------------------------------------------------
                        # SAVE FIRESTORE
                        # -------------------------------------------------

                        print(
                            "SAVING TO FIRESTORE..."
                        )

                        proc_doc.reference.update({

                            "procedures": procedures,

                            "updated_at":
                                firestore.SERVER_TIMESTAMP

                        })
                        # NEW: incrementally update cached financial stats
                        self.db.collection("Stats").document("financial_summary").set({
                            "total_income": firestore.Increment(value - old_paid),
                            "total_outstanding": firestore.Increment(-old_balance),
                            "unpaid_procedures": firestore.Increment(-1)
                        }, merge=True)
                        
                        print("========================================")
                        print("✅ PAYMENT UPDATED SUCCESSFULLY")
                        print("DOCUMENT:", proc_doc.id)
                        print("PROCEDURE:", current_procedure)
                        print("STATUS: Paid")
                        print("PAID:", value)
                        print("BALANCE: 0")
                        print("========================================")

                        return True

            # -----------------------------------------------------
            # NO MATCH
            # -----------------------------------------------------

            print("========================================")
            print("❌ NO MATCHING PROCEDURE FOUND")
            print("PATIENT:", patient_uid)
            print("PROCEDURE:", procedure)
            print("========================================")

            return False

        except Exception as e:

            print("========================================")
            print("❌ ERROR UPDATING PAYMENT STATUS")
            print("ERROR:", str(e))
            print("========================================")

            return False

        
    def payment_success(self):

        # =========================================================
        # GET DATA FROM URL
        # =========================================================

        checkout_session_id = request.args.get(
            "checkout_session_id",
            ""
        ).strip()

        patient_uid = request.args.get(
            "uid",
            ""
        ).strip()

        procedure = request.args.get(
            "procedure",
            ""
        ).strip()

        # =========================================================
        # FALLBACK TO FLASK SESSION
        # =========================================================

        if not checkout_session_id:

            checkout_session_id = session.get(
                "paymongo_checkout_session_id",
                ""
            )

        if not patient_uid:

            patient_uid = session.get(
                "paymongo_patient_uid",
                ""
            )

        if not procedure:

            procedure = session.get(
                "paymongo_procedure",
                ""
            )

        print("========================================")
        print("PAYMENT SUCCESS")
        print("CHECKOUT SESSION:", checkout_session_id)
        print("PATIENT UID:", patient_uid)
        print("PROCEDURE:", procedure)
        print("========================================")

        # =========================================================
        # CHECK REQUIRED DATA
        # =========================================================

        if not checkout_session_id:

            print(
                "ERROR: CHECKOUT SESSION ID NOT FOUND"
            )

            flash(
                "Payment could not be verified because "
                "the PayMongo checkout session was not found.",
                "error"
            )

            return redirect(
                url_for("index")
            )

        if not patient_uid or not procedure:

            print(
                "ERROR: PATIENT UID OR PROCEDURE MISSING"
            )

            flash(
                "Payment information is incomplete.",
                "error"
            )

            return redirect(
                url_for("index")
            )

        try:

            # =====================================================
            # PAYMONGO AUTHENTICATION
            # =====================================================

            auth = base64.b64encode(
                f"{self.pay_mongo_secret_key}:".encode()
            ).decode()

            headers = {
                "accept": "application/json",
                "authorization": f"Basic {auth}"
            }

            # =====================================================
            # GET CHECKOUT SESSION
            # =====================================================

            url = (
                "https://api.paymongo.com/v1/"
                f"checkout_sessions/"
                f"{checkout_session_id}"
            )

            r = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            print(
                "PAYMONGO HTTP STATUS:",
                r.status_code
            )

            print(
                "PAYMONGO RESPONSE:",
                r.text
            )

            if r.status_code != 200:

                flash(
                    "Unable to verify payment with PayMongo.",
                    "error"
                )

                return redirect(
                    url_for("index")
                )

            result = r.json()

            session_data = (
                result
                .get("data", {})
                .get("attributes", {})
            )

            # =====================================================
            # CHECK PAYMENTS
            # =====================================================

            payments = session_data.get(
                "payments",
                []
            )

            payment_paid = False

            for payment in payments:

                payment_attributes = (
                    payment.get(
                        "attributes",
                        {}
                    )
                )

                payment_status = str(
                    payment_attributes.get(
                        "status",
                        ""
                    )
                ).lower().strip()

                print(
                    "PAYMENT ID:",
                    payment.get("id")
                )

                print(
                    "PAYMENT STATUS:",
                    payment_status
                )

                if payment_status == "paid":

                    payment_paid = True

                    break

            # =====================================================
            # PAYMENT SUCCESSFUL
            # =====================================================

            if payment_paid:

                print("========================================")
                print("PAYMENT CONFIRMED AS PAID")
                print("PATIENT UID:", patient_uid)
                print("PROCEDURE:", procedure)
                print("========================================")

                updated = self.update_payment_status(
                    patient_uid,
                    procedure
                )

                if updated:

                    print(
                        "FIRESTORE PAYMENT STATUS UPDATED"
                    )

                    flash(
                        "Payment successful! "
                        "Your payment status is now Paid.",
                        "success"
                    )

                    # Clear temporary payment session data
                    session.pop(
                        "paymongo_checkout_session_id",
                        None
                    )

                    session.pop(
                        "paymongo_patient_uid",
                        None
                    )

                    session.pop(
                        "paymongo_procedure",
                        None
                    )

                else:

                    print(
                        "PAYMENT WAS PAID BUT FIRESTORE "
                        "UPDATE FAILED"
                    )

                    flash(
                        "Payment was successful, but "
                        "the dental record could not be updated.",
                        "warning"
                    )

            else:

                print(
                    "PAYMENT NOT CONFIRMED AS PAID"
                )

                flash(
                    "PayMongo has not confirmed the payment yet.",
                    "info"
                )

        except Exception as e:

            print("========================================")
            print("ERROR VERIFYING PAYMENT:")
            print(str(e))
            print("========================================")

            flash(
                "Could not verify payment status.",
                "error"
            )

        return redirect(
            url_for("index")
        )


    def payment_cancel(self):
        flash("Payment was cancelled or expired.", "error")
        return redirect(url_for("index"))
    
    

    def paymongo_webhook(self):

        try:

            print("========================================")
            print("PAYMONGO WEBHOOK RECEIVED")
            print("========================================")

            event = request.json

            print("FULL WEBHOOK DATA:")
            print(event)

            # ============================================
            # GET EVENT ATTRIBUTES
            # ============================================

            attributes = (
                event
                .get("data", {})
                .get("attributes", {})
            )

            event_type = attributes.get(
                "type",
                ""
            )

            print("EVENT TYPE:", event_type)

            # ============================================
            # PAYMONGO SUCCESSFUL PAYMENT
            # ============================================

            if event_type == "checkout_session.payment.paid":

                session_data = (
                    attributes
                    .get("data", {})
                )

                session_attrs = (
                    session_data
                    .get("attributes", {})
                )

                # ========================================
                # GET METADATA
                # ========================================

                metadata = (
                    session_attrs
                    .get("metadata", {})
                )

                patient_uid = str(
                    metadata.get(
                        "patient_uid",
                        ""
                    )
                ).strip()

                procedure = str(
                    metadata.get(
                        "procedure",
                        ""
                    )
                ).strip()

                print("========================================")
                print("PAYMENT SUCCESSFUL")
                print("PATIENT UID:", patient_uid)
                print("PROCEDURE:", procedure)
                print("========================================")

                # ========================================
                # VALIDATE DATA
                # ========================================

                if not patient_uid:

                    print(
                        "ERROR: PATIENT UID IS MISSING"
                    )

                    return "", 200

                if not procedure:

                    print(
                        "ERROR: PROCEDURE IS MISSING"
                    )

                    return "", 200

                # ========================================
                # UPDATE FIRESTORE
                # ========================================

                updated = self.update_payment_status(
                    patient_uid,
                    procedure
                )

                if updated:

                    print("========================================")
                    print("FIRESTORE PAYMENT UPDATE SUCCESSFUL")
                    print("PATIENT UID:", patient_uid)
                    print("PROCEDURE:", procedure)
                    print("STATUS: Paid")
                    print("BALANCE: 0")
                    print("========================================")

                else:

                    print("========================================")
                    print("FIRESTORE UPDATE FAILED")
                    print("NO MATCHING UNPAID PROCEDURE FOUND")
                    print("PATIENT UID:", patient_uid)
                    print("PROCEDURE:", procedure)
                    print("========================================")

            else:

                print(
                    "IGNORED WEBHOOK EVENT:",
                    event_type
                )

        except Exception as e:

            print("========================================")
            print("PAYMONGO WEBHOOK ERROR")
            print(str(e))
            print("========================================")

        # Always tell PayMongo we received the webhook
        return "", 200




    
    def create_gcash_payment(self):
        try:

            data = request.json

            amount = int(
                float(data.get("amount", 0)) * 100
            )

            procedure = str(
                data.get("procedure", "")
            ).strip()

            patient_uid = str(
                data.get("uid", "")
            ).strip()

            print("========================================")
            print("CREATING GCASH PAYMENT")
            print("PATIENT UID:", patient_uid)
            print("PROCEDURE:", procedure)
            print("AMOUNT:", amount / 100)
            print("========================================")

            # =====================================================
            # VALIDATION
            # =====================================================

            if not patient_uid:
                return {"error": "Patient UID is required"}

            if not procedure:
                return {"error": "Procedure is required"}

            if amount <= 0:
                return {"error": "Invalid payment amount"}

            # =====================================================
            # PATIENT INFORMATION
            # =====================================================

            patient_email = session.get(
                "email",
                "patient@example.com"
            )

            patient_name = session.get(
                "name",
                "Dental Patient"
            )

            # =====================================================
            # PAYMENT URL
            # =====================================================

            base_url = request.host_url.rstrip("/")

            success_url = (
                f"{base_url}/payment-success"
                f"?uid={patient_uid}"
                f"&procedure={procedure}"
            )

            cancel_url = (
                f"{base_url}/payment-cancel"
            )

            # =====================================================
            # PAYMONGO AUTHENTICATION
            # =====================================================

            auth = base64.b64encode(
                f"{self.pay_mongo_secret_key}:".encode()
            ).decode()

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Basic {auth}"
            }

            # =====================================================
            # PAYMONGO DATA
            # =====================================================

            payload = {
                "data": {
                    "attributes": {

                        "billing": {
                            "name": patient_name,
                            "email": patient_email
                        },

                        "line_items": [
                            {
                                "currency": "PHP",
                                "amount": amount,
                                "name": procedure,
                                "quantity": 1
                            }
                        ],

                        "payment_method_types": [
                            "qrph"
                        ],

                        "success_url": success_url,

                        "cancel_url": cancel_url,

                        "metadata": {
                            "patient_uid": patient_uid,
                            "procedure": procedure
                        }
                    }
                }
            }

            # =====================================================
            # CREATE PAYMONGO CHECKOUT
            # =====================================================

            r = requests.post(
                "https://api.paymongo.com/v1/checkout_sessions",
                headers=headers,
                json=payload,
                timeout=30
            )

            result = r.json()

            print("PAYMONGO HTTP STATUS:", r.status_code)
            print("PAYMONGO RESPONSE:")
            print(result)

            # =====================================================
            # CHECK RESPONSE
            # =====================================================

            if r.status_code not in (200, 201):

                return {
                    "error": (
                        result
                        .get("errors", [{}])[0]
                        .get(
                            "detail",
                            "Failed to create payment session"
                        )
                    )
                }

            if "data" not in result:

                return {
                    "error": "PayMongo did not return a checkout session"
                }

            # =====================================================
            # GET CHECKOUT SESSION ID
            # =====================================================

            checkout_session_id = result["data"].get("id")

            checkout_url = (
                result["data"]
                .get("attributes", {})
                .get("checkout_url")
            )

            print("========================================")
            print("CHECKOUT SESSION CREATED")
            print("CHECKOUT SESSION ID:", checkout_session_id)
            print("CHECKOUT URL:", checkout_url)
            print("========================================")

            if not checkout_session_id:
                return {
                    "error": "Checkout session ID was not returned"
                }

            if not checkout_url:
                return {
                    "error": "Checkout URL was not returned"
                }

            # =====================================================
            # SAVE CHECKOUT SESSION ID
            # =====================================================

            session["paymongo_checkout_session_id"] = (
                checkout_session_id
            )

            session["paymongo_patient_uid"] = patient_uid

            session["paymongo_procedure"] = procedure

            session.modified = True

            print(
                "PAYMONGO SESSION ID SAVED:",
                checkout_session_id
            )

            # =====================================================
            # RETURN CHECKOUT URL
            # =====================================================

            return {
                "checkout_url": checkout_url,
                "checkout_session_id": checkout_session_id
            }

        except Exception as e:

            print("========================================")
            print("CREATE GCASH PAYMENT ERROR:")
            print(str(e))
            print("========================================")

            return {
                "error": str(e)
            }
    def refresh_session(self):
        session.permanent = True
        session.modified = True
    

    def index(self):
        uid = session.get('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
    
        if uid and email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            if user_query:
                profile_pic = user_query[0].to_dict().get('profile_pic', '')
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    profile_pic = user_query[0].to_dict().get('profile_pic', '')
    
        pending_match = session.pop('pending_patient_match', None)
        return render_template("index.html", uid=uid, name=name, email=email,
                            profile_pic=profile_pic, pending_match=pending_match)
    
    
    

    def google_index(self):
        uid = session.get ('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
    
        if uid and email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            if user_query:
                profile_pic = user_query[0].to_dict().get('profile_pic', '')
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    profile_pic = user_query[0].to_dict().get('profile_pic', '')
    
        pending_match = session.pop('pending_patient_match', None)
        return render_template("index.html", uid=uid, name=name, email=email,
                            profile_pic=profile_pic, pending_match=pending_match)
    
    

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
            error_msg = "Incorrect email or password."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": error_msg}), 401
            flash(error_msg, "error")
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
            error_msg = "Unable to verify your account."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": error_msg}), 401
            flash(error_msg, "error")
            return redirect(url_for("index"))

        lookup_data = lookup_resp.json()

        verified = lookup_data["users"][0]["emailVerified"]

        if not verified:
            error_msg = "Please verify your email first."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": error_msg}), 401
            flash(error_msg, "error")
            return redirect(url_for("index"))

        uid = lookup_data["users"][0]["localId"]

        # Get user data from Firestore
        user_doc = self.db.collection(self.Customer_Account).document(uid).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}

        if user_data.get("disabled"):
            error_msg = "Your account has been disabled by the administrator. Please contact the clinic for assistance."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": error_msg}), 403
            flash(error_msg, "error")
            return redirect(url_for("index"))

        session["name"] = user_data.get("firstname", "")
        session["email"] = email
        session["uid"] = uid
        
        self.maybe_flag_patient_match(
            uid, 
            user_data.get("firstname", ""), 
            user_data.get("lastname", ""),
            user_data.get("middlename", ""),
            user_data.get("birthday", "")
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "redirect": url_for("index")})

        flash(f"Welcome back, {user_data.get('firstname', '')}!", "success")
        return redirect(url_for("index"))


    def login_g_auth(self):
        token = request.form["token"]
        try:
            google_account = id_token.verify_oauth2_token(token, google_requests.Request(), self.CLIENT_ID)
            uid = google_account["sub"]

            account_ref = self.db.collection(self.Customer_Account).document(uid)
            existing_doc = account_ref.get()
            existing_data = existing_doc.to_dict() if existing_doc.exists else {}

            if existing_data.get("disabled"):
                return render_template(
                    "error.html",
                    message="Your account has been disabled by the administrator. Please contact the clinic for assistance."
                )

            session['uid'] = uid
            session['email'] = google_account["email"]
            session['name'] = google_account.get("name", "User")

            update_data = {
                "uid": session['uid'],
                "email": session['email'],
                "name": session['name'],
                "provider": "google",
                "last_login": datetime.now(UTC).isoformat()
            }

            # Only set created_at on the very first login for this account
            if not existing_doc.exists or not existing_data.get("created_at"):
                update_data["created_at"] = datetime.now(UTC).isoformat()

            account_ref.set(update_data, merge=True)
            
            # --- NEW: Try to get identity from appointments first ---
            identity = self.get_identity_from_appointments(session['uid'])
            
            if identity:
                # Use the real name from their appointment form
                self.maybe_flag_patient_match(
                    session['uid'],
                    identity["first_name"],
                    identity["last_name"],
                    identity["middle_name"],
                    identity["birthday"]
                )
            else:
                # Fallback to Google name if they haven't booked yet
                name_parts = session['name'].strip().split(" ", 1)
                guess_first = name_parts[0] if name_parts else ""
                guess_last = name_parts[1] if len(name_parts) > 1 else ""
                self.maybe_flag_patient_match(session['uid'], guess_first, guess_last)
                
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
                self._invalidate_accounts_cache()

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
    
    def link_patient_account(self):
        if not session.get('uid'):
            return jsonify({"success": False, "message": "Not logged in"}), 401

        confirm = request.form.get("confirm", "false") == "true"
        match = session.pop('pending_patient_match', None)
        if not match:
            return jsonify({"success": False, "message": "No pending match"}), 400

        if not confirm:
            return jsonify({"success": True, "linked": False})

        uid = session['uid']
        patient_id = match["patient_id"]

        try:
            patient_ref = self.db.collection(self.Doc_Patients).document(patient_id)
            patient_doc = patient_ref.get()
            if not patient_doc.exists:
                return jsonify({"success": False, "message": "Patient record no longer exists"}), 404

            old_account_uid = patient_doc.to_dict().get("account_uid") or ""

            # If the patient's canonical record was tied to a temporary
            # walk-in account, fold that account's real history into the
            # account the patient is actually logged in with.
            if old_account_uid and old_account_uid != uid and old_account_uid.startswith("walkin_"):
                self.merge_patient_accounts(old_account_uid, uid)

            # Clean up any other duplicate Patients docs already linked to this uid
            duplicate_query = self.db.collection(self.Doc_Patients).where("account_uid", "==", uid).stream()
            for dup_doc in duplicate_query:
                if dup_doc.id != patient_id:
                    print(f"🗑️ Deleting duplicate patient record: {dup_doc.id}")
                    dup_doc.reference.delete()

            patient_ref.update({"account_uid": uid})
            self._invalidate_patients_cache()

            return jsonify({"success": True, "linked": True})
        except Exception as e:
            print("LINK PATIENT ACCOUNT ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500
    

    def p_forms(self):
        return render_template("patientForms.html")
    

    def about_customer(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
        uid = session.get('uid', '')
    
        if uid and email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            if user_query:
                profile_pic = user_query[0].to_dict().get('profile_pic', '')
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    profile_pic = user_query[0].to_dict().get('profile_pic', '')
    
        return render_template("about.html", name=name, email=email, profile_pic=profile_pic)
    
    
    def google_bookedCustomer(self):
        uid = session.get('uid')
        email = session.get('email')

        # ---------------------------------------------------------
        # PERSONAL INFORMATION
        # ---------------------------------------------------------

        FirstName = bleach.clean(
            request.form.get("First_Name", "").strip()
        )

        MiddleName = bleach.clean(
            request.form.get("Middle_Name", "").strip()
        )

        LastName = bleach.clean(
            request.form.get("Last_Name", "").strip()
        )

        HouseNo = bleach.clean(
            request.form.get("House_No", "")
        )

        Street = bleach.clean(
            request.form.get("Street", "")
        )

        Brgy = bleach.clean(
            request.form.get("Brgy", "")
        )

        Municipality = bleach.clean(
            request.form.get("Municipality", "")
        )

        City = bleach.clean(
            request.form.get("City", "")
        )

        Nationality = bleach.clean(
            request.form.get("Nationality", "")
        )

        Religion = bleach.clean(
            request.form.get("Religion", "")
        )

        Age = bleach.clean(
            request.form.get("Age", "")
        )

        Sex = bleach.clean(
            request.form.get("Sex", "")
        )

        ContactNumber = bleach.clean(
            request.form.get("Contact_number", "")
        )

        Birthday = bleach.clean(
            request.form.get("Birthday", "").strip()
        )

        Occupation = bleach.clean(
            request.form.get("Occupation", "")
        )

        CivilStatus = bleach.clean(
            request.form.get("Civil_Status", "")
        )

        Service = bleach.clean(
            request.form.get("Service", "")
        )

        UrgencyLevel = bleach.clean(
            request.form.get("Urgency_Level", "")
        )

        appointment_date = bleach.clean(
            request.form.get("appointment_date", "")
        )

        # ---------------------------------------------------------
        # MEDICAL QUESTIONS
        # ---------------------------------------------------------

        q1 = bleach.clean(request.form.get("q1", ""))
        q2 = bleach.clean(request.form.get("q2", ""))
        q3 = bleach.clean(request.form.get("q3", ""))
        q4 = bleach.clean(request.form.get("q4", ""))
        q5 = bleach.clean(request.form.get("q5", ""))
        q6 = bleach.clean(request.form.get("q6", ""))
        q7 = bleach.clean(request.form.get("q7", ""))
        q9 = bleach.clean(request.form.get("q9", ""))

        q2_spec = bleach.clean(
            request.form.get("q2_spec", "")
        )

        q3_spec = bleach.clean(
            request.form.get("q3_spec", "")
        )

        q4_spec = bleach.clean(
            request.form.get("q4_spec", "")
        )

        q5_spec = bleach.clean(
            request.form.get("q5_spec", "")
        )

        q7_spec = bleach.clean(
            request.form.get("q7_spec", "")
        )

        q9_spec = bleach.clean(
            request.form.get("q9_spec", "")
        )

        w_preg = request.form.get("w_preg", "")
        w_nurse = request.form.get("w_nurse", "")
        w_pill = request.form.get("w_pill", "")

        # ---------------------------------------------------------
        # VALIDATE PATIENT
        # ---------------------------------------------------------

        if not FirstName or not LastName:
            flash(
                "First name and last name are required.",
                "error"
            )
            return redirect(url_for("index"))
        
        blocked, block_reason = self.is_slot_blocked(appointment_date)
        if blocked:
            flash(
                f"Sorry, that date/time is unavailable ({block_reason}). Please choose another slot.",
                "error"
            )
            return redirect(url_for("google_index"))
        

        # ---------------------------------------------------------
        # FIND OR CREATE CANONICAL PATIENT
        # ---------------------------------------------------------
        #
        # The Firebase UID belongs to the account.
        #
        # The Patient ID belongs to the actual patient.
        #
        # They are intentionally separate.
        #

        try:

            patient_id = self.get_or_create_patient(
                first_name=FirstName,
                middle_name=MiddleName,
                last_name=LastName,
                birthday=Birthday,
                account_uid=uid,
                created_by="google_booking"
            )

        except Exception as e:

            print(
                "GOOGLE PATIENT IDENTITY ERROR:",
                e
            )

            flash(
                "There was an error creating the patient record.",
                "error"
            )

            return redirect(url_for("index"))
        
        # =====================================================
        # FIX: FORCE UPDATE ACCOUNT_UID AND MERGE OLD HISTORY
        # =====================================================
        patient_ref = self.db.collection(self.Doc_Patients).document(patient_id)
        patient_doc = patient_ref.get()
        if patient_doc.exists:
            old_uid = patient_doc.to_dict().get("account_uid", "")
            # If the patient record was pointing to a temporary walk-in account,
            # merge that old history into their real logged-in account.
            if old_uid and old_uid != uid and old_uid.startswith("walkin_"):
                self.merge_patient_accounts(old_uid, uid)
            # Always ensure the canonical record points to the current session UID
            patient_ref.update({"account_uid": uid})
            self._invalidate_patients_cache()

        # ---------------------------------------------------------
        # SAVE APPOINTMENT
        # ---------------------------------------------------------
        #
        # We are still using the existing location:
        #
        # Customer_Account/{uid}/appointments
        #
        # because other parts of the current application still
        # depend on this structure.
        #
        # But the appointment now has:
        #
        # patient_id = P-000001
        #

        try:

            self.db.collection(
                self.Customer_Account
            ).document(
                uid
            ).collection(
                self.Appointment_cliets
            ).add({

                # NEW CANONICAL ID
                "patient_id": patient_id,

                # KEEP LEGACY ACCOUNT ID FOR NOW
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

            flash(
                "Appointment successfully booked!",
                "success"
            )

        except Exception as e:

            print(
                f"Error adding Google appointment: {e}"
            )

            flash(
                "There was an error booking your appointment.",
                "error"
            )

        return redirect(url_for("index"))
    
    
    def bookedCustomer(self):
        uid = session.get('uid')
        email = session.get('email')

        # ---------------------------------------------------------
        # PERSONAL INFORMATION
        # ---------------------------------------------------------

        FirstName = bleach.clean(
            request.form.get("First_Name", "").strip()
        )

        MiddleName = bleach.clean(
            request.form.get("Middle_Name", "").strip()
        )

        LastName = bleach.clean(
            request.form.get("Last_Name", "").strip()
        )

        HouseNo = bleach.clean(
            request.form.get("House_No", "")
        )

        Street = bleach.clean(
            request.form.get("Street", "")
        )

        Brgy = bleach.clean(
            request.form.get("Brgy", "")
        )

        Municipality = bleach.clean(
            request.form.get("Municipality", "")
        )

        City = bleach.clean(
            request.form.get("City", "")
        )

        Nationality = bleach.clean(
            request.form.get("Nationality", "")
        )

        Religion = bleach.clean(
            request.form.get("Religion", "")
        )

        Age = bleach.clean(
            request.form.get("Age", "")
        )

        Sex = bleach.clean(
            request.form.get("Sex", "")
        )

        ContactNumber = bleach.clean(
            request.form.get("Contact_number", "")
        )

        Birthday = bleach.clean(
            request.form.get("Birthday", "").strip()
        )

        Occupation = bleach.clean(
            request.form.get("Occupation", "")
        )

        CivilStatus = bleach.clean(
            request.form.get("Civil_Status", "")
        )

        Service = bleach.clean(
            request.form.get("Service", "")
        )

        UrgencyLevel = bleach.clean(
            request.form.get("Urgency_Level", "")
        )

        appointment_date = bleach.clean(
            request.form.get("appointment_date", "")
        )

        # ---------------------------------------------------------
        # MEDICAL QUESTIONS
        # ---------------------------------------------------------

        q1 = bleach.clean(request.form.get("q1", ""))
        q2 = bleach.clean(request.form.get("q2", ""))
        q3 = bleach.clean(request.form.get("q3", ""))
        q4 = bleach.clean(request.form.get("q4", ""))
        q5 = bleach.clean(request.form.get("q5", ""))
        q6 = bleach.clean(request.form.get("q6", ""))
        q7 = bleach.clean(request.form.get("q7", ""))
        q9 = bleach.clean(request.form.get("q9", ""))

        q2_spec = bleach.clean(
            request.form.get("q2_spec", "")
        )

        q3_spec = bleach.clean(
            request.form.get("q3_spec", "")
        )

        q4_spec = bleach.clean(
            request.form.get("q4_spec", "")
        )

        q5_spec = bleach.clean(
            request.form.get("q5_spec", "")
        )

        q7_spec = bleach.clean(
            request.form.get("q7_spec", "")
        )

        q9_spec = bleach.clean(
            request.form.get("q9_spec", "")
        )

        w_preg = request.form.get("w_preg", "")
        w_nurse = request.form.get("w_nurse", "")
        w_pill = request.form.get("w_pill", "")

        # ---------------------------------------------------------
        # VALIDATE PATIENT
        # ---------------------------------------------------------

        if not FirstName or not LastName:
            flash(
                "First name and last name are required.",
                "error"
            )
            return redirect(url_for("index"))
        
        
        blocked, block_reason = self.is_slot_blocked(appointment_date)
        if blocked:
            flash(
                f"Sorry, that date/time is unavailable ({block_reason}). Please choose another slot.",
                "error"
            )
            return redirect(url_for("index"))

        # ---------------------------------------------------------
        # FIND OR CREATE CANONICAL PATIENT
        # ---------------------------------------------------------

        try:

            patient_id = self.get_or_create_patient(
                first_name=FirstName,
                middle_name=MiddleName,
                last_name=LastName,
                birthday=Birthday,
                account_uid=uid,
                created_by="online_booking"
            )

        except Exception as e:

            print(
                "PATIENT IDENTITY ERROR:",
                e
            )

            flash(
                "There was an error creating the patient record.",
                "error"
            )

            return redirect(url_for("index"))
        
        # =====================================================
        # FIX: FORCE UPDATE ACCOUNT_UID AND MERGE OLD HISTORY
        # =====================================================
        patient_ref = self.db.collection(self.Doc_Patients).document(patient_id)
        patient_doc = patient_ref.get()
        if patient_doc.exists:
            old_uid = patient_doc.to_dict().get("account_uid", "")
            # If the patient record was pointing to a temporary walk-in account,
            # merge that old history into their real logged-in account.
            if old_uid and old_uid != uid and old_uid.startswith("walkin_"):
                self.merge_patient_accounts(old_uid, uid)
            # Always ensure the canonical record points to the current session UID
            patient_ref.update({"account_uid": uid})

        # ---------------------------------------------------------
        # SAVE APPOINTMENT
        # ---------------------------------------------------------

        try:

            self.db.collection(
                self.Customer_Account
            ).document(
                uid
            ).collection(
                self.Appointment_cliets
            ).add({

                # NEW CANONICAL PATIENT ID
                "patient_id": patient_id,

                # KEEP FIREBASE UID FOR COMPATIBILITY
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

            flash(
                "Appointment successfully booked!",
                "success"
            )

        except Exception as e:

            print(
                f"Error adding appointment: {e}"
            )

            flash(
                "There was an error booking your appointment.",
                "error"
            )

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

            "accepted_at": datetime.now(UTC).isoformat(),
        }


        user_doc = user_ref.get()

        patient_email = (
            user_doc.to_dict().get("email")
            if user_doc.exists
            else None
        )

        fullname = f"{data['FirstName']} {data['LastName']}"

        # ---------------------------------------------------------
        # DOCTOR AVAILABILITY CHECK
        # ---------------------------------------------------------

        blocked, block_reason = self.is_slot_blocked(data["appointment_date"])

        if blocked:
            return jsonify({
                "success": False,
                "message": (
                    f"This date/time is blocked by the dentist ({block_reason}). "
                    f"Please choose another slot."
                )
            }), 409
        # -------------------------------------------------------------
        # DOUBLE-BOOKING CHECK
        # -------------------------------------------------------------
        # Only relevant when actually accepting -- two pending requests
        # can compete for the same slot, but it only becomes a real
        # conflict once one of them gets confirmed here.

        if action == "accept":

            conflict = self.find_appointment_conflict(
                dentist_name=dentist_name,
                appointment_date=data.get("appointment_date", "")
            )

            if conflict:
                return jsonify({
                    "success": False,
                    "message": (
                        f"{conflict['dentist_name'] or 'This dentist'} already "
                        f"has an accepted appointment with "
                        f"{conflict['patient_name'] or 'another patient'} at "
                        f"{conflict['appointment_date']}. Please choose a "
                        f"different time or dentist before accepting."
                    )
                }), 409


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

                # NEW: cache history flag + latest date on the account doc
                user_ref.update({
                    "has_history": True,
                    "last_approved_at": data["accepted_at"]
                })


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
    
    
    def admin_create_appointment(self):
        if not session.get('admin_logged_in'):
            return jsonify({
                "success": False,
                "message": "Unauthorized"
            }), 403

        patient_mode = request.form.get(
            "patientMode",
            "existing"
        )

        # ---------------------------------------------------------
        # PATIENT INFORMATION
        # ---------------------------------------------------------

        first_name = bleach.clean(
            request.form.get("First_Name", "").strip()
        )

        middle_name = bleach.clean(
            request.form.get("Middle_Name", "").strip()
        )

        last_name = bleach.clean(
            request.form.get("Last_Name", "").strip()
        )

        birthday = bleach.clean(
            request.form.get("Birthday", "").strip()
        )

        email = ""

        uid = request.form.get(
            "uid",
            ""
        ).strip()

        # This will become the permanent patient identity.
        patient_id = None

        # ---------------------------------------------------------
        # EXISTING ACCOUNT PATIENT
        # ---------------------------------------------------------

        if patient_mode == "existing":

            patient_id = request.form.get(
                "patient_id",
                ""
            ).strip()

            if not patient_id:
                return jsonify({
                    "success": False,
                    "message": "Patient is required"
                }), 400

            patient_ref = self.db.collection(
                self.Doc_Patients
            ).document(patient_id)

            patient_doc = patient_ref.get()

            if not patient_doc.exists:
                return jsonify({
                    "success": False,
                    "message": "Patient record not found"
                }), 404

            patient_data = patient_doc.to_dict()

            # Get the linked account UID if this patient has one.
            uid = patient_data.get(
                "account_uid",
                ""
            ) or ""
            
            # --- ADD THIS: handle existing patients with no linked account ---
            if not uid:
                uid = f"walkin_{uuid.uuid4().hex[:12]}"

                self.db.collection(
                    self.Customer_Account
                ).document(uid).set({
                    "uid": uid,
                    "firstname": patient_data.get("first_name", ""),
                    "middlename": patient_data.get("middle_name", ""),
                    "lastname": patient_data.get("last_name", ""),
                    "email": patient_data.get("email", "") or "",
                    "provider": "walk_in",
                    "created_by_admin": True,
                    "created_at": datetime.now(UTC).isoformat()
                })

                # Link this new account back to the patient record
                # so future appointments reuse it instead of creating
                # a new one each time.
                patient_ref.update({
                    "account_uid": uid
                })
            # -------------------------------------------------------------

            first_name = bleach.clean(
                str(
                    patient_data.get(
                        "first_name",
                        ""
                    )
                ).strip()
            )

            middle_name = bleach.clean(
                str(
                    patient_data.get(
                        "middle_name",
                        ""
                    )
                ).strip()
            )

            last_name = bleach.clean(
                str(
                    patient_data.get(
                        "last_name",
                        ""
                    )
                ).strip()
            )

            birthday = bleach.clean(
                str(
                    patient_data.get(
                        "birthday",
                        ""
                    )
                ).strip()
            )

            email = patient_data.get(
                "email",
                ""
            ) or ""

            # If the patient has a linked login account,
            # retrieve additional account information.
            if uid:
                user_ref = self.db.collection(
                    self.Customer_Account
                ).document(uid)

                user_doc = user_ref.get()

                if user_doc.exists:
                    user_data = user_doc.to_dict()

                    if not email:
                        email = user_data.get(
                            "email",
                            ""
                        ) or ""

        # ---------------------------------------------------------
        # WALK-IN PATIENT
        # ---------------------------------------------------------

        else:

            # ---------------------------------------------------------
            # VALIDATE PATIENT NAME FIRST
            # ---------------------------------------------------------
            #
            # Must happen before any account lookup/creation below,
            # since find_patient() needs a usable name to search on.
            #

            if not first_name or not last_name:
                return jsonify({
                    "success": False,
                    "message": "Patient first name and last name are required"
                }), 400

            # ---------------------------------------------------------
            # CHECK IF THIS PERSON ALREADY HAS A CANONICAL PATIENT
            # RECORD (AND A LINKED ACCOUNT) BEFORE CREATING A NEW ONE
            # ---------------------------------------------------------
            #
            # Without this check, choosing "New Patient" for someone
            # who was already added before creates a brand-new,
            # unlinked Customer_Account every time -- which shows up
            # as duplicate rows with the same name in "My Patients".
            #

            existing_patient = self.find_patient(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                birthday=birthday
            )

            if existing_patient and existing_patient.get("account_uid"):

                # Reuse the account already linked to this patient.
                uid = existing_patient["account_uid"]

            else:

                # A walk-in still receives a temporary account UID
                # because the existing application currently expects
                # an account UID in several places.
                #
                # IMPORTANT:
                # This UID is NOT the patient's permanent identity.
                #

                uid = f"walkin_{uuid.uuid4().hex[:12]}"

                user_ref = self.db.collection(
                    self.Customer_Account
                ).document(uid)

                user_ref.set({
                    "uid": uid,
                    "firstname": first_name,
                    "middlename": middle_name,
                    "lastname": last_name,
                    "email": "",
                    "provider": "walk_in",
                    "created_by_admin": True,
                    "created_at": datetime.now(UTC).isoformat()
                })

        # ---------------------------------------------------------
        # VALIDATE PATIENT NAME
        # ---------------------------------------------------------
        #
        # Still needed here as a guard for the "existing" branch
        # above, which does not perform this check itself.
        #

        if not first_name or not last_name:
            return jsonify({
                "success": False,
                "message": "Patient first name and last name are required"
            }), 400

        # ---------------------------------------------------------
        # FIND OR CREATE CANONICAL PATIENT
        # ---------------------------------------------------------
        #
        # This is the important part.
        #
        # The appointment creator's UID is no longer considered
        # the permanent patient identity.
        #
        # Instead:
        #
        # Customer_Account UID
        #          |
        #          v
        #     Patient ID
        #
        # Example:
        #
        # firebase UID = abc123
        # Patient ID   = P-000001
        #

        try:

            if patient_mode != "existing":
                patient_id = self.get_or_create_patient(
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    birthday=birthday,
                    account_uid=uid,
                    created_by="admin"
                )

        except Exception as e:

            print(
                "PATIENT IDENTITY ERROR:",
                e
            )

            return jsonify({
                "success": False,
                "message": "Unable to create or find patient record"
            }), 500

        # ---------------------------------------------------------
        # CREATE APPOINTMENT ID
        # ---------------------------------------------------------

        appointment_id = str(
            uuid.uuid4()
        )

        # ---------------------------------------------------------
        # APPOINTMENT DATA
        # ---------------------------------------------------------

        data = {

            # -----------------------------------------------------
            # CANONICAL PATIENT ID
            # -----------------------------------------------------

            "patient_id": patient_id,

            # -----------------------------------------------------
            # LEGACY ACCOUNT UID
            # -----------------------------------------------------
            #
            # Keep this for now because other parts of main.py
            # still depend on UID-based storage.
            #
            # We will migrate those later.
            #

            "uid": uid,

            "email": email,

            # -----------------------------------------------------
            # APPOINTMENT IDENTIFIER
            # -----------------------------------------------------

            "Patient_unq_id": appointment_id,

            "status": "accept",

            # -----------------------------------------------------
            # PATIENT INFORMATION
            # -----------------------------------------------------

            "FirstName": first_name,

            "MiddleName": middle_name,

            "LastName": last_name,

            "Birthday": birthday,

            # -----------------------------------------------------
            # DENTIST
            # -----------------------------------------------------

            "DentistName": bleach.clean(
                request.form.get(
                    "dentist_name",
                    ""
                )
            ),

            # -----------------------------------------------------
            # ADDRESS
            # -----------------------------------------------------

            "HouseNo": bleach.clean(
                request.form.get(
                    "House_No",
                    ""
                )
            ),

            "Street": bleach.clean(
                request.form.get(
                    "Street",
                    ""
                )
            ),

            "Brgy": bleach.clean(
                request.form.get(
                    "Brgy",
                    ""
                )
            ),

            "Municipality": bleach.clean(
                request.form.get(
                    "Municipality",
                    ""
                )
            ),

            "City": bleach.clean(
                request.form.get(
                    "City",
                    ""
                )
            ),

            # -----------------------------------------------------
            # PERSONAL INFORMATION
            # -----------------------------------------------------

            "Nationality": bleach.clean(
                request.form.get(
                    "Nationality",
                    ""
                )
            ),

            "Religion": bleach.clean(
                request.form.get(
                    "Religion",
                    ""
                )
            ),

            "Age": bleach.clean(
                request.form.get(
                    "Age",
                    ""
                )
            ),

            "Sex": bleach.clean(
                request.form.get(
                    "Sex",
                    ""
                )
            ),

            "ContactNumber": bleach.clean(
                request.form.get(
                    "Contact_number",
                    ""
                )
            ),

            "Occupation": bleach.clean(
                request.form.get(
                    "Occupation",
                    ""
                )
            ),

            "CivilStatus": bleach.clean(
                request.form.get(
                    "Civil_Status",
                    ""
                )
            ),

            # -----------------------------------------------------
            # APPOINTMENT INFORMATION
            # -----------------------------------------------------

            "Service": bleach.clean(
                request.form.get(
                    "Service",
                    ""
                )
            ),

            "UrgencyLevel": bleach.clean(
                request.form.get(
                    "UrgencyLevel",
                    "Normal"
                )
            ),

            "appointment_date": bleach.clean(
                request.form.get(
                    "appointment_date",
                    ""
                )
            ),

            # -----------------------------------------------------
            # MEDICAL QUESTIONS
            # -----------------------------------------------------

            "q1": request.form.get("q1", ""),

            "q2": request.form.get("q2", ""),

            "q3": request.form.get("q3", ""),

            "q4": request.form.get("q4", ""),

            "q5": request.form.get("q5", ""),

            "q6": request.form.get("q6", ""),

            "q7": request.form.get("q7", ""),

            "q9": request.form.get("q9", ""),

            "q2_spec": bleach.clean(
                request.form.get(
                    "q2_spec",
                    ""
                )
            ),

            "q3_spec": bleach.clean(
                request.form.get(
                    "q3_spec",
                    ""
                )
            ),

            "q4_spec": bleach.clean(
                request.form.get(
                    "q4_spec",
                    ""
                )
            ),

            "q5_spec": bleach.clean(
                request.form.get(
                    "q5_spec",
                    ""
                )
            ),

            "q7_spec": bleach.clean(
                request.form.get(
                    "q7_spec",
                    ""
                )
            ),

            "q9_spec": bleach.clean(
                request.form.get(
                    "q9_spec",
                    ""
                )
            ),

            "w_preg": request.form.get(
                "w_preg",
                ""
            ),

            "w_nurse": request.form.get(
                "w_nurse",
                ""
            ),

            "w_pill": request.form.get(
                "w_pill",
                ""
            ),

            "signature": request.form.get(
                "signature",
                ""
            ),

            # -----------------------------------------------------
            # CREATION INFORMATION
            # -----------------------------------------------------

            "created_by_admin": True,

            "accepted_at": datetime.now(
                UTC
            ).isoformat()
        }

        # ---------------------------------------------------------
        # VALIDATE APPOINTMENT
        # ---------------------------------------------------------

        if not data["Service"]:
            return jsonify({
                "success": False,
                "message": "Service is required"
            }), 400

        if not data["appointment_date"]:
            return jsonify({
                "success": False,
                "message": "Appointment date is required"
            }), 400

        # ---------------------------------------------------------
        # DOUBLE-BOOKING CHECK
        # ---------------------------------------------------------
        #
        # This route writes straight into Approve (auto-confirmed),
        # unlike the patient-facing booking flow which lands in
        # "appointments" first and only becomes confirmed once admin
        # accepts it. So the conflict check has to run here too.
        #

        conflict = self.find_appointment_conflict(
            dentist_name=data["DentistName"],
            appointment_date=data["appointment_date"]
        )

        if conflict:
            return jsonify({
                "success": False,
                "message": (
                    f"{conflict['dentist_name'] or 'This dentist'} already "
                    f"has an accepted appointment with "
                    f"{conflict['patient_name'] or 'another patient'} at "
                    f"{conflict['appointment_date']}. Please choose a "
                    f"different time or dentist."
                )
            }), 409

        # ---------------------------------------------------------
        # SAVE APPOINTMENT
        # ---------------------------------------------------------
        #
        # For now we KEEP the old storage location:
        #
        # Customer_Account/{uid}/Approve/{appointment_id}
        #
        # This prevents the rest of your existing system from
        # immediately breaking.
        #
        # BUT the appointment now contains:
        #
        # "patient_id": "P-000001"
        #
        # The next migration stage will move the actual appointment
        # storage away from UID-based identity.
        #

        try:

            self.db.collection(
                self.Customer_Account
            ).document(uid).collection(
                "Approve"
            ).document(
                appointment_id
            ).set(data)

            # NEW: cache history flag + latest date on the account doc
            self.db.collection(
                self.Customer_Account
            ).document(uid).update({
                "has_history": True,
                "last_approved_at": data["accepted_at"]
            })

            return jsonify({
                "success": True,
                "message": "Appointment created and approved",
                "patient_id": patient_id,
                "appointment_id": appointment_id
            })

        except Exception as e:

            print(
                "ADMIN CREATE APPOINTMENT ERROR:",
                e
            )

            return jsonify({
                "success": False,
                "message": str(e)
            }), 500


    def p_profile(self):
        if not session.get('uid'):
            return redirect(url_for("index"))
        
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
    
    
    
    def _fetch_my_patients_page(self, cursor=None):
        """
        Returns one page of 'My Patients' rows (accounts with has_history=True),
        newest-approved-first, without ever scanning the full Customer_Account
        collection. patient_id is looked up per-row, but that's bounded by
        page size (max PATIENTS_PAGE_SIZE extra reads), not total patient count.
        """
        query = (
            self.db.collection(self.Customer_Account)
            .where("has_history", "==", True)
            .order_by("last_approved_at", direction="DESCENDING")
        )

        if cursor:
            query = query.start_after({"last_approved_at": cursor})

        query = query.limit(self.PATIENTS_PAGE_SIZE + 1)
        docs = list(query.stream())

        has_more = len(docs) > self.PATIENTS_PAGE_SIZE
        docs = docs[:self.PATIENTS_PAGE_SIZE]

        # Was: one Firestore query per row to find its linked patient_id.
        # Now: one cached lookup map shared across the whole page.
        account_to_patient = self._get_account_to_patient_map()

        rows = []
        for doc in docs:
            account_uid = doc.id
            account_data = doc.to_dict()

            patient_id = account_to_patient.get(account_uid, "")

            first = account_data.get("firstname") or ""
            last = account_data.get("lastname") or ""

            rows.append({
                "patient_id": patient_id,
                "uid": account_uid,
                "first_name": first,
                "middle_name": account_data.get("middlename", ""),
                "last_name": last,
                "full_name": account_data.get("name") or f"{first} {last}".strip(),
                "contact_number": account_data.get("contact_number", ""),
                "email": account_data.get("email", ""),
                "most_recent_appointment": account_data.get("last_approved_at", ""),
            })

        next_cursor = None
        if has_more and docs:
            next_cursor = docs[-1].to_dict().get("last_approved_at", "")

        return rows, next_cursor

    def admin_my_patients_page(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        cursor = request.args.get("cursor", "").strip() or None
        rows, next_cursor = self._fetch_my_patients_page(cursor=cursor)

        return jsonify({
            "success": True,
            "rows": rows,
            "next_cursor": next_cursor
        })
    
    
    def _fetch_manageable_accounts_page(self, cursor=None):
        """
        User Management page: real (non-walk-in) accounts, newest-created
        first. Queries Customer_Account directly instead of deriving from
        a full Patients scan — this also fixes a pre-existing bug where
        real accounts with no linked Patients doc never appeared here.

        NOTE: We intentionally do NOT use Firestore's .order_by("created_at")
        here, because combining it with the .where("provider", "in", [...])
        filter requires a composite index in Firebase. Instead we fetch all
        matching docs and sort them in Python. This works for reasonable
        user counts and requires no extra Firebase setup.
        """
        # Was: a full Customer_Account scan on every page load AND every
        # "load more" click. Now: one scan per cache window, invalidated
        # the instant an account is created, edited, deleted, or merged.
        all_docs = self._get_manageable_accounts_cached()
        docs = [
            (account_uid, data) for account_uid, data in all_docs
            if data.get("provider") in ("google", "password")
        ]

        # Sort newest-first by created_at (accounts missing created_at go last)
        docs.sort(
            key=lambda d: d[1].get("created_at", "") or "",
            reverse=True
        )

        # Manual cursor: skip everything newer than the cursor value
        if cursor:
            docs = [
                d for d in docs
                if (d[1].get("created_at", "") or "") < cursor
            ]

        has_more = len(docs) > self.PATIENTS_PAGE_SIZE
        docs = docs[:self.PATIENTS_PAGE_SIZE]

        # Was: one Firestore query per row to find its linked patient_id.
        # Now: one cached lookup map shared across the whole page.
        account_to_patient = self._get_account_to_patient_map()

        rows = []
        for account_uid, account_data in docs:
            patient_id = account_to_patient.get(account_uid, "")

            first = account_data.get("firstname") or ""
            last = account_data.get("lastname") or ""

            rows.append({
                "patient_id": patient_id,
                "uid": account_uid,
                "first_name": first,
                "middle_name": account_data.get("middlename", ""),
                "last_name": last,
                "full_name": account_data.get("name") or f"{first} {last}".strip(),
                "contact_number": account_data.get("contact_number", ""),
                "email": account_data.get("email", ""),
                "disabled": bool(account_data.get("disabled", False)),
            })

        next_cursor = None
        if has_more and docs:
            next_cursor = docs[-1][1].get("created_at", "") or ""

        return rows, next_cursor

    def admin_manageable_accounts_page(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        cursor = request.args.get("cursor", "").strip() or None
        rows, next_cursor = self._fetch_manageable_accounts_page(cursor=cursor)

        return jsonify({
            "success": True,
            "rows": rows,
            "next_cursor": next_cursor
        })
        
        
    def _fetch_appointments_page(self, cursor=None):
        """Pending appointments, newest appointment_date first."""
        query = (
            self.db.collection_group("appointments")
            .order_by("appointment_date", direction="DESCENDING")
        )

        if cursor:
            query = query.start_after({"appointment_date": cursor})

        query = query.limit(self.PATIENTS_PAGE_SIZE + 1)
        docs = list(query.stream())

        has_more = len(docs) > self.PATIENTS_PAGE_SIZE
        docs = docs[:self.PATIENTS_PAGE_SIZE]

        rows = []
        for doc in docs:
            data = doc.to_dict()
            account_uid = doc.reference.parent.parent.id
            data["id"] = doc.id
            data["uid"] = account_uid
            rows.append(data)

        next_cursor = None
        if has_more and docs:
            next_cursor = docs[-1].to_dict().get("appointment_date", "")

        return rows, next_cursor

    def admin_appointments_page(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        cursor = request.args.get("cursor", "").strip() or None
        rows, next_cursor = self._fetch_appointments_page(cursor=cursor)

        return jsonify({
            "success": True,
            "rows": rows,
            "next_cursor": next_cursor
        })

    def _fetch_approved_page(self, cursor=None):
        """Approved appointments, newest accepted_at first."""
        query = (
            self.db.collection_group("Approve")
            .order_by("accepted_at", direction="DESCENDING")
        )

        if cursor:
            query = query.start_after({"accepted_at": cursor})

        query = query.limit(self.PATIENTS_PAGE_SIZE + 1)
        docs = list(query.stream())

        has_more = len(docs) > self.PATIENTS_PAGE_SIZE
        docs = docs[:self.PATIENTS_PAGE_SIZE]

        rows = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["uid"] = doc.reference.parent.parent.id
            rows.append(data)

        next_cursor = None
        if has_more and docs:
            next_cursor = docs[-1].to_dict().get("accepted_at", "")

        return rows, next_cursor

    def admin_approved_page(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        cursor = request.args.get("cursor", "").strip() or None
        rows, next_cursor = self._fetch_approved_page(cursor=cursor)

        return jsonify({
            "success": True,
            "rows": rows,
            "next_cursor": next_cursor
        })
    
    

    def adminDashboard(self):
        if not session.get('admin_logged_in'):
            return redirect(url_for("adminLogin"))

        # =========================
        # APPOINTMENTS (pending) — paginated, page 1 only
        # =========================
        appointment_list, appointment_list_next_cursor = self._fetch_appointments_page()

        # =========================
        # APPROVED APPOINTMENTS — paginated, page 1 only
        # =========================
        approve_list, approve_list_next_cursor = self._fetch_approved_page()

        # Step 5: render only page 1 of My Patients, not the full list.
        my_patients, my_patients_next_cursor = self._fetch_my_patients_page()

        # Step 5: paginate User Management too, sourced directly from
        # Customer_Account instead of via the Patients collection. This
        # also fixes a pre-existing bug: real accounts with no linked
        # Patients doc now correctly appear here.
        manageable_accounts, manageable_accounts_next_cursor = self._fetch_manageable_accounts_page()

        # =========================
        # COUNTS (true totals via server-side aggregation, not full scans)
        # =========================
        total_patients = self.db.collection(self.Doc_Patients).count().get()[0][0].value
        pending_count = self.db.collection_group("appointments").count().get()[0][0].value
        approved_count = self.db.collection_group("Approve").count().get()[0][0].value

        urgency_order = {"Emergency": 0, "Urgent": 1, "Normal": 2}
        appointment_list.sort(
            key=lambda x: urgency_order.get(x.get("UrgencyLevel", ""), 99)
        )

        urgency_counts = {"Emergency": 0, "Urgent": 0, "Normal": 0}
        for appt in appointment_list:
            level = appt.get("UrgencyLevel", "Normal")
            if level in urgency_counts:
                urgency_counts[level] += 1

        recent_approve = approve_list[:3]

        # =========================
        # FINANCIAL CALCULATIONS (Step 2: cached, no full scan)
        # =========================
        try:
            stats_doc = self.db.collection("Stats").document("financial_summary").get()
            stats_data = stats_doc.to_dict() if stats_doc.exists else {}
            total_income = stats_data.get("total_income", 0.0)
            total_outstanding = stats_data.get("total_outstanding", 0.0)
            unpaid_procedures = stats_data.get("unpaid_procedures", 0)
        except Exception as e:
            print(f"Financial stats read error: {e}")
            total_income = 0.0
            total_outstanding = 0.0
            unpaid_procedures = 0

        # =========================
        # RENDER TEMPLATE
        # =========================
        return render_template(
            "admin_dashboard.html",
            Appointment_clients=appointment_list,
            Approve=approve_list,
            manageable_accounts=manageable_accounts,
            my_patients=my_patients,
            pending_count=pending_count,
            approved_count=approved_count,
            total_patients=total_patients,
            urgency_counts=urgency_counts,
            recent_approve=recent_approve,
            total_income=total_income,
            total_outstanding=total_outstanding,
            unpaid_procedures=unpaid_procedures,
            my_patients_next_cursor=my_patients_next_cursor,
            manageable_accounts_next_cursor=manageable_accounts_next_cursor,
            appointment_list_next_cursor=appointment_list_next_cursor,
            approve_list_next_cursor=approve_list_next_cursor,
        )

    def search_patients(self):
        query = request.args.get("q", "").strip().lower()

        if len(query) < 2:
            return jsonify([])

        results = []

        patients = self._get_patients_cached()

        for doc_id, data in patients:

            first = str(
                data.get("first_name", "")
            ).strip()

            middle = str(
                data.get("middle_name", "")
            ).strip()

            last = str(
                data.get("last_name", "")
                ).strip()

            full_name = " ".join(
                part for part in [first, middle, last]
                if part
            )

            searchable_name = full_name.lower()

            if (
                query in first.lower()
                or query in middle.lower()
                or query in last.lower()
                or query in searchable_name
            ):
                account_uid = data.get("account_uid") or ""
                email = data.get("email", "")

                # If the patient has a linked login account,
                # get the email from Customer_Account if needed.
                if account_uid:
                    account_doc = (
                        self.db.collection(
                            self.Customer_Account
                        )
                        .document(account_uid)
                        .get()
                    )

                    if account_doc.exists:
                        account_data = account_doc.to_dict()

                        if not email:
                            email = account_data.get(
                                "email",
                                ""
                                )

                results.append({
                    "patient_id": doc_id,
                    "account_uid": account_uid,

                    "firstname": first,
                    "middlename": middle,
                    "lastname": last,

                    "name": full_name,
                    "email": email,

                    "birthday": data.get(
                        "birthday",
                        ""
                    )
                })
        return jsonify(results)
    
    def check_duplicate_patient(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        first_name = request.args.get("first_name", "").strip()
        last_name = request.args.get("last_name", "").strip()
        middle_name = request.args.get("middle_name", "").strip()
        birthday = request.args.get("birthday", "").strip()

        if not first_name or not last_name:
            return jsonify({"match": False})

        existing_patient = self.find_patient(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            birthday=birthday
        )

        if not existing_patient:
            return jsonify({"match": False})

        return jsonify({
            "match": True,
            "patient_id": existing_patient["patient_id"],
            "first_name": existing_patient.get("first_name", ""),
            "middle_name": existing_patient.get("middle_name", ""),
            "last_name": existing_patient.get("last_name", ""),
            "has_account": bool(existing_patient.get("account_uid"))
        })

    def update_patient(self):
        """
        Update a patient's basic info from the admin "My Patients" table.

        Updates the Customer_Account document (the account used for
        login/booking), and keeps the canonical Patients record in
        sync when one is linked.
        """

        if not session.get('admin_logged_in'):
            return jsonify({
                "success": False,
                "message": "Unauthorized"
            }), 403

        uid = request.form.get("uid", "").strip()
        patient_id = request.form.get("patient_id", "").strip()

        first_name = bleach.clean(
            request.form.get("first_name", "").strip()
        )

        middle_name = bleach.clean(
            request.form.get("middle_name", "").strip()
        )

        last_name = bleach.clean(
            request.form.get("last_name", "").strip()
        )

        contact_number = bleach.clean(
            request.form.get("contact_number", "").strip()
        )

        email = bleach.clean(
            request.form.get("email", "").strip()
        )

        if not uid:
            return jsonify({
                "success": False,
                "message": "Account UID is required"
            }), 400

        if not first_name or not last_name:
            return jsonify({
                "success": False,
                "message": "First name and last name are required"
            }), 400

        try:

            account_ref = self.db.collection(
                self.Customer_Account
            ).document(uid)

            if not account_ref.get().exists:
                return jsonify({
                    "success": False,
                    "message": "Account not found"
                }), 404

            account_ref.update({
                "firstname": first_name,
                "middlename": middle_name,
                "lastname": last_name,
                "contact_number": contact_number,
                "email": email
            })

            # Keep the canonical Patients record in sync, if linked.
            if patient_id:

                patient_ref = self.db.collection(
                    self.Doc_Patients
                ).document(patient_id)

                if patient_ref.get().exists:

                    patient_ref.update({
                        "first_name": first_name,
                        "middle_name": middle_name,
                        "last_name": last_name,

                        "first_name_normalized":
                            self.normalize_patient_name(first_name),

                        "middle_name_normalized":
                            self.normalize_patient_name(middle_name),

                        "last_name_normalized":
                            self.normalize_patient_name(last_name),

                        "email": email
                    })
                    self._invalidate_patients_cache()

            self._invalidate_accounts_cache()

            return jsonify({
                "success": True,
                "message": "Patient updated successfully"
            })

        except Exception as e:

            print("UPDATE PATIENT ERROR:", e)

            return jsonify({
                "success": False,
                "message": str(e)
            }), 500

    def toggle_user_block(self):
        """
        Block or unblock a patient's account via a custom Firestore
        flag (Customer_Account.disabled). Checked manually at login
        time for both manual (email/password) and Google sign-in, so
        it works the same way regardless of how the account signs in.
        """

        if not session.get('admin_logged_in'):
            return jsonify({
                "success": False,
                "message": "Unauthorized"
            }), 403

        uid = request.form.get("uid", "").strip()
        disabled = request.form.get("disabled", "").strip().lower() == "true"

        if not uid:
            return jsonify({
                "success": False,
                "message": "Account UID is required"
            }), 400

        try:
            account_ref = self.db.collection(
                self.Customer_Account
            ).document(uid)

            if not account_ref.get().exists:
                return jsonify({
                    "success": False,
                    "message": "Account not found"
                }), 404

            update_data = {"disabled": disabled}
            if disabled:
                update_data["disabled_at"] = datetime.now(UTC).isoformat()
            else:
                update_data["disabled_at"] = firestore.DELETE_FIELD

            account_ref.set(update_data, merge=True)
            self._invalidate_accounts_cache()

            return jsonify({
                "success": True,
                "disabled": disabled,
                "message": "Account blocked" if disabled else "Account unblocked"
            })

        except Exception as e:
            return jsonify({
                "success": False,
                "message": str(e)
            }), 500

    def delete_patient(self):
        """
        Permanently delete a patient's account and canonical patient
        record from the admin "My Patients" table.

        Also clears out known subcollections under the account
        (appointments, Approve, Done_procedure) since Firestore does
        not delete subcollections automatically when a parent
        document is deleted.
        """

        if not session.get('admin_logged_in'):
            return jsonify({
                "success": False,
                "message": "Unauthorized"
            }), 403

        uid = request.form.get("uid", "").strip()
        patient_id = request.form.get("patient_id", "").strip()

        if not uid:
            return jsonify({
                "success": False,
                "message": "Account UID is required"
            }), 400

        try:

            account_ref = self.db.collection(
                self.Customer_Account
            ).document(uid)

            if account_ref.get().exists:

                # Clean up known subcollections first, since deleting
                # a document does not delete its subcollections.
                for sub_name in (
                    self.Appointment_cliets,
                    "Approve",
                    "Done_procedure"
                ):
                    for sub_doc in account_ref.collection(sub_name).stream():
                        sub_doc.reference.delete()

                account_ref.delete()
                self._invalidate_accounts_cache()
                self._invalidate_financial_cache()

            # Also remove the Firebase Authentication record so the
            # login credential doesn't outlive the patient's data.
            # Without this, the account could still sign in even
            # though none of their data exists anymore.
            auth_warning = None
            try:
                auth.delete_user(uid)
            except auth.UserNotFoundError:
                pass  # Already gone from Auth - nothing to do.
            except Exception as auth_err:
                auth_warning = (
                    "Patient data was deleted, but the Firebase "
                    "Authentication account could not be removed: "
                    f"{auth_err}"
                )

            if patient_id:

                patient_ref = self.db.collection(
                    self.Doc_Patients
                ).document(patient_id)

                if patient_ref.get().exists:
                    patient_ref.delete()
                    self._invalidate_patients_cache()

            return jsonify({
                "success": True,
                "message": auth_warning or "Patient deleted successfully"
            })

        except Exception as e:

            print("DELETE PATIENT ERROR:", e)

            return jsonify({
                "success": False,
                "message": str(e)
            }), 500
            
    def update_treatment_record(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        patient_id = request.form.get("patient_id", "").strip()
        done_doc_id = request.form.get("done_doc_id", "").strip()
        proc_index_raw = request.form.get("proc_index", "").strip()

        if not patient_id or not done_doc_id or proc_index_raw == "":
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        try:
            proc_index = int(proc_index_raw)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid procedure index"}), 400

        # Resolve the account behind this patient (server-side, don't trust client for this)
        patient_ref = self.db.collection(self.Doc_Patients).document(patient_id)
        patient_doc = patient_ref.get()

        if not patient_doc.exists:
            return jsonify({"success": False, "message": "Patient not found"}), 404

        account_uid = patient_doc.to_dict().get("account_uid") or ""

        if not account_uid:
            return jsonify({"success": False, "message": "Patient has no linked account"}), 404

        done_ref = (
            self.db.collection(self.Customer_Account)
            .document(account_uid)
            .collection("Done_procedure")
            .document(done_doc_id)
        )

        done_doc = done_ref.get()

        if not done_doc.exists:
            return jsonify({"success": False, "message": "Treatment record not found"}), 404

        procedures = done_doc.to_dict().get("procedures", [])

        if proc_index < 0 or proc_index >= len(procedures):
            return jsonify({"success": False, "message": "Procedure index out of range"}), 400

        existing = procedures[proc_index]

        updated_value = self.safe_float(request.form.get("value", existing.get("value", 0)))
        updated_paid = self.safe_float(request.form.get("paid", existing.get("paid", 0)))
        old_paid = self.safe_float(existing.get("paid", 0))
        old_balance = self.safe_float(existing.get("balance", 0))
        new_balance = round(updated_value - updated_paid, 2)

        procedures[proc_index] = {
            "date": bleach.clean(request.form.get("date", existing.get("date", ""))),
            "tooth": bleach.clean(request.form.get("tooth", existing.get("tooth", ""))),
            "procedure": bleach.clean(request.form.get("procedure", existing.get("procedure", ""))),
            "dentist": bleach.clean(request.form.get("dentist", existing.get("dentist", ""))),
            "value": updated_value,
            "paid": updated_paid,
            "balance": round(updated_value - updated_paid, 2),
            "next_appointment": bleach.clean(request.form.get("next_appointment", existing.get("next_appointment", ""))),
            "medicine": bleach.clean(request.form.get("medicine", existing.get("medicine", ""))),
            "status": bleach.clean(request.form.get("status", existing.get("status", "")))
        }

        try:
            done_ref.update({
                "procedures": procedures,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            # NEW: incrementally update cached financial stats
            delta_income = updated_paid - old_paid
            delta_outstanding = new_balance - old_balance
            delta_unpaid = (1 if new_balance > 0 else 0) - (1 if old_balance > 0 else 0)

            self.db.collection("Stats").document("financial_summary").set({
                "total_income": firestore.Increment(delta_income),
                "total_outstanding": firestore.Increment(delta_outstanding),
                "unpaid_procedures": firestore.Increment(delta_unpaid)
            }, merge=True)

            # =================================================
            # REFRESH "NEXT VISIT" SUGGESTION FOR THIS RECORD
            # =================================================
            # Same rule as save_dental_record: last row (top to bottom)
            # in THIS treatment record that has a next_appointment date
            # wins. Keeps the patient's "My Schedule" guide in sync if
            # the dentist corrects the date later.
            next_appt_date = ""
            next_appt_service = ""
            next_appt_dentist = ""

            for p in procedures:
                if p.get("next_appointment"):
                    next_appt_date = p["next_appointment"]
                    next_appt_service = p.get("procedure", "")
                    next_appt_dentist = p.get("dentist", "")

            next_visit_ref = (
                self.db.collection(self.Customer_Account)
                .document(account_uid)
                .collection("Approve")
                .document("next_visit")
            )

            if next_appt_date:
                next_visit_ref.set({
                    "Patient_unq_id": patient_id,
                    "uid": account_uid,
                    "appointment_date": next_appt_date,
                    "Service": next_appt_service,
                    "DentistName": next_appt_dentist,
                    "status": "suggested",
                    "source": "treatment_record",
                    "created_at": datetime.now(UTC).isoformat()
                })
            else:
                next_visit_ref.delete()

            self._invalidate_financial_cache()

            return jsonify({"success": True, "message": "Treatment record updated successfully"})

        except Exception as e:
            print("UPDATE TREATMENT RECORD ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500

    def get_patient(self, uid):
        """
        Get patient information.

        Compatibility behavior:
        - If the supplied value is a Firebase UID, load Customer_Account/{uid}
        - If the supplied value is a Patient ID such as P-000001,
        load Patients/{patient_id} and then use account_uid when available.
        """

        # ============================================================
        # 1. CHECK IF THIS IS A PATIENT ID
        # ============================================================

        patient_ref = self.db.collection(
            self.Doc_Patients
        ).document(uid)

        patient_doc = patient_ref.get()

        if patient_doc.exists:
            patient_data = patient_doc.to_dict()

            patient_id = patient_doc.id
            account_uid = patient_data.get("account_uid")

            data = {
                "patient_id": patient_id,
                "uid": account_uid or "",
                "account_uid": account_uid or "",

                "first_name": (
                    patient_data.get("first_name")
                    or patient_data.get("firstname")
                    or ""
                ),

                "middle_name": (
                    patient_data.get("middle_name")
                    or patient_data.get("middlename")
                    or ""
                ),

                "last_name": (
                    patient_data.get("last_name")
                    or patient_data.get("lastname")
                    or ""
                ),

                "birthday": patient_data.get("birthday", ""),

                "email": patient_data.get("email", ""),

                "full_name": (
                    f"{patient_data.get('first_name', '')} "
                    f"{patient_data.get('middle_name', '')} "
                    f"{patient_data.get('last_name', '')}"
                ).strip(),

                "account_type": (
                    "Account"
                    if account_uid
                    else "No Account"
                )
            }

            # ========================================================
            # IF PATIENT HAS AN ACCOUNT, GET ACCOUNT INFORMATION
            # ========================================================

            if account_uid:

                account_ref = (
                    self.db
                    .collection(self.Customer_Account)
                    .document(account_uid)
                )

                account_doc = account_ref.get()

                if account_doc.exists:

                    account_data = account_doc.to_dict()

                    data["email"] = (
                        account_data.get("email")
                        or data["email"]
                    )

                    data["contact_number"] = (
                        account_data.get("contact_number")
                        or account_data.get("ContactNumber")
                        or ""
                    )

            visit_history = []
            if account_uid:
                done_docs = (
                    self.db.collection(self.Customer_Account)
                    .document(account_uid)
                    .collection("Done_procedure")
                    .order_by("updated_at")
                    .stream()
            )
            
                for done in done_docs:
                    done_data = done.to_dict()
                    chart_image = done_data.get("chart_image", "")
                    for p in done_data.get("procedures", []):
                        visit_history.append({
                            "dentist": p.get("dentist", ""),
                            "date": p.get("date", ""),
                            "procedure": p.get("procedure", ""),
                            "paid": p.get("paid", 0),
                            "balance": p.get("balance", 0),
                            "value": p.get("value", 0),
                            "tooth": p.get("tooth", ""),
                            "status": p.get("status", ""),
                            "next_appointment": p.get("next_appointment", ""),
                            "medicine": p.get("medicine", ""),
                            "chart_image": chart_image
                        })

            data["Done_procedure"] = visit_history
            return data

        # ============================================================
        # 2. OLD SYSTEM: TREAT SUPPLIED VALUE AS FIREBASE UID
        # ============================================================

        doc_ref = (
            self.db
            .collection(self.Customer_Account)
            .document(uid)
        )

        doc = doc_ref.get()

        if not doc.exists:
            return {
                "error": "Patient not found"
            }

        data = doc.to_dict()

        data["uid"] = doc.id
        data["account_uid"] = doc.id

        # ============================================================
        # 3. FIND LINKED PATIENT RECORD
        # ============================================================

        patient_query = (
            self.db
            .collection(self.Doc_Patients)
            .where(
                "account_uid",
                "==",
                uid
            )
            .limit(1)
            .stream()
        )

        linked_patient = None

        for patient in patient_query:
            linked_patient = patient
            break

        if linked_patient:
            patient_data = linked_patient.to_dict()

            data["patient_id"] = linked_patient.id

            data["middle_name"] = (
                patient_data.get("middle_name")
                or ""
            )

            data["birthday"] = (
                patient_data.get("birthday")
                or data.get("birthday")
                or ""
            )

        else:
            # Old account that has not been linked yet
            data["patient_id"] = ""

        # ============================================================
        # 4. NORMALIZE EXISTING ACCOUNT NAME FIELDS
        # ============================================================

        first = (
            data.get("firstname")
            or data.get("first_name")
            or ""
        )

        middle = (
            data.get("middlename")
            or data.get("middle_name")
            or ""
        )

        last = (
            data.get("lastname")
            or data.get("last_name")
            or ""
        )

        data["first_name"] = first
        data["middle_name"] = middle
        data["last_name"] = last

        data["full_name"] = (
            data.get("name")
            or f"{first} {middle} {last}".strip()
        )

        data["account_type"] = (
            data.get("provider", "password").capitalize()
        )
        visit_history = []
        done_docs = (
            self.db.collection(self.Customer_Account)
            .document(uid)
            .collection("Done_procedure")
            .stream()
        )
        for done in done_docs:
            done_data = done.to_dict()
            chart_image = done_data.get("chart_image", "")
            for p in done_data.get("procedures", []):
                visit_history.append({
                    "dentist": p.get("dentist", ""),
                    "date": p.get("date", ""),
                    "procedure": p.get("procedure", ""),
                    "paid": p.get("paid", 0),
                    "balance": p.get("balance", 0),
                    "value": p.get("value", 0),
                    "tooth": p.get("tooth", ""),
                    "status": p.get("status", ""),
                    "next_appointment": p.get("next_appointment", ""),
                    "medicine": p.get("medicine", ""),
                    "chart_image": chart_image
                })

        data["Done_procedure"] = visit_history

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
                session['admin_last_activity'] = datetime.now(UTC).isoformat()
                
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

    def update_profile(self):
        try:
            uid = request.form.get("uid", "").strip()
            new_firstname = request.form.get("new_firstname", "").strip()
            new_lastname = request.form.get("new_lastname", "").strip()
            new_phone = request.form.get("new_phone", "").strip()

            if not uid:
                flash("Unable to identify your account.", "error")
                return redirect(request.referrer)

            if not new_firstname:
                flash("First name is required.", "error")
                return redirect(request.referrer)

            # Find account using UID
            accounts = self.db.collection("Customer_Account").where(
                "uid", "==", uid
            ).limit(1).stream()

            account_doc = None

            for doc in accounts:
                account_doc = doc
                break

            if account_doc is None:
                flash("Account not found.", "error")
                return redirect(request.referrer)

            # Get existing account data
            account_data = account_doc.to_dict()

            # Check account provider
            provider = account_data.get("provider", "")

            if provider == "google":
                # Google accounts: update name and also store first/last name
                full_name = f"{new_firstname} {new_lastname}".strip()
                account_doc.reference.update({
                    "name": full_name,
                    "firstname": new_firstname,
                    "lastname": new_lastname,
                    "contact_number": new_phone
                })
                session["name"] = full_name

            else:
                # Password accounts: update firstname + lastname
                account_doc.reference.update({
                    "firstname": new_firstname,
                    "lastname": new_lastname,
                    "contact_number": new_phone
                })
                session["name"] = f"{new_firstname} {new_lastname}".strip()

            flash("Profile updated successfully!", "success")

            return redirect(url_for("p_profile"))

        except Exception as e:
            print(f"Update profile error: {e}")
            flash("Failed to update profile. Please try again.", "error")
            return redirect(request.referrer)
        

    def upload_profile_pic(self):
        try:
            uid = session.get('uid', '')
            
            if not uid:
                return jsonify({"success": False, "message": "Not authenticated"}), 401
            
            if 'profile_pic' not in request.files:
                return jsonify({"success": False, "message": "No file uploaded"}), 400
            
            file = request.files['profile_pic']
            
            if file.filename == '':
                return jsonify({"success": False, "message": "No file selected"}), 400
            
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            filename = file.filename
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            
            if ext not in allowed_extensions:
                return jsonify({"success": False, "message": "Invalid file type. Please upload PNG, JPG, or GIF."}), 400
            
            save_folder = os.path.join("static", "profile_pics")
            os.makedirs(save_folder, exist_ok=True)
            
            new_filename = f"{uid}.{ext}"
            filepath = os.path.join(save_folder, new_filename)
            
            for old_file in os.listdir(save_folder):
                if old_file.startswith(uid + "."):
                    old_path = os.path.join(save_folder, old_file)
                    if old_path != filepath:
                        os.remove(old_path)
            
            file.save(filepath)
            
            profile_pic_url = f"/static/profile_pics/{new_filename}"
            user_ref = self.db.collection(self.Customer_Account).document(uid)
            
            if user_ref.get().exists:
                user_ref.update({"profile_pic": profile_pic_url})
            else:
                return jsonify({"success": False, "message": "User not found"}), 404
            
            return jsonify({
                "success": True,
                "message": "Profile picture updated successfully",
                "profile_pic_url": profile_pic_url
            })
            
        except Exception as e:
            print(f"Upload profile pic error: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
        
    

    def service_detail(self, service_id):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        uid = session.get('uid', '')
        profile_pic = ''

        service = self.SERVICES_DATA.get(service_id)
        
        if not service:
            abort(404)

        if uid and email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            if user_query:
                profile_pic = user_query[0].to_dict().get('profile_pic', '')
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    profile_pic = user_query[0].to_dict().get('profile_pic', '')
            
        return render_template('service.html', service=service, name=name, email=email, uid=uid, profile_pic=profile_pic)
    

    def dental_location(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        uid = session.get('uid', '')
        profile_pic = ''

        if uid and email:
            user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
            if user_query:
                profile_pic = user_query[0].to_dict().get('profile_pic', '')
            else:
                user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
                if user_query:
                    profile_pic = user_query[0].to_dict().get('profile_pic', '')
            
        return render_template("location.html",name=name, email=email, profile_pic=profile_pic)
    
    def privacy_policy(self):
        name = session.get('name', 'Guest')
        return render_template(
            "privacy_policy.html",
            name=name,
            last_updated=datetime.now(UTC).strftime("%B %d, %Y")
        )

    def terms_of_service(self):
        name = session.get('name', 'Guest')
        return render_template(
            "terms_of_service.html",
            name=name,
            last_updated=datetime.now(UTC).strftime("%B %d, %Y")
        )
    

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

            # =====================================================
            # GET UID
            # =====================================================
            uid = request.form.get("uid", "").strip()

            print("====================================")
            print("RECEIVED UID:", repr(uid))
            print("CUSTOMER ACCOUNT:", self.Customer_Account)
            print("====================================")

            if not uid:
                return jsonify({
                    "success": False,
                    "message": "UID is required"
                }), 400

            # =====================================================
            # FIND CUSTOMER ACCOUNT
            # =====================================================
            user_ref = (
                self.db
                .collection(self.Customer_Account)
                .document(uid)
            )

            user_doc = user_ref.get()

            print("LOOKING FOR DOCUMENT:", uid)
            print("DOCUMENT EXISTS:", user_doc.exists)

            if not user_doc.exists:
                return jsonify({
                    "success": False,
                    "message": f"User not found for UID: {uid}"
                }), 404

            # =====================================================
            # GET PATIENT UNIQUE ID 
            # =====================================================
            patient_unq_id = request.form.get(
                "Patient_unq_id",
                ""
            ).strip()

            print("PATIENT UNIQUE ID:", repr(patient_unq_id))

            # =====================================================
            # DENTAL CHART JSON
            # =====================================================
            dental_chart = {}

            for key in request.form:

                if key.startswith("tooth_"):

                    dental_chart[key] = request.form.get(key)

                    # =====================================================
                    # IMAGE TO BASE64
                    # =====================================================
                    image_base64 = ""
                    image_file = request.files.get("dental_chart_image")
                    if image_file and image_file.filename:
                        try:
                            # Check file size
                            image_file.seek(0, 2)  # Seek to end
                            file_size = image_file.tell()
                            image_file.seek(0)  # Reset to beginning

                            if file_size == 0:
                                print("WARNING: Image file is empty (0 bytes)")
                            else:
                                image_bytes = image_file.read()
                                if image_bytes:
                                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                                    print(f"CHART IMAGE SAVED. BASE64 LENGTH: {len(image_base64)}")
                        except Exception as img_error:
                            print(f"IMAGE ENCODE ERROR: {str(img_error)}")
                            # Continue without image - don't fail the entire save
                            image_base64 = ""
                    else:
                        print("WARNING: No dental chart image file received")

            # =====================================================
            # TREATMENT TABLE
            # =====================================================
            dates = request.form.getlist("date[]")
            teeth = request.form.getlist("tooth[]")
            procedures = request.form.getlist("procedure[]")
            dentists = request.form.getlist("dentist[]")
            values = request.form.getlist("value[]")
            paids = request.form.getlist("paid[]")
            balances = request.form.getlist("balance[]")
            next_appts = request.form.getlist(
                "next_appointment[]"
            )
            medicines = request.form.getlist(
                "medicine[]"
            )
            statuses = request.form.getlist(
                "status[]"
            )

            # =====================================================
            # DETERMINE NUMBER OF ROWS
            # =====================================================
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

            print("TREATMENT ROW COUNT:", length)

            # =====================================================
            # BUILD DONE PROCEDURES
            # =====================================================
            done_procedures = []

            for i in range(length):

                # Skip completely empty rows
                if not procedures[i] and not teeth[i]:
                    continue

                done_procedures.append({

                    "date": dates[i],

                    "tooth": teeth[i],

                    "procedure": procedures[i],

                    "dentist": dentists[i],

                    "value": self.safe_float(
                        values[i]
                    ),

                    "paid": self.safe_float(
                        paids[i]
                    ),

                    "balance": self.safe_float(
                        balances[i]
                    ),

                    "next_appointment": next_appts[i],

                    "medicine": medicines[i],

                    "status": statuses[i]
                })

            # =====================================================
            # SAVE TO DONE_PROCEDURE
            # =====================================================
            # NEW: incrementally update cached financial stats
            delta_income = sum(p["paid"] for p in done_procedures)
            delta_outstanding = sum(p["balance"] for p in done_procedures)
            delta_unpaid = sum(1 for p in done_procedures if p["balance"] > 0)

            self.db.collection("Stats").document("financial_summary").set({
                "total_income": firestore.Increment(delta_income),
                "total_outstanding": firestore.Increment(delta_outstanding),
                "unpaid_procedures": firestore.Increment(delta_unpaid)
            }, merge=True)
            
            done_ref = user_ref.collection(
                "Done_procedure"
            )

            done_ref.add({

                "uid": uid,

                "Patient_unq_id": patient_unq_id,

                "chart": dental_chart,

                "chart_image": image_base64,

                "procedures": done_procedures,

                "updated_at":
                    firestore.SERVER_TIMESTAMP
            })

            print("DONE_PROCEDURE SAVED SUCCESSFULLY.")
            self._invalidate_financial_cache()

            # NEW: cache history flag on the account doc
            user_ref.update({
                "has_history": True,
                "last_approved_at": datetime.now(UTC).isoformat()
            })

            # =====================================================
            # DELETE MATCHING APPROVE RECORD
            # =====================================================
            if patient_unq_id:

                print(
                    "SEARCHING APPROVE RECORD:",
                    patient_unq_id
                )

                approve_docs = (
                    user_ref
                    .collection("Approve")
                    .where(
                        "Patient_unq_id",
                        "==",
                        patient_unq_id
                    )
                    .stream()
                )

                deleted = False

                for doc in approve_docs:

                    print(
                        "Deleting Approve document:",
                        doc.id
                    )

                    doc.reference.delete()

                    deleted = True

                if deleted:

                    print(
                        "APPROVE RECORD DELETED."
                    )

                else:

                    print(
                        "No matching Approve document found."
                    )

            # =====================================================
            # SET / CLEAR "NEXT VISIT" SUGGESTION
            # =====================================================
            # Formality guide for the patient's "My Schedule" card, NOT a
            # confirmed/blocked appointment slot. Uses the last row (top to
            # bottom) that has a next_appointment date filled in. If none of
            # the rows have one, any previous suggestion is cleared so the
            # patient doesn't see a stale date.
            next_appt_date = ""
            next_appt_service = ""
            next_appt_dentist = ""

            for p in done_procedures:
                if p.get("next_appointment"):
                    next_appt_date = p["next_appointment"]
                    next_appt_service = p.get("procedure", "")
                    next_appt_dentist = p.get("dentist", "")

            next_visit_ref = user_ref.collection("Approve").document("next_visit")

            if next_appt_date:
                next_visit_ref.set({
                    "Patient_unq_id": patient_unq_id,
                    "uid": uid,
                    "appointment_date": next_appt_date,
                    "Service": next_appt_service,
                    "DentistName": next_appt_dentist,
                    "status": "suggested",
                    "source": "treatment_record",
                    "created_at": datetime.now(UTC).isoformat()
                })
                print("NEXT VISIT SUGGESTION SAVED:", next_appt_date)
            else:
                next_visit_ref.delete()
                print("NO NEXT VISIT DATE PROVIDED - CLEARED ANY EXISTING SUGGESTION.")

            # =====================================================
            # SUCCESS
            # =====================================================
            return jsonify({

                "success": True,

                "message":
                    "Dental record saved successfully",

                "uid": uid,

                "Patient_unq_id":
                    patient_unq_id

            })

        except Exception as e:

            print(
                "SAVE DENTAL RECORD ERROR:",
                str(e)
            )

            return jsonify({

                "success": False,

                "message": str(e)

            }), 500
    
    

    def get_treatment_info(self, patient_id):
        try:

            # ==========================================
            # CLEAN PATIENT ID
            # ==========================================

            if not patient_id:
                return jsonify({
                    "success": False,
                    "message": "Patient ID is required"
                }), 400

            patient_id = str(patient_id).strip()

            patient_id = patient_id.replace("Patient ID:", "").strip()

            print("====================================")
            print("GET TREATMENT INFO")
            print("PATIENT ID:", patient_id)
            print("====================================")

            # ==========================================
            # FIND PATIENT
            # ==========================================

            patient_ref = self.db.collection(
                self.Doc_Patients
            ).document(patient_id)

            patient_doc = patient_ref.get()

            if not patient_doc.exists:

                print("PATIENT NOT FOUND:", patient_id)

                return jsonify({
                    "success": False,
                    "message": f"Patient not found for Patient ID: {patient_id}"
                }), 404

            patient_data = patient_doc.to_dict()

            account_uid = patient_data.get("account_uid") or ""

            print("PATIENT ID:", patient_id)
            print("ACCOUNT UID:", account_uid)

            # Patient exists but has no login account.
            # There can be no old Customer_Account treatment history.
            if not account_uid:

                return jsonify({
                    "success": True,
                    "procedures": []
                })
            
            user_ref = self.db.collection(
                self.Customer_Account
            ).document(account_uid)

            # ==========================================
            # GET DONE PROCEDURES (ORDERED BY DATE)
            # ==========================================
            procedures = []
            done_docs = list(
                user_ref
                .collection("Done_procedure")
                .order_by("updated_at")
                .stream()
            )

            print(
                "DONE_PROCEDURE DOCUMENTS:",
                len(done_docs)
            )

            # ==========================================
            # LOOP DONE_PROCEDURE
            # ==========================================

            for doc in done_docs:
                data = doc.to_dict()
                chart_image = data.get("chart_image", "")
                procedure_list = data.get("procedures", [])

                for index, p in enumerate(procedure_list):
                    procedures.append({
                        "done_doc_id": doc.id,      # NEW
                        "proc_index": index,        # NEW
                        "dentist": p.get("dentist", ""),
                        "medicine": p.get("medicine", ""),
                        "date": p.get("date", ""),
                        "procedure": p.get("procedure", ""),
                        "paid": p.get("paid", 0),
                        "next_appointment": p.get("next_appointment", ""),
                        "status": p.get("status", ""),
                        "balance": p.get("balance", 0),
                        "value": p.get("value", 0),
                        "tooth": p.get("tooth", ""),
                        "chart_image": chart_image
                    })

            print(
                "TOTAL PROCEDURES:",
                len(procedures)
            )

            # ==========================================
            # RESPONSE
            # ==========================================

            return jsonify({

                "success": True,

                "procedures": procedures

            })

        except Exception as e:

            print(
                "ERROR in get_treatment_info:",
                e
            )

            return jsonify({

                "success": False,

                "message": str(e)

            }), 500
    
    def get_patient_profile_data(self):
        """Fetches schedule and treatment data for the logged-in patient's profile page."""
        uid = session.get('uid')
        if not uid:
            return jsonify({"error": "Not logged in"}), 401

        account_ref = self.db.collection(self.Customer_Account).document(uid)
        
        # 1. Get Approved Appointments (My Schedule)
        schedule = []
        for doc in account_ref.collection("Approve").stream():
            data = doc.to_dict()
            data['id'] = doc.id
            schedule.append(data)

        # 2. Get Done Procedures (Dental Records & Payments) - ORDERED BY DATE
        procedures = []
        for doc in account_ref.collection("Done_procedure").order_by("updated_at").stream():
            data = doc.to_dict()
            chart_image = data.get("chart_image", "")
            for p in data.get("procedures", []):
                p['chart_image'] = chart_image
                procedures.append(p)

        return jsonify({
            "success": True,
            "schedule": schedule,
            "procedures": procedures
        })
        

    def admin_merge_patients(self):
        """Allows admin to manually merge two duplicate patient records."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        
        source_patient_id = request.form.get("source_patient_id", "").strip()
        target_patient_id = request.form.get("target_patient_id", "").strip()
        
        if not source_patient_id or not target_patient_id:
            return jsonify({"success": False, "message": "Both source and target patient IDs are required"}), 400
            
        if source_patient_id == target_patient_id:
            return jsonify({"success": False, "message": "Source and target cannot be the same"}), 400

        source_ref = self.db.collection(self.Doc_Patients).document(source_patient_id)
        target_ref = self.db.collection(self.Doc_Patients).document(target_patient_id)
        
        source_doc = source_ref.get()
        target_doc = target_ref.get()
        
        if not source_doc.exists or not target_doc.exists:
            return jsonify({"success": False, "message": "One of the patient records does not exist"}), 404
            
        source_uid = source_doc.to_dict().get("account_uid", "")
        target_uid = target_doc.to_dict().get("account_uid", "")
        
        if not source_uid or not target_uid:
            return jsonify({"success": False, "message": "One of the patients does not have a linked account"}), 400

        # Merge subcollections from source account to target account
        source_acc_ref = self.db.collection(self.Customer_Account).document(source_uid)
        target_acc_ref = self.db.collection(self.Customer_Account).document(target_uid)
        
        for sub_name in (self.Appointment_cliets, "Approve", "Done_procedure"):
            docs = list(source_acc_ref.collection(sub_name).stream())
            for doc in docs:
                data = doc.to_dict()
                # Use the original document ID to prevent duplicates if run twice
                target_acc_ref.collection(sub_name).document(doc.id).set(data)
                doc.reference.delete()
                
        # Clean up source account and patient record
        source_acc_ref.delete()
        source_ref.delete()

        self._invalidate_financial_cache()
        self._invalidate_accounts_cache()
        self._invalidate_patients_cache()

        return jsonify({"success": True, "message": "Patients merged successfully"})

    def admin_financial_chart_data(self):
        """
        Returns income-over-time data for the Financial Reports trend chart.
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
            
        period = request.args.get("period", "weekly").strip().lower()
        today = datetime.now(UTC).date()
        
        # --- NEW: Handle Yearly (Last 12 Months) ---
        if period == "yearly":
            income_by_month = {}
            labels = []
            # Generate last 12 months keys
            current = today.replace(day=1)
            months = []
            for i in range(12):
                months.append(current)
                if current.month == 1:
                    current = current.replace(year=current.year-1, month=12)
                else:
                    current = current.replace(month=current.month-1)
            months.reverse() # Oldest to newest
            
            for m in months:
                key = m.strftime("%Y-%m")
                income_by_month[key] = 0.0
                labels.append(m.strftime("%b %Y"))
                
            try:
                done_docs = self._get_done_procedures_cached()
                for data in done_docs:
                    for p in data.get("procedures", []):
                        date_str = str(p.get("date", "")).strip()
                        if date_str:
                            try:
                                proc_date = datetime.fromisoformat(date_str).date()
                                key = proc_date.strftime("%Y-%m")
                                if key in income_by_month:
                                    income_by_month[key] += self.safe_float(p.get("paid", 0))
                            except:
                                pass
            except Exception as e:
                print("FINANCIAL CHART DATA ERROR:", e)
                return jsonify({"success": False, "message": str(e)}), 500
                
            values = [round(income_by_month[k], 2) for k in income_by_month.keys()]
            return jsonify({"success": True, "period": period, "labels": labels, "data": values})

        # --- NEW: Handle Overall (All Time Total) ---
        if period == "overall":
            total = 0.0
            try:
                done_docs = self._get_done_procedures_cached()
                for data in done_docs:
                    for p in data.get("procedures", []):
                        total += self.safe_float(p.get("paid", 0))
            except Exception as e:
                print("FINANCIAL CHART DATA ERROR:", e)
                return jsonify({"success": False, "message": str(e)}), 500
            return jsonify({"success": True, "period": period, "labels": ["All Time"], "data": [round(total, 2)]})

        # --- Existing Logic for Today/Weekly/Monthly ---
        if period == "today":
            start_date = today
            num_days = 1
        elif period == "monthly":
            start_date = today - timedelta(days=29)
            num_days = 30
        else:
            period = "weekly"
            start_date = today - timedelta(days=6)
            num_days = 7
            
        date_keys = [
            (start_date + timedelta(days=i)).isoformat()
            for i in range(num_days)
        ]
        income_by_date = {d: 0.0 for d in date_keys}
        
        try:
            done_docs = self._get_done_procedures_cached()
            for data in done_docs:
                for p in data.get("procedures", []):
                    date_str = str(p.get("date", "")).strip()
                    if date_str in income_by_date:
                        income_by_date[date_str] += self.safe_float(p.get("paid", 0))
        except Exception as e:
            print("FINANCIAL CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500
            
        if period == "today":
            labels = ["Today"]
        else:
            labels = [
                datetime.fromisoformat(d).strftime("%b %d")
                for d in date_keys
            ]
        values = [round(income_by_date[d], 2) for d in date_keys]
        
        return jsonify({
            "success": True,
            "period": period,
            "labels": labels,
            "data": values
        })

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
    
    def find_unlinked_patient_match(self, first_name, last_name, middle_name="", birthday=""):
        match = self.find_patient(
            first_name=first_name, 
            middle_name=middle_name, 
            last_name=last_name,
            birthday=birthday
        )
        if not match:
            return None
        account_uid = match.get("account_uid") or ""
        # Empty, or still just a walk-in placeholder — treat as unlinked
        if not account_uid or account_uid.startswith("walkin_"):
            return match
        return None

    def maybe_flag_patient_match(self, uid, first_name, last_name, middle_name="", birthday=""):
        """Runs once per account. If an unlinked walk-in Patients record
        shares this name, stash it in session so the frontend can prompt."""
        try:
            print(f"--- PATIENT MATCH CHECK STARTING FOR UID: {uid} ---")
            print(f"Searching for: First='{first_name}', Last='{last_name}', Middle='{middle_name}', Bday='{birthday}'")
            
            account_ref = self.db.collection(self.Customer_Account).document(uid)
            account_doc = account_ref.get()
            account_data = account_doc.to_dict() if account_doc.exists else {}
            
            # TEMPORARY FIX: Ignore the 'patient_match_checked' flag so it runs again
            # if account_data.get("patient_match_checked"):
            #     print("SKIPPING: Already checked this account.")
            #     return
                
            # Mark as checked so it doesn't run on every single login in the future
            account_ref.set({"patient_match_checked": True}, merge=True)
            
            first_name = (first_name or "").strip()
            last_name = (last_name or "").strip()
            if not first_name or not last_name:
                print("SKIPPING: Missing first or last name.")
                return
                
            candidate = self.find_unlinked_patient_match(first_name, last_name, middle_name, birthday)
            
            if candidate:
                print(f"MATCH FOUND! Patient ID: {candidate['patient_id']}")
                session['pending_patient_match'] = {
                    "patient_id": candidate["patient_id"],
                    "display_name": f"{candidate.get('first_name','')} {candidate.get('last_name','')}".strip()
                }
            else:
                print("NO MATCH FOUND in Patients collection.")
                
        except Exception as e:
            print("PATIENT MATCH CHECK ERROR:", e)
    
    def has_visit_history(self, uid):
        """A real patient = someone with at least one accepted appointment
        (Approve) or completed treatment (Done_procedure)."""
        account_ref = self.db.collection(self.Customer_Account).document(uid)

        approve_docs = account_ref.collection("Approve").limit(1).stream()
        if any(True for _ in approve_docs):
            return True

        done_docs = account_ref.collection("Done_procedure").limit(1).stream()
        if any(True for _ in done_docs):
            return True

        return False
    
    def admin_procedure_chart_data(self):
        """
        Returns per-procedure breakdown. Now supports period filtering.
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
            
        period = request.args.get("period", "overall").strip().lower()
        today = datetime.now(UTC).date()
        
        # Determine start date for filtering
        start_date = None
        if period == "today":
            start_date = today
        elif period == "weekly":
            start_date = today - timedelta(days=6)
        elif period == "monthly":
            start_date = today - timedelta(days=29)
        elif period == "yearly":
            start_date = today - timedelta(days=364) # Last 12 months
        # 'overall' leaves start_date as None (no filter)

        counts = {}
        revenue = {}
        display_names = {}
        
        try:
            done_docs = self._get_done_procedures_cached()
            for data in done_docs:
                for p in data.get("procedures", []):
                    # Filter by date if a period is selected (not overall)
                    if start_date is not None:
                        date_str = str(p.get("date", "")).strip()
                        if not date_str:
                            continue
                        try:
                            proc_date = datetime.fromisoformat(date_str).date()
                            if proc_date < start_date:
                                continue
                        except ValueError:
                            continue # Skip invalid dates
                    
                    name = str(p.get("procedure", "")).strip()
                    if not name:
                        continue
                    key = name.lower()
                    display_names.setdefault(key, name)
                    counts[key] = counts.get(key, 0) + 1
                    revenue[key] = revenue.get(key, 0) + self.safe_float(p.get("paid", 0))
        except Exception as e:
            print("PROCEDURE CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": str(e)}), 500

        def top_n(metric_dict, limit=10):
            sorted_keys = sorted(metric_dict.keys(), key=lambda k: metric_dict[k], reverse=True)
            top_keys = sorted_keys[:limit]
            other_keys = sorted_keys[limit:]
            labels = [display_names[k] for k in top_keys]
            values = [round(metric_dict[k], 2) for k in top_keys]
            if other_keys:
                other_total = round(sum(metric_dict[k] for k in other_keys), 2)
                if other_total > 0:
                    labels.append("Other")
                    values.append(other_total)
            return labels, values

        count_labels, count_values = top_n(counts)
        revenue_labels, revenue_values = top_n(revenue)
        
        return jsonify({
            "success": True,
            "counts": {"labels": count_labels, "data": count_values},
            "revenue": {"labels": revenue_labels, "data": revenue_values}
        })

        def top_n(metric_dict, limit=10):
            sorted_keys = sorted(metric_dict.keys(), key=lambda k: metric_dict[k], reverse=True)
            top_keys = sorted_keys[:limit]
            other_keys = sorted_keys[limit:]

            labels = [display_names[k] for k in top_keys]
            values = [round(metric_dict[k], 2) for k in top_keys]

            if other_keys:
                other_total = round(sum(metric_dict[k] for k in other_keys), 2)
                if other_total > 0:
                    labels.append("Other")
                    values.append(other_total)

            return labels, values

        count_labels, count_values = top_n(counts)
        revenue_labels, revenue_values = top_n(revenue)

        return jsonify({
            "success": True,
            "counts": {"labels": count_labels, "data": count_values},
            "revenue": {"labels": revenue_labels, "data": revenue_values}
        })

    
        

    def _register_routes(self):
        """Polymorphism: Register all routes"""
        self.app.route("/payment-success")(self.payment_success)
        self.app.route("/update-profile", methods=["POST"])(self.update_profile)
        self.app.route("/upload_profile_pic", methods=["POST"])(self.upload_profile_pic)
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
        self.app.route("/admin/my_patients_page")(self.admin_my_patients_page)
        self.app.route("/admin/appointments_page")(self.admin_appointments_page)
        self.app.route("/admin/approved_page")(self.admin_approved_page)
        self.app.route("/admin/manageable_accounts_page")(self.admin_manageable_accounts_page)
        self.app.route("/get_patient/<uid>")(self.get_patient)
        self.app.route("/admin_login", methods=["GET", "POST"])(self.adminLogin)
        self.app.route("/services/<service_id>")(self.service_detail)
        self.app.route("/location")(self.dental_location)
        self.app.route("/prac")(self.prac)
        self.app.route("/medical_records")(self.medical_records)
        self.app.route("/save_dental_record", methods=["POST"])(self.save_dental_record)
        self.app.route("/get_treatment_info/<patient_id>")(self.get_treatment_info)
        self.app.route("/get_approve/<uid>")(self.get_approve)
        self.app.route("/admin/create_appointment", methods=["POST"])(self.admin_create_appointment)
        self.app.route("/get_blocked_slots")(self.get_blocked_slots)
        self.app.route("/admin/block_slot", methods=["POST"])(self.admin_block_slot)
        self.app.route("/admin/unblock_slot", methods=["POST"])(self.admin_unblock_slot)
        self.app.route("/search_patients")(self.search_patients)
        self.app.route("/admin/update_patient", methods=["POST"])(self.update_patient)
        self.app.route("/admin/delete_patient", methods=["POST"])(self.delete_patient)
        self.app.route("/admin/toggle_user_block", methods=["POST"])(self.toggle_user_block)
        self.app.route("/admin/update_treatment_record", methods=["POST"])(self.update_treatment_record)
        self.app.route("/admin/check_duplicate_patient")(self.check_duplicate_patient)
        self.app.route("/link_patient_account", methods=["POST"])(self.link_patient_account)
        self.app.route("/get_patient_profile_data")(self.get_patient_profile_data)
        self.app.route("/admin/merge_patients", methods=["POST"])(self.admin_merge_patients)
        self.app.route("/admin/financial_chart_data")(self.admin_financial_chart_data)
        self.app.route("/privacy-policy")(self.privacy_policy)
        self.app.route("/terms-of-service")(self.terms_of_service)
        self.app.route("/admin/procedure_chart_data")(self.admin_procedure_chart_data)




app_instance = DentalClinicApp()
app = app_instance.app

if __name__ == "__main__":
    print("🦷 Capizonda Dental Clinic Server Starting...")
    app.run(debug=True, port=5000)