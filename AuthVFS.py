#!/usr/bin/env python
import os
import time
import random
import json
from datetime import datetime, timezone, timedelta
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, InvalidSessionIdException
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
        """Type the OTP code into the OTP input field, handle Cloudflare checkbox, and submit."""
        args = self.args
        try:
            # 1. Enter OTP code
            otp_input = driver.find_element(By.XPATH, args["otp_input"])
            otp_input.clear()
            otp_input.send_keys(otp_code)
            time.sleep(1)

            # 2. Cloudflare checkbox'a tıkla (varsa)
            try:
                cloudflare_xpath = args.get("cloudflare_checkbox", "//input[@type='checkbox']")
                # Cloudflare checkbox iframe içinde olabilir
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                clicked = False
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        checkbox = driver.find_element(By.XPATH, cloudflare_xpath)
                        checkbox.click()
                        clicked = True
                        driver.switch_to.default_content()
                        break
                    except Exception:
                        driver.switch_to.default_content()
                        continue

                if not clicked:
                    # Try in main page
                    try:
                        checkbox = driver.find_element(By.XPATH, cloudflare_xpath)
                        checkbox.click()
                    except NoSuchElementException:
                        pass  # Cloudflare checkbox not present, skip

                time.sleep(2)  # Wait for Cloudflare verification
            except Exception as e:
                print(f"Note: Cloudflare checkbox handling: {e}")
                driver.switch_to.default_content()

            # 3. Click the submit button
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
