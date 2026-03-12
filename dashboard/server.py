#!/usr/bin/env python
"""
dashboard/server.py — HTTP server for the VFS slot monitor dashboard.

Serves:
  GET  /                           → dashboard/index.html
  GET  /api/status                 → ../dashboard_status.json
  GET  /api/countries              → list configured countries
  GET  /api/config/<code>/auth     → get auth_creds.json (masked)
  GET  /api/config/<code>/ping     → get ping_creds.json
  POST /api/config/<code>/auth     → save auth_creds.json
  POST /api/config/<code>/ping     → save ping_creds.json
  DELETE /api/config/<code>        → delete country config directory
  POST /api/config/<code>/test-telegram → send Telegram test message
  POST /api/process/<code>/start   → start AuthVFS + PingVFS subprocesses
  POST /api/process/<code>/stop    → stop both subprocesses
  GET  /api/process/status         → return running status for all countries
  GET  /api/process/<code>/logs    → return recent logs for a country

Usage:
    python dashboard/server.py
    → http://localhost:8080
"""
import collections
import copy
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

# Resolve paths relative to this file so the server works from any cwd
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
INDEX_HTML = os.path.join(SCRIPT_DIR, "index.html")
STATUS_JSON = os.path.join(ROOT_DIR, "dashboard_status.json")
COUNTRIES_DIR = os.path.join(ROOT_DIR, "countries")

PORT = 8080
MASKED_PREFIX = "****"


# ── Process manager ───────────────────────────────────────────────────────────

# _processes maps country code → process info dict
_processes: dict = {}
_processes_lock = threading.Lock()


def _read_output(proc, log_deque, stop_event):
    """Read lines from a subprocess stdout and append to a deque."""
    try:
        for line in proc.stdout:
            if stop_event.is_set():
                break
            log_deque.append(line.rstrip("\r\n"))
    except Exception:
        pass


