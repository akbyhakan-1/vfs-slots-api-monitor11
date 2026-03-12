#!/usr/bin/env python
"""
dashboard/server.py — Minimal HTTP server for the VFS slot monitor dashboard.

Serves:
  GET /           → dashboard/index.html
  GET /api/status → ../dashboard_status.json (from project root)

Usage:
    python dashboard/server.py
    → http://localhost:8080
"""
import os
import sys
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# Resolve paths relative to this file so the server works from any cwd
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
INDEX_HTML = os.path.join(SCRIPT_DIR, "index.html")
STATUS_JSON = os.path.join(ROOT_DIR, "dashboard_status.json")

PORT = 8080


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default noisy access log
        pass

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._serve_file(INDEX_HTML, "text/html; charset=utf-8")

        elif path == "/api/status":
            if os.path.isfile(STATUS_JSON):
                self._serve_file(STATUS_JSON, "application/json; charset=utf-8")
            else:
                # Return empty skeleton when the file doesn't exist yet
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cors_headers()
                self.end_headers()
                empty = json.dumps({"last_updated": "", "countries": {}})
                self.wfile.write(empty.encode())

        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, filepath, content_type):
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()


def main():
    server = HTTPServer(("", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}", flush=True)
    print(f"Serving index from: {INDEX_HTML}", flush=True)
    print(f"Status file:        {STATUS_JSON}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)


if __name__ == "__main__":
    main()
