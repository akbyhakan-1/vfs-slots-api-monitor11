#!/usr/bin/env python
"""
StatusWriter.py — Writes per-country slot check results to dashboard_status.json.
Used by PingVFS.py after each centre check so the web dashboard can display live status.
"""
import json
import os
import threading
from datetime import datetime

DASHBOARD_STATUS_FILE = "./dashboard_status.json"
_lock = threading.Lock()


def _load_status():
    """Load existing dashboard_status.json or return an empty skeleton."""
    if os.path.isfile(DASHBOARD_STATUS_FILE):
        try:
            with open(DASHBOARD_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_updated": "", "countries": {}}


def _save_status(data):
    """Atomically write the status dict to dashboard_status.json."""
    tmp_path = DASHBOARD_STATUS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, DASHBOARD_STATUS_FILE)


def update_center(country_code, country_name, login_url, booking_url,
                  center_name, vac_code, status, earliest_date=None):
    """
    Update a single centre entry inside dashboard_status.json.

    Parameters
    ----------
    country_code  : str   e.g. "nld"
    country_name  : str   e.g. "Netherlands"
    login_url     : str   VFS login URL for this country
    booking_url   : str   VFS booking URL for this country
    center_name   : str   e.g. "Ankara"
    vac_code      : str   e.g. "NANKA"
    status        : str   one of "slot_found", "no_slot", "waitlist", "error"
    earliest_date : str|None  e.g. "04/07/2026 00:00:00"
    """
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with _lock:
        data = _load_status()

        countries = data.setdefault("countries", {})
        country_entry = countries.setdefault(country_code, {
            "name": country_name,
            "login_url": login_url,
            "booking_url": booking_url,
            "auth_status": "active",
            "last_check": now_iso,
            "centers": [],
        })

        # Keep meta fields up-to-date
        country_entry["name"] = country_name
        country_entry["login_url"] = login_url
        country_entry["booking_url"] = booking_url
        country_entry["last_check"] = now_iso

        # Find or create the centre entry
        centers = country_entry.setdefault("centers", [])
        for c in centers:
            if c.get("vacCode") == vac_code:
                c["name"] = center_name
                c["status"] = status
                c["last_check"] = now_iso
                c["earliest_date"] = earliest_date
                break
        else:
            centers.append({
                "name": center_name,
                "vacCode": vac_code,
                "status": status,
                "last_check": now_iso,
                "earliest_date": earliest_date,
            })

        data["last_updated"] = now_iso
        _save_status(data)
