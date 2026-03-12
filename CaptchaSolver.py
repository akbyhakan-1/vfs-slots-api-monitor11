"""2Captcha Cloudflare Turnstile solver."""
import time
import requests


class CaptchaSolver:
    """Solve Cloudflare Turnstile using 2Captcha API."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://2captcha.com"

    def solve_turnstile(self, site_url, sitekey, timeout=120):
        """Submit Turnstile challenge to 2Captcha and wait for solution.
        
        Args:
            site_url: The URL of the page with Turnstile (e.g. https://visa.vfsglobal.com/tur/tr/nld/login)
            sitekey: The Turnstile sitekey from the page
            timeout: Max seconds to wait for solution
            
        Returns:
            str: The solution token, or None if failed
        """
        print(f"2Captcha: Submitting Turnstile challenge for {site_url}...", flush=True)
        
        # Step 1: Submit the captcha
        payload = {
            "key": self.api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": site_url,
            "json": 1,
        }
        try:
            resp = requests.post(f"{self.base_url}/in.php", data=payload, timeout=30)
            result = resp.json()
        except Exception as e:
            print(f"2Captcha: Submit error: {e}", flush=True)
            return None

        if result.get("status") != 1:
            print(f"2Captcha: Submit failed: {result.get('request')}", flush=True)
            return None

        captcha_id = result["request"]
        print(f"2Captcha: Captcha ID: {captcha_id}, waiting for solution...", flush=True)

        # Step 2: Poll for solution
        params = {
            "key": self.api_key,
            "action": "get",
            "id": captcha_id,
            "json": 1,
        }
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(5)
            try:
                resp = requests.get(f"{self.base_url}/res.php", params=params, timeout=30)
                result = resp.json()
            except Exception as e:
                print(f"2Captcha: Poll error: {e}", flush=True)
                continue

            if result.get("status") == 1:
                token = result["request"]
                print("2Captcha: Turnstile solved successfully!", flush=True)
                return token
            elif result.get("request") == "CAPCHA_NOT_READY":
                print("2Captcha: Still solving...", flush=True)
            else:
                print(f"2Captcha: Error: {result.get('request')}", flush=True)
                return None

        print("2Captcha: Timed out waiting for solution.", flush=True)
        return None
