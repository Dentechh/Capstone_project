# check_althea_patients.py
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("dentech_key.json")
firebase_admin.initialize_app(cred, {"projectId": "dentech-c2ee0"})
db = firestore.client()

TARGET_UID = "102241580757593650898"

print("=== Patients docs matching 'roa' ===")
for doc in db.collection("Patients").stream():
    data = doc.to_dict()
    full = f"{data.get('first_name','')} {data.get('middle_name','')} {data.get('last_name','')}".lower()
    if "roa" in full:
        print(f"\nPatient ID: {doc.id}")
        print(f"  Name: {data.get('first_name')} {data.get('middle_name')} {data.get('last_name')}")
        print(f"  account_uid: {data.get('account_uid')}")

print("\n=== Confirming target account still has the merged data ===")
target_ref = db.collection("Customer_Account").document(TARGET_UID)
for sub in ("appointments", "Approve", "Done_procedure"):
    docs = list(target_ref.collection(sub).stream())
    print(f"{sub}: {len(docs)} doc(s)")