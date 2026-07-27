from app.models.user import User
from app.models.appointment import Appointment
from app.utils.firebase import get_db
from firebase_admin import auth as firebase_auth
import bleach
from werkzeug.security import generate_password_hash, check_password_hash


class UserRepository:
    MANUAL_COLLECTION = "manual_create_account"
    GOOGLE_COLLECTION = "google_create_account"

    def __init__(self, db):
        self.db = db

    def find_by_email(self, email: str) -> User | None:
        email = bleach.clean(email.strip())
        query = self.db.collection(self.MANUAL_COLLECTION).where("email", "==", email).get()
        if query:
            data = query[0].to_dict()
            data["uid"] = query[0].id
            return User.from_dict(data)
        return None

    def find_by_uid(self, uid: str) -> User | None:
        doc = self.db.collection(self.MANUAL_COLLECTION).document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            data["uid"] = doc.id
            return User.from_dict(data)
        return None

    def find_google_by_email(self, email: str) -> User | None:
        query = self.db.collection(self.GOOGLE_COLLECTION).where("email", "==", email).get()
        if query:
            data = query[0].to_dict()
            data["uid"] = query[0].id
            return User.from_dict(data)
        return None

    def find_google_by_uid(self, uid: str) -> User | None:
        doc = self.db.collection(self.GOOGLE_COLLECTION).document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            data["uid"] = doc.id
            return User.from_dict(data)
        return None

    def create_manual(self, user: User) -> bool:
        firebase_user = firebase_auth.get_user_by_email(user.email)
        uid = firebase_user.uid
        doc_ref = self.db.collection(self.MANUAL_COLLECTION).document(uid)
        if doc_ref.get().exists:
            return False
        user.uid = uid
        data = user.to_dict()
        data["password"] = generate_password_hash(data.get("password_hash", "")) if user.password_hash else ""
        data.pop("password_hash", None)
        doc_ref.set(data)
        return True

    def create_google(self, user: User) -> None:
        self.db.collection(self.GOOGLE_COLLECTION).document(user.uid).set(
            {
                "uid": user.uid,
                "email": user.email,
                "name": user.name,
                "provider": "google",
                "last_login": user.created_at,
            },
            merge=True,
        )

    def get_collection_for_uid(self, uid: str) -> str | None:
        if self.db.collection(self.GOOGLE_COLLECTION).document(uid).get().exists:
            return self.GOOGLE_COLLECTION
        if self.db.collection(self.MANUAL_COLLECTION).document(uid).get().exists:
            return self.MANUAL_COLLECTION
        return None

    def get_all_accounts(self) -> list[dict]:
        accounts = []
        for collection_name in [self.GOOGLE_COLLECTION, self.MANUAL_COLLECTION]:
            for doc in self.db.collection(collection_name).stream():
                data = doc.to_dict()
                data["uid"] = doc.id
                data["account_type"] = "Google" if collection_name == self.GOOGLE_COLLECTION else "Manual"
                first = data.get("firstname") or data.get("first_name") or ""
                last = data.get("lastname") or data.get("last_name") or ""
                data["first_name"] = first
                data["last_name"] = last
                data["full_name"] = data.get("name") or f"{first} {last}".strip()
                accounts.append(data)
        return accounts
