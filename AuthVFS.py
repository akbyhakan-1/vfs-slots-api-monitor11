#!/usr/bin/env python
import os
import time
import json
from datetime import datetime, timezone
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, InvalidSessionIdException
from OTPReader import OTPReader
from CaptchaSolver import CaptchaSolver


class AuthVFS:
    # default constructor
    def __init__(self, args, jwt):
        self.args = args
        self.jwt = jwt
        self._otp_reader = None
        # Initialize 2Captcha solver if configured
        captcha_config = args.get("captcha", {})
        api_key = captcha_config.get("api_key", "")
        self.captcha_solver = CaptchaSolver(api_key) if api_key else None

    def create_driver(self):
        self.safe_quit()
        options = uc.ChromeOptions()
        # Use existing Chrome user profile to pass Cloudflare verification
        # The real browser cookies and history help Cloudflare recognize as a real user
        options.add_argument("--user-data-dir=C:/Users/akbyh/AppData/Local/Google/Chrome/User Data")
        options.add_argument("--profile-directory=Default")
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

    def wait_for_cloudflare(self, driver, timeout=120):
        """Wait for Cloudflare verification page — with user profile, usually passes automatically.
        Falls back to 2Captcha if automatic verification fails."""
        start_time = time.time()

        # Phase 1: Wait for automatic pass (Chrome profile usually handles this)
        auto_timeout = min(timeout, 30)  # Wait max 30 seconds for auto pass
        while time.time() - start_time < auto_timeout:
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

        # Phase 2: Try 2Captcha if available
        if self.captcha_solver:
            print("Automatic Cloudflare pass failed, trying 2Captcha...", flush=True)
            token = self._solve_with_2captcha(driver)
            if token:
                return True

        # Phase 3: Keep waiting until full timeout
        while time.time() - start_time < timeout:
            try:
                current_title = driver.title.lower()
            except (InvalidSessionIdException, Exception):
                time.sleep(3)
                continue

            if "bir dakika" not in current_title and "just a moment" not in current_title:
                print("Cloudflare verification passed.", flush=True)
                return True

            time.sleep(3)

        print("Warning: Cloudflare verification timed out, reloading page...", flush=True)
        return False

    def _solve_with_2captcha(self, driver):
        """Extract Turnstile sitekey from page and solve with 2Captcha."""
        import re
        import urllib.parse

        try:
            sitekey = None

            # Method 1: Look for turnstile div with data-sitekey
            try:
                turnstile_divs = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
                for div in turnstile_divs:
                    sitekey = div.get_attribute("data-sitekey")
                    if sitekey:
                        break
            except Exception:
                pass

            # Method 2: Look in iframe src
            if not sitekey:
                try:
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        src = iframe.get_attribute("src") or ""
                        if src:
                            parsed_src = urllib.parse.urlparse(src)
                            hostname = parsed_src.hostname or ""
                            is_cf = (hostname == "challenges.cloudflare.com" or
                                     hostname.endswith(".challenges.cloudflare.com"))
                            if is_cf or "turnstile" in parsed_src.path:
                                params = urllib.parse.parse_qs(parsed_src.query)
                                if "k" in params:
                                    sitekey = params["k"][0]
                                break
                except Exception:
                    pass

            # Method 3: Search page source for sitekey pattern
            if not sitekey:
                try:
                    page_source = driver.page_source
                    match = re.search(r'sitekey["\s:=]+["\']?(0x[0-9a-fA-F]+)', page_source)
                    if match:
                        sitekey = match.group(1)
                except Exception:
                    pass

            if not sitekey:
                print("2Captcha: Could not find Turnstile sitekey on page.", flush=True)
                return None

            print(f"2Captcha: Found sitekey: {sitekey[:20]}...", flush=True)

            # Solve with 2Captcha
            current_url = driver.current_url
            token = self.captcha_solver.solve_turnstile(current_url, sitekey)

            if not token:
                return None

            # Inject the solution token into the page
            driver.execute_script("""
                var token = arguments[0];
                // Try to find and fill cf-turnstile-response input
                var inputs = document.querySelectorAll('[name="cf-turnstile-response"]');
                inputs.forEach(function(input) {
                    input.value = token;
                });

                // Try to trigger the callback
                if (typeof window.turnstileCallback === 'function') {
                    window.turnstileCallback(token);
                }

                // Fallback: find the form and add the token
                var forms = document.querySelectorAll('form');
                forms.forEach(function(form) {
                    var existing = form.querySelector('[name="cf-turnstile-response"]');
                    if (!existing) {
                        var hidden = document.createElement('input');
                        hidden.type = 'hidden';
                        hidden.name = 'cf-turnstile-response';
                        hidden.value = token;
                        form.appendChild(hidden);
                    }
                });
            """, token)

            print("2Captcha: Token injected into page.", flush=True)
            time.sleep(5)  # Wait for page to process token

            # Check if Cloudflare passed
            try:
                current_title = driver.title.lower()
                if "bir dakika" not in current_title and "just a moment" not in current_title:
                    print("2Captcha: Cloudflare verification passed!", flush=True)
                    return True
            except Exception:
                pass

            return None

        except Exception as e:
            print(f"2Captcha: Error: {e}", flush=True)
            return None

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
            print(f"Warning: Gmail IMAP connection error: {e}", flush=True)
            print("Check: are email_user and email_pass in auth_creds.json correct?", flush=True)
            print("App Password must be 16 characters without spaces (e.g., zkihpinfhrftxmql)", flush=True)
            self._otp_reader = None  # Reset so next call retries the connection
            return None
        return reader.wait_for_otp(
            poll_interval=poll_interval,
            login_time=datetime.now(timezone.utc),
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
            if not self.wait_for_cloudflare(driver, timeout=60):
                # If not passed, reload the page and retry
                print("Cloudflare not passed, retrying...", flush=True)
                continue

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
        print("IMPORTANT: Please close ALL Chrome windows before running this script!", flush=True)
        print("(Chrome profile can only be used by one process at a time.)", flush=True)
        print("Press Enter when ready...", flush=True)
        input()
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
