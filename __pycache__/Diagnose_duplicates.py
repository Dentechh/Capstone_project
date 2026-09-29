# diagnose_duplicates.py
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("dentech_key.json")
firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
db = firestore.client()

def inspect(name_contains):
    for doc in db.collection("Patients").stream():
        data = doc.to_dict()
        full = f"{data.get('first_name','')} {data.get('middle_name','')} {data.get('last_name','')}".lower()
        if name_contains.lower() not in full:
            continue

        account_uid = data.get("account_uid") or "(none)"
        print(f"\nPatient ID: {doc.id}")
        print(f"  Name: {data.get('first_name')} {data.get('middle_name')} {data.get('last_name')}")
        print(f"  account_uid: {account_uid}")

        if account_uid != "(none)":
            acct = db.collection("Customer_Account").document(account_uid).get()
            if acct.exists:
                a = acct.to_dict()
                print(f"  account provider: {a.get('provider')}, email: {a.get('email')}")
            for sub in ("appointments", "Approve", "Done_procedure"):
                n = len(list(db.collection("Customer_Account").document(account_uid).collection(sub).stream()))
                print(f"  {sub}: {n} doc(s)")

inspect("roa")