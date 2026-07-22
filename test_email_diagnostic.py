"""Diagnostic script to test sign-up flow components without starting Flask server."""
import os
import sys
import smtplib
from dotenv import load_dotenv

load_dotenv()

print("=== ENV CHECK ===")
print("MAIL_USERNAME:", repr(os.getenv("MAIL_USERNAME")))
print("MAIL_PASSWORD set:", bool(os.getenv("MAIL_PASSWORD")))
print("MAIL_SERVER:", repr(os.getenv("MAIL_SERVER")))
print("MAIL_PORT:", repr(os.getenv("MAIL_PORT")))

print("\n=== SMTP CONNECTION TEST ===")
try:
    server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
    server.ehlo()
    server.starttls()
    server.ehlo()
    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    server.login(username, password)
    print("SMTP login successful")
    
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = "SMTP Diagnostic Test"
    msg["From"] = username
    msg["To"] = username
    msg.set_content("This is a test message from the diagnostic script.")
    server.sendmail(username, username, msg.as_string())
    print("Diagnostic email sent successfully")
    server.quit()
except Exception as e:
    print("SMTP ERROR:", repr(e))
    sys.exit(1)

print("\n=== ALL CHECKS PASSED ===")
