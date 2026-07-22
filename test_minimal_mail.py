"""Minimal Flask repro for mail sending."""
from flask import Flask
from flask_mail import Mail, Message
import os, threading, sys
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_USERNAME'),
    MAIL_TIMEOUT=10,
)
mail = Mail(app)

@app.route('/send')
def send():
    try:
        msg = Message('SMTP Test', recipients=['jerichoph01@gmail.com'])
        msg.body = 'hello from minimal app'
        mail.send(msg)
        return 'sent'
    except Exception as e:
        return f'Error: {repr(e)}', 500

if __name__ == '__main__':
    app.run(debug=False, port=5010)
