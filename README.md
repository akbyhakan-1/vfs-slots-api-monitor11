# VFS slots API monitor
These are some **Python 3** scripts written for monitoring the VFS visa application slots API. **Selenium** with **ChromeDriver(webdriver)** used for collecting the JWT, **tmux** used for the UX and **tail** utility used for printing the output in the terminal.

Supports multiple countries simultaneously — currently configured for **Netherlands** and **Croatia** (Turkey applicants).

![Screenshot](screenshot.png)

## Features

- 🌍 **Multi-country support** — monitor Netherlands, Croatia, or any VFS country in parallel
- 🔐 Automatic OTP reading via Gmail IMAP (VFS now requires OTP on every login)
- 📲 Telegram notifications when a slot is found
- 🔊 Desktop notification + sound alert on slot found
- 🖥️ **Web dashboard** — real-time status for all countries at `http://localhost:8080`
- 🔄 Monitors all configured VFS centres in a loop

## Application Centres

### Netherlands (nld)

| # | Centre | vacCode |
|---|---|---|
| 1 | Ankara | `NANKA` |
| 2 | Antalya | `NANT` |
| 3 | Bursa | `NBUR` |
| 4 | Edirne | `NEDIE` |
| 5 | Gaziantep | `NGAZ` |
| 6 | Istanbul (Altunizade) | `NALT` |
| 7 | Istanbul (Istinye) | `NISTA` |
| 8 | Izmir | `ADB` |

### Croatia (hrv)

> ⚠️ **Note:** The vacCodes below are placeholders. Check the actual codes on the VFS Global portal for Croatia (Turkey applicants) and update `countries/hrv/ping_creds.json` accordingly.

| # | Centre | vacCode |
|---|---|---|
| 1 | Ankara | `HANKA` *(placeholder)* |
| 2 | Istanbul | `HIST` *(placeholder)* |

## Installation

Hints:
- These scripts are crafted for _Linux_ machines.
- You need `python3` installed and configured in your machine.
- Selenium and ChromeWebdriver needed to be installed in the machine.
- For using the `monitor` UX `tmux` also needed to be installed in the machine.
- Understand the `monitor`, `.gitignore` file and the `main()` function of the `*.py` files.
- Rename the `example.*.json` files to `*.json` and set necessary credentials in there.
- Place a `*.mp3` music file as `alert.mp3` in the project root directory.

```bash
pip install -r requirements.txt
```

## Configuration

### Directory structure

```
countries/
├── nld/
│   ├── auth_creds.json    ← copy from countries/nld/auth_creds.json and fill in
│   ├── ping_creds.json    ← copy from countries/nld/ping_creds.json and fill in
│   ├── auth.txt           ← auto-generated (JWT token)
│   └── output.txt         ← auto-generated (log)
└── hrv/
    ├── auth_creds.json
    ├── ping_creds.json
    ├── auth.txt
    └── output.txt
```

Each `countries/<code>/auth_creds.json` and `countries/<code>/ping_creds.json` file follows the same format as the root-level example files, but also includes `country_name` and `country_code` fields, and paths point to `./countries/<code>/auth.txt` etc.

### `auth_creds.json` — Login credentials with OTP

```json
{
    "country_name": "Netherlands",
    "country_code": "nld",
    "url": "https://visa.vfsglobal.com/tur/tr/nld/login",
    "email_id": "//*[@id='email']",
    "password_id": "//*[@id='password']",
    "ensure_login": "//*[contains(text(), 'Start New Booking')]",
    "submit": "//button[contains(.,'Oturum')]",
    "otp_input": "//input[contains(@id, 'mat-input')]",
    "otp_submit": "//button[contains(.,'Oturum')]",
    "user": "YOUR_VFS_EMAIL",
    "pass": "YOUR_VFS_PASSWORD",
    "auth_path": "./countries/nld/auth.txt",
    "refr_delay": 600,
    "avrg_delay": 10,
    "otp": {
        "enabled": true,
        "method": "email",
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "email_user": "YOUR_GMAIL_ADDRESS",
        "email_pass": "YOUR_GMAIL_APP_PASSWORD",
        "sender_filter": "donotreply@vfshelpline.com",
        "subject_filter": "One Time Password",
        "otp_timeout": 300,
        "poll_interval": 5
    }
}
```

### `ping_creds.json` — Slot monitoring with Telegram

```json
{
    "country_name": "Netherlands",
    "country_code": "nld",
    "api_url": "https://lift-api.vfsglobal.com/appointment/CheckIsSlotAvailable",
    "countryCode": "tur",
    "missionCode": "nld",
    "visaCategoryCode": "NSTOURISM",
    "loginUser": "YOUR_EMAIL",
    "payCode": "",
    "roleName": "Individual",
    "booking_url": "https://visa.vfsglobal.com/tur/tr/nld/book-appointment",
    "centers": [
        {"name": "Ankara", "vacCode": "NANKA"},
        {"name": "Istanbul (Istinye)", "vacCode": "NISTA"}
    ],
    "paths": {
        "auth": "./countries/nld/auth.txt",
        "output": "./countries/nld/output.txt"
    },
    "sound": "./alert.mp3",
    "delay_between_centers": 3,
    "delay_between_rounds": 30,
    "telegram": {
        "enabled": true,
        "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
        "chat_id": "YOUR_TELEGRAM_CHAT_ID"
    }
}
```

