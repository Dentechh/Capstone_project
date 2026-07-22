"""Standalone repro of the exact _send_email_async code path in main.py."""
import os, sys, threading, smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

def _send_email_async(recipient, subject, body):
    def _task():
        try:
            print("1. Creating SMTP connection...")
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
            print("2. Connected!")
            server.ehlo()
            print("3. Starting TLS...")
            server.starttls()
            server.ehlo()
            print("4. Logging in...")
            server.login(os.getenv("MAIL_USERNAME"), os.getenv("MAIL_PASSWORD"))
            print("5. Sending email...")
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = os.getenv("MAIL_USERNAME")
            msg["To"] = recipient
            msg.set_content(body)
            server.send_message(msg)
            print("6. Email sent!")
            server.quit()
        except Exception:
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_task, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    t = _send_email_async(
        "jayr.bonitillo.ui@phinmaed.com",
        "Verify Your Email",
        "Hello,\n\nYour verification code is:\n\n999999\n\nThis code expires in 10 minutes."
    )
    print("Thread started, alive =", t.is_alive())
    t.join(timeout=15)
    print("Thread finished, alive =", t.is_alive())
