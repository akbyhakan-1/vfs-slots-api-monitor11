# VFS slots API monitor
These are some **Python 3** scripts written for monitoring the VFS visa application slots API. **Selenium** with **ChromeDriver(webdriver)** used for collecting the JWT, **tmux** used for the UX and **tail** utility used for printing the output in the terminal.

Configured for **Turkey → Netherlands (Tourism Visa)** — monitors all 8 application centres automatically.

![Screenshot](screenshot.png)

## Application Centres

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
pip install selenium requests playsound
```

## Configuration

### `auth_creds.json` — Login credentials

```json
{
    "url": "https://visa.vfsglobal.com/tur/tr/nld/login",
    "email_id": "//*[@id=\"mat-input-0\"]",
    "password_id": "//*[@id=\"mat-input-1\"]",
    "ensure_login": "//*[contains(text(), 'Start New Booking')]",
    "submit": "//*[contains(text(), 'Sign In')]",
    "user": "YOUR_EMAIL",
    "pass": "YOUR_PASSWORD",
    "auth_path": "./auth.txt",
    "refr_delay": 600,
    "avrg_delay": 10
}
```

### `ping_creds.json` — Slot monitoring

```json
{
    "api_url": "https://lift-api.vfsglobal.com/appointment/CheckIsSlotAvailable",
    "countryCode": "tur",
    "missionCode": "nld",
    "visaCategoryCode": "NSTOURISM",
    "loginUser": "YOUR_EMAIL",
    "payCode": "",
    "roleName": "Individual",
    "centers": [
        {"name": "Ankara", "vacCode": "NANKA"},
        {"name": "Antalya", "vacCode": "NANT"},
        {"name": "Bursa", "vacCode": "NBUR"},
        {"name": "Edirne", "vacCode": "NEDIE"},
        {"name": "Gaziantep", "vacCode": "NGAZ"},
        {"name": "Istanbul (Altunizade)", "vacCode": "NALT"},
        {"name": "Istanbul (Istinye)", "vacCode": "NISTA"},
        {"name": "Izmir", "vacCode": "ADB"}
    ],
    "paths": {
        "auth": "./auth.txt",
        "output": "./output.txt"
    },
    "sound": "./alert.mp3",
    "delay_between_centers": 3,
    "delay_between_rounds": 30
}
```

- `delay_between_centers` — seconds to wait between each centre query (default: 3)
- `delay_between_rounds` — seconds to wait between full rounds of all 8 centres (default: 30)

## Usage

```bash
# 1. Clone the repository
git clone https://github.com/akbyhakan-1/vfs-slots-api-monitor11.git
cd vfs-slots-api-monitor11

# 2. Install dependencies
pip install selenium requests playsound

# 3. Rename and fill in your credentials
cp example.auth_creds.json auth_creds.json
cp example.ping_creds.json ping_creds.json
# Edit auth_creds.json and ping_creds.json with your VFS account details

# 4. Get the JWT token first
python3 AuthVFS.py

# 5. In another terminal, start slot monitoring
python3 PingVFS.py

# OR run everything together with tmux
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
- All results are saved to `output.txt`

## License
Copyright (c) 2021 [CodeMascot](https://www.codemascot.com/) AKA [Khan Mohammad R.](https://www.codemascot.com/)

Good news, these scripts are free for everyone! Since these are released under the [MIT License](LICENSE) you can use them free of charge for your personal or commercial interest as long as you follow the [MIT License](LICENSE).

## Contributing

All feedback / bug reports / pull requests are welcome.
