"""
seed_dummy_patients.py  (v2)

Seeds the Capizonda Dental Firestore database with fake patients, each with
1-2 completed procedures (Done_procedure) dated across the last N days, with
a mix of Paid / Not Paid statuses.

WHERE TO PUT THIS FILE:
    Same folder as your dentech_key.json (same convention main.py uses).

INSTALL:
    pip install firebase-admin

USAGE:
    python seed_dummy_patients.py --dry-run --count 800   # preview, no connection
    python seed_dummy_patients.py --count 5               # small real test run
    python seed_dummy_patients.py --count 800             # the big run
    python seed_dummy_patients.py --count 800 --days 90   # spread over 90 days
    python seed_dummy_patients.py --wipe SEED_BATCH_ID    # remove one seed run

WHAT'S NEW IN v2:
  * Updates Stats/financial_summary, the document your dashboard reads for
    Total Income / Outstanding / Unpaid. v1 skipped it, so seeded data would
    not have shown up in those totals.
  * Records each run's totals in SeedBatches/<batch id>, so --wipe can
    subtract exactly what the run added.
  * Writes in bulk (about 100 patients per commit) instead of one at a time.
  * Every patient gets a unique, realistic last_approved_at. Your "My
    Patients" list pages by that field, and identical values would break
    paging.
  * Uses the project inside dentech_key.json, prints it, and asks you to
    confirm. If the project does not look like dev/test, you must type the
    project ID to continue (--yes does not skip that).
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud import firestore as gcf
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:  # allows --dry-run without firebase-admin installed
    firebase_admin = None
    credentials = None
    firestore = None
    gcf = None
    FieldFilter = None

# ---------------------------------------------------------------
# CONFIG - matches the collection names used in main.py
# ---------------------------------------------------------------

CUSTOMER_ACCOUNT = "Customer_Account"
DOC_PATIENTS = "Patients"
COUNTERS = "Counters"
STATS_COLLECTION = "Stats"
STATS_DOC = "financial_summary"
SEED_BATCHES = "SeedBatches"

SEED_BATCH_ID = "seed_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

NUM_PATIENTS = 50
DAYS_SPREAD = 30
CHUNK_PATIENTS = 100  # 3 writes per patient + 2 stats writes = 302 per commit (limit 500)

FIRST_NAMES = [
    "Juan", "Maria", "Jose", "Ana", "Pedro", "Carmen", "Antonio", "Rosa",
    "Manuel", "Teresa", "Francisco", "Cristina", "Ricardo", "Angela",
    "Eduardo", "Patricia", "Roberto", "Karen", "Miguel", "Grace",
    "Carlos", "Joy", "Rafael", "Michelle", "Daniel", "Jenny", "Andres",
    "Kristine", "Fernando", "Bea", "Marco", "Alyssa", "Paolo", "Nicole",
    "Gabriel", "Camille", "Vincent", "Danica", "Emmanuel", "Trisha",
    "Renato", "Divine", "Arnel", "Charmaine", "Bernard", "Cherry",
    "Nelson", "Josephine", "Alvin", "Marilou",
]

LAST_NAMES = [
    "Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Garcia", "Mendoza",
    "Torres", "Flores", "Ramos", "Villanueva", "Castillo", "Del Rosario",
    "Gonzales", "Aquino", "Fernandez", "Rivera", "Salazar", "Navarro",
    "Domingo", "Pascual", "Valdez", "Marquez", "Ignacio", "Bernardo",
    "Manalo", "Alvarez", "Roa", "Dela Cruz", "Tan", "Lim", "Sy",
    "Gomez", "Diaz", "Morales", "Soriano", "Concepcion", "Aguilar",
    "Espiritu", "Mercado",
]

MIDDLE_NAMES = ["Dela", "Santos", "Reyes", "Garcia", "Cruz", "Bautista", "Ramos", ""]

DENTIST_NAMES = [
    "Dr. Julix Dionne Capizonda",
    "Dr. Anna Villareal",
    "Dr. Marco Suarez",
    "Dr. Bianca Fuentes",
]

MEDICINES = ["Mefenamic Acid", "Tranexamic Acid", "Amoxicillin", "Co- amoxiclav", ""]

# Matches the procedure dropdown options used in admin_dashboard.html
SERVICE_PRICES = {
    "Dental Consultation": (300, 300),
    "Oral Prophylaxis (Cleaning)": (800, 2000),
    "Tooth Restoration (Pasta)": (800, 1500),
    "Tooth Extraction (Gabot)": (800, 1500),
    "Dentures (Pustiso)": (5000, 15000),
    "Crowns and Bridges": (8000, 15000),
    "Teeth Whitening": (3000, 6000),
    "Fluoride Treatment": (500, 1000),
    "Pit and Fissure Sealant": (500, 1000),
    "Wisdom Teeth Removal": (3000, 8000),
    "Root Canal Treatment": (5000, 12000),
    "Periapical Xray": (300, 600),
}

TOOTH_NUMBERS = [
    str(n)
    for n in list(range(11, 19)) + list(range(21, 29)) + list(range(31, 39)) + list(range(41, 49))
]


# ---------------------------------------------------------------
# FIREBASE SETUP
# ---------------------------------------------------------------

def read_key_project_id():
    """Reads project_id from dentech_key.json without touching the network."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    key_path = os.path.join(basedir, "dentech_key.json")
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"dentech_key.json not found at {key_path}. "
            "Put this script in the same folder as your Firebase service account key."
        )
    with open(key_path, "r", encoding="utf-8") as f:
        key_data = json.load(f)
    return key_path, key_data.get("project_id", "")


