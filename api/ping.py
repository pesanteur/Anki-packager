# api/ping.py
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type","application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true, "service": "anki-packager"}')