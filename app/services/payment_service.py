import requests
import base64
from app.config import config


class PaymentService:
    def __init__(self):
        self.secret_key = config.get("PAYMONGO_SECRET_KEY", "")
        self.public_key = config.get("PAYMONGO_PUBLIC_KEY", "")

    def create_gcash_payment(self, amount: float, procedure: str, patient_uid: str, base_url: str) -> dict:
        try:
            amount_cents = int(amount * 100)
            patient_name = "Dental Patient"
            patient_email = "patient@example.com"
            success_url = f"{base_url}/payment-success?uid={patient_uid}&procedure={procedure}"
            cancel_url = f"{base_url}/payment-cancel"

            auth = base64.b64encode(f"{self.secret_key}:".encode()).decode()
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Basic {auth}",
            }
            payload = {
                "data": {
                    "attributes": {
                        "billing": {
                            "name": patient_name,
                            "email": patient_email,
                        },
                        "line_items": [{
                            "currency": "PHP",
                            "amount": amount_cents,
                            "name": procedure,
                            "quantity": 1,
                        }],
                        "payment_method_types": ["gcash"],
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                        "metadata": {
                            "patient_uid": patient_uid,
                            "procedure": procedure,
                        },
                    }
                }
            }
            r = requests.post(
                "https://api.paymongo.com/v1/checkout_sessions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            result = r.json()
            if "data" in result:
                return {"checkout_url": result["data"]["attributes"]["checkout_url"]}
            return {"error": result.get("error", {}).get("message", "Failed to create payment session")}
        except Exception as e:
            return {"error": str(e)}

    def verify_payment(self, checkout_session_id: str) -> dict:
        try:
            auth = base64.b64encode(f"{self.secret_key}:".encode()).decode()
            headers = {
                "accept": "application/json",
                "authorization": f"Basic {auth}",
            }
            r = requests.get(
                f"https://api.paymongo.com/v1/checkout_sessions/{checkout_session_id}",
                headers=headers,
                timeout=30,
            )
            result = r.json()
            session_data = result.get("data", {}).get("attributes", {})
            return {
                "payment_status": session_data.get("payment_status", ""),
                "success": "paid" in session_data.get("payment_status", "").lower(),
            }
        except Exception as e:
            print(f"Error verifying payment: {e}")
            return {"success": False, "error": str(e)}
