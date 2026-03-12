#!/usr/bin/env python
"""
run_all.py — Launch AuthVFS and PingVFS for every country found in countries/*/
Each country's processes run in separate threads (using subprocesses).

Usage:
    python run_all.py
"""
import os
import sys
import glob
import subprocess
import threading
import json
import time


def find_countries():
    """Return list of country codes that have both auth_creds.json and ping_creds.json."""
    base = os.path.join(os.path.dirname(__file__), "countries")
    countries = []
    for auth_path in sorted(glob.glob(os.path.join(base, "*", "auth_creds.json"))):
        code = os.path.basename(os.path.dirname(auth_path))
        ping_path = os.path.join(base, code, "ping_creds.json")
        if os.path.isfile(ping_path):
            countries.append(code)
    return countries


def _run_subprocess(label, cmd):
    """Run a subprocess and stream its stdout/stderr with a label prefix."""
    print(f"[{label}] Starting: {' '.join(cmd)}", flush=True)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            print(f"[{label}] {line}", end="", flush=True)
        proc.wait()
        print(f"[{label}] Process exited with code {proc.returncode}", flush=True)
    except Exception as e:
        print(f"[{label}] Error: {e}", flush=True)


def launch_country(code):
    """Launch AuthVFS and PingVFS for a single country in background threads."""
    python = sys.executable
    auth_thread = threading.Thread(
        target=_run_subprocess,
        args=(f"auth/{code}", [python, "AuthVFS.py", "--country", code]),
        daemon=True,
        name=f"auth-{code}",
    )
    ping_thread = threading.Thread(
        target=_run_subprocess,
        args=(f"ping/{code}", [python, "PingVFS.py", "--country", code]),
        daemon=True,
        name=f"ping-{code}",
    )
    auth_thread.start()
    # Give auth a few seconds head-start so the JWT is ready before ping begins
    time.sleep(5)
    ping_thread.start()
    return auth_thread, ping_thread


def main():
    countries = find_countries()
    if not countries:
        print("No countries found in countries/*/. "
              "Copy example configs and fill in your credentials.", flush=True)
        sys.exit(1)

    print(f"Found {len(countries)} country(ies): {', '.join(countries)}", flush=True)

    threads = []
    for code in countries:
        auth_t, ping_t = launch_country(code)
        threads.extend([auth_t, ping_t])

    print("\nAll country processes started. Press Ctrl+C to stop.\n", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)


if __name__ == "__main__":
    main()
