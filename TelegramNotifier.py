#!/usr/bin/env python
import requests


class TelegramNotifier:
    def __init__(self, config):
        self.bot_token = config["bot_token"]
        self.chat_id = config["chat_id"]
        self.enabled = config.get("enabled", True)

    def send_message(self, message):
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"Warning: Telegram notification failed: {e}", flush=True)
            return False

    def notify_slot_found(self, center_name, earliest_date, booking_url=None, slot_details=None):
        message = "🟢 <b>VFS SLOT BULUNDU!</b>\n\n"
        message += f"🏢 Merkez: <b>{center_name}</b>\n"
        message += f"📅 En Erken Tarih: <b>{earliest_date}</b>\n"
        if slot_details:
            message += f"👤 Başvuru Sahibi: {slot_details}\n"
        message += "\n⚡ Hemen randevu alın!"
        if booking_url:
            message += f"\n🔗 {booking_url}"
        return self.send_message(message)

    def notify_status(self, message):
        return self.send_message(message)
