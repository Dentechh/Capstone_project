from app.models.appointment import Appointment


class Approve(Appointment):
    def __init__(self, appointment_id: str = "", patient_unq_id: str = "", **kwargs):
        super().__init__(appointment_id=appointment_id, **kwargs)
        self.patient_unq_id = patient_unq_id

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["Patient_unq_id"] = self.patient_unq_id
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Approve":
        appt = Appointment.from_dict(data)
        return cls(
            appointment_id=appt.appointment_id,
            patient_unq_id=data.get("Patient_unq_id", ""),
            uid=appt.uid,
            email=appt.email,
            first_name=appt.first_name,
            middle_name=appt.middle_name,
            last_name=appt.last_name,
            house_no=appt.house_no,
            street=appt.street,
            brgy=appt.brgy,
            municipality=appt.municipality,
            city=appt.city,
            contact_number=appt.contact_number,
            nationality=appt.nationality,
            religion=appt.religion,
            age=appt.age,
            sex=appt.sex,
            birthday=appt.birthday,
            occupation=appt.occupation,
            civil_status=appt.civil_status,
            service=appt.service,
            urgency_level=appt.urgency_level,
            appointment_date=appt.appointment_date,
            q1=appt.q1,
            q2=appt.q2,
            q3=appt.q3,
            q4=appt.q4,
            q5=appt.q5,
            q6=appt.q6,
            q7=appt.q7,
            q9=appt.q9,
            q2_spec=appt.q2_spec,
            q3_spec=appt.q3_spec,
            q4_spec=appt.q4_spec,
            q5_spec=appt.q5_spec,
            q7_spec=appt.q7_spec,
            q9_spec=appt.q9_spec,
            w_preg=appt.w_preg,
            w_nurse=appt.w_nurse,
            w_pill=appt.w_pill,
            status=appt.status,
            dentist_name=appt.dentist_name,
        )
