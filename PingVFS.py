#!/usr/bin/env python
import os
import sys
import time
import json
import requests
import subprocess
from playsound import playsound
from datetime import datetime
from TelegramNotifier import TelegramNotifier

MIN_JWT_LENGTH = 10

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
        print("Monitoring VFS appointment slots for Turkey → Netherlands (Tourism)...")
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

                if status == "SLOT_FOUND":
                    msg = f"Slot available at {center['name']}! Earliest: {earliest_date}"
                    subprocess.call([
                        "/usr/bin/notify-send",
                        "VFS Slots!!!",
                        msg
                    ])
                    try:
                        playsound(self.sound)
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
    main("./ping_creds.json")
