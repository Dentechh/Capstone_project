"""
backfill_seed_has_history.py

One-off fix for test data seeded BEFORE seed_dummy_patients.py was updated
to stamp has_history. Sets has_history: True on every Customer_Account doc
tagged with the given seed_batch_id. Does not touch any other field.

WHERE TO PUT THIS FILE:
    Same folder as your dentech_key.json (same convention as main.py /
    seed_dummy_patients.py).

USAGE:
    python backfill_seed_has_history.py SEED_BATCH_ID
    python backfill_seed_has_history.py SEED_BATCH_ID --dry-run
"""

import os
import sys
import argparse

import firebase_admin
from firebase_admin import credentials, firestore

CUSTOMER_ACCOUNT = "Customer_Account"


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


def backfill(batch_id, dry_run=False):
    db = init_firebase()

    accounts = list(
        db.collection(CUSTOMER_ACCOUNT)
        .where("seed_batch_id", "==", batch_id)
        .stream()
    )

    if not accounts:
        print(f"No Customer_Account docs found with seed_batch_id = {batch_id}")
        print("Double-check the batch ID and try again.")
        return

    print(f"Found {len(accounts)} accounts tagged with seed_batch_id = {batch_id}")

    already_set = 0
    updated = 0

    for doc in accounts:
        data = doc.to_dict()
        if data.get("has_history") is True:
            already_set += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] would set has_history=True on {doc.id}")
        else:
            doc.reference.update({"has_history": True})
        updated += 1

    print("\nDone.")
    print(f"Already had has_history=True: {already_set}")
    print(f"{'Would update' if dry_run else 'Updated'}: {updated}")

    if dry_run:
        print("\n[DRY RUN] Nothing was written to Firestore.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill has_history=True on seeded Customer_Account docs."
    )
    parser.add_argument("batch_id", help="The seed_batch_id to backfill (e.g. seed_20260912_131230)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    args = parser.parse_args()

    backfill(args.batch_id, dry_run=args.dry_run)