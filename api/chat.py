from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

print("loading chat.py")

# Ensure project root is in sys.path so chatbot module loads correctly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load environment variables for chatbot dependencies
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "chatbot/.env")
load_dotenv()

# Lazy-loaded chatbot instance
_chatbot_instance = None


def get_chatbot():
    """Lazy-load the Chatbot instance on first request"""
    global _chatbot_instance
    if _chatbot_instance is None:
        print("Initializing Chatbot...")
        try:
            token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
            if not token:
                print("Chatbot init warning: HUGGINGFACEHUB_API_TOKEN missing")
            from chatbot.chat import Chatbot
            _chatbot_instance = Chatbot()
        except Exception as e:
            print("Chatbot import/init error:", e)
            raise e
    return _chatbot_instance


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Vercel sometimes probes endpoints with GET before POST."""
        self._send_response(200, {"status": "chat endpoint active"})

    def do_POST(self):
        try:
            # Parse JSON body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            message = data.get("message", "")
            if not message:
                return self._send_response(400, {
                    "success": False,
                    "response": "Message is required"
                })

            chatbot = get_chatbot()
            response_text = chatbot.get_response(message)

            self._send_response(200, {
                "success": True,
                "response": response_text
            })

        except Exception as e:
            print("Chat error:", e)
            self._send_response(500, {
                "success": False,
                "response": "Server error"
            })

    def do_OPTIONS(self):
        """Handle CORS preflight"""
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