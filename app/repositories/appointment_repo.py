from app.models.appointment import Appointment
from app.models.approve import Approve
from app.repositories.user_repo import UserRepository


class AppointmentRepository:
    APPOINTMENT_COLLECTION = "appointments"
    APPROVE_COLLECTION = "Approve"

    def __init__(self, db, user_repo: UserRepository):
        self.db = db
        self.user_repo = user_repo

    def add_appointment(self, user_uid: str, appointment: Appointment) -> str | None:
        try:
            collection = self.user_repo.get_collection_for_uid(user_uid)
            if not collection:
                return None
            doc_ref = self.db.collection(collection).document(user_uid).collection(self.APPOINTMENT_COLLECTION).add(appointment.to_dict())
            return doc_ref[1].id
        except Exception as e:
            print(f"Error adding appointment: {e}")
            return None

    def get_pending_appointments(self) -> list[dict]:
        docs = self.db.collection_group(self.APPOINTMENT_COLLECTION).get()
        appointment_list = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["user_uid"] = doc.reference.parent.parent.id
            data["source"] = "appointment"
            appointment_list.append(data)
        return appointment_list

    def get_approvals(self) -> list[dict]:
        docs = self.db.collection_group(self.APPROVE_COLLECTION).get()
        approve_list = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["appointment_id"] = doc.reference.parent.parent.id
            data["user_uid"] = doc.reference.parent.parent.parent.id
            data["source"] = "approve"
            approve_list.append(data)
        return approve_list

    def move_to_approve(self, user_uid: str, appointment_id: str, approve: Approve) -> bool:
        try:
            user_collection = self.user_repo.get_collection_for_uid(user_uid)
            if not user_collection:
                return False
            user_ref = self.db.collection(user_collection).document(user_uid)
            approve_ref = user_ref.collection(self.APPROVE_COLLECTION).document(appointment_id)
            appt_ref = user_ref.collection(self.APPOINTMENT_COLLECTION).document(appointment_id)
            batch = self.db.batch()
            batch.set(approve_ref, approve.to_dict())
            batch.delete(appt_ref)
            batch.commit()
            return True
        except Exception as e:
            print(f"Error moving to approve: {e}")
            return False

    def delete_appointment(self, user_uid: str, appointment_id: str) -> bool:
        try:
            user_collection = self.user_repo.get_collection_for_uid(user_uid)
            if not user_collection:
                return False
            appt_ref = self.db.collection(user_collection).document(user_uid).collection(self.APPOINTMENT_COLLECTION).document(appointment_id)
            appt_ref.delete()
            return True
        except Exception as e:
            print(f"Error deleting appointment: {e}")
            return False

    def get_approvals_by_uid(self, uid: str) -> list[dict]:
        approve_list = []
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return []
            docs = self.db.collection(user_collection).document(uid).collection(self.APPROVE_COLLECTION).stream()
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                approve_list.append(data)
        except Exception as e:
            print(f"Error getting approvals: {e}")
        return approve_list
