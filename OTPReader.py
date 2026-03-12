#!/usr/bin/env python
import imaplib
import email
import re
import time
from datetime import datetime, timedelta, timezone


class OTPReader:
    def __init__(self, config):
        self.imap_server = config["imap_server"]  # imap.gmail.com
        self.imap_port = config.get("imap_port", 993)
        self.email_user = config["email_user"]
        self.email_pass = config["email_pass"]  # Gmail App Password
        self.sender_filter = config.get("sender_filter", "donotreply@vfshelpline.com")
        self.subject_filter = config.get("subject_filter", "One Time Password")
        self.otp_timeout = config.get("otp_timeout", 300)  # 5 minutes
        self.otp_pattern = re.compile(
            config.get("otp_pattern", r"The OTP for your application with VFS Global is (\d{6})")
        )
        self.mail = None

    def connect(self):
        """Establish SSL IMAP connection."""
        self.mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        self.mail.login(self.email_user, self.email_pass)
        self.mail.select("inbox")

    def disconnect(self):
        """Close IMAP connection gracefully."""
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except Exception:
                pass
            self.mail = None

    def _extract_otp_from_message(self, msg):
        """Extract 6-digit OTP from email message body."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/plain", "text/html"):
                    try:
                        body += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            except Exception:
                pass

        match = self.otp_pattern.search(body)
        if match:
            return match.group(1)
        return None

    def fetch_otp(self, login_time=None):
        """
        Search inbox for a VFS OTP email received after login_time.
        Returns the 6-digit OTP string, or None if not found.
        login_time: datetime (UTC-aware). Defaults to now - otp_timeout seconds.
        """
        if login_time is None:
            login_time = datetime.now(timezone.utc) - timedelta(seconds=self.otp_timeout)

        # IMAP date search uses date only (no time), so fetch today's and yesterday's mail
        # and filter by actual received time afterward.
        date_str = login_time.strftime("%d-%b-%Y")
        # Escape any double-quotes in user-supplied filter values to prevent malformed IMAP commands
        sender = self.sender_filter.replace('"', '\\"')
        subject = self.subject_filter.replace('"', '\\"')
        search_criteria = (
            f'(FROM "{sender}" SUBJECT "{subject}" SINCE "{date_str}")'
        )

        try:
            status, data = self.mail.search(None, search_criteria)
        except Exception:
            return None

        if status != "OK" or not data or not data[0]:
            return None

        # Iterate newest first - only check last 3 emails to avoid IMAP timeout
        message_ids = data[0].split()
        for msg_id in reversed(message_ids[-3:]):
            try:
                status, msg_data = self.mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # Check received date
                date_header = msg.get("Date", "")
                try:
                    msg_date = email.utils.parsedate_to_datetime(date_header)
                    # Make login_time naive if msg_date is naive, or compare aware
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                    if msg_date < login_time:
                        continue
                except Exception:
                    pass  # If we can't parse the date, still try to read OTP

                otp = self._extract_otp_from_message(msg)
                if otp:
                    return otp
            except Exception:
                continue

        return None

    def wait_for_otp(self, poll_interval=5, login_time=None):
        """
        Poll inbox until OTP is found or otp_timeout expires.
        Returns the 6-digit OTP string, or None on timeout.
        """
        if login_time is None:
            login_time = datetime.now(timezone.utc)

        deadline = time.time() + self.otp_timeout
        print("Waiting for OTP email...", flush=True)
        while time.time() < deadline:
            try:
                # Re-select inbox to refresh unseen messages
                self.mail.select("inbox")
                otp = self.fetch_otp(login_time=login_time)
                if otp:
                    print(f"OTP received.", flush=True)
                    return otp
            except Exception as e:
                print(f"OTP check error: {e}", flush=True)
                try:
                    self.connect()
                except Exception:
                    pass
            time.sleep(poll_interval)

        print("OTP timeout: no OTP email received within the allowed time.", flush=True)
        return None