def init_firebase(project_id, key_path):
    if firebase_admin is None:
        raise SystemExit("firebase-admin is not installed. Run: pip install firebase-admin")
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {"projectId": project_id})
    return firestore.client()


def preflight_check(db, project_id):
    """Fails fast (about 20s) with a clear message instead of hanging."""
    try:
        db.collection(COUNTERS).document("patients").get(timeout=20)
    except Exception as e:
        print("\nCould not connect to Firestore.")
        print(f"  Project: {project_id}")
        print(f"  Error:   {e}\n")
        text = str(e)
        if "Invalid JWT" in text or "invalid_grant" in text:
            print("The key in dentech_key.json was rejected by Google.")
            print("It was probably deleted or disabled. Generate a new key in")
            print("Firebase Console > Project settings > Service accounts.")
        elif "PermissionDenied" in text or "403" in text:
            print("The service account has no permission on this project.")
        elif "NotFound" in text or "404" in text:
            print("Firestore may not be created yet. In Firebase Console open")
            print("Build > Firestore Database and create the database first.")
        sys.exit(1)


def confirm_target(project_id, action, assume_yes):
    looks_like_dev = any(w in project_id.lower() for w in ("dev", "test", "staging"))
    print(f"\nTarget Firebase project: {project_id}")

    if not looks_like_dev:
        print("WARNING: this project does not look like a dev/test project.")
        typed = input(f"Type the project ID ({project_id}) to {action}: ").strip()
        if typed != project_id:
            print("Cancelled. Nothing was changed.")
            sys.exit(0)
        return

    if assume_yes:
        return

    answer = input(f"Type 'yes' to {action} in this project: ").strip().lower()
    if answer != "yes":
        print("Cancelled. Nothing was changed.")
        sys.exit(0)


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------

def normalize(value):
    return " ".join(str(value or "").strip().lower().split())


def reserve_patient_ids(db, count):
    """
    Reserves `count` permanent Patient IDs in ONE transaction, using the same
    Counters/patients document and P-000123 format as main.py.
    """
    counter_ref = db.collection(COUNTERS).document("patients")

    @firestore.transactional
    def reserve(transaction):
        snapshot = counter_ref.get(transaction=transaction)
        last_number = snapshot.to_dict().get("last_number", 0) if snapshot.exists else 0
        transaction.set(counter_ref, {"last_number": last_number + count}, merge=True)
        return last_number

    last = reserve(db.transaction())
    return [f"P-{n:06d}" for n in range(last + 1, last + count + 1)]


def random_visit_datetime(days_back):
    delta_days = random.randint(0, days_back)
    return datetime.now(UTC) - timedelta(days=delta_days)


def build_procedure(visit_dt):
    service_name = random.choice(list(SERVICE_PRICES.keys()))
    lo, hi = SERVICE_PRICES[service_name]
    value = round(random.uniform(lo, hi), 2)

    is_paid = random.random() < 0.6  # ~60% fully paid, ~40% not paid

    if is_paid:
        paid = value
        balance = 0.0
        status = "Paid"
    else:
        paid = round(random.uniform(0, value * 0.7), 2)
        balance = round(value - paid, 2)
        status = "Not Paid"

    next_appointment = ""
    if random.random() < 0.5:
        next_appt_dt = visit_dt + timedelta(days=random.randint(7, 60))
        next_appointment = next_appt_dt.strftime("%Y-%m-%d")

    return {
        "date": visit_dt.strftime("%Y-%m-%d"),
        "tooth": random.choice(TOOTH_NUMBERS),
        "procedure": service_name,
        "dentist": random.choice(DENTIST_NAMES),
        "value": value,
        "paid": paid,
        "balance": balance,
        "next_appointment": next_appointment,
        "medicine": random.choice(MEDICINES),
        "status": status,
    }


def stat_increments(income, outstanding, unpaid):
    """Same fields main.py increments whenever a treatment is saved or paid."""
    return {
        "total_income": gcf.Increment(round(income, 2)),
        "total_outstanding": gcf.Increment(round(outstanding, 2)),
        "unpaid_procedures": gcf.Increment(unpaid),
    }


