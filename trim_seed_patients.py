"""
trim_seed_patients.py

Reduces the number of seeded dummy patients down to a target count,
to keep Firestore reads low during testing while still leaving enough
volume to exercise pagination, search, and Load More.

Only touches documents tagged with a seed_batch_id (from seed_dummy_patients.py),
so real patient accounts (e.g. Althea) are never affected.

Keeps the OLDEST `--keep` seeded patients (by created_at) and deletes the rest,
including their Customer_Account doc and all subcollections
(appointments, Approve, Done_procedure) — same cleanup pattern as
main.py's delete_patient().

USAGE:
    python trim_seed_patients.py --dry-run           # preview only
    python trim_seed_patients.py --keep 100          # actually delete, keep 100
"""

import os
import argparse

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

CUSTOMER_ACCOUNT = "Customer_Account"
DOC_PATIENTS = "Patients"


def init_firebase():
    basedir = os.path.abspath(os.path.dirname(__file__))
    key_path = os.path.join(basedir, "dentech_key.json")
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
    return firestore.client()


def trim(keep, dry_run=False):
    db = init_firebase()

    # Fetch ALL patients (no inequality filter — avoids the
    # "range filter on one field, order_by another field" restriction),
    # then filter/sort in Python. Cost is the same either way since we
    # need to read the whole collection regardless.
    all_docs = list(db.collection(DOC_PATIENTS).stream())

    seeded_docs = [
        d for d in all_docs
        if d.to_dict().get("seed_batch_id")
    ]

    seeded_docs.sort(key=lambda d: d.to_dict().get("created_at", ""))

    total = len(seeded_docs)
    print(f"Found {total} seeded patients total.")

    if total <= keep:
        print(f"Nothing to trim — {total} is already <= --keep {keep}.")
        return

    to_delete = seeded_docs[keep:]
    print(f"Will keep the oldest {keep}, delete {len(to_delete)}.")

    deleted_patients = 0
    deleted_accounts = 0

    for patient_doc in to_delete:
        patient_data = patient_doc.to_dict()
        account_uid = patient_data.get("account_uid") or ""
        name = f"{patient_data.get('first_name','')} {patient_data.get('last_name','')}"

        if dry_run:
            print(f"[DRY RUN] Would delete: {patient_doc.id} ({name}) -> account {account_uid}")
            continue

        if account_uid:
            account_ref = db.collection(CUSTOMER_ACCOUNT).document(account_uid)
            if account_ref.get().exists:
                for sub_name in ("appointments", "Approve", "Done_procedure"):
                    for sub_doc in account_ref.collection(sub_name).stream():
                        sub_doc.reference.delete()
                account_ref.delete()
                deleted_accounts += 1

        patient_doc.reference.delete()
        deleted_patients += 1

        if deleted_patients % 100 == 0:
            print(f"  ...{deleted_patients}/{len(to_delete)} deleted")

    print(f"\nDone. Deleted {deleted_patients} Patients docs and {deleted_accounts} Customer_Account docs.")
    print(f"Remaining seeded patients: {keep}")

    if dry_run:
        print("\n[DRY RUN] Nothing was actually deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trim seeded dummy patients down to a target count.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    parser.add_argument("--keep", type=int, default=100, help="How many seeded patients to keep (default 100)")
    args = parser.parse_args()

    trim(keep=args.keep, dry_run=args.dry_run)