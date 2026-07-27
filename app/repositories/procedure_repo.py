from app.models.procedure import DoneProcedure, Procedure


class ProcedureRepository:
    DONE_PROCEDURE_COLLECTION = "Done_procedure"

    def __init__(self, db, user_repo):
        self.db = db
        self.user_repo = user_repo

    def add_record(self, uid: str, done_procedure: DoneProcedure) -> str | None:
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return None
            doc_ref = (
                self.db.collection(user_collection)
                .document(uid)
                .collection(self.DONE_PROCEDURE_COLLECTION)
                .add(done_procedure.to_dict())
            )
            return doc_ref[1].id
        except Exception as e:
            print(f"Error adding procedure record: {e}")
            return None

    def get_history(self, uid: str) -> list[dict]:
        visit_history = []
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return []
            docs = (
                self.db.collection(user_collection)
                .document(uid)
                .collection(self.DONE_PROCEDURE_COLLECTION)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                procedures = data.get("procedures", [])
                for p in procedures:
                    visit_history.append({
                        "dentist": p.get("dentist", ""),
                        "uid": p.get("uid", ""),
                        "date": p.get("date", ""),
                        "procedure": p.get("procedure", ""),
                        "paid": p.get("paid", 0),
                        "balance": p.get("balance", 0),
                        "tooth": p.get("tooth", ""),
                        "value": p.get("value", 0),
                        "status": p.get("status", ""),
                        "next_appointment": p.get("next_appointment", ""),
                        "medicine": p.get("medicine", ""),
                    })
        except Exception as e:
            print(f"Error getting procedure history: {e}")
        return visit_history

    def get_done_procedures(self, uid: str) -> list[dict]:
        procedures = []
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return []
            docs = (
                self.db.collection(user_collection)
                .document(uid)
                .collection(self.DONE_PROCEDURE_COLLECTION)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                for p in data.get("procedures", []):
                    procedures.append({
                        "dentist": p.get("dentist", ""),
                        "medicine": p.get("medicine", ""),
                        "date": p.get("date", ""),
                        "procedure": p.get("procedure", ""),
                        "paid": p.get("paid", 0),
                        "next_appointment": p.get("next_appointment", ""),
                        "status": p.get("status", ""),
                        "balance": p.get("balance", 0),
                        "value": p.get("value", 0),
                        "tooth": p.get("tooth", ""),
                    })
        except Exception as e:
            print(f"Error getting treatment info: {e}")
        return procedures

    def delete_approve_document(self, uid: str, patient_unq_id: str) -> None:
        try:
            user_collection = self.user_repo.get_collection_for_uid(uid)
            if not user_collection:
                return
            self.db.collection(user_collection).document(uid).collection("Approve").document(patient_unq_id).delete()
        except Exception as e:
            print(f"Delete Approve error: {e}")
