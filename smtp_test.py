import os, smtplib
from dotenv import load_dotenv
load_dotenv()

user = os.getenv("MAIL_USERNAME")
pw = os.getenv("MAIL_PASSWORD")

s = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
s.set_debuglevel(1)
s.starttls()
s.login(user, pw)
print("LOGIN OK")
s.quit()