# ≡ƒÜÇ OTPMAN 2 (KSI IPRN) Bot ΓÇö 24/7 Hosting & Setup Guide

Standalone, high-performance Telegram bot that receives A2P OTP SMS from the **KSI IPRN panel** and forwards them to your Telegram groups in real-time with **persistent SQLite database (`bot3_database.db`)** and **28-hour cloud memory (`otpman2_seen_messages.json`)**.

---

## ≡ƒôü Files in This Folder

| File | Description |
| :--- | :--- |
| [`bot.py`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/bot.py) | Self-contained single script (auto-installs dependencies, 28h memory) |
| [`.github/workflows/run_bot.yml`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/.github/workflows/run_bot.yml) | 24/7 GitHub Actions always-online runner (zero-downtime loop) |
| [`PUSH_TO_GITHUB.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/PUSH_TO_GITHUB.bat) | 1-Click push script for PC (pushes ONLY bot.py + workflow to GitHub) |
| [`START_BOT.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/START_BOT.bat) | Run bot locally with auto-restart on crash |
| [`TEST_BOT.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/TEST_BOT.bat) | Run complete connection & system diagnostics |
| [`bot3_database.db`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/bot3_database.db) | Dedicated SQLite database for Bot 3 (persisted across restarts) |
| [`.env`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/.env) | Local environment variables & secrets |

---

## ≡ƒöæ GitHub Secrets Configuration (For 24/7 Server Hosting)

Repository: ≡ƒæë **[https://github.com/HimelKhan006/KKH-OTPMAN](https://github.com/HimelKhan006/KKH-OTPMAN)**

Go to: **Settings Γ₧ö Secrets and variables Γ₧ö Actions Γ₧ö New repository secret**

### 1. Required Secrets

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | `8897218550:AAF4-N84Bu...` | Telegram Bot token from [@BotFather](https://t.me/BotFather) |
| `KSI_API_KEY` | `sk_live_Gn3RcrDO...` | KSI Live API key |
| `GIST_TOKEN` | `ghp_yourPersonalAccessToken...` | GitHub Token with `gist` scope *(powers 28h memory)* |
| `TELEGRAM_GROUP_CHAT_ID` | `-1004473973263` | Primary Telegram Group Chat ID |

### 2. Optional Secrets

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `SECONDARY_GROUP_CHAT_ID` | `-1003597354059` | Secondary Telegram Group ID for dual forwarding |
| `ADMIN_USER_IDS` | `6798979733` | Telegram Admin User ID (receives restart alerts via private DM) |
| `GIST_ID` | `abc123def456...` | Gist ID *(Optional ΓÇö bot auto-creates or auto-discovers Gist)* |
| `MESSAGE_TYPE` | `a2p` | Message filter (`a2p` for OTP SMS only) |
| `POLL_INTERVAL_SECONDS` | `12.0` | Polling speed in seconds (default: `12.0` for safe rate limiting) |
| `KSI_BASE_URL` | `https://ksiiprn.com` | KSI API base URL |

---

## Γÿü∩╕Å How to Generate `GIST_TOKEN` (1-Minute Guide)

1. Open GitHub: **[https://github.com/settings/tokens/new](https://github.com/settings/tokens/new)**
2. Set **Note:** `OTP_BOT_STORAGE`
3. Set **Expiration:** `No expiration` (or desired timeframe)
4. Under **Select scopes**, check only: Γ£à **`gist`** (Create gists)
5. Scroll to the bottom and click **Generate token**.
6. Copy the token and save it as the **`GIST_TOKEN`** secret in your GitHub repository!

> ≡ƒÆí **Automatic Gist Management & Deduplication:**
>
> - You do NOT need to create a Gist manually.
> - The bot automatically searches for its existing Gist (`otpman2_seen_messages.json`), reuses it, and **automatically deletes any duplicate Gists**.
> - Pushing code updates never deletes or resets your database or Gist memory!

---

## ≡ƒô▒ Mobile Phone Setup & Upload Guide (No PC Required)

You can upload bot files, configure secrets, and start the 24/7 bot directly from your **mobile phone browser** (Chrome / Safari / Firefox):

### 1. How to Upload and Edit bot.py from Mobile

1. Open your repository on mobile: **[https://github.com/HimelKhan006/KKH-OTPMAN](https://github.com/HimelKhan006/KKH-OTPMAN)**
2. Tap on **`bot.py`**.
3. Tap the **Γ£Å∩╕Å (Pencil icon)** at the top right of the file.
4. Select all text, delete, and paste your updated `bot.py` code.
5. Scroll to the bottom and tap **`Commit changes...`** Γ₧ö **`Commit changes`**.
6. *(Alternative)*: Tap **`Add file`** Γ₧ö **`Upload files`** Γ₧ö select `bot.py` from your phone's file manager Γ₧ö Tap **`Commit changes`**.

### 2. How to Add GitHub Secrets from Mobile

1. In your repository, tap **`Settings`** (if hidden, enable "Desktop site" in your mobile browser menu).
2. Tap **`Secrets and variables`** Γ₧ö **`Actions`**.
3. Tap the green **`New repository secret`** button.
4. Enter `TELEGRAM_BOT_TOKEN`, `KSI_API_KEY`, `GIST_TOKEN`, and `TELEGRAM_GROUP_CHAT_ID`.

### 3. How to Start the Bot from Mobile

1. In your repository, tap the **`Actions`** tab.
2. Tap **`OTPMAN 2 (KSI) 24/7 Always-Online Bot Runner`** on the left menu.
3. Tap the **`Run workflow`** dropdown Γ₧ö Tap the green **`Run workflow`** button.
4. The bot will start immediately in the cloud and run 24/7 even if your phone is turned off! ≡ƒƒó

---

## ≡ƒÆ╗ Running & Deploying from PC

- **1-Click Push from PC:** Double-click `PUSH_TO_GITHUB.bat`
- **Run Diagnostics Locally:** Double-click `TEST_BOT.bat`
- **Start Bot Locally:** Double-click `START_BOT.bat`

---

## ⚡ Zero-Restart Engine (5h 25min Auto-Handover)

This bot uses a **professional zero-restart handover system** — it never shows restart messages and never drops OTPs during session switches.

| Stage | What Happens |
| :--- | :--- |
| **Session Running** | Bot polls live OTPs every 12 seconds, 24/7 |
| **60s Before Timeout** | Bot saves full state (seen IDs, counts, countries) to GitHub Gist with `handover=true` |
| **Clean Exit** | Bot exits with code 0 — workflow immediately triggers next session |
| **New Session Starts** | Bot reads Gist, restores all state, silently continues — zero messages |
| **OTP Gap Recovery** | Any OTPs received during the brief runner switch are delivered on startup |

> ✅ **No restart messages.** Admin is never spammed during routine handovers.
> ✅ **No missed OTPs.** Any OTP received during session switch is caught and delivered.
> ✅ **Counts accumulate.** Bot maintains cumulative totals across all sessions.

### Session Schedule

| Setting | Value | Description |
| :--- | :--- | :--- |
| Session Length | 5h 25min (19,500s) | Each runner session before handover |
| Handover Time | ~1–3 min | Gap between session end and new session start |
| Backup Cron | Every 6h | Failsafe if self-trigger ever fails |

---
# ≡ƒÜÇ OTPMAN 2 (KSI IPRN) Bot ΓÇö 24/7 Hosting & Setup Guide

Standalone, high-performance Telegram bot that receives A2P OTP SMS from the **KSI IPRN panel** and forwards them to your Telegram groups in real-time with **persistent SQLite database (`bot3_database.db`)** and **28-hour cloud memory (`otpman2_seen_messages.json`)**.

---

## ≡ƒôü Files in This Folder

| File | Description |
| :--- | :--- |
| [`bot.py`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/bot.py) | Self-contained single script (auto-installs dependencies, 28h memory) |
| [`.github/workflows/run_bot.yml`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/.github/workflows/run_bot.yml) | 24/7 GitHub Actions always-online runner (zero-downtime loop) |
| [`PUSH_TO_GITHUB.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/PUSH_TO_GITHUB.bat) | 1-Click push script for PC (pushes ONLY bot.py + workflow to GitHub) |
| [`START_BOT.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/START_BOT.bat) | Run bot locally with auto-restart on crash |
| [`TEST_BOT.bat`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/TEST_BOT.bat) | Run complete connection & system diagnostics |
| [`bot3_database.db`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/bot3_database.db) | Dedicated SQLite database for Bot 3 (persisted across restarts) |
| [`.env`](file:///c:/thirdwave%20bot/3_OTPMAN2_BOT/.env) | Local environment variables & secrets |

---

## ≡ƒöæ GitHub Secrets Configuration (For 24/7 Server Hosting)

Repository: ≡ƒæë **[https://github.com/HimelKhan006/KKH-OTPMAN](https://github.com/HimelKhan006/KKH-OTPMAN)**

Go to: **Settings Γ₧ö Secrets and variables Γ₧ö Actions Γ₧ö New repository secret**

### 1. Required Secrets

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | `8897218550:AAF4-N84Bu...` | Telegram Bot token from [@BotFather](https://t.me/BotFather) |
| `KSI_API_KEY` | `sk_live_Gn3RcrDO...` | KSI Live API key |
| `GIST_TOKEN` | `ghp_yourPersonalAccessToken...` | GitHub Token with `gist` scope *(powers 28h memory)* |
| `TELEGRAM_GROUP_CHAT_ID` | `-1004473973263` | Primary Telegram Group Chat ID |

### 2. Optional Secrets

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `SECONDARY_GROUP_CHAT_ID` | `-1003597354059` | Secondary Telegram Group ID for dual forwarding |
| `ADMIN_USER_IDS` | `6798979733` | Telegram Admin User ID (receives restart alerts via private DM) |
| `GIST_ID` | `abc123def456...` | Gist ID *(Optional ΓÇö bot auto-creates or auto-discovers Gist)* |
| `MESSAGE_TYPE` | `a2p` | Message filter (`a2p` for OTP SMS only) |
| `POLL_INTERVAL_SECONDS` | `12.0` | Polling speed in seconds (default: `12.0` for safe rate limiting) |
| `KSI_BASE_URL` | `https://ksiiprn.com` | KSI API base URL |

---

## Γÿü∩╕Å How to Generate `GIST_TOKEN` (1-Minute Guide)

1. Open GitHub: **[https://github.com/settings/tokens/new](https://github.com/settings/tokens/new)**
2. Set **Note:** `OTP_BOT_STORAGE`
3. Set **Expiration:** `No expiration` (or desired timeframe)
4. Under **Select scopes**, check only: Γ£à **`gist`** (Create gists)
5. Scroll to the bottom and click **Generate token**.
6. Copy the token and save it as the **`GIST_TOKEN`** secret in your GitHub repository!

> ≡ƒÆí **Automatic Gist Management & Deduplication:**
>
> - You do NOT need to create a Gist manually.
> - The bot automatically searches for its existing Gist (`otpman2_seen_messages.json`), reuses it, and **automatically deletes any duplicate Gists**.
> - Pushing code updates never deletes or resets your database or Gist memory!

---

## ≡ƒô▒ Mobile Phone Setup & Upload Guide (No PC Required)

You can upload bot files, configure secrets, and start the 24/7 bot directly from your **mobile phone browser** (Chrome / Safari / Firefox):

### 1. How to Upload and Edit bot.py from Mobile

1. Open your repository on mobile: **[https://github.com/HimelKhan006/KKH-OTPMAN](https://github.com/HimelKhan006/KKH-OTPMAN)**
2. Tap on **`bot.py`**.
3. Tap the **Γ£Å∩╕Å (Pencil icon)** at the top right of the file.
4. Select all text, delete, and paste your updated `bot.py` code.
5. Scroll to the bottom and tap **`Commit changes...`** Γ₧ö **`Commit changes`**.
6. *(Alternative)*: Tap **`Add file`** Γ₧ö **`Upload files`** Γ₧ö select `bot.py` from your phone's file manager Γ₧ö Tap **`Commit changes`**.

### 2. How to Add GitHub Secrets from Mobile

1. In your repository, tap **`Settings`** (if hidden, enable "Desktop site" in your mobile browser menu).
2. Tap **`Secrets and variables`** Γ₧ö **`Actions`**.
3. Tap the green **`New repository secret`** button.
4. Enter `TELEGRAM_BOT_TOKEN`, `KSI_API_KEY`, `GIST_TOKEN`, and `TELEGRAM_GROUP_CHAT_ID`.

### 3. How to Start the Bot from Mobile

1. In your repository, tap the **`Actions`** tab.
2. Tap the **`OTPMAN 2 (KSI) 24/7 Always-Online Bot Runner`** on the left menu.
3. Tap the **`Run workflow`** dropdown Γ₧ö Tap the green **`Run workflow`** button.
4. The bot will start immediately in the cloud and run 24/7 even if your phone is turned off! ≡ƒƒó

---

## ≡ƒÆ╗ Running & Deploying from PC

- **1-Click Push from PC:** Double-click `PUSH_TO_GITHUB.bat`
- **Run Diagnostics Locally:** Double-click `TEST_BOT.bat`
- **Start Bot Locally:** Double-click `START_BOT.bat`

---

## ⚡ Zero-Restart Engine (5h 25min Auto-Handover)

This bot uses a **professional zero-restart handover system** — it never shows restart messages and never drops OTPs during session switches.

| Stage | What Happens |
| :--- | :--- |
| **Session Running** | Bot polls live OTPs every 12 seconds, 24/7 |
| **60s Before Timeout** | Bot saves full state (seen IDs, counts, countries) to GitHub Gist with `handover=true` |
| **Clean Exit** | Bot exits with code 0 — workflow immediately triggers next session |
| **New Session Starts** | Bot reads Gist, restores all state, silently continues — zero messages |
| **OTP Gap Recovery** | Any OTPs received during the brief runner switch are delivered on startup |

> ✅ **No restart messages.** Admin is never spammed during routine handovers.
> ✅ **No missed OTPs.** Any OTP received during session switch is caught and delivered.
> ✅ **Counts accumulate.** Bot maintains cumulative totals across all sessions.

### Session Schedule

| Setting | Value | Description |
| :--- | :--- | :--- |
| Session Length | 5h 25min (19,500s) | Each runner session before handover |
| Handover Time | ~1–3 min | Gap between session end and new session start |
| Backup Cron | Every 6h | Failsafe if self-trigger ever fails |

---

## 🔔 Delivery & Notification Flow

| Event | Destination | Description |
| :--- | :--- | :--- |
| **Incoming OTP** | All Linked Telegram Groups | Real-time OTP notification with country, number & code |
| **Routine Handover (every 5h 25min)** | *Silent — no message* | 🤫 Zero-restart engine handles silently |
| **Initial Deployment / Push** | Admin Private DM Only | 🔔 One-time online alert sent only when ADMIN_STARTUP_ALERT=true |

---

## 📊 Admin Commands

| Command | Description |
| :--- | :--- |
| `/start` | Live bot status, session uptime, next handover countdown, OTP stats |
| `/status` | Same as `/start` |
| `/set_icon <service> <url>` | Set a real app logo image URL for a service (e.g. `WhatsApp`, `Telegram`) |
| `/list_icons` | View all configured service logo icons |
| `/remove_icon <service>` | Remove a configured icon for a service |
| `/test` | Send a test OTP notification to all connected groups (verifies full delivery pipeline) |