# ---------------------------------------------------------------
# SEED
# ---------------------------------------------------------------

def seed(dry_run=False, count=NUM_PATIENTS, days=DAYS_SPREAD, assume_yes=False):
    key_path, project_id = read_key_project_id()
    print(f"Seed batch ID: {SEED_BATCH_ID}")
    print(f"Key file project: {project_id}")

    db = None
    stats_ref = None
    seed_ref = None
    patient_ids = [f"DRYRUN-{i + 1:03d}" for i in range(count)]

    if not dry_run:
        confirm_target(project_id, f"write {count} fake patients", assume_yes)
        db = init_firebase(project_id, key_path)
        preflight_check(db, project_id)
        patient_ids = reserve_patient_ids(db, count)
        stats_ref = db.collection(STATS_COLLECTION).document(STATS_DOC)
        seed_ref = db.collection(SEED_BATCHES).document(SEED_BATCH_ID)

    print(f"Creating {count} fake patients spread over the last {days} days...")
    started = time.time()

    run_income = run_outstanding = 0.0
    run_unpaid = run_procs = 0

    batch = db.batch() if db else None
    chunk_income = chunk_outstanding = 0.0
    chunk_unpaid = chunk_patients = 0

    def commit_chunk():
        nonlocal batch, chunk_income, chunk_outstanding, chunk_unpaid, chunk_patients
        if dry_run or chunk_patients == 0:
            return
        inc = stat_increments(chunk_income, chunk_outstanding, chunk_unpaid)
        # Same increments the app applies on every save, so dashboard totals
        # include the seeded data.
        batch.set(stats_ref, inc, merge=True)
        # Per-run record so --wipe can subtract exactly this run's totals.
        batch.set(seed_ref, {
            "seed_batch_id": SEED_BATCH_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "patients": gcf.Increment(chunk_patients),
            **inc,
        }, merge=True)
        batch.commit()
        batch = db.batch()
        chunk_income = chunk_outstanding = 0.0
        chunk_unpaid = chunk_patients = 0

    for i in range(count):
        first = random.choice(FIRST_NAMES)
        middle = random.choice(MIDDLE_NAMES)
        last = random.choice(LAST_NAMES)
        birth_year = random.randint(1955, 2015)
        birthday = f"{birth_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"

        account_uid = f"walkin_{uuid.uuid4().hex[:12]}"
        patient_id = patient_ids[i]
        now_iso = datetime.now(UTC).isoformat()

        num_procs = random.randint(1, 2)
        visit_dts = [random_visit_datetime(days) for _ in range(num_procs)]
        procedures = [build_procedure(dt) for dt in visit_dts]

        # Unique per patient (microsecond offset by index): "My Patients" pages
        # by this field, so duplicates would skip or repeat rows.
        last_approved_at = (max(visit_dts) + timedelta(microseconds=i)).isoformat()

        patient_doc = {
            "patient_id": patient_id,
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "first_name_normalized": normalize(first),
            "middle_name_normalized": normalize(middle),
            "last_name_normalized": normalize(last),
            "birthday": birthday,
            "account_uid": account_uid,
            "created_by": "seed_script",
            "seed_batch_id": SEED_BATCH_ID,
            "created_at": now_iso,
        }

        account_doc = {
            "uid": account_uid,
            "firstname": first,
            "middlename": middle,
            "last_sex": random.choice(["Male", "Female"]),
            "CivilStatus": random.choice(["Single", "Married"]),
            "lastname": last,
            "email": "",
            "contact_number": f"09{random.randint(100000000, 999999999)}",
            "provider": "walk_in",
            "created_by_admin": True,
            "seed_batch_id": SEED_BATCH_ID,
            "created_at": now_iso,
            "has_history": True,
            "last_approved_at": last_approved_at,
        }

        p_income = sum(p["paid"] for p in procedures)
        p_outstanding = sum(p["balance"] for p in procedures)
        p_unpaid = sum(1 for p in procedures if p["balance"] > 0)

        run_income += p_income
        run_outstanding += p_outstanding
        run_unpaid += p_unpaid
        run_procs += num_procs

        if not dry_run:
            batch.set(db.collection(DOC_PATIENTS).document(patient_id), patient_doc)

            account_ref = db.collection(CUSTOMER_ACCOUNT).document(account_uid)
            batch.set(account_ref, account_doc)

            batch.set(account_ref.collection("Done_procedure").document(), {
                "uid": account_uid,
                "Patient_unq_id": patient_id,
                "chart": {},
                "chart_image": "",
                "has_unpaid": any(p["balance"] > 0 for p in procedures),
                "procedures": procedures,
                "seed_batch_id": SEED_BATCH_ID,
                "updated_at": gcf.SERVER_TIMESTAMP,
            })

            chunk_income += p_income
            chunk_outstanding += p_outstanding
            chunk_unpaid += p_unpaid
            chunk_patients += 1

            if chunk_patients >= CHUNK_PATIENTS:
                commit_chunk()

        if (i + 1) % 100 == 0 or i + 1 == count:
            print(f"  ...{i + 1}/{count} patients prepared" + ("" if dry_run else " / written"))

    commit_chunk()  # remaining patients

    elapsed = time.time() - started
    print("\nDone.")
    print(f"Patients: {count}   Procedures: {run_procs}   Time: {elapsed:.1f}s")
    print(f"Totals this run  ->  income: {run_income:,.2f}   "
          f"outstanding: {run_outstanding:,.2f}   unpaid procedures: {run_unpaid}")
    print(f"Seed batch ID (save this to wipe later): {SEED_BATCH_ID}")

    if dry_run:
        print("\n[DRY RUN] Nothing was written to Firestore.")
    else:
        print("\nRestart Flask so its in-memory caches pick up the new data.")


