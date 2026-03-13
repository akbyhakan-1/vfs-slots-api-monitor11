#!/usr/bin/env python
import os
import sys
import time
import random
import json
import argparse
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(errors='replace')
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import InvalidSessionIdException, TimeoutException
from OTPReader import OTPReader


class AuthVFS:
    # default constructor
    def __init__(self, args, jwt):
        self.args = args
        self.jwt = jwt
        self._otp_reader = None

    def create_driver(self):
        self.safe_quit()
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        self.driver = uc.Chrome(
            options=options,
            version_main=145
        )

    def safe_quit(self):
        """Safely quit the driver, ignoring errors."""
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
        except Exception:
            pass

    def wait_for_cloudflare(self, driver, timeout=20):
        """Wait up to timeout seconds for Cloudflare verification to pass automatically."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                current_title = driver.title.lower()
            except (InvalidSessionIdException, Exception):
                print("Warning: Could not read page title, waiting...", flush=True)
                time.sleep(3)
                continue

            if "bir dakika" not in current_title and "just a moment" not in current_title:
                print("Cloudflare verification passed (automatic).", flush=True)
                return True

            print("Waiting for Cloudflare verification...", flush=True)
            time.sleep(3)

        print("Warning: Cloudflare verification timed out.", flush=True)
        return False

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
            # Wait for Angular page to fully load (max 30 seconds)
            wait = WebDriverWait(driver, 30)

            # Wait for email field to be present
            email = wait.until(EC.presence_of_element_located((By.XPATH, args["email_id"])))
            password = wait.until(EC.presence_of_element_located((By.XPATH, args["password_id"])))

            print("Login form found, filling credentials...", flush=True)
        except Exception as e:
            print(f"Warning: Login form not found: {e}", flush=True)
            return False

        # Fill up the form fields with necessary credentials.
        email.clear()
        email.send_keys(args["user"])
        time.sleep(1)
        password.clear()
        password.send_keys(args["pass"])
        time.sleep(2)  # Wait for Angular to detect input and enable submit button

        # Now wait for submit button to become clickable (it starts disabled)
        try:
            submit = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, args["submit"]))
            )
        except Exception as e:
            print(f"Warning: Submit button not clickable: {e}", flush=True)
            # Try clicking anyway
            try:
                submit = driver.find_element(By.XPATH, args["submit"])
            except Exception:
                print("Warning: Submit button not found at all.", flush=True)
                return False

        # Submit the form.
        print("Submitting login form...", flush=True)
        submit.click()
        # Wait for the response to come.
        time.sleep(self.args["avrg_delay"])
        # Return the driver instance.
        return driver

    def is_already_logged_in(self, driver):
        """Check if the page already shows the logged-in state (e.g. 'Start New Booking').

        Uses a very short timeout so we don't block the flow when OTP is required.
        Returns True if the ensure_login element is found, False otherwise.
        """
        ensure_xpath = self.args.get("ensure_login", "")
        if not ensure_xpath:
            return False
        try:
            timeout = self.args.get("otp", {}).get("login_check_timeout", 4)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, ensure_xpath))
            )
            return True
        except TimeoutException:
            return False

    def detect_otp_screen(self, driver):
        """Check whether the OTP input field is currently visible on the page.

        Uses a short timeout so we detect the screen quickly without long waits.
        Returns True if the OTP input is present, False otherwise.
        """
        otp_xpath = self.args.get("otp_input", "//input[contains(@id, 'mat-input')]")
        try:
            timeout = self.args.get("otp", {}).get("screen_check_timeout", 6)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, otp_xpath))
            )
            return True
        except TimeoutException:
            return False

    def wait_for_otp(self):
        """Fetch OTP via configured method (currently: email IMAP)."""
        otp_config = self.args.get("otp", {})
        poll_interval = otp_config.get("poll_interval", 5)
        try:
            reader = self._get_otp_reader()
        except Exception as e:
            print(f"Warning: Gmail IMAP connection error: {e}", flush=True)
            print("Check: are email_user and email_pass in auth_creds.json correct?", flush=True)
            print("App Password must be 16 characters without spaces (e.g., zkihpinfhrftxmql)", flush=True)
            self._otp_reader = None  # Reset so next call retries the connection
            return None
        return reader.wait_for_otp(
            poll_interval=poll_interval,
            login_time=datetime.now(timezone.utc) - timedelta(seconds=60),
        )

    def enter_otp(self, otp_code, driver):
        """Type the OTP code into the OTP input field and submit."""
        args = self.args
        try:
            # 1. Wait for OTP input field to appear (may take a moment after login submit)
            otp_xpath = args.get("otp_input", "//input[contains(@id, 'mat-input')]")
            fallback_input_xpath = "//input[contains(@id, 'mat-input')]"
            try:
                otp_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, otp_xpath))
                )
            except TimeoutException:
                if otp_xpath != fallback_input_xpath:
                    # Fallback: try a broader Angular Material input selector
                    print("OTP input not found with configured XPath, trying fallback...", flush=True)
                    otp_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, fallback_input_xpath))
                    )
                else:
                    raise

            otp_input.clear()
            otp_input.send_keys(otp_code)
            print("OTP code entered successfully.", flush=True)
            time.sleep(2)

            # 2. Click the submit button
            otp_submit_xpath = args.get("otp_submit", "//button[contains(.,'Oturum')]")
            fallback_submit_xpath = "//button[contains(.,'Oturum')]"
            try:
                otp_submit = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, otp_submit_xpath))
                )
            except TimeoutException:
                if otp_submit_xpath != fallback_submit_xpath:
                    # Fallback: try a broader button selector
                    print("OTP submit button not found with configured XPath, trying fallback...", flush=True)
                    otp_submit = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, fallback_submit_xpath))
                    )
                else:
                    raise

            otp_submit.click()
            print("OTP submitted.", flush=True)
            time.sleep(self.args["avrg_delay"])
            return True
        except Exception as e:
            print(f"Warning: OTP entry failed: {e}", flush=True)
            print("Retrying login from the start.", flush=True)
            return False

    def get_jwt(self, args):
        driver = self.driver
        while True:
            try:
                driver.get(args["url"])
            except Exception as e:
                print(f"Warning: Driver error: {e}, recreating driver...", flush=True)
                try:
                    self.create_driver()
                    driver = self.driver
                except Exception as create_err:
                    print(f"Warning: Could not recreate driver: {create_err}, retrying in 5s...", flush=True)
                    time.sleep(5)
                continue

            # Wait for Cloudflare verification
            if not self.wait_for_cloudflare(driver):
                # Cloudflare not passed — recreate driver for a fresh fingerprint and retry
                print("Cloudflare not passed, recreating driver for new fingerprint...", flush=True)
                try:
                    self.create_driver()
                    driver = self.driver
                except Exception as create_err:
                    print(f"Warning: Could not recreate driver: {create_err}, retrying...", flush=True)
                time.sleep(random.uniform(2, 5))
                continue

            # Let the page load fully.
            time.sleep(self.args["avrg_delay"])
            login_result = self.get_loggedin(args, driver)
            if login_result is False:
                print("Warning: Could not fill login form, retrying...", flush=True)
                continue
            driver = login_result

            # OTP step — screen-detection based
            if self.args.get("otp", {}).get("enabled", False):
                # First check: did we land directly on the logged-in page?
                if self.is_already_logged_in(driver):
                    print("Login successful without OTP, skipping OTP step.", flush=True)
                # Second check: is the OTP input field visible?
                elif self.detect_otp_screen(driver):
                    print("OTP screen detected, waiting for OTP...", flush=True)
                    otp_code = self.wait_for_otp()
                    if otp_code:
                        self.enter_otp(otp_code, driver)
                    else:
                        print("Warning: OTP not received, retrying login...", flush=True)
                        continue
                else:
                    print("No OTP screen detected, proceeding to JWT extraction...", flush=True)

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
        print(r"""
 =============================================
  __   _____ ___       _ _  _ _____
  \ \ / / __/ __|     | | || |_   _|
   \ V /| _|\___ \ _  | | || | | |
    \_/ |_| |____/\___|_|\__/  |_|
  VFS JWT Authenticator
 =============================================
""")

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
    parser = argparse.ArgumentParser(description="VFS JWT authenticator")
    parser.add_argument(
        "--country",
        help="Country code to authenticate (e.g. nld, hrv). Reads from countries/<code>/auth_creds.json",
        default=None,
    )
    args = parser.parse_args()

    if args.country:
        creds_path = f"./countries/{args.country}/auth_creds.json"
    else:
        creds_path = "./auth_creds.json"

    main(creds_path)
