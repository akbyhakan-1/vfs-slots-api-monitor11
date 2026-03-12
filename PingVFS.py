#!/usr/bin/env python
import os
import sys
import time
import json
import argparse
import requests
import subprocess
import platform
from datetime import datetime
from TelegramNotifier import TelegramNotifier
from StatusWriter import update_center

MIN_JWT_LENGTH = 10

def play_alert():
    """Play an alert sound when a slot is found."""
    try:
        if platform.system() == "Windows":
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 500)
                winsound.Beep(1500, 300)
                winsound.Beep(2000, 500)
        else:
            # Linux/Mac fallback
            os.system("echo -e '\\a'")
    except Exception as e:
        print(f"Could not play alert sound: {e}")

class PingVFS:
    # default constructor
    def __init__(self, params):
        self.url = params["api_url"]
        self.country_code = params["countryCode"]
        self.mission_code = params["missionCode"]
        self.visa_category_code = params["visaCategoryCode"]
        self.login_user = params["loginUser"]
        self.pay_code = params.get("payCode", "")
        self.role_name = params.get("roleName", "Individual")
        self.centers = params["centers"]
        self.paths = params["paths"]
        self.auth = ""
        self.start_time = datetime.now()
        self.sound = params["sound"]
        self.delay_between_centers = params.get("delay_between_centers", 3)
        self.delay_between_rounds = params.get("delay_between_rounds", 30)
        self.booking_url = params.get("booking_url", "https://visa.vfsglobal.com/tur/tr/nld/book-appointment")
        self.country_name = params.get("country_name", self.mission_code.upper())
        self.login_url = params.get("login_url", "")

        telegram_config = params.get("telegram", {})
        if telegram_config.get("enabled", False):
            self.telegram = TelegramNotifier(telegram_config)
        else:
            self.telegram = None

    def get_auth_token(self):
        if not os.path.isfile(self.paths["auth"]):
            return False

        path = os.path.realpath(self.paths["auth"])
        read = open(path, "r")
        auth = read.read().replace("\n", " ").strip()
        read.close()

        if not auth or len(auth) < MIN_JWT_LENGTH:
            return False

        if auth == self.auth:
            return self.auth

        self.auth = auth
        return self.auth

    def store_output(self, output):
        # Saving the output in output.txt.
        with open(self.paths["output"], "a") as file_object:
            file_object.write(output)

    def hit_vfs(self, center):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth,
        }

        body = {
            "countryCode": self.country_code,
            "missionCode": self.mission_code,
            "vacCode": center["vacCode"],
            "loginUser": self.login_user,
            "payCode": self.pay_code,
            "roleName": self.role_name,
            "visaCategoryCode": self.visa_category_code,
        }

        try:
            resp = requests.post(self.url, headers=headers, json=body)
        except Exception:
            return None, "ERROR Connection Refused"

        if os.path.isfile(self.paths["auth"]):
            self.get_auth_token()

        try:
            resp_json = resp.json()
        except Exception:
            return None, "ERROR " + str(resp.status_code)

        return resp_json, None

    def evaluate_response(self, resp):
        if resp is None:
            return "NO_SLOT", None

        earliest_date = resp.get("earliestDate")
        earliest_slots = resp.get("earliestSlotLists", [])
        error = resp.get("error")

        if earliest_date and earliest_slots:
            return "SLOT_FOUND", earliest_date

        if error and error.get("code") == 4001:
            return "WAITLIST", None

        return "NO_SLOT", None

    def init(self):
        self.get_auth_token()

        print("""
██    ██ ███████ ███████     ███████ ██       ██████  ████████ ███████          
██    ██ ██      ██          ██      ██      ██    ██    ██    ██               
██    ██ █████   ███████     ███████ ██      ██    ██    ██    ███████          
 ██  ██  ██           ██          ██ ██      ██    ██    ██         ██          
  ████   ██      ███████     ███████ ███████  ██████     ██    ███████ ██ ██ ██""")

        print("\n")
        print("Started at:", end=" ")
        print(datetime.now())
        print(f"Monitoring VFS appointment slots for Turkey → {self.country_name} (Tourism)...")
        print("Centers:", ", ".join(c["name"] for c in self.centers))
        print("\n")

        round_count = 0
        while True:
            round_count += 1
            round_time = datetime.now()
            print(f"\n--- Round {round_count} | {round_time.strftime('%Y-%m-%d %H:%M:%S')} ---")

            for center in self.centers:
                resp, err = self.hit_vfs(center)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if err:
                    result_str = f"[{now_str}] {center['name']} → {err}"
                    status = "ERROR"
                    earliest_date = None
                else:
                    status, earliest_date = self.evaluate_response(resp)
                    if status == "SLOT_FOUND":
                        result_str = f"[{now_str}] {center['name']} → 🎉 SLOT FOUND! Earliest: {earliest_date}"
                    elif status == "WAITLIST":
                        result_str = f"[{now_str}] {center['name']} → Waitlist (no slot)"
                    else:
                        result_str = f"[{now_str}] {center['name']} → No appointment available"

                print(result_str)
                self.store_output(result_str + "\n")

                # Write result to dashboard status file
                dash_status = status.lower() if status else "no_slot"
                try:
                    update_center(
                        country_code=self.mission_code,
                        country_name=self.country_name,
                        login_url=self.login_url,
                        booking_url=self.booking_url,
                        center_name=center["name"],
                        vac_code=center["vacCode"],
                        status=dash_status,
                        earliest_date=earliest_date,
                    )
                except Exception as sw_err:
                    print(f"Warning: StatusWriter error: {sw_err}")

                if status == "SLOT_FOUND":
                    msg = f"Slot available at {center['name']}! Earliest: {earliest_date}"
                    subprocess.call([
                        "/usr/bin/notify-send",
                        "VFS Slots!!!",
                        msg
                    ])
                    try:
                        play_alert()
                    except Exception as e:
                        print(f"Warning: could not play alert sound: {e}")
                    if self.telegram:
                        # Extract applicant count from slot list if available
                        slot_details = None
                        if resp and resp.get("earliestSlotLists"):
                            slot_details = resp["earliestSlotLists"][0].get("applicant")
                        self.telegram.notify_slot_found(
                            center_name=center["name"],
                            earliest_date=earliest_date,
                            booking_url=self.booking_url,
                            slot_details=slot_details,
                        )

                time.sleep(self.delay_between_centers)

            print(f"Round {round_count} complete. Waiting {self.delay_between_rounds}s before next round...")
            time.sleep(self.delay_between_rounds)


def main(params):
    if not os.path.isfile(params):
        return False

    path = os.path.realpath(params)
    read = open(path, "r")
    params = json.loads(read.read())
    read.close()

    ping = PingVFS(params)
    ping.init()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VFS slot monitor")
    parser.add_argument(
        "--country",
        help="Country code to monitor (e.g. nld, hrv). Reads from countries/<code>/ping_creds.json",
        default=None,
    )
    args = parser.parse_args()

    if args.country:
        creds_path = f"./countries/{args.country}/ping_creds.json"
    else:
        creds_path = "./ping_creds.json"

    main(creds_path)