# ---------------------------------------------------------------
# WIPE
# ---------------------------------------------------------------

class BatchDeleter:
    """Deletes documents in bulk (400 per commit) instead of one at a time."""

    def __init__(self, db, limit=400):
        self.db = db
        self.limit = limit
        self.batch = db.batch()
        self.pending = 0
        self.total = 0

    def delete(self, ref):
        self.batch.delete(ref)
        self.pending += 1
        self.total += 1
        if self.pending >= self.limit:
            self.flush()

    def flush(self):
        if self.pending:
            self.batch.commit()
            self.batch = self.db.batch()
            self.pending = 0


def wipe(batch_id, assume_yes=False):
    """Deletes everything created by one seed run and reverses its stats."""
    key_path, project_id = read_key_project_id()
    confirm_target(project_id, f"DELETE all data tagged {batch_id}", assume_yes)
    db = init_firebase(project_id, key_path)
    preflight_check(db, project_id)
    print(f"Wiping all data tagged with seed_batch_id = {batch_id} ...")

    deleter = BatchDeleter(db)

    patients = 0
    patient_query = db.collection(DOC_PATIENTS).where(filter=FieldFilter("seed_batch_id", "==", batch_id))
    for p in patient_query.stream():
        deleter.delete(p.reference)
        patients += 1
    deleter.flush()

    accounts = 0
    account_query = db.collection(CUSTOMER_ACCOUNT).where(filter=FieldFilter("seed_batch_id", "==", batch_id))
    for a in account_query.stream():
        # Subcollections don't auto-delete with the parent doc in Firestore.
        for sub_name in ("appointments", "Approve", "Done_procedure"):
            for sub_doc in a.reference.collection(sub_name).stream():
                deleter.delete(sub_doc.reference)
        deleter.delete(a.reference)
        accounts += 1
    deleter.flush()

    print(f"Deleted {patients} Patients docs and {accounts} Customer_Account docs "
          f"(with subcollections). Total documents removed: {deleter.total}")

    # Reverse the dashboard totals this run added.
    seed_ref = db.collection(SEED_BATCHES).document(batch_id)
    seed_doc = seed_ref.get()
    if seed_doc.exists:
        d = seed_doc.to_dict() or {}
        db.collection(STATS_COLLECTION).document(STATS_DOC).set(
            stat_increments(
                -float(d.get("total_income", 0)),
                -float(d.get("total_outstanding", 0)),
                -int(d.get("unpaid_procedures", 0)),
            ),
            merge=True,
        )
        seed_ref.delete()
        print("Dashboard financial totals reversed for this run.")
    else:
        print("No totals record found for this batch (it was seeded with the older script).")
        print("Dashboard financial totals were NOT adjusted.")

    print("Note: the Patient ID counter is not rolled back, so new real patients")
    print("will continue numbering after the seeded IDs.")
    print("Restart Flask so its in-memory caches drop the removed data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dummy dental patient data into Firestore.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without connecting to Firestore")
    parser.add_argument("--count", type=int, default=NUM_PATIENTS, help="Number of fake patients to create")
    parser.add_argument("--days", type=int, default=DAYS_SPREAD, help="Spread procedure dates over the last N days")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt (dev/test projects only)")
    parser.add_argument(
        "--wipe",
        metavar="SEED_BATCH_ID",
        help="Delete all data created by a given seed batch ID (printed at the end of a seed run)",
    )
    args = parser.parse_args()

    if args.count < 1 or args.days < 1:
        parser.error("--count and --days must be at least 1")

    if args.wipe:
        wipe(args.wipe, assume_yes=args.yes)
    else:
        seed(dry_run=args.dry_run, count=args.count, days=args.days, assume_yes=args.yes)