from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.procedure_repo import ProcedureRepository


class DashboardService:
    def __init__(self, appointment_repo: AppointmentRepository, user_repo: UserRepository, procedure_repo: ProcedureRepository):
        self.appointment_repo = appointment_repo
        self.user_repo = user_repo
        self.procedure_repo = procedure_repo

    def get_admin_dashboard_data(self) -> dict:
        appointment_list = self.appointment_repo.get_pending_appointments()
        approve_list = self.appointment_repo.get_approvals()
        accounts = self.user_repo.get_all_accounts()

        for account in accounts:
            user_uid = account["uid"]
            done_procedures = self.procedure_repo.get_history(user_uid)
            account["Done_procedure"] = {"procedures": done_procedures}

        urgency_order = {"Emergency": 0, "Urgent": 1, "Normal": 2}
        appointment_list.sort(key=lambda x: urgency_order.get(x.get("UrgencyLevel", ""), 99))

        return {
            "appointment_list": appointment_list,
            "approve_list": approve_list,
            "accounts": accounts,
            "pending_count": len(appointment_list),
            "approved_count": len(approve_list),
            "total_patients": len(accounts),
        }

    def get_patient_dashboard_data(self, uid: str) -> dict | None:
        user = self.user_repo.find_by_uid(uid) or self.user_repo.find_google_by_uid(uid)
        if not user:
            return None
        approvals = self.appointment_repo.get_approvals_by_uid(uid)
        return {
            "user": user,
            "approvals": approvals,
        }
