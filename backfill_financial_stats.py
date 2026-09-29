"""
backfill_financial_stats.py

One-time initialization of Stats/financial_summary from a full scan of
every existing Done_procedure doc. Run this ONCE, after applying the
Step 2 code changes to main.py and BEFORE relying on the cached totals
in adminDashboard(). After this runs, main.py's incremental updates
(save_dental_record / update_treatment_record / update_payment_status)
keep the doc correct going forward without further full scans.

Safe to re-run: it OVERWRITES the doc with a fresh full-scan total each
time (not an increment), so re-running just recomputes ground truth.

WHERE TO PUT THIS FILE:
    Same folder as your dentech_key.json.

USAGE:
    python backfill_financial_stats.py
    python backfill_financial_stats.py --dry-run
"""

import os
import argparse

import firebase_admin
from firebase_admin import credentials, firestore


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


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def backfill(dry_run=False):
    db = init_firebase()

    total_income = 0.0
    total_outstanding = 0.0
    unpaid_procedures = 0
    doc_count = 0
    procedure_count = 0

    done_docs = db.collection_group("Done_procedure").stream()

    for doc in done_docs:
        doc_count += 1
        data = doc.to_dict()
        for p in data.get("procedures", []):
            procedure_count += 1
            paid = safe_float(p.get("paid", 0))
            balance = safe_float(p.get("balance", 0))
            total_income += paid
            total_outstanding += balance
            if balance > 0:
                unpaid_procedures += 1

    print(f"Scanned {doc_count} Done_procedure docs, {procedure_count} procedures total.")
    print(f"total_income:       {total_income:.2f}")
    print(f"total_outstanding:  {total_outstanding:.2f}")
    print(f"unpaid_procedures:  {unpaid_procedures}")

    if dry_run:
        print("\n[DRY RUN] Nothing was written to Firestore.")
        return

    db.collection("Stats").document("financial_summary").set({
        "total_income": round(total_income, 2),
        "total_outstanding": round(total_outstanding, 2),
        "unpaid_procedures": unpaid_procedures,
    })

    print("\nStats/financial_summary written successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="One-time backfill of Stats/financial_summary from a full Done_procedure scan."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    args = parser.parse_args()

    backfill(dry_run=args.dry_run)