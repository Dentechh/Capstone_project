"""
seed_dummy_patients.py

Seeds the Capizonda Dental Firestore database with 100 fake patients,
each with 1-2 completed procedures (Done_procedure), dated across the
last 30 days, with a mix of Paid / Not Paid statuses.

WHERE TO PUT THIS FILE:
    Same folder as your dentech_key.json (same convention main.py uses).

INSTALL:
    pip install firebase-admin

USAGE:
    python seed_dummy_patients.py              # seed 100 fake patients
    python seed_dummy_patients.py --dry-run    # preview only, writes nothing
    python seed_dummy_patients.py --wipe SEED_BATCH_ID
                                                # delete everything from one seed run

Every run prints a "seed batch ID" at the end (e.g. seed_20260912_101530).
Save that ID if you want to cleanly remove just that batch later via --wipe,
without touching your real patient data.
"""

import os
import random
import uuid
import argparse
from datetime import datetime, timedelta, UTC

import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------
# CONFIG - matches the collection names used in main.py
# ---------------------------------------------------------------

CUSTOMER_ACCOUNT = "Customer_Account"
DOC_PATIENTS = "Patients"
COUNTERS = "Counters"

SEED_BATCH_ID = "seed_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

NUM_PATIENTS = 100
DAYS_SPREAD = 30  # spread procedure dates across the last 30 days

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
# (CI_PROCEDURE_OPTIONS / td-procedure select), with realistic price ranges.
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


def init_firebase():
    basedir = os.path.abspath(os.path.dirname(__file__))
    key_path = os.path.join(basedir, "dentech_key.json")
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"dentech_key.json not found at {key_path}. "
            "Put this script in the same folder as your Firebase service account key."
        )
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
    return firestore.client()


def normalize(value):
    return " ".join(str(value or "").strip().lower().split())


def generate_patient_id(db):
    """Same permanent Patient ID scheme as main.py's generate_patient_id()."""
    counter_ref = db.collection(COUNTERS).document("patients")

    @firestore.transactional
    def update_counter(transaction):
        snapshot = counter_ref.get(transaction=transaction)
        last_number = snapshot.to_dict().get("last_number", 0) if snapshot.exists else 0
        new_number = last_number + 1
        transaction.set(counter_ref, {"last_number": new_number}, merge=True)
        return new_number

    transaction = db.transaction()
    return f"P-{update_counter(transaction):06d}"


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


def seed(dry_run=False, count=NUM_PATIENTS):
    db = init_firebase()
    print(f"Seed batch ID: {SEED_BATCH_ID}")
    print(f"Creating {count} fake patients...")

    created_summary = []

    for i in range(count):
        first = random.choice(FIRST_NAMES)
        middle = random.choice(MIDDLE_NAMES)
        last = random.choice(LAST_NAMES)
        birth_year = random.randint(1955, 2015)
        birthday = f"{birth_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"

        account_uid = f"walkin_{uuid.uuid4().hex[:12]}"
        patient_id = f"DRYRUN-{i + 1:03d}" if dry_run else generate_patient_id(db)

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
            "created_at": datetime.now(UTC).isoformat(),
        }

        account_doc = {
            "uid": account_uid,
            "firstname": first,
            "middlename": middle,
            "lastname": last,
            "email": "",
            "contact_number": f"09{random.randint(100000000, 999999999)}",
            "provider": "walk_in",
            "created_by_admin": True,
            "seed_batch_id": SEED_BATCH_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "has_history": True,
            "last_approved_at": datetime.now(UTC).isoformat(),
        }

        num_procs = random.randint(1, 2)
        procedures = [build_procedure(random_visit_datetime(DAYS_SPREAD)) for _ in range(num_procs)]

        if dry_run:
            created_summary.append((patient_id, f"{first} {last}", num_procs))
            continue

        db.collection(DOC_PATIENTS).document(patient_id).set(patient_doc)

        account_ref = db.collection(CUSTOMER_ACCOUNT).document(account_uid)
        account_ref.set(account_doc)

        account_ref.collection("Done_procedure").add({
            "uid": account_uid,
            "Patient_unq_id": patient_id,
            "chart": {},
            "chart_image": "",
            "procedures": procedures,
            "seed_batch_id": SEED_BATCH_ID,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

        created_summary.append((patient_id, f"{first} {last}", num_procs))

        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{count} patients created")

    print("\nDone.")
    print(f"Total patients created: {len(created_summary)}")
    print(f"Seed batch ID (save this to wipe later): {SEED_BATCH_ID}")

    if dry_run:
        print("\n[DRY RUN] Nothing was written to Firestore.")


def wipe(batch_id):
    """Deletes everything created by one seed run, identified by seed_batch_id."""
    db = init_firebase()
    print(f"Wiping all data tagged with seed_batch_id = {batch_id} ...")

    deleted_patients = 0
    for p in db.collection(DOC_PATIENTS).where("seed_batch_id", "==", batch_id).stream():
        p.reference.delete()
        deleted_patients += 1

    deleted_accounts = 0
    for a in db.collection(CUSTOMER_ACCOUNT).where("seed_batch_id", "==", batch_id).stream():
        # Subcollections don't auto-delete with the parent doc in Firestore.
        for sub_name in ("appointments", "Approve", "Done_procedure"):
            for sub_doc in a.reference.collection(sub_name).stream():
                sub_doc.reference.delete()
        a.reference.delete()
        deleted_accounts += 1

    print(
        f"Deleted {deleted_patients} Patients docs and "
        f"{deleted_accounts} Customer_Account docs (with subcollections)."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dummy dental patient data into Firestore.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    parser.add_argument("--count", type=int, default=NUM_PATIENTS, help="Number of fake patients to create")
    parser.add_argument(
        "--wipe",
        metavar="SEED_BATCH_ID",
        help="Delete all data created by a given seed batch ID (printed at the end of a seed run)",
    )
    args = parser.parse_args()

    if args.wipe:
        wipe(args.wipe)
    else:
        seed(dry_run=args.dry_run, count=args.count)