- `delay_between_centers` — seconds to wait between each centre query (default: 3)
- `delay_between_rounds` — seconds to wait between full rounds of all centres (default: 30)
- `booking_url` — URL sent in Telegram notifications for quick access to the booking page

## OTP Setup (Gmail IMAP)

VFS Global now requires a One-Time Password (OTP) sent to your registered email on every login. The system reads this code automatically via IMAP.

**You must use a Gmail App Password — your normal Gmail password will not work over IMAP.**

### Creating a Gmail App Password

1. Go to your Google Account → **Security**
2. Make sure **2-Step Verification** is enabled
3. Go to **Security → App passwords** (search for "App passwords" if not visible)
4. Select app: **Mail**, device: **Other** (give it a name like "VFS Monitor")
5. Click **Generate** — copy the 16-character password
6. Use this password as `email_pass` in `auth_creds.json`

### Gmail IMAP Settings

| Setting | Value |
|---|---|
| Server | `imap.gmail.com` |
| Port | `993` |
| SSL | Yes |

### How OTP Reading Works

1. `AuthVFS.py` submits your email + password on the VFS login page
2. VFS sends a 6-digit OTP to your registered email (`donotreply@vfshelpline.com`)
3. `OTPReader.py` connects to your Gmail via IMAP and polls every 5 seconds
4. When the OTP email arrives, the code is extracted with regex and entered automatically
5. After successful verification, the JWT token is saved to `auth.txt`

The OTP email looks like:
> *"Dear Applicant, The OTP for your application with VFS Global is 667177. The OTP will expire in 5 minutes."*

## Telegram Notifications

When a slot is found, a Telegram message is sent automatically:

```
🟢 VFS SLOT BULUNDU!

🏢 Merkez: Gaziantep
📅 En Erken Tarih: 04/07/2026 00:00:00
👤 Başvuru Sahibi: 1

⚡ Hemen randevu alın!
🔗 https://visa.vfsglobal.com/tur/tr/nld/book-appointment
```

### Setting Up a Telegram Bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts to create your bot
3. Copy the **bot token** (looks like `123456789:AABBcc...`)
4. Start a conversation with your new bot (send it any message)
5. Get your **chat ID** by opening:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   Look for `"chat":{"id":...}` in the response
6. Set `bot_token` and `chat_id` in `ping_creds.json`

## Usage

### Single country (backward compatible)

```bash
# Legacy mode — reads from root-level auth_creds.json / ping_creds.json
python3 AuthVFS.py
python3 PingVFS.py

# Per-country mode — reads from countries/<code>/
python3 AuthVFS.py --country nld
python3 PingVFS.py --country nld

python3 AuthVFS.py --country hrv
python3 PingVFS.py --country hrv
```

### All countries at once

```bash
python3 run_all.py
```

`run_all.py` scans `countries/*/` for valid config pairs and launches `AuthVFS.py` + `PingVFS.py` for each country in separate threads.

### Web Dashboard

```bash
python3 dashboard/server.py
```

Then open **http://localhost:8080** in your browser. The dashboard:
- Shows all monitored countries as cards
- Color-codes each centre: 🟢 slot found, 🔴 no slot, 🟡 waitlist/error, ⚪ not yet checked
- Auto-refreshes every 10 seconds
- Shows earliest available date when a slot is found
- Works on mobile (responsive)
- Dark theme, Turkish UI

The dashboard reads `dashboard_status.json` in the project root, which is updated by `PingVFS.py` after every centre check.

### Full setup example (Netherlands + Croatia)

```bash
# 1. Clone
git clone https://github.com/akbyhakan-1/vfs-slots-api-monitor11.git
cd vfs-slots-api-monitor11

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit configs for each country (the example files are committed to the repo)
# Edit countries/nld/auth_creds.json — set user, pass, email credentials
# Edit countries/nld/ping_creds.json — set loginUser, telegram config
# Edit countries/hrv/auth_creds.json and countries/hrv/ping_creds.json similarly

# 4. Run everything
python3 run_all.py

# 5. Open dashboard
python3 dashboard/server.py
# → http://localhost:8080

# OR run with tmux
chmod +x monitor
./monitor
```

## Output

Each query prints a line like:

```
[2026-03-12 11:00:00] Ankara → No appointment available
[2026-03-12 11:00:03] Antalya → Waitlist (no slot)
[2026-03-12 11:00:06] Istanbul (Istinye) → 🎉 SLOT FOUND! Earliest: 04/07/2026 00:00:00
```

When a slot is found:
- A desktop notification (`notify-send`) is shown with the centre name and earliest date
- The alert sound (`alert.mp3`) is played
- A Telegram message is sent (if configured)
- All results are saved to `countries/<code>/output.txt`
- The dashboard is updated in real-time

## License
Copyright (c) 2021 [CodeMascot](https://www.codemascot.com/) AKA [Khan Mohammad R.](https://www.codemascot.com/)

Good news, these scripts are free for everyone! Since these are released under the [MIT License](LICENSE) you can use them free of charge for your personal or commercial interest as long as you follow the [MIT License](LICENSE).

## Contributing

All feedback / bug reports / pull requests are welcome.
