#!/usr/bin/env python
import os
import time
import json
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from OTPReader import OTPReader


class AuthVFS:
    # default constructor
    def __init__(self, args, jwt):
        self.args = args
        self.jwt = jwt
        self._otp_reader = None

    def create_driver(self):
        options = webdriver.ChromeOptions()
        # Let's work in incognito mode.
        options.add_argument("--incognito")
        # Initializing the driver client.
        self.driver = webdriver.Chrome(options=options)

    def _get_otp_reader(self):
        """Return a connected OTPReader, creating one if needed."""
        if self._otp_reader is None:
            otp_config = self.args.get("otp", {})
            reader = OTPReader(otp_config)
            reader.connect()  # Raises on failure — caller should handle
            self._otp_reader = reader
        return self._otp_reader

    def get_loggedin(self, args, driver):
        try:
            # Find the elements in the page.
            email    = driver.find_element(By.XPATH, args["email_id"])
            password = driver.find_element(By.XPATH, args["password_id"])
            submit   = driver.find_element(By.XPATH, args["submit"])
        except NoSuchElementException:
            # If any of the elements aren't there, return false.
            return False

        # Fill up the form fields with necessary credentials.
        email.send_keys(args["user"])
        password.send_keys(args["pass"])
        time.sleep(self.args["avrg_delay"])
        # Submit the form.
        submit.click()
        # Wait for the response to come.
        time.sleep(self.args["avrg_delay"])
        # Return the driver instance.
        return driver

    def wait_for_otp(self):
        """Fetch OTP via configured method (currently: email IMAP)."""
        otp_config = self.args.get("otp", {})
        poll_interval = otp_config.get("poll_interval", 5)
        try:
            reader = self._get_otp_reader()
        except Exception as e:
            print(f"Warning: could not connect to IMAP server: {e}", flush=True)
            self._otp_reader = None  # Reset so next call retries the connection
            return None
        return reader.wait_for_otp(
            poll_interval=poll_interval,
            login_time=datetime.now(timezone.utc),
        )

    def enter_otp(self, otp_code, driver):
        """Type the OTP code into the OTP input field and submit."""
        args = self.args
        try:
            otp_input = driver.find_element(By.XPATH, args["otp_input"])
            otp_input.clear()
            otp_input.send_keys(otp_code)
            time.sleep(1)
            otp_submit = driver.find_element(By.XPATH, args["otp_submit"])
            otp_submit.click()
            time.sleep(self.args["avrg_delay"])
            return True
        except NoSuchElementException:
            print("Warning: OTP input field not found on page — retrying login from the start.")
            return False

    def get_jwt(self, args):
        driver = self.driver
        while True:
            try:
                # Initiate the GET request.
                driver.get(args["url"])
            except Exception:
                return False

            # Let the page load fully.
            time.sleep(self.args["avrg_delay"])
            driver = self.get_loggedin(args, driver)

            # OTP step
            if self.args.get("otp", {}).get("enabled", False):
                otp_code = self.wait_for_otp()
                if otp_code:
                    self.enter_otp(otp_code, driver)
                else:
                    print("Warning: OTP not received, retrying login...")
                    continue

            time.sleep(self.args["avrg_delay"])

            try:
                driver.find_elements(By.XPATH, args["ensure_login"])
                jwt = driver.execute_script("return window.sessionStorage.JWT")
                if not isinstance(jwt, str) or len(jwt) < 10:
                    jwt = driver.execute_script("return window.localStorage.JWT")
                if not isinstance(jwt, str) or len(jwt) < 10:
                    print("Warning: could not retrieve a valid JWT from sessionStorage or localStorage.")
                    continue
            except Exception:
                continue

            if isinstance(jwt, str) and 10 < len(jwt):
                return jwt
        
    def write_auth(self, file_path, jwt):
        if os.path.exists(file_path):
            file_path = os.path.realpath(file_path)
            os.remove(file_path)

        f = open(file_path, "a")

        if not isinstance(jwt, str) or 10 > len(jwt):
            return False

        f.write(jwt)
        f.close()
        return True
    
    def intialize(self):
        self.create_driver()
        print("""
██    ██ ███████ ███████          ██ ██     ██ ████████
██    ██ ██      ██               ██ ██     ██    ██
██    ██ █████   ███████          ██ ██  █  ██    ██
 ██  ██  ██           ██     ██   ██ ██ ███ ██    ██
  ████   ██      ███████      █████   ███ ███     ██ ██ ██ ██""")

        print("\n")
        print("Started at:", end =" ")
        print(datetime.now())
        print("Generating JWT for VFS slots API...")
        print("\n")

        count = 0
        while True:
            jwt = self.get_jwt(self.args)
            if self.write_auth(self.args["auth_path"], jwt):
                count += 1
                # # Printing the JWT, Time and Count
                # print("JWT:", end =" ")
                # print(jwt)
                # print("Time:", end =" ")
                # print(datetime.now(), end =" --- Count: ")
                # print(count)
                # print("====")
                print(".", end="", flush=True),
                # Putting the script to sleep for the delay
                time.sleep(self.args["refr_delay"])

def main(params):
    params = open(params, "r")
    params = json.loads(params.read())
    # creating object of the class
    auth = AuthVFS(params, "")
    auth.intialize()

if __name__ == "__main__":
    main("./auth_creds.json")
