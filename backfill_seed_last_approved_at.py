"""
backfill_seed_last_approved_at.py

One-time fix for accounts created by seed_dummy_patients.py before the
last_approved_at bug was found. Those accounts have has_history=True but
are missing last_approved_at, so Firestore's order_by silently excludes
them from "My Patients".

Only touches accounts that HAVE a seed_batch_id (i.e., seeded data),
so real patient accounts are never touched.

USAGE:
    python backfill_seed_last_approved_at.py --dry-run
    python backfill_seed_last_approved_at.py
"""

import os
import argparse
from datetime import datetime, UTC

import firebase_admin
from firebase_admin import credentials, firestore

CUSTOMER_ACCOUNT = "Customer_Account"


def init_firebase():
    basedir = os.path.abspath(os.path.dirname(__file__))
    key_path = os.path.join(basedir, "dentech_key.json")
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
    return firestore.client()


def backfill(dry_run=False):
    db = init_firebase()

    # Only accounts tagged as seeded, missing last_approved_at.
    # Firestore has no "field does not exist" filter, so we fetch all
    # seeded accounts and check in Python.
    accounts = (
        db.collection(CUSTOMER_ACCOUNT)
        .where("seed_batch_id", "!=", "")
        .stream()
    )

    fixed = 0
    skipped = 0

    for doc in accounts:
        data = doc.to_dict()

        if "last_approved_at" in data and data["last_approved_at"]:
            skipped += 1
            continue

        if dry_run:
            print(f"[DRY RUN] Would fix: {doc.id} ({data.get('firstname','')} {data.get('lastname','')})")
            fixed += 1
            continue

        doc.reference.update({
            "last_approved_at": data.get("created_at") or datetime.now(UTC).isoformat()
        })
        fixed += 1

    print(f"\nDone. Fixed: {fixed}, already OK / skipped: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)