def _start_ping_delayed(code, ping_log, delay=5):
    """Start PingVFS after a short delay so the JWT token is ready."""
    time.sleep(delay)
    with _processes_lock:
        if code not in _processes:
            return
        try:
            ping_proc = subprocess.Popen(
                [sys.executable, "PingVFS.py", "--country", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=ROOT_DIR,
                bufsize=1,
            )
        except Exception as exc:
            _processes[code]["ping_log"].append(f"[ERROR] PingVFS başlatılamadı: {exc}")
            return
        ping_stop = threading.Event()
        t = threading.Thread(
            target=_read_output,
            args=(ping_proc, ping_log, ping_stop),
            daemon=True,
        )
        t.start()
        _processes[code]["ping_proc"] = ping_proc
        _processes[code]["ping_stop"] = ping_stop


def process_start(code):
    """Start AuthVFS and PingVFS for *code*.

    Returns (response_dict, error_str).  On success error_str is None.
    """
    with _processes_lock:
        if code in _processes:
            info = _processes[code]
            auth_alive = info.get("auth_proc") and info["auth_proc"].poll() is None
            ping_alive = info.get("ping_proc") and info["ping_proc"].poll() is None
            if auth_alive or ping_alive:
                return None, "already running"
            # Dead processes: clean up and allow restart
            _processes.pop(code)

        auth_log: collections.deque = collections.deque(maxlen=200)
        ping_log: collections.deque = collections.deque(maxlen=200)

        try:
            auth_proc = subprocess.Popen(
                [sys.executable, "AuthVFS.py", "--country", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=ROOT_DIR,
                bufsize=1,
            )
        except Exception as exc:
            return None, f"AuthVFS başlatılamadı: {exc}"

        auth_stop = threading.Event()
        t = threading.Thread(
            target=_read_output,
            args=(auth_proc, auth_log, auth_stop),
            daemon=True,
        )
        t.start()

        _processes[code] = {
            "auth_proc": auth_proc,
            "ping_proc": None,
            "auth_log": auth_log,
            "ping_log": ping_log,
            "auth_stop": auth_stop,
            "ping_stop": None,
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    # Start PingVFS after a 5-second delay in a background thread
    ping_timer = threading.Thread(
        target=_start_ping_delayed,
        args=(code, ping_log),
        daemon=True,
    )
    ping_timer.start()

    return {"status": "started", "country": code}, None


def process_stop(code):
    """Terminate both processes for *code*.

    Returns (response_dict, error_str).
    """
    with _processes_lock:
        if code not in _processes:
            return None, "not running"
        info = _processes.pop(code)

    for proc_key, stop_key in (("auth_proc", "auth_stop"), ("ping_proc", "ping_stop")):
        stop_ev = info.get(stop_key)
        if stop_ev:
            stop_ev.set()
        proc = info.get(proc_key)
        if proc is None:
            continue
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    return {"status": "stopped", "country": code}, None


def get_all_process_status():
    """Return a dict of country_code → status info."""
    with _processes_lock:
        result = {}
        for code, info in _processes.items():
            auth_proc = info.get("auth_proc")
            ping_proc = info.get("ping_proc")
            auth_running = auth_proc is not None and auth_proc.poll() is None
            ping_running = ping_proc is not None and ping_proc.poll() is None
            result[code] = {
                "running": auth_running or ping_running,
                "auth_running": auth_running,
                "ping_running": ping_running,
                "auth_pid": auth_proc.pid if auth_proc else None,
                "ping_pid": ping_proc.pid if ping_proc else None,
                "started_at": info.get("started_at", ""),
                "auth_log": list(info["auth_log"])[-50:],
                "ping_log": list(info["ping_log"])[-50:],
            }
        return result


def get_process_logs(code):
    """Return full log buffers for *code*."""
    with _processes_lock:
        if code not in _processes:
            return None
        info = _processes[code]
        return {
            "auth_log": list(info["auth_log"]),
            "ping_log": list(info["ping_log"]),
        }


# ── Password masking helpers ──────────────────────────────────────────────────

def _mask_value(val):
    """Return masked string showing only the last 4 characters."""
    if not val or not isinstance(val, str):
        return val
    if len(val) <= 4:
        return MASKED_PREFIX
    return MASKED_PREFIX + val[-4:]


def _is_masked(val):
    return isinstance(val, str) and val.startswith(MASKED_PREFIX)


def _mask_auth_config(config):
    """Return a deep copy of auth config with sensitive fields masked."""
    masked = copy.deepcopy(config)
    if "pass" in masked:
        masked["pass"] = _mask_value(masked["pass"])
    otp = masked.get("otp")
    if isinstance(otp, dict) and "email_pass" in otp:
        otp["email_pass"] = _mask_value(otp["email_pass"])
    return masked


def _restore_masked_fields(new_cfg, existing_cfg, field_paths):
    """
    For each dot-separated field path in field_paths, if new_cfg contains a
    masked placeholder, replace it with the real value from existing_cfg.
    """
    for field_path in field_paths:
        parts = field_path.split(".")
        new_obj = new_cfg
        old_obj = existing_cfg
        for part in parts[:-1]:
            if not isinstance(new_obj, dict) or part not in new_obj:
                new_obj = None
                break
            new_obj = new_obj[part]
            if isinstance(old_obj, dict):
                old_obj = old_obj.get(part, {})
            else:
                old_obj = {}
        if new_obj is None:
            continue
        key = parts[-1]
        if key in new_obj and _is_masked(new_obj[key]):
            if isinstance(old_obj, dict) and key in old_obj:
                new_obj[key] = old_obj[key]


# ── Request handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default noisy access log
        pass

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg, status=400):
        self._json({"error": msg}, status)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._serve_file(INDEX_HTML, "text/html; charset=utf-8")

        elif path == "/api/status":
            if os.path.isfile(STATUS_JSON):
                self._serve_file(STATUS_JSON, "application/json; charset=utf-8")
            else:
                self._json({"last_updated": "", "countries": {}})

        elif path == "/api/countries":
            self._get_countries()

        elif path.startswith("/api/config/"):
            parts = path[len("/api/config/"):].strip("/").split("/")
            if len(parts) == 2:
                code, cfg_type = parts
                if cfg_type == "auth":
                    self._get_config(code, "auth_creds.json", mask=True)
                elif cfg_type == "ping":
                    self._get_config(code, "ping_creds.json", mask=False)
                else:
                    self._error("Unknown config type", 404)
            else:
                self._error("Invalid path", 404)

        elif path == "/api/process/status":
            self._json(get_all_process_status())

        elif path.startswith("/api/process/"):
            parts = path[len("/api/process/"):].strip("/").split("/")
            if len(parts) == 2 and parts[1] == "logs":
                code = parts[0]
                logs = get_process_logs(code)
                if logs is None:
                    self._error("Country not running", 404)
                else:
                    self._json(logs)
            else:
                self._error("Not found", 404)

        else:
            self.send_response(404)
            self.end_headers()

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = self.path.split("?")[0]

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._error("Invalid JSON body")
            return

        if path.startswith("/api/config/"):
            parts = path[len("/api/config/"):].strip("/").split("/")
            if len(parts) == 2:
                code, action = parts
                if action == "auth":
                    self._save_config(code, "auth_creds.json", body,
                                      masked_fields=["pass", "otp.email_pass"])
                elif action == "ping":
                    self._save_config(code, "ping_creds.json", body, masked_fields=[])
                elif action == "test-telegram":
                    self._test_telegram(code)
                else:
                    self._error("Unknown action", 404)
            else:
                self._error("Invalid path", 404)

        elif path.startswith("/api/process/"):
            parts = path[len("/api/process/"):].strip("/").split("/")
            if len(parts) == 2:
                code, action = parts
                if action == "start":
                    result, err = process_start(code)
                    if err:
                        self._error(err, 409 if err == "already running" else 500)
                    else:
                        self._json(result)
                elif action == "stop":
                    result, err = process_stop(code)
                    if err:
                        self._error(err, 404 if err == "not running" else 500)
                    else:
                        self._json(result)
                else:
                    self._error("Unknown action", 404)
            else:
                self._error("Invalid path", 404)

        else:
            self._error("Not found", 404)

    # ── DELETE ───────────────────────────────────────────────────────────────

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/config/"):
            parts = path[len("/api/config/"):].strip("/").split("/")
            if len(parts) == 1 and parts[0]:
                self._delete_country(parts[0])
            else:
                self._error("Invalid path", 404)
        else:
            self._error("Not found", 404)

    # ── Business logic ────────────────────────────────────────────────────────

    def _get_countries(self):
        countries = []
        for country_dir in sorted(glob.glob(os.path.join(COUNTRIES_DIR, "*"))):
            if not os.path.isdir(country_dir):
                continue
            code = os.path.basename(country_dir)
            has_auth = os.path.isfile(os.path.join(country_dir, "auth_creds.json"))
            has_ping = os.path.isfile(os.path.join(country_dir, "ping_creds.json"))
            if not (has_auth or has_ping):
                continue
            name = code.upper()
            for fname in ("ping_creds.json", "auth_creds.json"):
                fpath = os.path.join(country_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        name = cfg.get("country_name", name)
                        break
                    except Exception:
                        pass
            countries.append({
                "code": code,
                "name": name,
                "has_auth": has_auth,
                "has_ping": has_ping,
            })
        self._json({"countries": countries})

    def _get_config(self, code, filename, mask=False):
        filepath = os.path.join(COUNTRIES_DIR, code, filename)
        if not os.path.isfile(filepath):
            self._error("Config not found", 404)
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)
            if mask:
                config = _mask_auth_config(config)
            self._json(config)
        except Exception as e:
            self._error(str(e), 500)

    def _save_config(self, code, filename, data, masked_fields=None):
        country_dir = os.path.join(COUNTRIES_DIR, code)
        os.makedirs(country_dir, exist_ok=True)
        filepath = os.path.join(country_dir, filename)

        if masked_fields and os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                _restore_masked_fields(data, existing, masked_fields)
            except Exception:
                pass  # If we can't read existing file, save as-is

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self._json({"success": True})
        except Exception as e:
            self._error(str(e), 500)

    def _delete_country(self, code):
        country_dir = os.path.join(COUNTRIES_DIR, code)
        if not os.path.isdir(country_dir):
            self._error("Country not found", 404)
            return
        try:
            shutil.rmtree(country_dir)
            self._json({"success": True})
        except Exception as e:
            self._error(str(e), 500)

    def _test_telegram(self, code):
        ping_path = os.path.join(COUNTRIES_DIR, code, "ping_creds.json")
        if not os.path.isfile(ping_path):
            self._error("ping_creds.json not found for country: " + code, 404)
            return
        try:
            with open(ping_path, "r", encoding="utf-8") as f:
                ping = json.load(f)
        except Exception as e:
            self._error("Failed to read ping config: " + str(e), 500)
            return

        tg = ping.get("telegram", {})
        if not tg.get("enabled"):
            self._error("Telegram is not enabled for this country", 400)
            return

        bot_token = tg.get("bot_token", "")
        chat_id = str(tg.get("chat_id", ""))
        if not bot_token or not chat_id:
            self._error("Bot token or chat ID is missing", 400)
            return
        if bot_token.startswith("YOUR_") or chat_id.startswith("YOUR_"):
            self._error("Please configure actual Telegram credentials first", 400)
            return

        try:
            country_name = ping.get("country_name", code.upper())
            message = f"✅ VFS Slot Monitor — Test message ({country_name})"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                self._json({"success": True, "message": "Test mesajı gönderildi!"})
            else:
                self._error("Telegram API hatası: " + json.dumps(result), 400)
        except Exception as e:
            self._error("Telegram gönderilemedi: " + str(e), 500)

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
