from app.models.procedure import DoneProcedure, Procedure
from app.repositories.procedure_repo import ProcedureRepository
from app.utils.validators import sanitize_input


class TreatmentService:
    def __init__(self, procedure_repo: ProcedureRepository):
        self.procedure_repo = procedure_repo

    def save_dental_record(self, uid: str, form_data: dict, files: dict) -> dict:
        try:
            dental_chart = {}
            for key, value in form_data.items():
                if key.startswith("tooth_"):
                    dental_chart[key] = value

            chart_image = ""
            image_file = files.get("dental_chart_image")
            if image_file:
                import os
                from datetime import datetime
                save_folder = os.path.join("static", "dental_charts")
                os.makedirs(save_folder, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{uid}_{timestamp}.jpg"
                filepath = os.path.join(save_folder, filename)
                image_file.save(filepath)
                chart_image = f"/static/dental_charts/{filename}"

            dates = form_data.getlist("date[]")
            teeth = form_data.getlist("tooth[]")
            procedures = form_data.getlist("procedure[]")
            dentists = form_data.getlist("dentist[]")
            values = form_data.getlist("value[]")
            paids = form_data.getlist("paid[]")
            balances = form_data.getlist("balance[]")
            next_appts = form_data.getlist("next_appointment[]")
            medicines = form_data.getlist("medicine[]")
            statuses = form_data.getlist("status[]")

            length = min(
                len(dates), len(teeth), len(procedures), len(dentists),
                len(values), len(paids), len(balances), len(next_appts),
                len(medicines), len(statuses),
            )

            procedure_objects = []
            for i in range(length):
                if not procedures[i] and not teeth[i]:
                    continue
                procedure_objects.append(Procedure(
                    date=dates[i],
                    tooth=teeth[i],
                    procedure=procedures[i],
                    dentist=dentists[i],
                    value=float(values[i] or 0),
                    paid=float(paids[i] or 0),
                    balance=float(balances[i] or 0),
                    next_appointment=next_appts[i],
                    medicine=medicines[i],
                    status=statuses[i],
                ))

            done_procedure = DoneProcedure(
                uid=uid,
                chart=dental_chart,
                chart_image=chart_image,
                procedures=procedure_objects,
            )

            self.procedure_repo.add_record(uid, done_procedure)

            patient_unq_id = form_data.get("Patient_unq_id")
            if patient_unq_id:
                self.procedure_repo.delete_approve_document(uid, patient_unq_id)

            return {"success": True, "message": "Dental record saved successfully", "chart_image": chart_image}
        except Exception as e:
            print("ERROR:", e)
            return {"success": False, "message": str(e)}

    def get_treatment_info(self, uid: str) -> list[dict]:
        return self.procedure_repo.get_done_procedures(uid)

    def get_visit_history(self, uid: str) -> list[dict]:
        return self.procedure_repo.get_history(uid)
