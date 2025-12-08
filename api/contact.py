from http.server import BaseHTTPRequestHandler
import json
import os
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from dotenv import load_dotenv

print("loading contact.py")

# Ensure .env loads in vercel dev
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")  # works for local dev
load_dotenv(ROOT / ".env")        # works for deployed env
load_dotenv(ROOT / "chatbot/.env")  # legacy location for secrets
load_dotenv()                     # fallback


def send_email(first, last, email, subject, message):
    try:
        body = f"""{message}

Best regards,
{first} {last}
{email}
"""
        msg = MIMEText(body)
        msg["Subject"] = f"Portfolio Contact: {subject}"
        msg["From"] = email
        msg["To"] = os.getenv("EMAIL_USERNAME")

        server = smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT")))
        server.starttls()
        server.login(os.getenv("EMAIL_USERNAME"), os.getenv("EMAIL_PASSWORD"))
        server.send_message(msg)
        server.quit()

        return True
    except Exception as e:
        print("Email error:", e)
        return False


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self._send_response(200, {"status": "contact endpoint active"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))

            first = data.get("firstName", "")
            last = data.get("lastName", "")
            email = data.get("email", "")
            subject = data.get("subject", "")
            message = data.get("message", "")

            if not all([first, last, email, subject, message]):
                return self._send_response(400, {
                    "success": False,
                    "message": "All fields are required"
                })

            success = send_email(first, last, email, subject, message)

            if success:
                self._send_response(200, {
                    "success": True,
                    "message": "Thank you for your message! I'll get back to you soon."
                })
            else:
                self._send_response(500, {
                    "success": False,
                    "message": "Failed to send email"
                })

        except Exception as e:
            print("Contact error:", e)
            self._send_response(500, {
                "success": False,
                "message": "Server error"
            })

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))