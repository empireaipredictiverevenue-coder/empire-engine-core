"""Simple health endpoint for customer container"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "empire-ai-customer"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    server = HTTPServer(("", 8080), HealthHandler)
    server.serve_forever()
