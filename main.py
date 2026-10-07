import base64
import hashlib
import hmac
import os
import random
import re
import smtplib
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta, timezone
from email.message import EmailMessage

import bleach
import firebase_admin
import requests
from dotenv import load_dotenv
from firebase_admin import auth, credentials
from firebase_admin import firestore as fb_firestore
from flask import (
    Flask,
    abort,
    flash,
    get_flashed_messages,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFError, CSRFProtect
from google.auth.transport import requests as google_requests
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import id_token

import firebase
from cache_store import SimpleCache

# The clinic runs on Philippine time (UTC+8, no daylight saving). Used by the
# Financial Reports chart so "today" / "this month" flip at local midnight
# instead of 8 AM.
PH_TZ = timezone(timedelta(hours=8))

# Doctors Calendar: blocking several days at once.
MAX_BLOCK_RANGE_DAYS = 90
MAX_UNBLOCK_RANGE_DAYS = 366
MAX_PAST_MARK_LOOKBACK_DAYS = 730


def parse_ymd(value):
    """'YYYY-MM-DD' -> date, or None when it is not a real calendar date."""
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def expand_range_days(start, end, skip_weekdays=(), max_days=MAX_BLOCK_RANGE_DAYS):
    """
    Every day from `start` to `end` (both included) as 'YYYY-MM-DD', leaving
    out the weekdays in `skip_weekdays` (Monday=0 ... Sunday=6).
    Raises ValueError for a backwards range or one longer than `max_days`.
    """
    if end < start:
        raise ValueError("The end date is before the start date.")
    span = (end - start).days + 1
    if span > max_days:
        raise ValueError(f"Please choose {max_days} days or fewer at a time.")
    skip = set(skip_weekdays)
    days = []
    for offset in range(span):
        day = start + timedelta(days=offset)
        if day.weekday() in skip:
            continue
        days.append(day.strftime("%Y-%m-%d"))
    return days


def group_blocked_days(entries):
    """
    Collapse per-day BlockedSlots entries into notices a patient can read.

    `entries` are dicts with date, full_day, blocked_times, patient_message
    and (optionally) range_id. Days saved together as one range share a
    range_id and become one notice even when some days were skipped (such as
    Sundays); other days are merged only when they are consecutive and carry
    the same message. Only the patient message is used, never the internal
    reason.
    """
    groups = []
    by_range = {}
    open_groups = {}

    for e in sorted(entries, key=lambda x: x["date"]):
        closed = bool(e.get("full_day"))
        times = [] if closed else sorted(e.get("blocked_times") or [])
        if not closed and not times:
            continue
        kind = "closed" if closed else "partial"
        message = (e.get("patient_message") or "").strip()
        rid = e.get("range_id") or ""
        day = e["date"]

        if rid and closed:
            g = by_range.get(rid)
            if g:
                g["end"] = day
                g["days"] += 1
                continue
            g = {"start": day, "end": day, "type": kind, "message": message,
                 "times": [], "days": 1, "_key": "r:" + rid}
            by_range[rid] = g
            groups.append(g)
            continue

        key = (kind, message, tuple(times))
        g = open_groups.get(key)
        prev_day = (parse_ymd(g["end"]) + timedelta(days=1)).strftime("%Y-%m-%d") if g else None
        if g and prev_day == day:
            g["end"] = day
            g["days"] += 1
            continue
        g = {"start": day, "end": day, "type": kind, "message": message,
             "times": times, "days": 1, "_key": "d:" + day}
        open_groups[key] = g
        groups.append(g)

    for g in groups:
        raw = f"{g.pop('_key')}|{g['start']}|{g['end']}|{g['type']}|{g['message']}|{','.join(g['times'])}"
        g["id"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return sorted(groups, key=lambda x: (x["start"], x["end"]))

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# Admin-scoped flash text must never surface on a patient page. The dashboard
# greeting now travels through admin_welcome_toast instead of the flash queue,
# so anything carrying the "Dr. " honorific is admin-only. This also clears the
# greeting already queued in sessions created before that change.
ADMIN_ONLY_FLASH = re.compile(r"\bDr\.\s")



_HTML_COMMENT = re.compile(r'<!--(?!\[if).*?-->', re.S)
_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.S)
_LINE_COMMENT = re.compile(r'^[ \t]*//.*(?:\r?\n|$)', re.M)
_SCRIPT_TAG = re.compile(r'(<script\b[^>]*>)(.*?)(</script>)', re.S | re.I)
_STYLE_TAG = re.compile(r'(<style\b[^>]*>)(.*?)(</style>)', re.S | re.I)

def strip_comments(html):
    html = _HTML_COMMENT.sub('', html)
    html = _SCRIPT_TAG.sub(
        lambda m: m.group(1) + _LINE_COMMENT.sub('', _BLOCK_COMMENT.sub('', m.group(2))) + m.group(3), html)
    html = _STYLE_TAG.sub(
        lambda m: m.group(1) + _BLOCK_COMMENT.sub('', m.group(2)) + m.group(3), html)
    return html

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
        self._setup_error_handlers()
        self._setup_csrf()
        self._setup_security_headers()
        self._register_routes()
        self.csrf.exempt(self.paymongo_webhook)
        self.PATIENTS_PAGE_SIZE = 25
        print("🦷 Capizonda Dental Clinic Initialized")

    def _setup_app(self):
        self._app = Flask(__name__)
        import read_meter; read_meter.install(self._app)

        def patient_flashed_messages():
            messages = get_flashed_messages(with_categories=True)
            return [
                m for m in messages
                if m[0] != "admin" and not ADMIN_ONLY_FLASH.search(m[1])
            ]

        self._app.jinja_env.globals["patient_flashed_messages"] = patient_flashed_messages

        # Server-rendered cards show a stored DentistName. Older rows hold the
        # short "Dr. Capizonda", so they are rendered through the same
        # display helper the API uses, otherwise the same dentist appears under
        # two spellings in one page. Registered as a global (not a filter) to
        # match the existing pattern above.
        self._app.jinja_env.globals["dentist_display"] = self.display_dentist_name

        # Same deal for the appointment date on the Accepted Patients cards.
        self._app.jinja_env.globals["appt_datetime_display"] = self.display_appt_datetime
        self._app.jinja_env.globals["appt_datetime_short"] = self.display_appt_datetime_short

    def _setup_config(self):
        self.app.config["MAIL_SERVER"] = "smtp.gmail.com"
        self.app.config["MAIL_PORT"] = 587
        self.app.config["MAIL_USE_TLS"] = True
        self.app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
        self.app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
        self.app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")
        self.app.config["MAIL_TIMEOUT"] = 10
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret.startswith("<") or len(secret) < 32:
            raise RuntimeError("SECRET_KEY is missing or is a placeholder")
        self.app.secret_key = secret
        self.app.permanent_session_lifetime = timedelta(hours=8)
        self.app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
        self.app.config["SESSION_COOKIE_HTTPONLY"] = True
        self.app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        self.app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
        

    def _setup_mail(self):
        self._mail = Mail(self.app)
        print("MAIL USER:", self.app.config["MAIL_USERNAME"])
        print("MAIL PASS:", "Loaded" if self.app.config["MAIL_PASSWORD"] else "Missing")

    def _setup_firebase(self):
        basedir = os.path.abspath(os.path.dirname(__file__))
        key_path = os.path.join(basedir, os.getenv("FIREBASE_KEY_PATH", "dentech_key.json"))
        if not firebase_admin._apps:
            try:
                if not os.path.exists(key_path):
                    raise FileNotFoundError(f"Firebase key not found at: {key_path}")
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred, {"projectId": os.getenv("FIREBASE_PROJECT_ID")})
                self._db = fb_firestore.client()
                print("✅ Firebase initialized successfully")
            except Exception as e:
                print("❌ Firebase initialization failed:", e)
                self._db = None
        else:
            self._db = fb_firestore.client()
            print("♻️ Firebase already initialized")

        # DEV ONLY: point Firestore at the local emulator (zero billed reads).
        # Start it with:  firebase emulators:start --only firestore
        # then run the app with:  USE_FIRESTORE_EMULATOR=1 python main.py
        # (PowerShell:  $env:USE_FIRESTORE_EMULATOR="1"; python main.py)
        if os.getenv("USE_FIRESTORE_EMULATOR") == "1":
            os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
            from google.auth.credentials import AnonymousCredentials
            from google.cloud import firestore as gc_firestore
            self._db = gc_firestore.Client(
                project=os.getenv("FIREBASE_PROJECT_ID"), credentials=AnonymousCredentials()
            )
            print(f"🧪 Firestore EMULATOR at {os.environ['FIRESTORE_EMULATOR_HOST']} (no real reads)")

    def _setup_constants(self):
        self.Customer_Account = "Customer_Account"
        self.Appointment_cliets = "appointments"
        self.Doc_Patients = "Patients"
        self.Blocked_Slots = "BlockedSlots"
        self.CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        self.firebase_api_key = os.getenv("FIREBASE_API_KEY", "")
        if not self.firebase_api_key:
            print("⚠️  FIREBASE_API_KEY is missing; set the FIREBASE_* values in .env")
        
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
            
        self.ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

        # In-memory cache to cut Firestore reads on hot admin endpoints.
        # See cache_store.py for how it works and its single-process caveat.
        self.cache = SimpleCache()
        self.CACHE_TTL_SECONDS = 1800  # 30 min safety-net expiry

        # One lock per cache so only one request refills it at a time
        self._done_procedures_lock = threading.Lock()
        # account uid -> identity fields already saved back to the account by
        # _heal_account_identity(), so a list render never repeats that write.
        self._identity_healed = {}
        self._accounts_lock = threading.Lock()
        self._patients_lock = threading.Lock()

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
        with self._done_procedures_lock:
            cached = self.cache.get("done_procedures_all")
            if cached is not None:
                return cached
            docs = []
            # Only these fields are ever used from the cached scan (checked
            # against every consumer). Leaving out "chart" and "chart_image"
            # keeps the big dental-chart images out of memory. This does NOT
            # reduce billed reads (Firestore bills per document).
            done_query = self.db.collection_group("Done_procedure").select(
                ["procedures", "uid", "Patient_unq_id"]
            )
            for doc in done_query.stream():
                d = doc.to_dict() or {}
                # Which account this record lives under; used to look up the
                # patient's name when the record itself has no usable uid.
                try:
                    d["_account_uid"] = doc.reference.parent.parent.id
                except Exception:
                    d["_account_uid"] = ""
                docs.append(d)
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
        with self._accounts_lock:
            cached = self.cache.get("manageable_accounts_all")
            if cached is not None:
                return cached
            query = self.db.collection(self.Customer_Account).where("provider", "in", ["google", "password"])
            docs = [(doc.id, doc.to_dict()) for doc in query.stream()]
            self.cache.set("manageable_accounts_all", docs, ttl_seconds=self.CACHE_TTL_SECONDS)
            return docs

    def _invalidate_accounts_cache(self):
        self.cache.invalidate("manageable_accounts_all")
        self.cache.invalidate("unpaid_account_names")

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
        with self._patients_lock:
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

    def _get_account_contact_and_sex(self, account_uid, cache=None):
        """
        Fallback lookup for the two identity fields that are NOT guaranteed
        to exist on Customer_Account/{uid}:

        contact_number - only written by password sign-up, the patient
                        profile update, and the admin EDIT save. The
                        Google sign-in path (which never sees a phone
                        number) and the admin walk-in account creator
                        never write it, so those accounts rendered a
                        blank "Mobile Number" forever.
        last_sex       - only written when an appointment actually
                        answered the Sex question, so any booking that
                        left it blank leaves the account with no sex.

        Both values ARE recorded on every appointment/Approve document, so
        fall back to the most recent one instead of rendering an empty cell.
        Stops at the first document that actually carries a value, so this
        costs at most one small query per row that is missing something.

        `cache` is a per-render dict so a row is never read twice.
        Returns (contact_number, sex, civil_status); any may be "".

        CivilStatus is included here because it is only ever written to the
        appointment/Approve documents, never to Customer_Account, so it rides
        along on the same read the other two already needed.
        """
        if not account_uid:
            return ("", "", "")

        if cache is not None and account_uid in cache:
            return cache[account_uid]

        account_ref = self.db.collection(
            self.Customer_Account
        ).document(account_uid)

        # Approved history first, then anything still pending.
        for collection_name, order_field in (
            ("Approve", "accepted_at"),
            (self.Appointment_cliets, "appointment_date"),
        ):
            docs = None

            # Newest first when the sort field is present and indexed...
            try:
                docs = list(
                    account_ref.collection(collection_name)
                    .order_by(order_field, direction="DESCENDING")
                    .limit(5)
                    .stream()
                )
            except Exception:
                docs = None

            # ...and an unordered scan otherwise. Firestore returns an EMPTY
            # result (rather than raising) when no document carries the sort
            # field, so this has to trigger on "no rows" as well, or a
            # legacy collection with no appointment_date would come back
            # blank.
            if not docs:
                try:
                    docs = list(
                        account_ref.collection(collection_name)
                        .limit(5)
                        .stream()
                    )
                except Exception:
                    docs = None

            for doc in (docs or []):
                data = doc.to_dict() or {}
                contact = str(data.get("ContactNumber") or "").strip()
                sex = str(data.get("Sex") or "").strip()
                civil = str(
                    data.get("CivilStatus") or data.get("civil_status") or ""
                ).strip()
                if contact or sex or civil:
                    result = (contact, sex, civil)
                    if cache is not None:
                        cache[account_uid] = result
                    return result

        result = ("", "", "")
        if cache is not None:
            cache[account_uid] = result
        return result

    def _resolve_google_name_fields(self, existing_data, google_name):
        """
        Name fields to write when a Google account signs in.

        The Google profile name must never overwrite a name the admin set in
        "My Patients": the account keeps whatever firstname/lastname it
        already has, and `name` is re-synced from those parts so every
        screen that reads `name` agrees with the editable ones.

        Only an account with no name parts of its own adopts the Google name,
        and then it is split into the parts so the admin edit form is
        pre-filled instead of blank. A single-word Google name leaves
        lastname empty, which the admin can complete.
        """
        data = existing_data or {}
        google_name = str(google_name or "").strip()

        first = str(data.get("firstname") or "").strip()
        middle = str(data.get("middlename") or "").strip()
        last = str(data.get("lastname") or "").strip()

        if first or last:
            return {
                "firstname": first,
                "middlename": middle,
                "lastname": last,
                "name": f"{first} {last}".strip()
            }

        parts = google_name.split(" ", 1)
        return {
            "firstname": parts[0] if parts else "",
            "lastname": parts[1] if len(parts) > 1 else "",
            # No middlename on a fresh adopt: middle is never inferred, and
            # overwriting an existing value with "" would lose data.
            **({} if "middlename" in data else {}),
            "name": google_name
        }

    def _resolve_account_identity(self, account_uid, account_data, cache=None):
        """
        contact_number / sex / civil_status for a Customer_Account doc,
        preferring the denormalised values already on the account and falling
        back to the patient's own appointment history. See
        _get_account_contact_and_sex() for why the fallback is needed.
        """
        data = account_data or {}

        contact = str(
            data.get("contact_number")
            or data.get("ContactNumber")
            or ""
        ).strip()

        sex = str(
            data.get("last_sex")
            or data.get("sex")
            or ""
        ).strip()

        # Accounts written by the walk-in/appointment flows carry it here;
        # password and Google sign-ups do not.
        civil = str(
            data.get("CivilStatus")
            or data.get("civil_status")
            or ""
        ).strip()

        if not contact or not sex or not civil:
            fb_contact, fb_sex, fb_civil = self._get_account_contact_and_sex(
                account_uid, cache
            )
            # Save what the fallback found onto the account (only the fields
            # the account itself was missing) so the next render reads it
            # straight from the account and skips the appointment lookup.
            self._heal_account_identity(
                account_uid,
                account_data,
                contact="" if contact else fb_contact,
                sex="" if sex else fb_sex,
                civil="" if civil else fb_civil,
            )
            contact = contact or fb_contact
            sex = sex or fb_sex
            civil = civil or fb_civil

        return (contact, sex, civil)

    def _fill_account_identity_if_blank(self, account_ref, contact="", sex="", civil=""):
        """
        Write contact number / sex / civil status onto a Customer_Account
        document, but ONLY into fields that are blank there. A value that is
        already on the account (for example one an admin corrected in My
        Patients) is never overwritten.

        The account is read fresh each time, so a stale cached copy can never
        cause an overwrite. Field names match what _resolve_account_identity()
        already reads: contact_number, last_sex, CivilStatus.

        Never raises. Returns the dict of fields written ({} if nothing needed
        writing) or None if something went wrong.
        """
        try:
            contact = str(contact or "").strip()
            sex = str(sex or "").strip()
            civil = str(civil or "").strip()
            if not (contact or sex or civil):
                return {}

            snap = account_ref.get()
            if not snap.exists:
                return {}
            current = snap.to_dict() or {}

            updates = {}
            if contact and not str(
                current.get("contact_number") or current.get("ContactNumber") or ""
            ).strip():
                updates["contact_number"] = contact
            if sex and not str(
                current.get("last_sex") or current.get("sex") or ""
            ).strip():
                updates["last_sex"] = sex
            if civil and not str(
                current.get("CivilStatus") or current.get("civil_status") or ""
            ).strip():
                updates["CivilStatus"] = civil

            if updates:
                account_ref.update(updates)
                print(f"[WRITES] account {getattr(account_ref, 'id', '?')}: filled blank "
                      f"{', '.join(sorted(updates))}")
            return updates
        except Exception as e:
            print("IDENTITY FILL FAILED:", e)
            return None

    def _heal_account_identity(self, account_uid, account_data, contact="", sex="", civil=""):
        """
        Self-healing step for _resolve_account_identity(): the caller passes
        only the values the appointment-history fallback found for fields the
        account was missing. They are saved once, fill-if-blank, and also
        placed into the in-memory account dict so any cached copy stops
        triggering the fallback. Never raises.
        """
        try:
            if not account_uid:
                return
            done = self._identity_healed.setdefault(account_uid, set())
            want = {}
            if contact and "contact_number" not in done:
                want["contact_number"] = str(contact).strip()
            if sex and "last_sex" not in done:
                want["last_sex"] = str(sex).strip()
            if civil and "CivilStatus" not in done:
                want["CivilStatus"] = str(civil).strip()
            want = {k: v for k, v in want.items() if v}
            if not want:
                return

            account_ref = self.db.collection(self.Customer_Account).document(account_uid)
            written = self._fill_account_identity_if_blank(
                account_ref,
                contact=want.get("contact_number", ""),
                sex=want.get("last_sex", ""),
                civil=want.get("CivilStatus", ""),
            )
            if written is None:
                return  # failed; allow a retry on a later render
            done.update(want.keys())
            if written and isinstance(account_data, dict):
                account_data.update(written)
        except Exception as e:
            print("IDENTITY HEAL FAILED:", e)

    def _merge_identity_fill(self, source_ref, target_ref, account_update):
        """
        Used by both merge functions. Adds contact number / sex / civil status
        from the source account to `account_update` for any field the TARGET
        account has blank. Never overwrites a value the target already has,
        and never overrides a last_sex the merge already computed.

        Never raises: if the reads fail, merge simply proceeds without it.
        """
        try:
            source_snap = source_ref.get()
            target_snap = target_ref.get()
            source_data = (source_snap.to_dict() or {}) if source_snap.exists else {}
            target_data = (target_snap.to_dict() or {}) if target_snap.exists else {}

            def first(d, *keys):
                for k in keys:
                    v = str(d.get(k) or "").strip()
                    if v:
                        return v
                return ""

            if not first(target_data, "contact_number", "ContactNumber"):
                v = first(source_data, "contact_number", "ContactNumber")
                if v:
                    account_update["contact_number"] = v

            if (
                not first(target_data, "last_sex", "sex")
                and not account_update.get("last_sex")
            ):
                v = first(source_data, "last_sex", "sex")
                if v:
                    account_update["last_sex"] = v

            if not first(target_data, "CivilStatus", "civil_status"):
                v = first(source_data, "CivilStatus", "civil_status")
                if v:
                    account_update["CivilStatus"] = v
        except Exception as e:
            print("MERGE IDENTITY FILL FAILED:", e)
        return account_update

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


    def compute_age_and_birth_year(self, birthday):
        """
        Given a birthday string (YYYY-MM-DD, as produced by an HTML
        <input type="date">), return (age, birth_year) as ints.

        Age is always computed live from the stored Birthday rather
        than saved anywhere, so it can never go stale/drift out of
        sync the way a manually-entered number would.

        Returns (None, None) if there's no usable birthday on file.
        """
        birthday = str(birthday or "").strip()
        if not birthday:
            return None, None

        try:
            bday = datetime.strptime(birthday[:10], "%Y-%m-%d").date()
        except ValueError:
            return None, None

        today = datetime.now(UTC).date()
        had_birthday_this_year = (today.month, today.day) >= (bday.month, bday.day)
        age = today.year - bday.year - (0 if had_birthday_this_year else 1)

        return age, bday.year

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


    def display_appt_datetime(self, value):
        """
        Render a stored appointment_date for the admin cards.

        Firestore stores "YYYY-MM-DD HH:MM" because that exact string is what the
        blocked-slot lookups and the order_by cursor compare against, so it must
        never be rewritten - only displayed differently. This mirrors
        formatApptDateTime() in static/js/appointments-helpers.js exactly; the
        admin renders these cards from JS, and the two paths must not disagree.
        """

        raw = str(value or "").strip()
        if not raw:
            return "Not scheduled"

        match = re.match(
            r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?", raw
        )
        if not match:
            return raw

        months = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        month_index = int(match.group(2)) - 1
        if month_index < 0 or month_index >= len(months):
            return raw

        date_part = f"{months[month_index]} {int(match.group(3))}, {match.group(1)}"
        if match.group(4) is None:
            return date_part

        # Stored hours are 24-hour ("13:00"), so the meridiem has to be derived
        # and the hour converted. The picker offers real PM slots (12:00 PM to
        # 5:00 PM), so appending "AM" unconditionally would print "13:00AM" for a
        # 1:00 PM appointment.
        hour24 = int(match.group(4))
        meridiem = "PM" if hour24 >= 12 else "AM"
        hour12 = hour24 % 12 or 12
        hours = f"{hour12:02d}"

        return f"{date_part} - {hours}:{match.group(5)}{meridiem}"

    def display_appt_datetime_short(self, value):
        """
        Compact appointment date for the dashboard cards: "6 Oct 2026, 9:00 AM".

        display_appt_datetime() is deliberately verbose ("October 6, 2026 -
        09:00AM") because it is read on its own line under a heading. In a card
        row it competes with the name for horizontal space, so this drops to
        abbreviated months and a 12-hour clock. Same 24-hour input, same
        meridiem handling.
        """

        raw = str(value or "").strip()
        if not raw:
            return ""

        match = re.match(
            r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?", raw
        )
        if not match:
            return raw

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        month_index = int(match.group(2)) - 1
        if month_index < 0 or month_index >= len(months):
            return raw

        out = f"{int(match.group(3))} {months[month_index]} {match.group(1)}"
        if match.group(4) is None:
            return out

        hour24 = int(match.group(4))
        meridiem = "AM" if hour24 < 12 else "PM"
        hour12 = hour24 % 12 or 12

        return f"{out}, {hour12}:{match.group(5)} {meridiem}"

    def display_dentist_name(self, value):
        """
        Human-facing spelling of a stored dentist name.

        Records saved before the rename hold "Dr. Capizonda"; the admin now
        enters "Dr. Julix Dionne Capizonda". Returning the canonical spelling
        keeps one dentist from appearing under two names across the schedule,
        the conflict messages and the admin tables. Anything unrecognised is
        returned trimmed but otherwise untouched, so other/future dentists
        keep working.
        """

        raw = str(value or "").strip()
        if not raw:
            return ""

        normalized = " ".join(raw.lower().split())

        if normalized in ("dr. capizonda", "dr capizonda", "capizonda",
                          "dr. julix dionne capizonda",
                          "dr julix dionne capizonda",
                          "julix dionne capizonda"):
            return "Dr. Julix Dionne Capizonda"

        return raw

    def normalize_dentist_name(self, value):
        """
        Reduce a dentist name to an identity key for double-booking checks.

        dentist_name is a free-text field, so this has to absorb the ways one
        practitioner can be spelled: case, stray whitespace, and the honorific
        being present or absent.

        It also has to absorb the rename. Records saved before the dentist was
        listed by his full name carry "Dr. Capizonda", while anything saved now
        carries "Dr. Julix Dionne Capizonda". A plain case-fold would treat those
        as two different dentists, so the conflict check would stop matching old
        rows and the same slot could be booked twice. Both spellings therefore
        collapse to the same key. Unknown names pass through unchanged, so any
        other or future dentist keeps working without a code change.
        """

        if not value:
            return ""

        normalized = " ".join(str(value).strip().lower().split())

        # Known spellings of the same practitioner -> one key.
        if normalized in ("dr. capizonda", "dr capizonda", "capizonda",
                          "dr. julix dionne capizonda",
                          "dr julix dionne capizonda",
                          "julix dionne capizonda"):
            return "capizonda"

        # Anything else: drop the honorific so "Dr. Smith" and "Smith" agree.
        if normalized.startswith("dr. "):
            normalized = normalized[4:]
        elif normalized.startswith("dr "):
            normalized = normalized[3:]

        return normalized


    def find_appointment_conflict(self, dentist_name, appointment_date, exclude_doc_id=None):
        """
        Check whether an already-ACCEPTED appointment (Approve collection)
        exists for the same dentist at the same date/time.

        Only checks confirmed appointments, not pending requests -- two
        pending requests can compete for the same slot, and the conflict
        only matters once one of them actually gets accepted.

        NOTE: the query filters on appointment_date server-side, which
        needs a collection-group index on Approve.appointment_date. If that
        index is missing the check fails loudly in the console (see the
        except block below) instead of scanning the whole collection.
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
            # Returning None means "no conflict", so a failure here (most
            # often a missing collection-group index on Approve.appointment_date)
            # would silently allow double-booking. Make it impossible to miss.
            print("=" * 60)
            print("!! FIND APPOINTMENT CONFLICT FAILED -- DOUBLE-BOOKING CHECK IS OFF !!")
            print("   Create a collection-group index on Approve.appointment_date")
            print("   (Firebase console > Firestore > Indexes > Single field > Collection group).")
            print("   Error:", e)
            print("=" * 60)
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
                    "dentist_name": self.display_dentist_name(data.get("DentistName", "")),
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

    def is_slot_blocked(self, appointment_date, for_patient=False):
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

        # Patients only ever see the message written for them, never the
        # internal note (admin callers keep getting the internal reason).
        patient_note = (data.get("patient_message") or "").strip() if for_patient else ""

        if data.get("full_day"):
            if for_patient:
                return True, patient_note or "Dentist unavailable this day"
            return True, data.get("reason", "Dentist unavailable this day")

        if time in data.get("blocked_times", []):
            if for_patient:
                return True, patient_note or "Dentist unavailable at this time"
            return True, data.get("reason", "Dentist unavailable at this time")

        return False, None


    BLOCKED_SLOTS_CACHE_KEY = "blocked_slots_upcoming"
    BLOCKED_SLOTS_TTL_SECONDS = 120

    def _load_blocked_slots(self):
        """Upcoming BlockedSlots (cached). Includes the internal reason."""
        result = self.cache.get(self.BLOCKED_SLOTS_CACHE_KEY)

        if result is None:
            # Only today onward (minus 1 day to be safe across timezones).
            cutoff = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
            query = self.db.collection(self.Blocked_Slots).where(
                filter=FieldFilter("date", ">=", cutoff)
            )

            result = []
            for doc in query.stream():
                data = doc.to_dict()
                result.append({
                    "date": doc.id,
                    "full_day": bool(data.get("full_day", False)),
                    "blocked_times": data.get("blocked_times", []),
                    "reason": data.get("reason", ""),
                    "patient_message": data.get("patient_message", ""),
                    "range_id": data.get("range_id", "")
                })

            self.cache.set(
                self.BLOCKED_SLOTS_CACHE_KEY,
                result,
                ttl_seconds=self.BLOCKED_SLOTS_TTL_SECONDS
            )

        return result

    def get_blocked_slots(self):
        try:
            result = self._load_blocked_slots()

            # The Doctors Calendar (logged-in admin) sees everything. Anyone
            # else gets only what is safe for patients: the internal note is
            # never sent, and "reason" carries the patient message.
            if session.get('admin_logged_in'):
                return jsonify(result)

            return jsonify([
                {
                    "date": item["date"],
                    "full_day": item["full_day"],
                    "blocked_times": item["blocked_times"],
                    "reason": item.get("patient_message", ""),
                    "patient_message": item.get("patient_message", "")
                }
                for item in result
            ])
        except Exception as e:
            print("GET BLOCKED SLOTS ERROR:", e)
            return jsonify({"error": "Something went wrong. Please try again."}), 500

    def get_clinic_notices(self):
        """Public: upcoming closures / limited-availability notices for the patient bell."""
        try:
            today = datetime.now(PH_TZ).strftime("%Y-%m-%d")
            upcoming = [e for e in self._load_blocked_slots() if e["date"] >= today]
            return jsonify(group_blocked_days(upcoming))
        except Exception as e:
            print("GET CLINIC NOTICES ERROR:", e)
            return jsonify({"error": "Something went wrong. Please try again."}), 500


    def admin_block_slot(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        date = bleach.clean(request.form.get("date", "").strip())
        full_day = request.form.get("full_day", "false") == "true"
        blocked_times = request.form.getlist("blocked_times[]")
        reason = bleach.clean(request.form.get("reason", "").strip())
        patient_message = bleach.clean(request.form.get("patient_message", "").strip())[:200]

        if not date:
            return jsonify({"success": False, "message": "Date is required"}), 400

        day_obj = parse_ymd(date)
        if not day_obj:
            return jsonify({"success": False, "message": "Invalid date"}), 400
        if day_obj < datetime.now(PH_TZ).date():
            return jsonify({"success": False, "message": "Past days can't be changed here. Use \"Mark past days as closed\" instead."}), 400

        if not full_day and not blocked_times:
            return jsonify({
                "success": False,
                "message": "Select full day or at least one time slot"
            }), 400

        # Warn before blocking time that already has appointments. The admin
        # can still go ahead (emergencies happen): the page re-sends the same
        # request with force=true after they confirm. Only newly blocked times
        # are checked, so re-saving an existing block does not nag again.
        if request.form.get("force", "false") != "true":
            try:
                existing_doc = self.db.collection(self.Blocked_Slots).document(date).get()
                existing = existing_doc.to_dict() if existing_doc.exists else {}
                existing_full = bool(existing.get("full_day", False))
                existing_times = set(existing.get("blocked_times", []))

                if existing_full:
                    newly_blocked = set()
                elif full_day:
                    newly_blocked = None  # every time on the day, minus nothing
                else:
                    newly_blocked = set(blocked_times) - existing_times

                if newly_blocked is None or newly_blocked:
                    hits = [
                        a for a in self._appointments_on_day(date)
                        if newly_blocked is None or a["time"] in newly_blocked
                    ]
                    if newly_blocked is None and existing_times:
                        hits = [a for a in hits if a["time"] not in existing_times]

                    if hits:
                        slots = {}
                        for a in hits:
                            slot = slots.setdefault(a["time"], {
                                "time": a["time"], "count": 0,
                                "accepted": 0, "pending": 0, "name": ""
                            })
                            slot["count"] += 1
                            if a["status"] == "Accepted":
                                slot["accepted"] += 1
                            else:
                                slot["pending"] += 1
                            slot["name"] = a["patient_name"]

                        slot_list = sorted(slots.values(), key=lambda x: x["time"])
                        for slot in slot_list:
                            if slot["count"] != 1:
                                slot["name"] = ""  # names only for single bookings

                        return jsonify({
                            "success": False,
                            "conflict": True,
                            "message": "Some of these times already have scheduled appointments.",
                            "total": len(hits),
                            "accepted": sum(1 for a in hits if a["status"] == "Accepted"),
                            "pending": sum(1 for a in hits if a["status"] != "Accepted"),
                            "slots": slot_list
                        }), 409
            except Exception as e:
                # Never block saving because the warning check failed.
                print("ADMIN BLOCK SLOT CONFLICT CHECK ERROR:", e)

        try:
            self.db.collection(self.Blocked_Slots).document(date).set({
                "date": date,
                "full_day": full_day,
                "blocked_times": [] if full_day else blocked_times,
                "reason": reason,
                "patient_message": patient_message,
                "created_by": session.get('admin_uid', ''),
                "updated_at": datetime.now(UTC).isoformat()
            })
            self.cache.invalidate(self.BLOCKED_SLOTS_CACHE_KEY)
            return jsonify({"success": True, "message": "Slot blocked successfully"})
        except Exception as e:
            print("ADMIN BLOCK SLOT ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500


    def admin_unblock_slot(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        date = bleach.clean(request.form.get("date", "").strip())
        if not date:
            return jsonify({"success": False, "message": "Date is required"}), 400

        day_obj = parse_ymd(date)
        if not day_obj:
            return jsonify({"success": False, "message": "Invalid date"}), 400
        if day_obj < datetime.now(PH_TZ).date():
            return jsonify({"success": False, "message": "Past days can't be unblocked, so the closure history stays accurate."}), 400

        try:
            self.db.collection(self.Blocked_Slots).document(date).delete()
            self.cache.invalidate(self.BLOCKED_SLOTS_CACHE_KEY)
            return jsonify({"success": True, "message": "Slot unblocked successfully"})
        except Exception as e:
            print("ADMIN UNBLOCK SLOT ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def _range_conflicts(self, days):
        """
        Appointments on days that are about to be fully blocked, grouped by
        day. Times that are already blocked do not count again (same rule as
        blocking a single day). Two collection-group queries cover the whole
        range, instead of two per day.
        """
        first, last = days[0], days[-1]
        wanted = set(days)

        existing = {}
        for doc in (
            self.db.collection(self.Blocked_Slots)
            .where(filter=FieldFilter("date", ">=", first))
            .where(filter=FieldFilter("date", "<=", last))
            .stream()
        ):
            existing[doc.id] = doc.to_dict() or {}

        per_day = {}
        for group, status in (("Approve", "Accepted"), ("appointments", "Pending")):
            query = (
                self.db.collection_group(group)
                .where(filter=FieldFilter("appointment_date", ">=", first + " 00:00"))
                .where(filter=FieldFilter("appointment_date", "<=", last + " 23:59"))
            )
            for doc in query.stream():
                data = doc.to_dict()
                day, _, time = str(data.get("appointment_date", "")).strip().partition(" ")
                if day not in wanted:
                    continue
                prior = existing.get(day)
                if prior and (prior.get("full_day") or time in (prior.get("blocked_times") or [])):
                    continue
                name = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip()
                per_day.setdefault(day, []).append({
                    "time": time,
                    "status": status,
                    "name": name or "Unknown patient"
                })

        return [
            {"date": day, "appointments": sorted(per_day[day], key=lambda x: x["time"])}
            for day in sorted(per_day)
        ]

    def admin_block_range(self):
        """Block several whole days at once (Doctors Calendar)."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        start = parse_ymd(request.form.get("start_date"))
        end = parse_ymd(request.form.get("end_date"))
        if not start or not end:
            return jsonify({"success": False, "message": "Choose a start and end date"}), 400
        if start < datetime.now(PH_TZ).date():
            return jsonify({"success": False, "message": "You can't block dates in the past"}), 400

        skip = [
            int(v) for v in request.form.getlist("skip_weekdays[]")
            if v.isdigit() and 0 <= int(v) <= 6
        ]
        try:
            days = expand_range_days(start, end, skip)
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        if not days:
            return jsonify({"success": False, "message": "Every day in that range is skipped"}), 400

        reason = bleach.clean(request.form.get("reason", "").strip())[:300]
        patient_message = bleach.clean(request.form.get("patient_message", "").strip())[:200]

        if request.form.get("force", "false") != "true":
            try:
                conflicts = self._range_conflicts(days)
                if conflicts:
                    all_appts = [a for d in conflicts for a in d["appointments"]]
                    return jsonify({
                        "success": False,
                        "conflict": True,
                        "message": "Some of these days already have scheduled appointments.",
                        "total": len(all_appts),
                        "accepted": sum(1 for a in all_appts if a["status"] == "Accepted"),
                        "pending": sum(1 for a in all_appts if a["status"] != "Accepted"),
                        "days": conflicts
                    }), 409
            except Exception as e:
                # Never block saving because the warning check failed.
                print("ADMIN BLOCK RANGE CONFLICT CHECK ERROR:", e)

        try:
            range_id = uuid.uuid4().hex
            stamp = datetime.now(UTC).isoformat()
            batch = self.db.batch()
            for day in days:
                batch.set(self.db.collection(self.Blocked_Slots).document(day), {
                    "date": day,
                    "full_day": True,
                    "blocked_times": [],
                    "reason": reason,
                    "patient_message": patient_message,
                    "range_id": range_id,
                    "created_by": session.get('admin_uid', ''),
                    "updated_at": stamp
                })
            batch.commit()
            self.cache.invalidate(self.BLOCKED_SLOTS_CACHE_KEY)
            return jsonify({
                "success": True,
                "message": f"Blocked {len(days)} day{'s' if len(days) != 1 else ''}",
                "days": len(days),
                "range_id": range_id
            })
        except Exception as e:
            print("ADMIN BLOCK RANGE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_unblock_range(self):
        """Remove every block between two dates (Doctors Calendar)."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        start = parse_ymd(request.form.get("start_date"))
        end = parse_ymd(request.form.get("end_date"))
        if not start or not end:
            return jsonify({"success": False, "message": "Choose a start and end date"}), 400
        try:
            expand_range_days(start, end, max_days=MAX_UNBLOCK_RANGE_DAYS)
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        if start < datetime.now(PH_TZ).date():
            return jsonify({"success": False, "message": "Past days can't be unblocked, so the closure history stays accurate."}), 400

        # Optional: only remove the days that were saved together as one
        # range (so a separately blocked day inside it is left alone).
        range_id = bleach.clean(request.form.get("range_id", "").strip())

        try:
            refs = [
                doc.reference for doc in (
                    self.db.collection(self.Blocked_Slots)
                    .where(filter=FieldFilter("date", ">=", start.strftime("%Y-%m-%d")))
                    .where(filter=FieldFilter("date", "<=", end.strftime("%Y-%m-%d")))
                    .stream()
                )
                if not range_id or (doc.to_dict() or {}).get("range_id") == range_id
            ]
            if refs:
                batch = self.db.batch()
                for ref in refs:
                    batch.delete(ref)
                batch.commit()
                self.cache.invalidate(self.BLOCKED_SLOTS_CACHE_KEY)
            return jsonify({
                "success": True,
                "message": f"Unblocked {len(refs)} day{'s' if len(refs) != 1 else ''}" if refs
                           else "There were no blocked days in that range",
                "days": len(refs)
            })
        except Exception as e:
            print("ADMIN UNBLOCK RANGE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_mark_past_closed(self):
        """Record past days as closed (Doctors Calendar). History/summary only."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        start = parse_ymd(request.form.get("start_date"))
        end = parse_ymd(request.form.get("end_date"))
        if not start or not end:
            return jsonify({"success": False, "message": "Choose a start and end date"}), 400

        today = datetime.now(PH_TZ).date()
        if end >= today:
            return jsonify({"success": False, "message": "Only days before today can be marked this way. Use Block for today and later."}), 400
        if start < today - timedelta(days=MAX_PAST_MARK_LOOKBACK_DAYS):
            return jsonify({"success": False, "message": "That date is too far back."}), 400
        try:
            days = expand_range_days(start, end)
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

        reason = bleach.clean(request.form.get("reason", "").strip())[:300]

        try:
            stamp = datetime.now(UTC).isoformat()
            batch = self.db.batch()
            for day in days:
                payload = {
                    "date": day,
                    "full_day": True,
                    "blocked_times": [],
                    "past_marked": True,
                    "created_by": session.get('admin_uid', ''),
                    "updated_at": stamp
                }
                if reason:
                    payload["reason"] = reason
                batch.set(self.db.collection(self.Blocked_Slots).document(day), payload, merge=True)
            batch.commit()
            self.cache.invalidate(self.BLOCKED_SLOTS_CACHE_KEY)
            return jsonify({
                "success": True,
                "message": f"Marked {len(days)} day{'s' if len(days) != 1 else ''} as closed",
                "days": len(days)
            })
        except Exception as e:
            print("ADMIN MARK PAST CLOSED ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_closure_summary(self):
        """Per-month closure counts for one year + the blocked days themselves."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        today = datetime.now(PH_TZ).date()
        try:
            year = int(request.args.get("year", today.year))
        except ValueError:
            year = today.year
        if not 2000 <= year <= today.year + 2:
            return jsonify({"success": False, "message": "Invalid year"}), 400

        try:
            months = []
            for m in range(1, 13):
                first = datetime(year, m, 1).date()
                nxt = datetime(year + (m == 12), m % 12 + 1, 1).date()
                if first > today:
                    elapsed = 0
                elif nxt <= today:
                    elapsed = (nxt - first).days
                else:
                    elapsed = (today - first).days + 1
                months.append({"month": m, "elapsed": elapsed,
                                "closed": 0, "scheduled": 0, "partial": 0})

            docs = (
                self.db.collection(self.Blocked_Slots)
                .where(filter=FieldFilter("date", ">=", f"{year}-01-01"))
                .where(filter=FieldFilter("date", "<=", f"{year}-12-31"))
                .stream()
            )
            entries = []
            for doc in docs:
                d = doc.to_dict() or {}
                parsed = parse_ymd(doc.id)
                if not parsed:
                    continue
                full = bool(d.get("full_day"))
                times = sorted(d.get("blocked_times") or [])
                if not full and not times:
                    continue
                row = months[parsed.month - 1]
                if full:
                    row["closed" if parsed <= today else "scheduled"] += 1
                else:
                    row["partial"] += 1
                entries.append({
                    "date": doc.id,
                    "full_day": full,
                    "blocked_times": [] if full else times,
                    "reason": d.get("reason", ""),
                    "past_marked": bool(d.get("past_marked", False)),
                    "upcoming": parsed > today
                })
            entries.sort(key=lambda x: x["date"])
            return jsonify({"success": True, "year": year,
                            "today": today.strftime("%Y-%m-%d"),
                            "months": months, "entries": entries})
        except Exception as e:
            print("ADMIN CLOSURE SUMMARY ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500
    
    def _appointments_on_day(self, day):
        """
        Accepted (Approve) and pending (appointments) records whose
        appointment_date -- stored as "YYYY-MM-DD HH:MM" -- falls on `day`
        ("YYYY-MM-DD"). Shared by the Doctors Calendar day schedule and the
        block-slot conflict check so both count exactly the same records.
        """
        start = day + " 00:00"
        end = day + " 23:59"
        items = []

        for group, status in (("Approve", "Accepted"), ("appointments", "Pending")):
            query = (
                self.db.collection_group(group)
                .where(filter=FieldFilter("appointment_date", ">=", start))
                .where(filter=FieldFilter("appointment_date", "<=", end))
            )
            for doc in query.stream():
                data = doc.to_dict()
                appt_date = str(data.get("appointment_date", "")).strip()
                parts = appt_date.split(" ", 1)
                name = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip()
                items.append({
                    "time": parts[1] if len(parts) > 1 else "",
                    "patient_name": name or "Unknown patient",
                    "service": data.get("Service", ""),
                    "dentist": self.display_dentist_name(data.get("DentistName", "")),
                    "status": status,
                    # Needed to reschedule the record from the Doctors Calendar.
                    "id": doc.id,
                    "uid": doc.reference.parent.parent.id if doc.reference.parent.parent else "",
                    "appointment_date": appt_date,
                    "source": "accepted" if status == "Accepted" else "pending"
                })

        items.sort(key=lambda x: x["time"])
        return items

    def admin_day_schedule(self):
        """Appointments booked on one calendar day (Doctors Calendar side panel)."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        day = bleach.clean(request.args.get("date", "").strip())
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify({"success": False, "message": "Invalid date"}), 400

        try:
            items = self._appointments_on_day(day)
            return jsonify({"success": True, "date": day, "appointments": items})
        except Exception as e:
            print("ADMIN DAY SCHEDULE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    RESCHEDULE_TIME_SLOTS = (
        "09:00", "10:00", "11:00", "12:00", "13:00",
        "14:00", "15:00", "16:00", "17:00"
    )

    def admin_reschedule_appointment(self):
        """
        Move an appointment to a new date/time. `source` says where it lives:
        "pending" (the appointments subcollection, default) or "accepted"
        (the Approve subcollection).

        Pending requests are moved from the Appointments tab; accepted ones
        from the Doctors Calendar day schedule.

        Used when the dentist blocks a day/time that already has requests:
        instead of accepting into a blocked slot (which /approve refuses) or
        declining, the admin picks an open slot. The new slot must be in the
        future, not blocked, and (when a dentist is known) not already taken by
        an accepted appointment for that dentist -- the same rules /approve
        enforces on accept, so the request can be accepted afterwards.
        """
        if not self._is_admin():
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        uid = request.form.get("user_id", "").strip()
        appointment_id = request.form.get("appointment_id", "").strip()
        new_date = bleach.clean(request.form.get("new_date", "").strip())
        new_time = bleach.clean(request.form.get("new_time", "").strip())
        dentist_name = bleach.clean(request.form.get("dentist_name", "")).strip()
        source = request.form.get("source", "pending").strip().lower()

        if source not in ("pending", "accepted"):
            return jsonify({"success": False, "message": "Invalid appointment type."}), 400

        if not uid or not appointment_id:
            return jsonify({"success": False, "message": "Missing appointment details"}), 400

        try:
            datetime.strptime(new_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"success": False, "message": "Please pick a valid date."}), 400

        if new_time not in self.RESCHEDULE_TIME_SLOTS:
            return jsonify({"success": False, "message": "Please pick a valid time slot."}), 400

        today_ph = datetime.now(PH_TZ).strftime("%Y-%m-%d")
        if new_date < today_ph:
            return jsonify({"success": False, "message": "The new date cannot be in the past."}), 400

        new_dt = f"{new_date} {new_time}"

        blocked, block_reason = self.is_slot_blocked(new_dt)
        if blocked:
            return jsonify({
                "success": False,
                "message": f"That slot is blocked by the dentist ({block_reason}). Please pick another."
            }), 409

        try:
            main_collection = None
            if self.db.collection("google_create_account").document(uid).get().exists:
                main_collection = "google_create_account"
            elif self.db.collection(self.Customer_Account).document(uid).get().exists:
                main_collection = self.Customer_Account

            if not main_collection:
                return jsonify({"success": False, "message": "Patient account not found."}), 404

            user_ref = self.db.collection(main_collection).document(uid)
            sub_name = "Approve" if source == "accepted" else self.Appointment_cliets
            appt_ref = user_ref.collection(sub_name).document(appointment_id)
            appt_doc = appt_ref.get()

            if not appt_doc.exists:
                return jsonify({
                    "success": False,
                    "message": "This appointment could not be found. It may have been moved, declined or removed. Refresh the page."
                }), 404

            appt_data = appt_doc.to_dict()
            old_dt = str(appt_data.get("appointment_date", "")).strip()

            if old_dt == new_dt:
                return jsonify({"success": False, "message": "That is already the current schedule."}), 400

            check_dentist = dentist_name or appt_data.get("DentistName", "")
            if check_dentist:
                conflict = self.find_appointment_conflict(
                    dentist_name=check_dentist,
                    appointment_date=new_dt,
                    exclude_doc_id=appointment_id if source == "accepted" else None
                )
                if conflict:
                    return jsonify({
                        "success": False,
                        "message": (
                            f"{conflict['dentist_name'] or 'This dentist'} already has an "
                            f"accepted appointment with {conflict['patient_name'] or 'another patient'} "
                            f"at {conflict['appointment_date']}. Please pick another slot."
                        )
                    }), 409

            appt_ref.update({
                "appointment_date": new_dt,
                "previous_appointment_date": old_dt,
                "rescheduled_at": datetime.now(UTC).isoformat(),
                "rescheduled_by": session.get("admin_uid", "")
            })

            user_doc = user_ref.get()
            patient_email = user_doc.to_dict().get("email") if user_doc.exists else None
            fullname = f"{appt_data.get('FirstName', '')} {appt_data.get('LastName', '')}".strip()

            threading.Thread(
                target=self.send_appointment_email,
                args=(patient_email, fullname, "reschedule", {
                    "Service": appt_data.get("Service", "your appointment"),
                    "appointment_date": new_dt,
                    "previous_appointment_date": old_dt
                }),
                daemon=True
            ).start()

            return jsonify({
                "success": True,
                "appointment_date": new_dt,
                "email_on_file": bool(patient_email)
            })
        except Exception as e:
            print("ADMIN RESCHEDULE APPOINTMENT ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

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

        # Add the new patient to the cached list instead of throwing the
        # whole cache away (which made the next search / list page re-read
        # every patient). If nothing is cached yet, clear it as before.
        cached_patients = self.cache.get("patients_all")
        if cached_patients is not None:
            self.cache.set(
                "patients_all",
                list(cached_patients) + [(patient_id, patient_data)],
                ttl_seconds=self.CACHE_TTL_SECONDS
            )
        else:
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
        latest_sex = ""
        for a in target_ref.collection("Approve").stream():
            a_data = a.to_dict()
            accepted_at = a_data.get("accepted_at", "")
            if accepted_at and (latest_accepted is None or accepted_at > latest_accepted):
                latest_accepted = accepted_at
                latest_sex = a_data.get("Sex", "")

        account_update = {
            "has_history": has_approve or has_done,
            "last_approved_at": latest_accepted or ""
        }
        if latest_sex:
            account_update["last_sex"] = latest_sex
        # Phase 2: carry contact / sex / civil status over, only into fields
        # the target account has blank.
        self._merge_identity_fill(source_ref, target_ref, account_update)
        target_ref.update(account_update)

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

    def _is_admin(self):
        return bool(session.get('admin_logged_in'))

    def _is_owner_or_admin(self, uid):
        return self._is_admin() or (bool(uid) and session.get('uid') == uid)

    def _setup_csrf(self):
        self.app.config["WTF_CSRF_TIME_LIMIT"] = None
        self.csrf = CSRFProtect(self.app)
        @self.app.context_processor
        def inject_google_client_id():
            return {"google_client_id": self.CLIENT_ID}

        @self.app.context_processor
        def inject_firebase_config():
            return {"firebase_config": {
                "apiKey": os.getenv("FIREBASE_API_KEY"),
                "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
                "projectId": os.getenv("FIREBASE_PROJECT_ID"),
                "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
                "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
                "appId": os.getenv("FIREBASE_APP_ID"),
            }}

        @self.app.errorhandler(CSRFError)
        def handle_csrf(e):
            if request.headers.get("X-CSRFToken") or request.headers.get("X-Requested-With"):
                return jsonify({"success": False, "message": "Session expired. Please refresh the page."}), 400
            return render_template("error.html", message="Your session expired. Please go back, refresh the page and try again."), 400

    def _verify_paymongo_signature(self):
        if not self.PAYMONGO_WEBHOOK_SECRET:
            return False
        header = request.headers.get("Paymongo-Signature", "")
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        timestamp = parts.get("t", "")
        provided = parts.get("li") or parts.get("te") or ""
        signed = f"{timestamp}.{request.get_data(as_text=True)}".encode()
        expected = hmac.new(self.PAYMONGO_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
        return bool(timestamp and provided) and hmac.compare_digest(expected, provided)
    
    def _setup_paymongo(self):
        self.pay_mongo_secret_key = os.getenv("PAYMONGO_SECRET_KEY", "")
        self.pay_mongo_public_key = os.getenv("PAYMONGO_PUBLIC_KEY", "")
        self.PAYMONGO_WEBHOOK_SECRET = os.getenv("PAYMONGO_WEBHOOK_SECRET", "")

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



    
    def _setup_error_handlers(self):
        @self.app.errorhandler(404)
        def handle_404(e):
            if request.path.startswith("/admin"):
                return jsonify({"success": False, "message": "Not found"}), 404
            return render_template("error.html", message="Page not found"), 404

        @self.app.errorhandler(500)
        def handle_500(e):
            if request.path.startswith("/admin"):
                return jsonify({"success": False, "message": "Something went wrong"}), 500
            return render_template("error.html", message="Something went wrong. Please try again."), 500
        
    def _setup_security_headers(self):
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://accounts.google.com https://www.gstatic.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob: https:",
            "connect-src 'self' https://accounts.google.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com",
            "frame-src https://accounts.google.com https://www.google.com",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
        ])

        @self.app.after_request
        def add_security_headers(response):
            response.headers["Content-Security-Policy"] = csp
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            if request.endpoint != "static":
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
            if response.mimetype == "text/html" and not response.direct_passthrough:
                response.set_data(strip_comments(response.get_data(as_text=True)))
            return response


    def require_firebase(self):
        """Checks if Firebase is initialized before running a database operation."""
        if self._db is None:
            raise RuntimeError("Firebase is not initialized. Check dentech_key.json")
        
        
    def _get_amount_due(self, patient_uid, procedure):
        """Unpaid amount in pesos for this patient's procedure, or None."""
        target = str(procedure).strip().lower()
        user_ref = self.db.collection(self.Customer_Account).document(str(patient_uid))
        for proc_doc in user_ref.collection("Done_procedure").stream():
            procs = proc_doc.to_dict().get("procedures", [])
            if not isinstance(procs, list):
                continue
            for p in procs:
                if not isinstance(p, dict):
                    continue
                if str(p.get("procedure", "")).strip().lower() != target:
                    continue
                if str(p.get("status", "")).strip().lower() == "paid":
                    return None
                value = self.safe_float(p.get("value", 0))
                paid = self.safe_float(p.get("paid", 0))
                balance = self.safe_float(p.get("balance", 0))
                return balance if balance > 0 else max(value - paid, 0)
        return None
    
    def update_payment_status(self, patient_uid, procedure, paid_centavos=None):

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
                        
                        due = old_balance if old_balance > 0 else max(value - old_paid, 0)
                        if paid_centavos is not None and paid_centavos < int(round(due * 100)):
                            self.app.logger.warning("Payment amount too low for procedure; not marking paid")
                            return False
                        
                        print(
                            "PROCEDURE VALUE:",
                            value
                        )

                        # Phase 3: remember the row as it was before it is marked paid.
                        agg_old_row = dict(p)

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

                            "has_unpaid": self._agg_has_unpaid(procedures),

                            "updated_at":
                                firestore.SERVER_TIMESTAMP

                        })
                        # NEW: incrementally update cached financial stats
                        self.db.collection("Stats").document("financial_summary").set({
                            "total_income": firestore.Increment(value - old_paid),
                            "total_outstanding": firestore.Increment(-old_balance),
                            "unpaid_procedures": firestore.Increment(-1)
                        }, merge=True)
                        # Phase 3: keep the daily aggregates in step (never raises).
                        self._agg_apply_rows(add=[procedures[index]], remove=[agg_old_row])
                        
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

        checkout_session_id = session.get(
            "paymongo_checkout_session_id", ""
            )
        
        patient_uid = session.get(
            "paymongo_patient_uid", ""
            )
        
        procedure = session.get(
            "paymongo_procedure", ""
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
            paid_centavos = 0

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
                    paid_centavos = int(payment_attributes.get("amount", 0))

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
                    procedure,
                    paid_centavos)

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
        
        if not self._verify_paymongo_signature():
            return "", 400

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

                payments = session_attrs.get("payments", [])
                paid_centavos = sum(
                    int(p.get("attributes", {}).get("amount", 0)) for p in payments
                )

                updated = self.update_payment_status(patient_uid, procedure, paid_centavos)

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
            print("========================================")

            # =====================================================
            # VALIDATION
            # =====================================================

            if not patient_uid:
                return {"error": "Patient UID is required"}

            if not procedure:
                return {"error": "Procedure is required"}

            
            if not self._is_owner_or_admin(patient_uid):
                return {"error": "Unauthorized"}, 403
            
            due = self._get_amount_due(patient_uid, procedure)
            if not due or due <= 0:
                return {"error": "No unpaid balance found for this procedure"}, 400
            amount = int(round(due * 100))

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

            success_url = f"{base_url}/payment-success"

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
                "error": "Something went wrong. Please try again."
            }
    def refresh_session(self):
        session.permanent = True
        session.modified = True
    

    def _get_profile_pic(self, uid, email):
        """
        The logged-in visitor's profile_pic for the public pages.

        Was: a Customer_Account query on EVERY page view (and a second,
        identical query whenever the first came back empty). Now: asked once
        per login session and remembered in the session. The session value is
        dropped on login (so one user's picture is never shown to the next)
        and replaced when a new picture is uploaded; logout clears it.
        """
        if not (uid and email):
            return ''
        if 'profile_pic' in session:
            return session.get('profile_pic') or ''
        user_query = self.db.collection(self.Customer_Account).where("email", "==", email).get()
        profile_pic = ''
        if user_query:
            profile_pic = user_query[0].to_dict().get('profile_pic', '') or ''
        session['profile_pic'] = profile_pic
        return profile_pic

    def index(self):
        uid = session.get('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
    
        profile_pic = self._get_profile_pic(uid, email)
    
        # Read, don't pop: link_patient_account() must still find the pending
        # match when the patient presses Yes / No on the card. It removes it.
        pending_match = session.get('pending_patient_match')
        return render_template("index.html", uid=uid, name=name, email=email,
                            profile_pic=profile_pic, pending_match=pending_match)
    
    
    

    def google_index(self):
        uid = session.get ('uid', '')
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
    
        profile_pic = self._get_profile_pic(uid, email)
    
        # Read, don't pop: link_patient_account() must still find the pending
        # match when the patient presses Yes / No on the card. It removes it.
        pending_match = session.get('pending_patient_match')
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
        session.pop("profile_pic", None)  # never carry a previous login's picture over
        
        self.maybe_flag_patient_match(
            uid, 
            user_data.get("firstname", ""), 
            user_data.get("lastname", ""),
            user_data.get("middlename", ""),
            user_data.get("birthday", "")
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "success": True,
                "redirect": url_for("index"),
                "name": user_data.get("firstname", "")
            })

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
            session.pop('profile_pic', None)  # never carry a previous login's picture over

            update_data = {
                "uid": session['uid'],
                "email": session['email'],
                "provider": "google",
                "last_login": datetime.now(UTC).isoformat()
            }
            update_data.update(
                self._resolve_google_name_fields(
                    existing_data, session['name']
                )
            )

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
                
            flash(f"Welcome back, {session['name'].split()[0]}!", "success")
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
            return "Sign-up failed. Please try again.", 500


    def logout(self):
        for k in ("uid", "email", "name", "profile_pic", "pending_patient_match"):
            session.pop(k, None)
        flash("You have been logged out.", "success")
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
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500
    

    def p_forms(self):
        return render_template("patientForms.html")
    

    def about_customer(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        profile_pic = ''
        uid = session.get('uid', '')
    
        profile_pic = self._get_profile_pic(uid, email)
    
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
        
        blocked, block_reason = self.is_slot_blocked(appointment_date, for_patient=True)
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

            # Phase 2: save contact number / sex / civil status onto the
            # account the first time they are known (fill-if-blank).
            self._fill_account_identity_if_blank(
                self.db.collection(self.Customer_Account).document(uid),
                contact=ContactNumber,
                sex=Sex,
                civil=CivilStatus,
            )

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
        
        
        blocked, block_reason = self.is_slot_blocked(appointment_date, for_patient=True)
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

            # Phase 2: save contact number / sex / civil status onto the
            # account the first time they are known (fill-if-blank).
            self._fill_account_identity_if_blank(
                self.db.collection(self.Customer_Account).document(uid),
                contact=ContactNumber,
                sex=Sex,
                civil=CivilStatus,
            )

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

            # The bodies below address the doctor as "by Dr. <name>", but
            # DentistName already carries the honorific ("Dr. Julix Dionne
            # Capizonda"), which rendered "Dr. Dr. Capizonda" in patient-facing
            # email. Strip a leading honorific so the sentence stays correct for
            # every spelling.
            email_dentist = re.sub(r"^\s*dr\.?\s+", "", str(dentist), flags=re.IGNORECASE) or dentist
    
            if action == "accept":
                subject = "Appointment Accepted - Capizonda Dental Clinic"
                body = f"""
    Hello {fullname},
    
    Good news! Your appointment for {service} has been accepted by Dr. {email_dentist}.
    {f'Appointment Date: {appointment_date}' if appointment_date else ''}
    
    Please arrive 10 minutes before your scheduled time.
    If you have any questions, feel free to contact us.
    
    Best regards,
    Capizonda Dental Clinic Team
    """
            elif action == "reschedule":
                previous_date = appointment_data.get("previous_appointment_date", "")
                subject = "Appointment Rescheduled - Capizonda Dental Clinic"
                body = f"""
    Hello {fullname},
    
    Your appointment for {service} has been moved to a new schedule because the dentist is unavailable at the original time.
    {f'Previous schedule: {previous_date}' if previous_date else ''}
    {f'New schedule: {appointment_date}' if appointment_date else ''}
    
    If the new schedule does not work for you, please contact us so we can find a time that does.
    We apologize for any inconvenience this may have caused.
    
    Best regards,
    Capizonda Dental Clinic Team
    """
            else:
                subject = "Appointment Declined - Capizonda Dental Clinic"
                body = f"""
    Hello {fullname},
    
    We regret to inform you that your appointment request for {service} has been declined by Dr. {email_dentist}.
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
        dentist_name = bleach.clean(
            request.form.get("dentist_name", "")
        ).strip()

        if not uid or not appointment_id:
            return "Missing user_id or appointment_id", 400

        if action not in ("accept", "decline"):
            return "Invalid action", 400
        
        if not self._is_admin():
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        # ---------------------------------------------------------
        # CONSULTING DENTIST REQUIRED ON ACCEPT
        # ---------------------------------------------------------
        #
        # Accepting is what actually assigns the appointment to a dentist, so
        # a name has to come with it. Declining assigns nobody, so it stays
        # allowed without one.

        if action == "accept" and not dentist_name:

            return jsonify({
                "success": False,
                "message": (
                    "Consulting dentist is required. "
                    "Please select or type a dentist before accepting."
                )
            }), 400


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

        # Only accepting needs the slot to be free. Declining must always work,
        # otherwise a request sitting in a slot the dentist just blocked could
        # not even be declined.
        if action == "accept":
            blocked, block_reason = self.is_slot_blocked(data["appointment_date"])

            if blocked:
                return jsonify({
                    "success": False,
                    "message": (
                        f"This date/time is blocked by the dentist ({block_reason}). "
                        f"Use Reschedule to move it to an open slot."
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

                # NEW: cache history flag + latest date on the account doc.
                # Also refresh last_sex from this appointment's answer, so
                # "My Patients" always reflects the most recent visit --
                # but only if this appointment actually answered it, so we
                # never clobber a known value with a blank one.
                account_update = {
                    "has_history": True,
                    "last_approved_at": data["accepted_at"]
                }
                if data.get("Sex"):
                    account_update["last_sex"] = data["Sex"]
                user_ref.update(account_update)

                # Phase 2: also save contact number / civil status onto the
                # account the first time they are known (fill-if-blank).
                self._fill_account_identity_if_blank(
                    user_ref,
                    contact=data.get("ContactNumber", ""),
                    civil=data.get("CivilStatus", ""),
                )


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


            return jsonify({
                "success": True,
                "action": action,
                "patient": data if action == "accept" else None
            })


        except Exception as e:

            print(f"{action.capitalize()} error: {e}")

            return f"Failed to {action} appointment. Please try again.", 500
    
    
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
        # CONSULTING DENTIST REQUIRED
        # ---------------------------------------------------------
        #
        # An appointment is never created without one. Read and checked up
        # front, before any write -- the walk-in branch below creates a
        # customer account partway through this handler, so validating
        # later would leave a half-created record behind.

        dentist_name = bleach.clean(
            request.form.get("dentist_name", "")
        ).strip()

        if not dentist_name:
            return jsonify({
                "success": False,
                "message": (
                    "Consulting dentist is required. "
                    "Please select or type a dentist."
                )
            }), 400

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

            "DentistName": dentist_name,

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

            # NEW: cache history flag + latest date on the account doc,
            # same as approve() -- see the comment there for why last_sex
            # is only set when this appointment actually answered it.
            account_update = {
                "has_history": True,
                "last_approved_at": data["accepted_at"]
            }
            if data.get("Sex"):
                account_update["last_sex"] = data["Sex"]

            self.db.collection(
                self.Customer_Account
            ).document(uid).update(account_update)

            # Phase 2: also save contact number / civil status onto the
            # account the first time they are known (fill-if-blank).
            self._fill_account_identity_if_blank(
                self.db.collection(self.Customer_Account).document(uid),
                contact=data.get("ContactNumber", ""),
                civil=data.get("CivilStatus", ""),
            )

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
                "message": "Something went wrong. Please try again."
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

        # NEW: patient_id -> full Patients doc, reusing the SAME cached
        # scan _get_account_to_patient_map() already pulled from, so
        # Birthday joins in for free -- no extra per-row Firestore reads.
        patients_by_id = {pid: data for pid, data in self._get_patients_cached()}

        rows = []
        # Shared across the page so a row needing the fallback is only
        # ever read once.
        identity_cache = {}
        for doc in docs:
            account_uid = doc.id
            account_data = doc.to_dict()

            patient_id = account_to_patient.get(account_uid, "")

            birthday = ""
            if patient_id:
                birthday = patients_by_id.get(patient_id, {}).get("birthday", "")

            age, birth_year = self.compute_age_and_birth_year(birthday)

            first = account_data.get("firstname") or ""
            last = account_data.get("lastname") or ""

            # Auto-pulled from the patient's most recently approved
            # appointment (whether self-booked or dentist-entered), kept in
            # sync in approve()/admin_create_appointment()/the merge paths
            # and still admin-editable via EDIT -- but the account doc does
            # not always carry them, so fall back to the appointment history.
            contact_number, sex, civil_status = self._resolve_account_identity(
                account_uid, account_data, identity_cache
            )

            rows.append({
                "patient_id": patient_id,
                "uid": account_uid,
                "first_name": first,
                "middle_name": account_data.get("middlename", ""),
                "last_name": last,
                # Prefer the editable name parts. A Google account's "name"
                # is the Google profile name and can disagree with what the
                # admin set here; it is only a fallback for accounts that
                # genuinely have no name parts yet.
                "full_name": f"{first} {last}".strip()
                or account_data.get("name") or "",
                "contact_number": contact_number,
                "email": account_data.get("email", ""),
                "birthday": birthday,
                "age": age,
                "birth_year": birth_year,
                "sex": sex,
                "civil_status": civil_status,
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
        identity_cache = {}
        for account_uid, account_data in docs:
            patient_id = account_to_patient.get(account_uid, "")

            first = account_data.get("firstname") or ""
            last = account_data.get("lastname") or ""

            # Same fallback as "My Patients": this table shares the EDIT
            # modal, so a blank contact/sex/civil here blanks it there too.
            contact_number, sex, civil_status = self._resolve_account_identity(
                account_uid, account_data, identity_cache
            )

            rows.append({
                "patient_id": patient_id,
                "uid": account_uid,
                "first_name": first,
                "middle_name": account_data.get("middlename", ""),
                "last_name": last,
                # Same precedence as "My Patients": the editable parts win
                # over a Google profile "name".
                "full_name": f"{first} {last}".strip()
                or account_data.get("name") or "",
                "contact_number": contact_number,
                "email": account_data.get("email", ""),
                "sex": sex,
                # admin_dashboard.html already reads a.CivilStatus on this
                # table, but nothing was ever returning it.
                "CivilStatus": civil_status,
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

        # Same within-page urgency ordering the dashboard used to apply to page 1.
        urgency_order = {"Emergency": 0, "Urgent": 1, "Normal": 2}
        rows.sort(key=lambda x: urgency_order.get(x.get("UrgencyLevel", ""), 99))

        return jsonify({
            "success": True,
            "rows": rows,
            "next_cursor": next_cursor
        })

    def _fetch_approved_page(self, cursor=None, page_size=None):
        """Approved appointments, newest accepted_at first."""
        page_size = page_size or self.PATIENTS_PAGE_SIZE
        query = (
            self.db.collection_group("Approve")
            .order_by("accepted_at", direction="DESCENDING")
        )

        if cursor:
            query = query.start_after({"accepted_at": cursor})

        query = query.limit(page_size + 1)
        docs = list(query.stream())

        has_more = len(docs) > page_size
        docs = docs[:page_size]

        rows = []
        identity_cache = {}
        account_data_cache = {}  # account_uid -> account data, one read per account per page

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            account_uid = doc.reference.parent.parent.id
            data["uid"] = account_uid

            # This list's data-sex is what the Patient Dashboard header
            # displays, so it has to agree with the editable value shown in
            # My Patients / User Management. Serving the Sex snapshotted on
            # this particular appointment instead made an admin's correction
            # look like it never saved: the account got the new value but
            # this list kept returning the old one.
            try:
                if account_uid in account_data_cache:
                    account_data = account_data_cache[account_uid]
                else:
                    account_doc = (
                        self.db.collection(self.Customer_Account)
                        .document(account_uid)
                        .get()
                    )
                    account_data = (
                        account_doc.to_dict() if account_doc.exists else {}
                    )
                    account_data_cache[account_uid] = account_data
                _, resolved_sex, _ = self._resolve_account_identity(
                    account_uid, account_data, identity_cache
                )
                if resolved_sex:
                    data["Sex"] = resolved_sex
            except Exception as e:
                print("APPROVED LIST SEX RESOLVE FAILED:", e)

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


    def admin_assign_dentist(self):
        """
        Set the consulting dentist on an already-accepted appointment that does
        not have one yet.

        The Accepted Patients list only offers this editor while DentistName is
        blank, so that blank is enforced here too -- otherwise a crafted request
        could silently overwrite an existing assignment, which is a different
        action with different consequences (it would need its own conflict and
        audit story).

        Accepted appointments are exactly the set the double-booking check
        cares about, so this runs the same check instead of writing a name that
        would collide with another patient's confirmed slot.
        """

        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        uid = request.form.get("uid", "").strip()
        appointment_id = request.form.get("appointment_id", "").strip()
        dentist_name = bleach.clean(
            request.form.get("dentist_name", "")
        ).strip()

        if not uid or not appointment_id:
            return jsonify({
                "success": False,
                "message": "Missing uid or appointment_id"
            }), 400

        if not dentist_name:
            return jsonify({
                "success": False,
                "message": (
                    "Consulting dentist is required. "
                    "Please select or type a dentist."
                )
            }), 400

        approve_ref = (
            self.db.collection(self.Customer_Account)
            .document(uid)
            .collection("Approve")
            .document(appointment_id)
        )

        try:

            appt_doc = approve_ref.get()

            if not appt_doc.exists:
                return jsonify({
                    "success": False,
                    "message": "Appointment not found"
                }), 404

            appt_data = appt_doc.to_dict() or {}

            if self.normalize_dentist_name(appt_data.get("DentistName", "")):
                return jsonify({
                    "success": False,
                    "message": (
                        "This appointment already has a dentist assigned."
                    )
                }), 409

            # No exclude_doc_id on purpose. The appointment being edited has an
            # empty DentistName, so it can never match the dentist being set
            # and would skip nothing -- whereas find_appointment_conflict
            # compares exclude_doc_id by doc id alone, so passing one could
            # wave through a genuine conflict with another patient's document
            # that happens to share an id.

            conflict = self.find_appointment_conflict(
                dentist_name=dentist_name,
                appointment_date=appt_data.get("appointment_date", "")
            )

            if conflict:
                return jsonify({
                    "success": False,
                    "message": (
                        f"{conflict['dentist_name'] or 'This dentist'} already "
                        f"has an accepted appointment with "
                        f"{conflict['patient_name'] or 'another patient'} at "
                        f"{conflict['appointment_date']}. Please choose a "
                        f"different dentist."
                    )
                }), 409

            approve_ref.update({
                "DentistName": dentist_name,
                "dentist_assigned_at": datetime.now(UTC).isoformat(),
                "dentist_assigned_by": session.get('admin_uid', '')
            })

            return jsonify({
                "success": True,
                "message": "Dentist assigned successfully",
                "dentist_name": dentist_name
            })

        except Exception as e:

            print("ADMIN ASSIGN DENTIST ERROR:", e)

            return jsonify({
                "success": False,
                "message": "Something went wrong. Please try again."
            }), 500


    def admin_patient_avatar(self):
        """
        Profile picture URL for a single patient, fetched on demand when the
        Patient Dashboard opens.

        Deliberately NOT folded into the list payloads (approved_page,
        my_patients_page): those are paginated, so adding it there would cost
        one extra account read per row on every page of every list. The
        dashboard only ever shows one patient at a time, so a single lookup
        per open is the cheapest correct place for it.

        Returns an empty profile_pic for a missing account or an account that
        never picked a picture, which the dashboard renders as its default
        avatar. Never raises -- a broken avatar must not break the page.
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        uid = ((request.get_json(silent=True) or {}).get("uid") or "").strip()
        if not uid:
            return jsonify({"success": True, "profile_pic": ""})

        try:
            account_doc = (
                self.db.collection(self.Customer_Account)
                .document(uid)
                .get()
            )
            account_data = account_doc.to_dict() if account_doc.exists else {}
            return jsonify({
                "success": True,
                "profile_pic": (account_data or {}).get("profile_pic", "") or ""
            })
        except Exception as e:
            print("PATIENT AVATAR READ FAILED:", e)
            return jsonify({"success": True, "profile_pic": ""})



    def adminDashboard(self):
        if not session.get('admin_logged_in'):
            return redirect(url_for("adminLogin"))

        # One-shot: pop it so the greeting is shown on this visit only, and so it
        # can never survive into a patient page render.
        admin_welcome_toast = session.pop('admin_welcome_toast', '')

        # The four big lists (pending appointments, approved patients,
        # My Patients, User Management) are NOT fetched here anymore. The
        # page loads them from their /admin/*_page endpoints the first time
        # their tab is opened (see showSection in admin_dashboard.html).
        # Opening the dashboard now only needs the cheap summary below.

        # =========================
        # COUNTS (server-side aggregation, ~1 read per 1000 index entries)
        # =========================
        total_patients = self.db.collection(self.Doc_Patients).count().get()[0][0].value
        pending_count = self.db.collection_group("appointments").count().get()[0][0].value
        approved_count = self.db.collection_group("Approve").count().get()[0][0].value

        # Urgency cards: one count() per level. Needs a collection-group
        # index on UrgencyLevel; if it is missing, fall back to counting
        # page 1 of pending appointments (the old behaviour) and say so.
        urgency_counts = {"Emergency": 0, "Urgent": 0, "Normal": 0}
        try:
            for level in urgency_counts:
                urgency_counts[level] = (
                    self.db.collection_group("appointments")
                    .where("UrgencyLevel", "==", level)
                    .count().get()[0][0].value
                )
        except Exception as e:
            print(f"URGENCY COUNT FALLBACK (create a collection-group index on "
                  f"appointments.UrgencyLevel to fix): {e}")
            urgency_counts = {"Emergency": 0, "Urgent": 0, "Normal": 0}
            first_page, _ = self._fetch_appointments_page()
            for appt in first_page:
                level = appt.get("UrgencyLevel", "Normal")
                if level in urgency_counts:
                    urgency_counts[level] += 1

        # Only the 3 newest accepted patients are needed for the overview card.
        recent_approve, _ = self._fetch_approved_page(page_size=3)

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
            Appointment_clients=[],
            Approve=[],
            manageable_accounts=[],
            my_patients=[],
            admin_welcome_toast=admin_welcome_toast,
            pending_count=pending_count,
            approved_count=approved_count,
            total_patients=total_patients,
            urgency_counts=urgency_counts,
            recent_approve=recent_approve,
            total_income=total_income,
            total_outstanding=total_outstanding,
            unpaid_procedures=unpaid_procedures,
            my_patients_next_cursor="",
            manageable_accounts_next_cursor="",
            appointment_list_next_cursor="",
            approve_list_next_cursor="",
        )

    def search_patients(self):
        if not session.get('admin_logged_in'):
            return jsonify([]), 403

        query = str((request.get_json(silent=True) or {}).get("q", "")).strip().lower()

        if len(query) < 2:
            return jsonify([])

        MAX_RESULTS = 20

        # uid -> account data, from the cache User Management already uses.
        # This replaces one Firestore read per matching patient.
        accounts_by_uid = {
            uid: data for uid, data in self._get_manageable_accounts_cached()
        }

        results = []

        for doc_id, data in self._get_patients_cached():
            first = str(data.get("first_name", "")).strip()
            middle = str(data.get("middle_name", "")).strip()
            last = str(data.get("last_name", "")).strip()

            full_name = " ".join(part for part in [first, middle, last] if part)

            if not (
                query in first.lower()
                or query in middle.lower()
                or query in last.lower()
                or query in full_name.lower()
            ):
                continue

            account_uid = data.get("account_uid") or ""
            email = data.get("email", "") or accounts_by_uid.get(account_uid, {}).get("email", "")

            results.append({
                "patient_id": doc_id,
                "account_uid": account_uid,
                "firstname": first,
                "middlename": middle,
                "lastname": last,
                "name": full_name,
                "email": email,
                "birthday": data.get("birthday", "")
            })

            if len(results) >= MAX_RESULTS:
                break

        return jsonify(results)
    
    def check_duplicate_patient(self):
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}
        first_name = str(data.get("first_name", "")).strip()
        last_name = str(data.get("last_name", "")).strip()
        middle_name = str(data.get("middle_name", "")).strip()
        birthday = str(data.get("birthday", "")).strip()

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

        # NEW: Sex is auto-pulled from the patient's most recent appointment
        # (see approve()/admin_create_appointment()), but admins can still
        # correct it here. Stored on Customer_Account as last_sex.
        sex = bleach.clean(
            request.form.get("sex", "").strip()
        )

        # Civil status is only ever written to the appointment documents, so
        # an admin correcting it here is the way it gets onto the account
        # (and therefore onto the My Patients / User Management tables).
        # Whitelisted so a hand-rolled POST cannot write junk.
        civil_status = bleach.clean(
            request.form.get("civil_status", "").strip()
        )

        CIVIL_STATUS_ALLOWED = (
            "", "Single", "Married", "Widowed", "Separated", "Divorced"
        )

        if civil_status not in CIVIL_STATUS_ALLOWED:
            return jsonify({
                "success": False,
                "message": "Invalid civil status"
            }), 400

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
                "email": email,
                "last_sex": sex,
                "CivilStatus": civil_status,
                # Google accounts carry a "name" copied from the Google
                # profile. Keep it in step with the parts the admin just
                # saved, or every screen that prefers "name" would keep
                # showing the stale Google value until the user re-signed in.
                "name": f"{first_name} {last_name}".strip()
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
                "message": "Something went wrong. Please try again."
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
            print("TOGGLE USER BLOCK ERROR:", e)
            return jsonify({
                "success": False,
                "message": "Something went wrong. Please try again."
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
                        # Phase 3: take this treatment record out of the daily aggregates.
                        if sub_name == "Done_procedure":
                            self._agg_remove_done_doc(sub_doc)

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
                print("AUTH DELETE ERROR:", auth_err)
                auth_warning = (
                    "Patient data was deleted, but the login account "
                    "could not be removed."
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
                "message": "Something went wrong. Please try again."
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
                "has_unpaid": self._agg_has_unpaid(procedures),
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

            # Phase 3: keep the daily aggregates in step (never raises).
            self._agg_apply_rows(add=[procedures[proc_index]], remove=[existing])

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
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def delete_treatment_record(self):
        """
        Remove a single procedure row from a Done_procedure document.

        Mirrors update_treatment_record() deliberately: the account is
        resolved from the Patient ID server-side (never trusted from the
        client), and the cached financial stats plus the "next visit"
        suggestion are kept in sync by SUBTRACTING the removed row's
        contribution, so deleting a row can never leave the totals
        double-counted or pointing at a row that no longer exists.
        """
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

        removed = procedures.pop(proc_index)
        removed_paid = self.safe_float(removed.get("paid", 0))
        removed_balance = self.safe_float(removed.get("balance", 0))

        try:
            if procedures:
                done_ref.update({
                    "procedures": procedures,
                    "has_unpaid": self._agg_has_unpaid(procedures),
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
            else:
                # That was the last row in this treatment record, so drop
                # the whole document (and its chart image with it) instead
                # of leaving an empty shell that still counts as history.
                done_ref.delete()

            self.db.collection("Stats").document("financial_summary").set({
                "total_income": firestore.Increment(-removed_paid),
                "total_outstanding": firestore.Increment(-removed_balance),
                "unpaid_procedures": firestore.Increment(-(1 if removed_balance > 0 else 0))
            }, merge=True)

            # Phase 3: keep the daily aggregates in step (never raises).
            self._agg_apply_rows(remove=[removed])

            # =================================================
            # REFRESH "NEXT VISIT" SUGGESTION FOR THIS RECORD
            # =================================================
            # Same rule as update_treatment_record(): last row (top to
            # bottom) in THIS treatment record that has a next_appointment
            # date wins, so the suggestion can never point at a row that
            # was just deleted.
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

            return jsonify({
                "success": True,
                "message": "Treatment record deleted successfully",
                "remaining": len(procedures)
            })

        except Exception as e:
            print("DELETE TREATMENT RECORD ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def get_patient(self, uid):
        """
        Get patient information.

        Compatibility behavior:
        - If the supplied value is a Firebase UID, load Customer_Account/{uid}
        - If the supplied value is a Patient ID such as P-000001,
        load Patients/{patient_id} and then use account_uid when available.

        Access: admins (any record) and the account owner themselves.
        The patient profile page calls this for the logged-in patient's
        own records, dental history and payments, so the owner must be
        allowed through, not just staff.
        """
        
        if not self._is_owner_or_admin(uid):
            return jsonify({"error": "Unauthorized"}), 403

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

                # Normalised sex key -- see the note in the account-uid
                # branch below. Prefer the account's latest accepted value.
                "sex": str(
                    patient_data.get("sex")
                    or patient_data.get("Sex")
                    or ""
                ).strip(),

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

                    # The account keeps the most recently accepted
                    # appointment's sex as "last_sex", which is fresher than
                    # whatever the patient document still holds.
                    data["sex"] = str(
                        account_data.get("last_sex")
                        or data.get("sex")
                        or ""
                    ).strip()

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

        # Expose the patient's sex under one stable key. It is stored under
        # three different names depending on where you look: "last_sex" on the
        # account (the latest accepted appointment), "Sex" on individual
        # Approve records, and "sex" on the patient document. Callers had to
        # know which document a value came from, and a patient whose Approve
        # record predates the field simply got nothing back.
        data["sex"] = str(
            data.get("last_sex")
            or data.get("sex")
            or data.get("Sex")
            or ""
        ).strip()

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
                
                if not google_account.get("email_verified") or email.lower() not in self.ADMIN_EMAILS:
                    flash("This account is not authorized.", "error")
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
                
                session['admin_welcome_toast'] = f"Welcome back, Dr. {name}!"
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
        
        return render_template("admin_login.html", google_client_id=self.CLIENT_ID)

    def update_profile(self):
        try:
            uid = session.get("uid", "")
            new_firstname = request.form.get("new_firstname", "").strip()
            new_lastname = request.form.get("new_lastname", "").strip()
            new_phone = request.form.get("new_phone", "").strip()

            if not uid:
                flash("Unable to identify your account.", "error")
                return redirect(url_for("index"))

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
                session['profile_pic'] = profile_pic_url
            else:
                return jsonify({"success": False, "message": "User not found"}), 404
            
            return jsonify({
                "success": True,
                "message": "Profile picture updated successfully",
                "profile_pic_url": profile_pic_url
            })
            
        except Exception as e:
            print(f"Upload profile pic error: {e}")
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500
        
    

    def service_detail(self, service_id):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        uid = session.get('uid', '')
        profile_pic = ''

        service = self.SERVICES_DATA.get(service_id)
        
        if not service:
            abort(404)

        profile_pic = self._get_profile_pic(uid, email)
            
        return render_template('service.html', service=service, name=name, email=email, uid=uid, profile_pic=profile_pic)
    

    def dental_location(self):
        name = session.get('name', 'Guest')
        email = session.get('email', '')
        uid = session.get('uid', '')
        profile_pic = ''

        profile_pic = self._get_profile_pic(uid, email)
            
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
        
        if not self._is_admin():
            return jsonify({"success": False, "message": "Unauthorized"}), 403

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

                "has_unpaid": self._agg_has_unpaid(done_procedures),

                "updated_at":
                    firestore.SERVER_TIMESTAMP
            })

            print("DONE_PROCEDURE SAVED SUCCESSFULLY.")
            # Phase 3: keep the daily aggregates in step (never raises).
            self._agg_apply_rows(add=done_procedures)
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

                "message": "Something went wrong. Please try again."

            }), 500
    
    

    def get_treatment_info(self, patient_id):
        
        if not self._is_admin():
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        
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

                "message": "Something went wrong. Please try again."

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

        source_data = source_doc.to_dict()
        target_data = target_doc.to_dict()

        source_uid = source_data.get("account_uid", "")
        target_uid = target_data.get("account_uid", "")
        
        if not source_uid or not target_uid:
            return jsonify({"success": False, "message": "One of the patients does not have a linked account"}), 400

        # NEW: reconcile Birthday BEFORE touching anything else. This
        # mirrors the same rule find_patient() already uses for duplicate
        # detection ("if both records have a birthday, it must match
        # exactly") -- so a genuine mismatch here is a signal these may
        # not actually be the same person, and we block rather than
        # silently discard one of the two birthdays.
        source_birthday = str(source_data.get("birthday", "") or "").strip()
        target_birthday = str(target_data.get("birthday", "") or "").strip()

        if source_birthday and target_birthday and source_birthday != target_birthday:
            return jsonify({
                "success": False,
                "message": (
                    f"These records have different birthdays "
                    f"(target: {target_birthday}, source: {source_birthday}) "
                    f"and may not be the same patient. Merge blocked -- "
                    f"please verify before merging."
                )
            }), 409

        birthday_to_keep = target_birthday or source_birthday

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

        # NEW: recompute has_history / last_approved_at / last_sex on the
        # target account now that source's appointments live there too.
        # Mirrors merge_patient_accounts() (the walk-in merge path), which
        # already does this -- without it, target's "most recent
        # appointment" data (including Sex) could go stale after a merge
        # if source actually had the more recent visit.
        has_approve = any(True for _ in target_acc_ref.collection("Approve").limit(1).stream())
        has_done = any(True for _ in target_acc_ref.collection("Done_procedure").limit(1).stream())

        latest_accepted = None
        latest_sex = ""
        for a in target_acc_ref.collection("Approve").stream():
            a_data = a.to_dict()
            accepted_at = a_data.get("accepted_at", "")
            if accepted_at and (latest_accepted is None or accepted_at > latest_accepted):
                latest_accepted = accepted_at
                latest_sex = a_data.get("Sex", "")

        account_update = {
            "has_history": has_approve or has_done,
            "last_approved_at": latest_accepted or ""
        }
        if latest_sex:
            account_update["last_sex"] = latest_sex
        # Phase 2: carry contact / sex / civil status over, only into fields
        # the target account has blank.
        self._merge_identity_fill(source_acc_ref, target_acc_ref, account_update)
        target_acc_ref.update(account_update)

        if birthday_to_keep and birthday_to_keep != target_birthday:
            target_ref.update({"birthday": birthday_to_keep})

        # Clean up source account and patient record
        source_acc_ref.delete()
        source_ref.delete()

        self._invalidate_financial_cache()
        self._invalidate_accounts_cache()
        self._invalidate_patients_cache()

        return jsonify({"success": True, "message": "Patients merged successfully"})

    def _financial_alltime_stats(self):
        """
        One pass over the cached Done_procedure scan (no extra Firestore
        reads) for the numbers that do NOT depend on the selected period:

        - outstanding / unpaid_count: everything with balance > 0, the same
          rule the Unpaid Procedures table uses, so the cards match it.
        - total_paid: every paid amount ever recorded (the "Overall" total).
        - paid_by_year / earliest: dated procedures only, used for the
          one-bar-per-year Overall view and to stop the picker from walking
          back into years with no data. Dates before 2000 or after today
          are treated as typos and ignored here (they still count in
          total_paid).
        """
        today = datetime.now(PH_TZ).date()
        total_paid = 0.0
        outstanding = 0.0
        unpaid_count = 0
        earliest = None
        paid_by_year = {}

        for data in self._get_done_procedures_cached():
            procs = data.get("procedures", [])
            if not isinstance(procs, list):
                continue
            for p in procs:
                if not isinstance(p, dict):
                    continue
                paid = self.safe_float(p.get("paid", 0))
                balance = self.safe_float(p.get("balance", 0))
                total_paid += paid
                if balance > 0:
                    outstanding += balance
                    unpaid_count += 1

                date_str = str(p.get("date", "")).strip()
                if not date_str:
                    continue
                try:
                    proc_date = datetime.fromisoformat(date_str).date()
                except Exception:
                    continue
                if proc_date.year < 2000 or proc_date > today:
                    continue
                paid_by_year[proc_date.year] = paid_by_year.get(proc_date.year, 0.0) + paid
                if earliest is None or proc_date < earliest:
                    earliest = proc_date

        return {
            "total_paid": total_paid,
            "outstanding": outstanding,
            "unpaid_count": unpaid_count,
            "earliest": earliest,
            "paid_by_year": paid_by_year,
        }

    def admin_financial_chart_data(self):
        """
        Returns income-over-time data for the Financial Reports trend chart.

        period=today    -> today only
        period=weekly   -> 7-day window ending today; &week=N steps back N weeks
        period=monthly  -> one calendar month, day by day; &month=YYYY-MM
        period=yearly   -> January to December of one year; &year=YYYY
        period=overall  -> one point per year, earliest year to this year

        Total income follows the selected period. Outstanding Balance and
        Unpaid Procedures always cover everything unpaid (same as the table).
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        # Phase 3: when the aggregate switch is on (and the aggregates have
        # been built) answer from the daily aggregates instead of the scan.
        if self._agg_enabled() and self._agg_ready():
            return self._agg_admin_financial_chart_data()

        period = request.args.get("period", "weekly").strip().lower()
        if period not in ("today", "weekly", "monthly", "yearly", "overall"):
            period = "weekly"
        today = datetime.now(PH_TZ).date()

        def int_arg(name, default):
            try:
                return int(request.args.get(name, default))
            except (TypeError, ValueError):
                return default

        try:
            stats = self._financial_alltime_stats()
            done_docs = self._get_done_procedures_cached()
        except Exception as e:
            print("FINANCIAL CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

        earliest = stats["earliest"]
        # Earliest year the pickers/dropdowns offer: at least the last 5 years
        # (this year + 4 before), or further back if there is older data. This
        # keeps the dropdowns usable even when all data is from this year.
        first_year = min(earliest.year if earliest else today.year, today.year - 4)

        def respond(labels, values, total_income, range_label, **extra):
            payload = {
                "success": True,
                "period": period,
                "labels": labels,
                "data": values,
                "total_income": round(total_income, 2),
                # Always everything unpaid, whatever period is on screen.
                "total_outstanding": round(stats["outstanding"], 2),
                "unpaid_procedures": stats["unpaid_count"],
                "range_label": range_label,
                "as_of_label": f"{today:%B} {today.day}, {today.year}",
                "chart_type": "line",
                "can_prev": False,
                "can_next": False,
                "min_year": first_year,
                "max_year": today.year,
                "max_month": today.month,  # last selectable month in max_year
            }
            payload.update(extra)
            return jsonify(payload)

        # --- Yearly: January to December of the chosen year ---
        if period == "yearly":
            min_year = first_year
            year = max(min_year, min(int_arg("year", today.year), today.year))

            income_by_month = {m: 0.0 for m in range(1, 13)}
            total_income = 0.0
            try:
                for data in done_docs:
                    for p in data.get("procedures", []):
                        if not isinstance(p, dict):
                            continue
                        date_str = str(p.get("date", "")).strip()
                        if not date_str:
                            continue
                        try:
                            proc_date = datetime.fromisoformat(date_str).date()
                        except Exception:
                            continue
                        if proc_date.year == year:
                            paid = self.safe_float(p.get("paid", 0))
                            income_by_month[proc_date.month] += paid
                            total_income += paid
            except Exception as e:
                print("FINANCIAL CHART DATA ERROR:", e)
                return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

            labels = [datetime(2000, m, 1).strftime("%b") for m in range(1, 13)]
            # Months that haven't happened yet are left empty (null) so the
            # line stops at the current month instead of dropping to zero.
            values = [
                None if (year == today.year and m > today.month) else round(income_by_month[m], 2)
                for m in range(1, 13)
            ]
            return respond(
                labels, values, total_income, str(year),
                year=year,
                can_prev=year > min_year,
                can_next=year < today.year,
            )

        # --- Overall: one point per year ---
        if period == "overall":
            overall_first_year = earliest.year if earliest else today.year
            years = list(range(overall_first_year, today.year + 1))
            labels = [str(y) for y in years]
            values = [round(stats["paid_by_year"].get(y, 0.0), 2) for y in years]
            range_label = str(years[0]) if len(years) == 1 else f"{years[0]} to {years[-1]}"
            return respond(
                labels, values, stats["total_paid"], range_label,
                chart_type="bar",
            )

        # --- Today / Weekly / Monthly: day-by-day ---
        extra = {}
        if period == "today":
            start_date = today
            num_days = 1
            range_label = f"{today:%B} {today.day}, {today.year}"
        elif period == "monthly":
            raw_month = request.args.get("month", "").strip()
            try:
                y, m = int(raw_month[:4]), int(raw_month[5:7])
                datetime(y, m, 1)  # rejects month 0 / 13
            except (TypeError, ValueError):
                y, m = today.year, today.month
            cur = (today.year, today.month)
            lowest = (first_year, 1)
            y, m = max(lowest, min((y, m), cur))

            start_date = today.replace(year=y, month=m, day=1)
            next_first = (
                today.replace(year=y + 1, month=1, day=1) if m == 12
                else today.replace(year=y, month=m + 1, day=1)
            )
            # The current month stops at today so the line doesn't fall to
            # zero for days that haven't happened yet.
            last_day = min(next_first - timedelta(days=1), today)
            num_days = (last_day - start_date).days + 1
            range_label = f"{start_date:%B} {y}"
            extra = {
                "month": f"{y}-{m:02d}",
                "can_prev": (y, m) > lowest,
                "can_next": (y, m) < cur,
            }
        else:
            period = "weekly"
            max_week = (today - today.replace(year=first_year, month=1, day=1)).days // 7
            week = min(max(0, int_arg("week", 0)), max_week)
            end_date = today - timedelta(days=7 * week)
            start_date = end_date - timedelta(days=6)
            num_days = 7
            if start_date.year == end_date.year:
                range_label = f"{start_date:%b} {start_date.day} to {end_date:%b} {end_date.day}, {end_date.year}"
            else:
                range_label = (
                    f"{start_date:%b} {start_date.day}, {start_date.year} to "
                    f"{end_date:%b} {end_date.day}, {end_date.year}"
                )
            extra = {
                "week": week,
                "can_prev": week < max_week,
                "can_next": week > 0,
            }

        date_keys = [
            (start_date + timedelta(days=i)).isoformat()
            for i in range(num_days)
        ]
        income_by_date = {d: 0.0 for d in date_keys}
        total_income = 0.0

        try:
            for data in done_docs:
                for p in data.get("procedures", []):
                    if not isinstance(p, dict):
                        continue
                    date_str = str(p.get("date", "")).strip()
                    if date_str in income_by_date:
                        paid = self.safe_float(p.get("paid", 0))
                        income_by_date[date_str] += paid
                        total_income += paid
        except Exception as e:
            print("FINANCIAL CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

        if period == "today":
            labels = ["Today"]
        else:
            labels = [
                datetime.fromisoformat(d).strftime("%b %d")
                for d in date_keys
            ]
        values = [round(income_by_date[d], 2) for d in date_keys]

        return respond(labels, values, total_income, range_label, **extra)

    def admin_unpaid_procedures(self):
        """
        Every procedure that still has an unpaid balance, with the patient's
        name, for the "Unpaid Procedures" table on Financial Reports.

        Costs no extra Firestore reads in the normal case: it reuses the
        cached Done_procedure scan the financial cards already use and the
        cached Patients list for names. The accounts cache is only touched
        when a name can't be found in the Patients list.

        "Unpaid" means balance > 0, the same rule the Unpaid Procedures card
        and the Outstanding Balance card use, so the totals agree.
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        # Phase 3: aggregate switch on and built -> read only the has_unpaid documents.
        if self._agg_enabled() and self._agg_ready():
            return self._agg_admin_unpaid_procedures()

        try:
            # --- name sources, best first -------------------------------------
            # 1. Customer_Account firstname/lastname: the same editable name
            #    My Patients and the Treatment Information window show. Walk-in
            #    accounts are NOT in the User Management cache, so accounts
            #    missing from it are read directly (a few reads, remembered).
            # 2. Patients collection (by account link, then by patient id).
            name_by_patient_id = {}
            name_by_account = {}
            for patient_id, pdata in self._get_patients_cached():
                parts = [
                    str(pdata.get("first_name", "")).strip(),
                    str(pdata.get("middle_name", "")).strip(),
                    str(pdata.get("last_name", "")).strip(),
                ]
                full = " ".join(part for part in parts if part)
                if not full:
                    continue
                name_by_patient_id[patient_id] = full
                linked_uid = pdata.get("account_uid") or ""
                if linked_uid and linked_uid not in name_by_account:
                    name_by_account[linked_uid] = full

            managed = None  # uid -> account data, built on first use
            direct_names = self.cache.get("unpaid_account_names")
            if direct_names is None:
                direct_names = {}
            direct_changed = False

            def account_name(account_uid):
                nonlocal managed, direct_changed
                if not account_uid:
                    return ""
                if managed is None:
                    managed = {uid: acc for uid, acc in self._get_manageable_accounts_cached()}
                acc = managed.get(account_uid)
                if acc is None:
                    if account_uid in direct_names:
                        return direct_names[account_uid]
                    try:
                        snap = (
                            self.db.collection(self.Customer_Account)
                            .document(account_uid)
                            .get()
                        )
                        acc = snap.to_dict() if snap.exists else {}
                    except Exception as e:
                        print("UNPAID NAME LOOKUP FAILED:", account_uid, e)
                        return ""
                    nm = (
                        f"{acc.get('firstname') or ''} {acc.get('lastname') or ''}".strip()
                        or str(acc.get("name") or "").strip()
                    )
                    direct_names[account_uid] = nm
                    direct_changed = True
                    return nm
                return (
                    f"{acc.get('firstname') or ''} {acc.get('lastname') or ''}".strip()
                    or str(acc.get("name") or "").strip()
                )

            rows = []
            total_balance = 0.0

            for data in self._get_done_procedures_cached():
                procs = data.get("procedures", [])
                if not isinstance(procs, list):
                    continue

                # Two places can say which account this record belongs to: the
                # uid saved inside the record, and the record's real location
                # in the database. They can disagree (e.g. records copied by a
                # patient merge keep the old uid), so try both.
                field_uid = str(data.get("uid") or "").strip()
                path_uid = str(data.get("_account_uid") or "").strip()
                uid_candidates = []
                for cand in (path_uid, field_uid):
                    if cand and cand not in uid_candidates:
                        uid_candidates.append(cand)
                account_uid = path_uid or field_uid
                patient_unq_id = str(data.get("Patient_unq_id") or "").strip()

                resolved_name = None  # same patient for every row of this record

                for p in procs:
                    if not isinstance(p, dict):
                        continue

                    balance = self.safe_float(p.get("balance", 0))
                    if balance <= 0:
                        continue

                    if resolved_name is None:
                        resolved_name = ""
                        for cand in uid_candidates:
                            resolved_name = account_name(cand) or name_by_account.get(cand) or ""
                            if resolved_name:
                                break
                        if not resolved_name:
                            resolved_name = name_by_patient_id.get(patient_unq_id) or ""
                        if not resolved_name:
                            print(
                                "UNPAID LIST: no name found. uid in record:", repr(field_uid),
                                "| record stored under account:", repr(path_uid),
                                "| Patient_unq_id:", repr(patient_unq_id),
                            )

                    rows.append({
                        "patient_name": resolved_name or "Unknown patient",
                        "uid": account_uid,
                        "patient_id": patient_unq_id,
                        "procedure": str(p.get("procedure", "") or ""),
                        "tooth": str(p.get("tooth", "") or ""),
                        "date": str(p.get("date", "") or "").strip(),
                        "dentist": str(p.get("dentist", "") or ""),
                        "value": round(self.safe_float(p.get("value", 0)), 2),
                        "paid": round(self.safe_float(p.get("paid", 0)), 2),
                        "balance": round(balance, 2),
                    })
                    total_balance += balance

            if direct_changed:
                self.cache.set("unpaid_account_names", direct_names, ttl_seconds=self.CACHE_TTL_SECONDS)

            rows.sort(key=lambda r: r["balance"], reverse=True)

            return jsonify({
                "success": True,
                "rows": rows,
                "total_balance": round(total_balance, 2),
            })

        except Exception as e:
            print("UNPAID PROCEDURES ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def get_approve(self, uid):
        
        if not self._is_owner_or_admin(uid):
            return jsonify({"error": "Unauthorized"}), 403
        
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
            return jsonify({"error": "Something went wrong. Please try again."}), 500
    
    def _find_unlinked_patient_by_name_parts(self, first_name, middle_name, last_name, birthday=""):
        """
        Strict, login-card-only lookup. Deliberately NOT used by find_patient()
        or anything that creates, links or merges records.

        A candidate must be an UNLINKED patient (no account, or a walkin_
        placeholder) and one name must be completely contained in the other:
        every word of the shorter name appears in the longer one, with at
        least two shared words. "Felix Adrian Prieto Roa" matches a walk-in
        "Felix Adrian" + "Prieto Roa", but "Adrian Porras Prieto" does not
        (Porras is not in that name). If two different patients tie, nothing
        is suggested rather than guessing. Never raises.
        """
        try:
            def words(*parts):
                return set(" ".join(
                    self.normalize_patient_name(x) for x in parts if x
                ).split())

            query = words(first_name, middle_name, last_name)
            birthday = str(birthday or "").strip()
            if len(query) < 2:
                return None

            found = []
            for patient_id, data in self._get_patients_cached():
                data = data or {}
                uid = data.get("account_uid") or ""
                if uid and not uid.startswith("walkin_"):
                    continue
                stored = words(
                    data.get("first_name_normalized", ""),
                    data.get("middle_name_normalized", ""),
                    data.get("last_name_normalized", ""),
                )
                shared = query & stored
                if len(shared) < 2 or not (shared == query or shared == stored):
                    continue
                stored_bday = str(data.get("birthday", "") or "").strip()
                if birthday and stored_bday and birthday != stored_bday:
                    continue
                found.append((len(shared), patient_id))

            if not found:
                return None
            found.sort(reverse=True)
            if len(found) > 1 and found[0][0] == found[1][0]:
                return None  # ambiguous: do not guess

            # Re-read the winner so a stale cache can't suggest a patient who
            # has since been linked, renamed or deleted.
            snap = self.db.collection(self.Doc_Patients).document(found[0][1]).get()
            if not snap.exists:
                return None
            fresh = snap.to_dict() or {}
            uid = fresh.get("account_uid") or ""
            if uid and not uid.startswith("walkin_"):
                return None
            fresh["patient_id"] = snap.id
            return fresh
        except Exception as e:
            print("NAME-PART PATIENT MATCH FAILED:", e)
            return None

    def find_unlinked_patient_match(self, first_name, last_name, middle_name="", birthday=""):
        match = self.find_patient(
            first_name=first_name, 
            middle_name=middle_name, 
            last_name=last_name,
            birthday=birthday
        )
        if match:
            # find_patient() returns its single best match even when that
            # patient is already linked to a real account. That is not a
            # candidate for this prompt, and it must not stop the strict
            # name-part search below from finding the unlinked walk-in.
            linked_uid = match.get("account_uid") or ""
            if linked_uid and not linked_uid.startswith("walkin_"):
                match = None
        if not match:
            # find_patient() only sees patients whose whole first or last
            # name equals the query's, so it misses a walk-in saved as
            # "Felix Adrian" / "Prieto Roa" when a Google sign-in splits the
            # same name as "Felix" / "Adrian Prieto Roa". For this prompt only
            # (the patient still has to press "Yes, that's me"), try a strict
            # name-part match against unlinked walk-in records.
            match = self._find_unlinked_patient_by_name_parts(
                first_name, middle_name, last_name, birthday
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
            # (The account doc used to be read here only to feed the guard
            # below. While that guard is switched off the read was wasted, so
            # it is skipped. If the guard is re-enabled, read the account again.)
            
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
            
        # Phase 3: aggregate switch on and built -> answer from the daily aggregates.
        if self._agg_enabled() and self._agg_ready():
            return self._agg_admin_procedure_chart_data()

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
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

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


    # ============================================================
    # PHASE 3: DAILY FINANCIAL AGGREGATES  (purely additive)
    # ============================================================
    # Nothing above this block was changed by Phase 3. What it adds:
    #
    #  * Stats_daily/{YYYY-MM-DD | undated}: one small document per day with
    #    that day's income, outstanding balance and per-procedure count and
    #    revenue. No uids are stored in it. Kept in step by tiny hook calls
    #    placed next to the existing Stats/financial_summary writes.
    #  * has_unpaid (bool) on every Done_procedure document.
    #  * _agg_admin_* : copies of the three scan-based endpoints with ONLY the
    #    data source swapped. The originals are untouched and still run
    #    whenever the switch is off, the aggregates were never built, or an
    #    aggregate read fails.
    #  * Admin-only tools: /admin/aggregates/repair, /compare and /switch.
    #
    # Every hook is wrapped so that an aggregate problem can never break the
    # save, edit, delete or payment it sits next to; the worst case is a
    # small drift that /admin/aggregates/repair rebuilds from the real data.
    AGG_COLLECTION = "Stats_daily"
    AGG_UNDATED = "undated"
    AGG_META = "_meta"
    AGG_UNPAID_TTL_SECONDS = 120
    _agg_lock = threading.Lock()
    _agg_repair_lock = threading.Lock()
    _agg_gen = 0
    _AGG_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def _agg_enabled(self):
        """In-memory override (set by /admin/aggregates/switch) wins, then
        the USE_AGGREGATES environment variable. Off by default."""
        override = getattr(self, "_agg_override", None)
        if override is not None:
            return bool(override)
        return os.getenv("USE_AGGREGATES", "").strip().lower() in ("1", "true", "yes", "on")

    def _agg_num(self, value):
        """safe_float, but never NaN/inf, so an aggregate write can't fail."""
        n = self.safe_float(value)
        try:
            if n != n or n in (float("inf"), float("-inf")):
                return 0.0
            return float(n)
        except Exception:
            return 0.0

    def _agg_has_unpaid(self, procedures):
        """True when any row might still be listed as unpaid. Deliberately
        over-inclusive (a false True is harmless because the Unpaid table
        still filters row by row; a false False would hide a debt). Never
        raises."""
        try:
            if not isinstance(procedures, list):
                return False
            for p in procedures:
                if isinstance(p, dict) and not (self.safe_float(p.get("balance", 0)) <= 0):
                    return True
            return False
        except Exception:
            return True

    def _agg_invalidate_caches(self):
        try:
            self._agg_gen += 1
            self.cache.invalidate("agg_daily_all")
            self.cache.invalidate("agg_unpaid_docs")
        except Exception as e:
            print("AGGREGATE CACHE INVALIDATE FAILED:", e)

    # --- turning treatment rows into daily contributions ---------------
    def _agg_row_parts(self, p):
        """The pieces of one treatment row the aggregates care about, using
        exactly the same reading rules as the scan-based code."""
        if not isinstance(p, dict):
            return None
        paid = self._agg_num(p.get("paid", 0))
        balance = self._agg_num(p.get("balance", 0))
        bucket = self.AGG_UNDATED
        canon = False
        date_str = str(p.get("date", "")).strip()
        if date_str:
            try:
                parsed = datetime.fromisoformat(date_str).date()
                bucket = parsed.isoformat()
                # The day-by-day charts only count a row whose date text is
                # exactly YYYY-MM-DD; the monthly/yearly ones accept anything
                # fromisoformat understands. "canon" keeps the two apart.
                canon = (date_str == bucket)
            except Exception:
                bucket = self.AGG_UNDATED
        name = str(p.get("procedure", "")).strip()
        pid = ""
        if name:
            pid = "p" + hashlib.sha1(name.lower().encode("utf-8", "replace")).hexdigest()[:20]
        return {
            "bucket": bucket, "canon": canon, "paid": paid, "balance": balance,
            "name": name, "pid": pid,
        }

    def _agg_new_bucket(self):
        return {"rows": 0, "paid": 0.0, "paid_alt": 0.0, "outstanding": 0.0, "unpaid": 0, "procs": {}}

    def _agg_accumulate(self, net, parts, sign):
        key = parts["bucket"]
        b = net.get(key)
        if b is None:
            b = net[key] = self._agg_new_bucket()
        b["rows"] += sign
        field = "paid" if (parts["canon"] or key == self.AGG_UNDATED) else "paid_alt"
        b[field] += sign * parts["paid"]
        if parts["balance"] > 0:
            b["outstanding"] += sign * parts["balance"]
            b["unpaid"] += sign
        if parts["pid"]:
            pr = b["procs"].get(parts["pid"])
            if pr is None:
                pr = b["procs"][parts["pid"]] = {"n": parts["name"], "c": 0, "r": 0.0}
            pr["c"] += sign
            pr["r"] += sign * parts["paid"]
            if sign > 0 or not pr["n"]:
                pr["n"] = parts["name"]

    def _agg_delta_is_zero(self, b):
        if b["rows"] != 0 or b["unpaid"] != 0:
            return False
        for f in ("paid", "paid_alt", "outstanding"):
            if abs(b[f]) > 1e-9:
                return False
        for pr in b["procs"].values():
            if pr["c"] != 0 or abs(pr["r"]) > 1e-9:
                return False
        return True

    def _agg_increment_payload(self, b):
        data = {
            "rows": firestore.Increment(b["rows"]),
            "paid": firestore.Increment(b["paid"]),
            "paid_alt": firestore.Increment(b["paid_alt"]),
            "outstanding": firestore.Increment(b["outstanding"]),
            "unpaid": firestore.Increment(b["unpaid"]),
        }
        procs = {}
        for pid, pr in b["procs"].items():
            if pr["c"] == 0 and abs(pr["r"]) <= 1e-9:
                continue
            procs[pid] = {
                "n": pr["n"],
                "c": firestore.Increment(pr["c"]),
                "r": firestore.Increment(pr["r"]),
            }
        if procs:
            data["procs"] = procs
        return data

    def _agg_apply_rows(self, add=None, remove=None):
        """Add the daily contribution of the `add` rows and take away that of
        the `remove` rows (an edit passes both). Never raises; returns False
        if the aggregate write failed so the caller can ignore it safely."""
        try:
            net = {}
            for rows, sign in ((remove, -1), (add, 1)):
                for p in (rows or []):
                    parts = self._agg_row_parts(p)
                    if parts is not None:
                        self._agg_accumulate(net, parts, sign)
            writes = [(k, b) for k, b in net.items() if not self._agg_delta_is_zero(b)]
            for i in range(0, len(writes), 400):
                batch = self.db.batch()
                for key, b in writes[i:i + 400]:
                    ref = self.db.collection(self.AGG_COLLECTION).document(key)
                    batch.set(ref, self._agg_increment_payload(b), merge=True)
                batch.commit()
            return True
        except Exception as e:
            print("DAILY AGGREGATE UPDATE FAILED (run /admin/aggregates/repair):", e)
            return False
        finally:
            self._agg_invalidate_caches()

    def _agg_remove_done_doc(self, snap):
        """delete_patient hook: take a just-deleted Done_procedure document's
        rows out of the aggregates. Never raises."""
        try:
            rows = (snap.to_dict() or {}).get("procedures", [])
            if isinstance(rows, list):
                self._agg_apply_rows(remove=rows)
        except Exception as e:
            print("DAILY AGGREGATE REMOVE FAILED (run /admin/aggregates/repair):", e)

    # --- reading the aggregates ------------------------------------------
    def _agg_load_all(self, force=False):
        """Every Stats_daily document (one per active day), cached like the
        other admin caches and cleared by every aggregate write."""
        if not force:
            cached = self.cache.get("agg_daily_all")
            if cached is not None:
                return cached
        with self._agg_lock:
            if not force:
                cached = self.cache.get("agg_daily_all")
                if cached is not None:
                    return cached
            gen = self._agg_gen
            data = {}
            for doc in self.db.collection(self.AGG_COLLECTION).stream():
                data[doc.id] = doc.to_dict() or {}
            if gen == self._agg_gen:
                self.cache.set("agg_daily_all", data, ttl_seconds=self.CACHE_TTL_SECONDS)
            return data

    def _agg_ready(self):
        """True only once /admin/aggregates/repair has built the aggregates
        at least once, so switching on early can never show empty charts.
        Any read problem counts as 'not ready' (the old scan then answers)."""
        try:
            meta = self._agg_load_all().get(self.AGG_META) or {}
            return bool(meta.get("repaired_at"))
        except Exception as e:
            print("AGGREGATES NOT READY:", e)
            return False

    def _agg_live_buckets(self, agg):
        for key, d in agg.items():
            if key == self.AGG_UNDATED or self._AGG_DATE_KEY.match(key):
                if isinstance(d, dict) and self._agg_num(d.get("rows")) > 0:
                    yield key, d

    def _agg_alltime_stats(self, agg):
        """Aggregate twin of _financial_alltime_stats(): same keys, same
        rules (dates before 2000 or after today are ignored for the yearly
        totals and the earliest year; everything else counts)."""
        today = datetime.now(PH_TZ).date()
        total_paid = 0.0
        outstanding = 0.0
        unpaid_count = 0
        earliest = None
        paid_by_year = {}
        for key, d in self._agg_live_buckets(agg):
            paid = self._agg_num(d.get("paid")) + self._agg_num(d.get("paid_alt"))
            total_paid += paid
            outstanding += self._agg_num(d.get("outstanding"))
            unpaid_count += int(round(self._agg_num(d.get("unpaid"))))
            if key == self.AGG_UNDATED:
                continue
            try:
                day = datetime.fromisoformat(key).date()
            except Exception:
                continue
            if day.year < 2000 or day > today:
                continue
            paid_by_year[day.year] = paid_by_year.get(day.year, 0.0) + paid
            if earliest is None or day < earliest:
                earliest = day
        return {
            "total_paid": total_paid,
            "outstanding": outstanding,
            "unpaid_count": unpaid_count,
            "earliest": earliest,
            "paid_by_year": paid_by_year,
        }

    def _agg_income_docs(self, agg):
        """Stand-in for the Done_procedure scan, shaped so the unchanged
        income-chart code reads the same totals from it: per day one row
        with the exact YYYY-MM-DD text (counted by the day-by-day views) and
        one row whose text has a time part (counted only by month/year)."""
        rows = []
        for key, d in self._agg_live_buckets(agg):
            if key == self.AGG_UNDATED:
                continue
            rows.append({"date": key, "paid": self._agg_num(d.get("paid"))})
            rows.append({"date": key + "T00:00:00", "paid": self._agg_num(d.get("paid_alt"))})
        return [{"procedures": rows}]

    def _agg_procedure_docs(self, agg):
        """Stand-in scan for the procedure chart: each procedure per day
        becomes `count` rows carrying the day's revenue, so the unchanged
        counting code reproduces the same counts and revenue."""
        out = []
        for key, d in self._agg_live_buckets(agg):
            date_val = "" if key == self.AGG_UNDATED else key
            procs = d.get("procs") or {}
            if not isinstance(procs, dict):
                continue
            for pr in procs.values():
                if not isinstance(pr, dict):
                    continue
                count = int(round(self._agg_num(pr.get("c"))))
                name = str(pr.get("n") or "").strip()
                if count <= 0 or not name:
                    continue
                rows = [{"date": date_val, "procedure": name, "paid": self._agg_num(pr.get("r"))}]
                for _ in range(count - 1):
                    rows.append({"date": date_val, "procedure": name, "paid": 0.0})
                out.append({"procedures": rows})
        return out

    def _agg_unpaid_docs(self):
        """Stand-in for the scan used by the Unpaid table: only documents
        flagged has_unpaid, in the same shape as the cached scan."""
        cached = self.cache.get("agg_unpaid_docs")
        if cached is not None:
            return cached
        with self._agg_lock:
            cached = self.cache.get("agg_unpaid_docs")
            if cached is not None:
                return cached
            gen = self._agg_gen
            docs = []
            try:
                query = (
                    self.db.collection_group("Done_procedure")
                    .where(filter=FieldFilter("has_unpaid", "==", True))
                    .select(["procedures", "uid", "Patient_unq_id"])
                )
                for doc in query.stream():
                    d = doc.to_dict() or {}
                    try:
                        d["_account_uid"] = doc.reference.parent.parent.id
                    except Exception:
                        d["_account_uid"] = ""
                    docs.append(d)
            except Exception as e:
                # Usually the has_unpaid collection-group index has not been
                # created yet. Fall back to the existing cached scan, which
                # gives the same rows (the table still filters row by row).
                print("UNPAID QUERY FAILED, using the full scan instead "
                      "(create the has_unpaid collection-group index):", e)
                docs = [
                    d for d in self._get_done_procedures_cached()
                    if self._agg_has_unpaid(d.get("procedures"))
                ]
            if gen == self._agg_gen:
                self.cache.set("agg_unpaid_docs", docs, ttl_seconds=self.AGG_UNPAID_TTL_SECONDS)
            return docs

    # --- repair / compare -------------------------------------------------
    def _agg_scan_truth(self, fix_flags=False):
        """Fresh scan of every Done_procedure document (bypasses the cache).
        Returns the daily buckets the real data adds up to, plus how the
        has_unpaid flags look. With fix_flags=True it also writes the flag
        on documents where it is missing or wrong."""
        buckets = {}
        docs = 0
        rows = 0
        flags_missing = 0
        flags_wrong = 0
        unpaid_not_flagged = 0
        to_fix = []
        query = self.db.collection_group("Done_procedure").select(["procedures", "has_unpaid"])
        for doc in query.stream():
            d = doc.to_dict() or {}
            procs = d.get("procedures", [])
            if not isinstance(procs, list):
                procs = []
            docs += 1
            for p in procs:
                parts = self._agg_row_parts(p)
                if parts is not None:
                    self._agg_accumulate(buckets, parts, 1)
                    rows += 1
            want = self._agg_has_unpaid(procs)
            have = d.get("has_unpaid")
            if "has_unpaid" not in d:
                flags_missing += 1
            elif have is not want:
                flags_wrong += 1
            if want and have is not True:
                unpaid_not_flagged += 1
            if have is not want:
                to_fix.append((doc.reference, want))
        flags_fixed = 0
        if fix_flags:
            for i in range(0, len(to_fix), 400):
                batch = self.db.batch()
                for ref, want in to_fix[i:i + 400]:
                    batch.update(ref, {"has_unpaid": want})
                batch.commit()
            flags_fixed = len(to_fix)
        return {
            "buckets": buckets, "docs": docs, "rows": rows,
            "flags_missing": flags_missing, "flags_wrong": flags_wrong,
            "unpaid_not_flagged": unpaid_not_flagged, "flags_fixed": flags_fixed,
        }

    def _agg_rebuild(self):
        """Rebuild every daily aggregate from the real Done_procedure
        documents and backfill has_unpaid. Safe to run any time (best when
        nobody is saving); running it again gives the same result."""
        with self._agg_repair_lock:
            truth = self._agg_scan_truth(fix_flags=True)
            coll = self.db.collection(self.AGG_COLLECTION)
            existing = [doc.id for doc in coll.stream()]
            new_docs = {}
            for key, b in truth["buckets"].items():
                if b["rows"] <= 0:
                    continue
                doc = {
                    "rows": int(b["rows"]),
                    "paid": round(b["paid"], 6),
                    "paid_alt": round(b["paid_alt"], 6),
                    "outstanding": round(b["outstanding"], 6),
                    "unpaid": int(b["unpaid"]),
                }
                procs = {
                    pid: {"n": pr["n"], "c": int(pr["c"]), "r": round(pr["r"], 6)}
                    for pid, pr in b["procs"].items() if pr["c"] > 0
                }
                if procs:
                    doc["procs"] = procs
                new_docs[key] = doc
            items = list(new_docs.items())
            for i in range(0, len(items), 400):
                batch = self.db.batch()
                for key, doc in items[i:i + 400]:
                    batch.set(coll.document(key), doc)
                batch.commit()
            stale = [k for k in existing if k not in new_docs and k != self.AGG_META]
            for i in range(0, len(stale), 400):
                batch = self.db.batch()
                for key in stale[i:i + 400]:
                    batch.delete(coll.document(key))
                batch.commit()
            summary = {
                "documents_scanned": truth["docs"],
                "rows_scanned": truth["rows"],
                "days_written": len(new_docs),
                "stale_days_removed": len(stale),
                "flags_fixed": truth["flags_fixed"],
            }
            meta = dict(summary)
            meta["repaired_at"] = datetime.now(UTC).isoformat()
            meta["version"] = 1
            coll.document(self.AGG_META).set(meta)
            self._agg_invalidate_caches()
            return summary

    def admin_aggregates_repair(self):
        """Admin-only: rebuild the daily aggregates + has_unpaid flags from
        the real treatment records. Idempotent."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            summary = self._agg_rebuild()
            summary["success"] = True
            return jsonify(summary)
        except Exception as e:
            print("AGGREGATE REPAIR ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_aggregates_compare(self):
        """Admin-only: read-only check of the stored aggregates against a
        fresh scan of the real records (costs one full scan)."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            truth = self._agg_scan_truth(fix_flags=False)
            stored = self._agg_load_all(force=True)
            live = {k: d for k, d in self._agg_live_buckets(stored)}
            tb_all = {k: b for k, b in truth["buckets"].items() if b["rows"] > 0}
            mismatches = []

            def num(d, field):
                return self._agg_num((d or {}).get(field))

            for key in sorted(set(tb_all) | set(live)):
                tb = tb_all.get(key)
                sb = live.get(key)
                problems = []
                if int(round(num(sb, "rows"))) != (tb["rows"] if tb else 0):
                    problems.append("rows")
                if int(round(num(sb, "unpaid"))) != (tb["unpaid"] if tb else 0):
                    problems.append("unpaid")
                for field in ("paid", "paid_alt", "outstanding"):
                    if abs(num(sb, field) - (tb[field] if tb else 0.0)) > 0.01:
                        problems.append(field)
                t_procs = (tb or {}).get("procs", {})
                s_procs = (sb or {}).get("procs", {}) if isinstance((sb or {}).get("procs", {}), dict) else {}
                for pid in set(t_procs) | set(s_procs):
                    tp = t_procs.get(pid) or {"c": 0, "r": 0.0}
                    sp = s_procs.get(pid) or {}
                    s_count = int(round(num(sp, "c")))
                    t_count = tp["c"]
                    if s_count <= 0 and t_count <= 0:
                        continue
                    if s_count != t_count or abs(num(sp, "r") - tp["r"]) > 0.01:
                        problems.append("procedure:" + str(tp.get("n") or sp.get("n") or pid))
                if problems:
                    mismatches.append({"day": key, "differs": problems})

            meta = stored.get(self.AGG_META) or {}
            flags = {
                "missing": truth["flags_missing"],
                "wrong": truth["flags_wrong"],
                "unpaid_not_flagged": truth["unpaid_not_flagged"],
            }
            return jsonify({
                "success": True,
                "ready": bool(meta.get("repaired_at")),
                "last_repair": meta.get("repaired_at", ""),
                "in_sync": (not mismatches and flags["missing"] == 0 and flags["wrong"] == 0),
                "documents_scanned": truth["docs"],
                "rows_scanned": truth["rows"],
                "days_compared": len(set(tb_all) | set(live)),
                "mismatch_count": len(mismatches),
                "mismatches": mismatches[:50],
                "flags": flags,
            })
        except Exception as e:
            print("AGGREGATE COMPARE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_aggregates_switch(self):
        """Admin-only: turn the aggregate-based charts on/off instantly
        without a restart. ?on=1 / ?on=0 / ?on=env (back to the
        USE_AGGREGATES setting). No parameter just reports the state."""
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        arg = request.args.get("on", "").strip().lower()
        if arg in ("1", "true", "on", "yes"):
            self._agg_override = True
        elif arg in ("0", "false", "off", "no"):
            self._agg_override = False
        elif arg in ("env", "reset"):
            self._agg_override = None
        enabled = self._agg_enabled()
        return jsonify({
            "success": True,
            "enabled": enabled,
            "ready": self._agg_ready() if enabled else None,
            "using_aggregates": bool(enabled and self._agg_ready()),
        })

    # ------------------------------------------------------------
    # Aggregate-backed copies of the three scan-based endpoints. Each is
    # the original function text with only the data source swapped (see
    # the marked lines); they run only when the aggregate switch is on.
    # ------------------------------------------------------------
    def _agg_admin_financial_chart_data(self):
        """
        Returns income-over-time data for the Financial Reports trend chart.

        period=today    -> today only
        period=weekly   -> 7-day window ending today; &week=N steps back N weeks
        period=monthly  -> one calendar month, day by day; &month=YYYY-MM
        period=yearly   -> January to December of one year; &year=YYYY
        period=overall  -> one point per year, earliest year to this year

        Total income follows the selected period. Outstanding Balance and
        Unpaid Procedures always cover everything unpaid (same as the table).
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        period = request.args.get("period", "weekly").strip().lower()
        if period not in ("today", "weekly", "monthly", "yearly", "overall"):
            period = "weekly"
        today = datetime.now(PH_TZ).date()

        def int_arg(name, default):
            try:
                return int(request.args.get(name, default))
            except (TypeError, ValueError):
                return default

        try:
            stats = self._agg_alltime_stats(self._agg_load_all())
            done_docs = self._agg_income_docs(self._agg_load_all())
        except Exception as e:
            print("FINANCIAL CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

        earliest = stats["earliest"]
        # Earliest year the pickers/dropdowns offer: at least the last 5 years
        # (this year + 4 before), or further back if there is older data. This
        # keeps the dropdowns usable even when all data is from this year.
        first_year = min(earliest.year if earliest else today.year, today.year - 4)

        def respond(labels, values, total_income, range_label, **extra):
            payload = {
                "success": True,
                "period": period,
                "labels": labels,
                "data": values,
                "total_income": round(total_income, 2),
                # Always everything unpaid, whatever period is on screen.
                "total_outstanding": round(stats["outstanding"], 2),
                "unpaid_procedures": stats["unpaid_count"],
                "range_label": range_label,
                "as_of_label": f"{today:%B} {today.day}, {today.year}",
                "chart_type": "line",
                "can_prev": False,
                "can_next": False,
                "min_year": first_year,
                "max_year": today.year,
                "max_month": today.month,  # last selectable month in max_year
            }
            payload.update(extra)
            return jsonify(payload)

        # --- Yearly: January to December of the chosen year ---
        if period == "yearly":
            min_year = first_year
            year = max(min_year, min(int_arg("year", today.year), today.year))

            income_by_month = {m: 0.0 for m in range(1, 13)}
            total_income = 0.0
            try:
                for data in done_docs:
                    for p in data.get("procedures", []):
                        if not isinstance(p, dict):
                            continue
                        date_str = str(p.get("date", "")).strip()
                        if not date_str:
                            continue
                        try:
                            proc_date = datetime.fromisoformat(date_str).date()
                        except Exception:
                            continue
                        if proc_date.year == year:
                            paid = self.safe_float(p.get("paid", 0))
                            income_by_month[proc_date.month] += paid
                            total_income += paid
            except Exception as e:
                print("FINANCIAL CHART DATA ERROR:", e)
                return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

            labels = [datetime(2000, m, 1).strftime("%b") for m in range(1, 13)]
            # Months that haven't happened yet are left empty (null) so the
            # line stops at the current month instead of dropping to zero.
            values = [
                None if (year == today.year and m > today.month) else round(income_by_month[m], 2)
                for m in range(1, 13)
            ]
            return respond(
                labels, values, total_income, str(year),
                year=year,
                can_prev=year > min_year,
                can_next=year < today.year,
            )

        # --- Overall: one point per year ---
        if period == "overall":
            overall_first_year = earliest.year if earliest else today.year
            years = list(range(overall_first_year, today.year + 1))
            labels = [str(y) for y in years]
            values = [round(stats["paid_by_year"].get(y, 0.0), 2) for y in years]
            range_label = str(years[0]) if len(years) == 1 else f"{years[0]} to {years[-1]}"
            return respond(
                labels, values, stats["total_paid"], range_label,
                chart_type="bar",
            )

        # --- Today / Weekly / Monthly: day-by-day ---
        extra = {}
        if period == "today":
            start_date = today
            num_days = 1
            range_label = f"{today:%B} {today.day}, {today.year}"
        elif period == "monthly":
            raw_month = request.args.get("month", "").strip()
            try:
                y, m = int(raw_month[:4]), int(raw_month[5:7])
                datetime(y, m, 1)  # rejects month 0 / 13
            except (TypeError, ValueError):
                y, m = today.year, today.month
            cur = (today.year, today.month)
            lowest = (first_year, 1)
            y, m = max(lowest, min((y, m), cur))

            start_date = today.replace(year=y, month=m, day=1)
            next_first = (
                today.replace(year=y + 1, month=1, day=1) if m == 12
                else today.replace(year=y, month=m + 1, day=1)
            )
            # The current month stops at today so the line doesn't fall to
            # zero for days that haven't happened yet.
            last_day = min(next_first - timedelta(days=1), today)
            num_days = (last_day - start_date).days + 1
            range_label = f"{start_date:%B} {y}"
            extra = {
                "month": f"{y}-{m:02d}",
                "can_prev": (y, m) > lowest,
                "can_next": (y, m) < cur,
            }
        else:
            period = "weekly"
            max_week = (today - today.replace(year=first_year, month=1, day=1)).days // 7
            week = min(max(0, int_arg("week", 0)), max_week)
            end_date = today - timedelta(days=7 * week)
            start_date = end_date - timedelta(days=6)
            num_days = 7
            if start_date.year == end_date.year:
                range_label = f"{start_date:%b} {start_date.day} to {end_date:%b} {end_date.day}, {end_date.year}"
            else:
                range_label = (
                    f"{start_date:%b} {start_date.day}, {start_date.year} to "
                    f"{end_date:%b} {end_date.day}, {end_date.year}"
                )
            extra = {
                "week": week,
                "can_prev": week < max_week,
                "can_next": week > 0,
            }

        date_keys = [
            (start_date + timedelta(days=i)).isoformat()
            for i in range(num_days)
        ]
        income_by_date = {d: 0.0 for d in date_keys}
        total_income = 0.0

        try:
            for data in done_docs:
                for p in data.get("procedures", []):
                    if not isinstance(p, dict):
                        continue
                    date_str = str(p.get("date", "")).strip()
                    if date_str in income_by_date:
                        paid = self.safe_float(p.get("paid", 0))
                        income_by_date[date_str] += paid
                        total_income += paid
        except Exception as e:
            print("FINANCIAL CHART DATA ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

        if period == "today":
            labels = ["Today"]
        else:
            labels = [
                datetime.fromisoformat(d).strftime("%b %d")
                for d in date_keys
            ]
        values = [round(income_by_date[d], 2) for d in date_keys]

        return respond(labels, values, total_income, range_label, **extra)

    def _agg_admin_unpaid_procedures(self):
        """
        Every procedure that still has an unpaid balance, with the patient's
        name, for the "Unpaid Procedures" table on Financial Reports.

        Costs no extra Firestore reads in the normal case: it reuses the
        cached Done_procedure scan the financial cards already use and the
        cached Patients list for names. The accounts cache is only touched
        when a name can't be found in the Patients list.

        "Unpaid" means balance > 0, the same rule the Unpaid Procedures card
        and the Outstanding Balance card use, so the totals agree.
        """
        if not session.get('admin_logged_in'):
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        try:
            # --- name sources, best first -------------------------------------
            # 1. Customer_Account firstname/lastname: the same editable name
            #    My Patients and the Treatment Information window show. Walk-in
            #    accounts are NOT in the User Management cache, so accounts
            #    missing from it are read directly (a few reads, remembered).
            # 2. Patients collection (by account link, then by patient id).
            name_by_patient_id = {}
            name_by_account = {}
            for patient_id, pdata in self._get_patients_cached():
                parts = [
                    str(pdata.get("first_name", "")).strip(),
                    str(pdata.get("middle_name", "")).strip(),
                    str(pdata.get("last_name", "")).strip(),
                ]
                full = " ".join(part for part in parts if part)
                if not full:
                    continue
                name_by_patient_id[patient_id] = full
                linked_uid = pdata.get("account_uid") or ""
                if linked_uid and linked_uid not in name_by_account:
                    name_by_account[linked_uid] = full

            managed = None  # uid -> account data, built on first use
            direct_names = self.cache.get("unpaid_account_names")
            if direct_names is None:
                direct_names = {}
            direct_changed = False

            def account_name(account_uid):
                nonlocal managed, direct_changed
                if not account_uid:
                    return ""
                if managed is None:
                    managed = {uid: acc for uid, acc in self._get_manageable_accounts_cached()}
                acc = managed.get(account_uid)
                if acc is None:
                    if account_uid in direct_names:
                        return direct_names[account_uid]
                    try:
                        snap = (
                            self.db.collection(self.Customer_Account)
                            .document(account_uid)
                            .get()
                        )
                        acc = snap.to_dict() if snap.exists else {}
                    except Exception as e:
                        print("UNPAID NAME LOOKUP FAILED:", account_uid, e)
                        return ""
                    nm = (
                        f"{acc.get('firstname') or ''} {acc.get('lastname') or ''}".strip()
                        or str(acc.get("name") or "").strip()
                    )
                    direct_names[account_uid] = nm
                    direct_changed = True
                    return nm
                return (
                    f"{acc.get('firstname') or ''} {acc.get('lastname') or ''}".strip()
                    or str(acc.get("name") or "").strip()
                )

            rows = []
            total_balance = 0.0

            for data in self._agg_unpaid_docs():
                procs = data.get("procedures", [])
                if not isinstance(procs, list):
                    continue

                # Two places can say which account this record belongs to: the
                # uid saved inside the record, and the record's real location
                # in the database. They can disagree (e.g. records copied by a
                # patient merge keep the old uid), so try both.
                field_uid = str(data.get("uid") or "").strip()
                path_uid = str(data.get("_account_uid") or "").strip()
                uid_candidates = []
                for cand in (path_uid, field_uid):
                    if cand and cand not in uid_candidates:
                        uid_candidates.append(cand)
                account_uid = path_uid or field_uid
                patient_unq_id = str(data.get("Patient_unq_id") or "").strip()

                resolved_name = None  # same patient for every row of this record

                for p in procs:
                    if not isinstance(p, dict):
                        continue

                    balance = self.safe_float(p.get("balance", 0))
                    if balance <= 0:
                        continue

                    if resolved_name is None:
                        resolved_name = ""
                        for cand in uid_candidates:
                            resolved_name = account_name(cand) or name_by_account.get(cand) or ""
                            if resolved_name:
                                break
                        if not resolved_name:
                            resolved_name = name_by_patient_id.get(patient_unq_id) or ""
                        if not resolved_name:
                            print(
                                "UNPAID LIST: no name found. uid in record:", repr(field_uid),
                                "| record stored under account:", repr(path_uid),
                                "| Patient_unq_id:", repr(patient_unq_id),
                            )

                    rows.append({
                        "patient_name": resolved_name or "Unknown patient",
                        "uid": account_uid,
                        "patient_id": patient_unq_id,
                        "procedure": str(p.get("procedure", "") or ""),
                        "tooth": str(p.get("tooth", "") or ""),
                        "date": str(p.get("date", "") or "").strip(),
                        "dentist": str(p.get("dentist", "") or ""),
                        "value": round(self.safe_float(p.get("value", 0)), 2),
                        "paid": round(self.safe_float(p.get("paid", 0)), 2),
                        "balance": round(balance, 2),
                    })
                    total_balance += balance

            if direct_changed:
                self.cache.set("unpaid_account_names", direct_names, ttl_seconds=self.CACHE_TTL_SECONDS)

            rows.sort(key=lambda r: r["balance"], reverse=True)

            return jsonify({
                "success": True,
                "rows": rows,
                "total_balance": round(total_balance, 2),
            })

        except Exception as e:
            print("UNPAID PROCEDURES ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def _agg_admin_procedure_chart_data(self):
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
            done_docs = self._agg_procedure_docs(self._agg_load_all())
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
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

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
        self.app.route("/admin/assign_dentist", methods=["POST"])(self.admin_assign_dentist)
        self.app.route("/admin/patient_avatar", methods=["POST"])(self.admin_patient_avatar)
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
        self.app.route("/admin/block_range", methods=["POST"])(self.admin_block_range)
        self.app.route("/admin/unblock_range", methods=["POST"])(self.admin_unblock_range)
        self.app.route("/admin/mark_past_closed", methods=["POST"])(self.admin_mark_past_closed)
        self.app.route("/admin/closure_summary")(self.admin_closure_summary)
        self.app.route("/get_clinic_notices")(self.get_clinic_notices)
        self.app.route("/admin/day_schedule")(self.admin_day_schedule)
        self.app.route("/admin/reschedule_appointment", methods=["POST"])(self.admin_reschedule_appointment)
        self.app.route("/search_patients", methods=["POST"])(self.search_patients)
        self.app.route("/admin/update_patient", methods=["POST"])(self.update_patient)
        self.app.route("/admin/delete_patient", methods=["POST"])(self.delete_patient)
        self.app.route("/admin/toggle_user_block", methods=["POST"])(self.toggle_user_block)
        self.app.route("/admin/update_treatment_record", methods=["POST"])(self.update_treatment_record)
        self.app.route("/admin/delete_treatment_record", methods=["POST"])(self.delete_treatment_record)
        self.app.route("/admin/check_duplicate_patient", methods=["POST"])(self.check_duplicate_patient)
        self.app.route("/link_patient_account", methods=["POST"])(self.link_patient_account)
        self.app.route("/get_patient_profile_data")(self.get_patient_profile_data)
        self.app.route("/admin/merge_patients", methods=["POST"])(self.admin_merge_patients)
        self.app.route("/admin/financial_chart_data")(self.admin_financial_chart_data)
        self.app.route("/admin/unpaid_procedures")(self.admin_unpaid_procedures)
        self.app.route("/privacy-policy")(self.privacy_policy)
        self.app.route("/terms-of-service")(self.terms_of_service)
        self.app.route("/admin/procedure_chart_data")(self.admin_procedure_chart_data)
        self.app.route("/admin/aggregates/repair")(self.admin_aggregates_repair)
        self.app.route("/admin/aggregates/compare")(self.admin_aggregates_compare)
        self.app.route("/admin/aggregates/switch")(self.admin_aggregates_switch)




app_instance = DentalClinicApp()
app = app_instance.app

if __name__ == "__main__":
    print("🦷 Capizonda Dental Clinic Server Starting...")
    app.run(debug=False, port=5000, use_reloader=False)