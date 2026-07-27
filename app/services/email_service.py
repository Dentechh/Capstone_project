import threading
from flask_mail import Mail, Message
from app.extensions import mail


class EmailService:
    def __init__(self, mail_instance: Mail = None):
        self.mail = mail_instance or mail

    def send_appointment_email(self, patient_email: str, fullname: str, action: str, appointment_data: dict):
        if not patient_email:
            return None
        service = appointment_data.get("Service", "your appointment")
        dentist = appointment_data.get("DentistName", "our dentist")
        appointment_date = appointment_data.get("appointment_date", "")

        if action == "accept":
            subject = "Appointment Accepted - Capizonda Dental Clinic"
            body = f"""
Hello {fullname},

Good news! Your appointment for {service} has been accepted by Dr. {dentist}.
{appointment_date}

Please arrive 10 minutes before your scheduled time.
If you have any questions, feel free to contact us.

Best regards,
Capizonda Dental Clinic Team
"""
        else:
            subject = "Appointment Declined - Capizonda Dental Clinic"
            body = f"""
Hello {fullname},

We regret to inform you that your appointment request for {service} has been declined by Dr. {dentist}.
{appointment_date}

Please feel free to book another appointment at your convenience.
We apologize for any inconvenience this may have caused.

Best regards,
Capizonda Dental Clinic Team
"""
        try:
            msg = Message(
                subject=subject,
                sender=self.mail.default_sender,
                recipients=[patient_email],
            )
            msg.body = body
            self.mail.send(msg)
            return True
        except Exception as e:
            print(f"EMAIL SEND ERROR: {e}")
            return False

    def send_async(self, patient_email: str, fullname: str, action: str, appointment_data: dict):
        thread = threading.Thread(
            target=self.send_appointment_email,
            args=(patient_email, fullname, action, appointment_data),
            daemon=True,
        )
        thread.start()
