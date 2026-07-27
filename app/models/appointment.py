from datetime import datetime


class Appointment:
    def __init__(
        self,
        appointment_id: str = "",
        uid: str = "",
        email: str = "",
        first_name: str = "",
        middle_name: str = "",
        last_name: str = "",
        house_no: str = "",
        street: str = "",
        brgy: str = "",
        municipality: str = "",
        city: str = "",
        contact_number: str = "",
        nationality: str = "",
        religion: str = "",
        age: str = "",
        sex: str = "",
        birthday: str = "",
        occupation: str = "",
        civil_status: str = "",
        service: str = "",
        urgency_level: str = "",
        appointment_date: str = "",
        q1: str = "",
        q2: str = "",
        q3: str = "",
        q4: str = "",
        q5: str = "",
        q6: str = "",
        q7: str = "",
        q9: str = "",
        q2_spec: str = "",
        q3_spec: str = "",
        q4_spec: str = "",
        q5_spec: str = "",
        q7_spec: str = "",
        q9_spec: str = "",
        w_preg: str = "",
        w_nurse: str = "",
        w_pill: str = "",
        status: str = "pending",
        dentist_name: str = "",
    ):
        self.appointment_id = appointment_id
        self.uid = uid
        self.email = email
        self.first_name = first_name
        self.middle_name = middle_name
        self.last_name = last_name
        self.house_no = house_no
        self.street = street
        self.brgy = brgy
        self.municipality = municipality
        self.city = city
        self.contact_number = contact_number
        self.nationality = nationality
        self.religion = religion
        self.age = age
        self.sex = sex
        self.birthday = birthday
        self.occupation = occupation
        self.civil_status = civil_status
        self.service = service
        self.urgency_level = urgency_level
        self.appointment_date = appointment_date
        self.q1 = q1
        self.q2 = q2
        self.q3 = q3
        self.q4 = q4
        self.q5 = q5
        self.q6 = q6
        self.q7 = q7
        self.q9 = q9
        self.q2_spec = q2_spec
        self.q3_spec = q3_spec
        self.q4_spec = q4_spec
        self.q5_spec = q5_spec
        self.q7_spec = q7_spec
        self.q9_spec = q9_spec
        self.w_preg = w_preg
        self.w_nurse = w_nurse
        self.w_pill = w_pill
        self.status = status
        self.dentist_name = dentist_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "email": self.email,
            "FirstName": self.first_name,
            "MiddleName": self.middle_name,
            "LastName": self.last_name,
            "HouseNo": self.house_no,
            "Street": self.street,
            "Brgy": self.brgy,
            "Municipality": self.municipality,
            "City": self.city,
            "ContactNumber": self.contact_number,
            "Nationality": self.nationality,
            "Religion": self.religion,
            "Age": self.age,
            "Sex": self.sex,
            "Birthday": self.birthday,
            "Occupation": self.occupation,
            "CivilStatus": self.civil_status,
            "Service": self.service,
            "UrgencyLevel": self.urgency_level,
            "appointment_date": self.appointment_date,
            "q1": self.q1,
            "q2": self.q2,
            "q3": self.q3,
            "q4": self.q4,
            "q5": self.q5,
            "q6": self.q6,
            "q7": self.q7,
            "q9": self.q9,
            "q2_spec": self.q2_spec,
            "q3_spec": self.q3_spec,
            "q4_spec": self.q4_spec,
            "q5_spec": self.q5_spec,
            "q7_spec": self.q7_spec,
            "q9_spec": self.q9_spec,
            "w_preg": self.w_preg,
            "w_nurse": self.w_nurse,
            "w_pill": self.w_pill,
            "status": self.status,
            "DentistName": self.dentist_name,
        }
