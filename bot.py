#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ OTPMAN 2 (KSI IPRN) - 100% Fully Automatic Standalone Telegram Bot
====================================================================
Single self-contained Python file for KSI IPRN SMS Panel (https://ksiiprn.com).
- Auto-installs dependencies
- SHA256 + SQLite deduplication (7-day retention)
- Forwards all incoming A2P OTPs to Primary + Secondary Groups simultaneously
- Shows ranked per-country statistics in /start admin panel
- Crash-proof polling engine with rate-limit handling & adaptive header parser
"""

import os
import sys
import subprocess

# ==========================================
# 1. Auto Dependency Installer
# ==========================================
def ensure_dependencies():
    required = [
        ("telegram", "python-telegram-bot>=21.0"),
        ("httpx",    "httpx>=0.27.0"),
        ("dotenv",   "python-dotenv>=1.0.0"),
    ]
    for module_name, package_spec in required:
        try:
            __import__(module_name)
        except ImportError:
            print(f"📦 Installing {package_spec}...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-warn-script-location", package_spec],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )

ensure_dependencies()

# ==========================================
# 2. Imports
# ==========================================
import re
import json
import html
import hashlib
import sqlite3
import logging
import asyncio
import argparse
from typing import Set, Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

import httpx
from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut, NetworkError, Conflict
from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, ContextTypes

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==========================================
# 3. Configuration
# ==========================================
def load_environment():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'").strip()
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

load_environment()

TELEGRAM_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# Support KSI_API_KEY, OTPMAN2_API_KEY, or PANEL_API_KEY
KSI_API_KEY            = os.getenv("KSI_API_KEY", os.getenv("OTPMAN2_API_KEY", os.getenv("PANEL_API_KEY", os.getenv("API_KEY", "")))).strip()
KSI_BASE_URL           = os.getenv("KSI_BASE_URL", os.getenv("OTPMAN2_BASE_URL", os.getenv("PANEL_BASE_URL", "https://ksiiprn.com"))).rstrip("/")
TELEGRAM_GROUP_CHAT_ID  = os.getenv("TELEGRAM_GROUP_CHAT_ID", "").strip()
SECONDARY_GROUP_CHAT_ID = os.getenv("SECONDARY_GROUP_CHAT_ID", os.getenv("TELEGRAM_SECONDARY_GROUP_CHAT_ID", "")).strip()
POLL_INTERVAL_SECONDS  = float(os.getenv("POLL_INTERVAL_SECONDS", "12.0"))
STARTUP_TYPE           = os.getenv("STARTUP_TYPE", "workflow_dispatch").strip().lower()

_admin_raw     = os.getenv("ADMIN_USER_IDS", "").strip()
ADMIN_USER_IDS: List[int] = [int(u.strip()) for u in _admin_raw.split(",") if u.strip().isdigit()]

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_FILE   = os.getenv("DB_FILE", os.path.join(BASE_DIR, "otp_database.db"))
DATA_FILE = os.path.join(BASE_DIR, "bot_data.json")

# ==========================================
# 4. Logging
# ==========================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OTPMAN2_BOT")

# ==========================================
# 5. Group Targets Management
# ==========================================
def load_stored_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def get_target_group_chat_ids() -> List[int]:
    """Returns a list of all configured target group chat IDs (Primary + Secondary)."""
    groups: List[int] = []
    seen = set()

    # Check stored json overrides
    data = load_stored_data()
    for key in ["group_chat_id", "primary_group_chat_id", "secondary_group_chat_id"]:
        val = data.get(key)
        if val:
            for part in str(val).split(","):
                part = part.strip()
                if part:
                    try:
                        cid = int(part)
                        if cid not in seen:
                            seen.add(cid)
                            groups.append(cid)
                    except ValueError:
                        pass

    # Check primary env variable
    if TELEGRAM_GROUP_CHAT_ID:
        for part in TELEGRAM_GROUP_CHAT_ID.split(","):
            part = part.strip()
            if part:
                try:
                    cid = int(part)
                    if cid not in seen:
                        seen.add(cid)
                        groups.append(cid)
                except ValueError:
                    pass

    # Check secondary env variable
    if SECONDARY_GROUP_CHAT_ID:
        for part in SECONDARY_GROUP_CHAT_ID.split(","):
            part = part.strip()
            if part:
                try:
                    cid = int(part)
                    if cid not in seen:
                        seen.add(cid)
                        groups.append(cid)
                except ValueError:
                    pass

    return groups

def get_linked_group_chat_id() -> Optional[int]:
    targets = get_target_group_chat_ids()
    return targets[0] if targets else None

def is_user_authorized(user_id: int) -> bool:
    if not ADMIN_USER_IDS:
        return True
    return user_id in ADMIN_USER_IDS

# ==========================================
# ==========================================
# 6. GitHub Gist Cloud Storage (28-Hour Retention)
# ==========================================
GIST_ID    = os.getenv("GIST_ID", os.getenv("GITHUB_GIST_ID", "")).strip()
GIST_TOKEN = os.getenv("GIST_TOKEN", os.getenv("GH_TOKEN", os.getenv("GITHUB_TOKEN", ""))).strip()
seen_message_ids: Set[str] = set()
seen_timestamps: Dict[str, float] = {}
_gist_dirty: bool = False

GIST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

class GistStorage:
    def __init__(self, gist_id: str, token: str, filename: str = "otpman2_seen_messages.json",
                 description: str = "OTPMAN 2 (KSI) Bot — 28h persistent storage"):
        self.gist_id = gist_id
        self.token = token
        self.filename = filename
        self.description = description
        self.enabled = bool(token)
        self.api_url = f"https://api.github.com/gists/{gist_id}" if gist_id else ""

    def _auth_headers(self) -> Dict[str, str]:
        return {**GIST_HEADERS, "Authorization": f"Bearer {self.token}"}

    async def ensure_gist(self) -> bool:
        """Auto-create a secret Gist if GIST_ID is not set."""
        if self.gist_id:
            return True
        if not self.token:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                res = await http.post(
                    "https://api.github.com/gists",
                    headers=self._auth_headers(),
                    json={
                        "description": self.description,
                        "public": False,
                        "files": {
                            self.filename: {
                                "content": json.dumps({"seen": {}, "bot": "OTPMAN2_KSI", "count": 0}, indent=2)
                            }
                        }
                    }
                )
                if res.is_success:
                    self.gist_id = res.json().get("id", "")
                    self.api_url = f"https://api.github.com/gists/{self.gist_id}"
                    logger.info(f"☁️ Auto-created GitHub Gist: {self.gist_id}")
                    logger.info(f"   ➜ Add this as a GitHub Secret: GIST_ID = {self.gist_id}")
                    return True
                else:
                    logger.warning(f"Gist auto-create failed {res.status_code}: {res.text[:120]}")
        except Exception as e:
            logger.warning(f"Gist auto-create error: {e}")
        return False

    async def load_seen(self) -> Dict[str, float]:
        """Fetch 28h history from GitHub Gist."""
        if not self.enabled or not self.api_url:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                res = await http.get(self.api_url, headers=self._auth_headers())
                if res.is_success:
                    data = res.json()
                    files = data.get("files", {})
                    if self.filename in files:
                        content_str = files[self.filename].get("content", "{}")
                        parsed = json.loads(content_str)
                        seen_map = parsed.get("seen", {}) if isinstance(parsed, dict) else {}
                        cutoff = datetime.now(timezone.utc).timestamp() - (28 * 3600)
                        valid = {k: float(v) for k, v in seen_map.items() if float(v) >= cutoff}
                        logger.info(f"☁️ Restored {len(valid)} seen messages from GitHub Gist ({self.gist_id[:8]}...).")
                        return valid
                else:
                    logger.warning(f"Gist load status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            logger.warning(f"Gist load error: {e}")
        return {}

    async def save_seen(self, seen_dict: Dict[str, float]) -> bool:
        """Prune older than 28h and sync to GitHub Gist."""
        if not self.enabled or not self.api_url:
            return False
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (28 * 3600)
            cleaned = {k: v for k, v in seen_dict.items() if v >= cutoff}
            payload = {
                "description": self.description,
                "files": {
                    self.filename: {
                        "content": json.dumps({
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "bot": "OTPMAN2_KSI",
                            "count": len(cleaned),
                            "seen": cleaned
                        }, indent=2)
                    }
                }
            }
            async with httpx.AsyncClient(timeout=15.0) as http:
                res = await http.patch(self.api_url, headers=self._auth_headers(), json=payload)
                if res.is_success:
                    logger.info(f"☁️ Synced {len(cleaned)} messages to GitHub Gist.")
                    return True
                else:
                    logger.warning(f"Gist sync status {res.status_code}: {res.text[:100]}")
        except Exception as e:
            logger.warning(f"Gist sync error: {e}")
        return False

gist_storage = GistStorage(
    GIST_ID, GIST_TOKEN,
    filename="otpman2_seen_messages.json",
    description="OTPMAN 2 (KSI) Bot — 28h persistent storage (auto-managed)"
)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_otps (
                id           TEXT PRIMARY KEY,
                source       TEXT,
                country      TEXT,
                number       TEXT,
                otp_code     TEXT,
                raw_message  TEXT,
                rate         TEXT,
                message_time TEXT,
                chat_id      INTEGER,
                forwarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_forwarded_at ON processed_otps(forwarded_at);")
        conn.commit()
    logger.info("📦 SQLite database initialized at %s", DB_FILE)

def is_message_seen(message_id: str) -> bool:
    if not message_id:
        return False
    if message_id in seen_message_ids:
        return True
    try:
        with get_db_connection() as conn:
            cur = conn.execute("SELECT 1 FROM processed_otps WHERE id = ? LIMIT 1;", (message_id,))
            found = cur.fetchone() is not None
            if found:
                seen_message_ids.add(message_id)
            return found
    except Exception as e:
        logger.error(f"DB check error: {e}")
        return False

def save_processed_message(item: Dict[str, Any], chat_id: int,
                           country: str = "", masked_num: str = "", otp_code: str = "") -> bool:
    global _gist_dirty
    mid = generate_message_key(item)
    if not mid:
        return False
    seen_message_ids.add(mid)
    now_ts = datetime.now(timezone.utc).timestamp()
    seen_timestamps[mid] = now_ts
    _gist_dirty = True
    source       = str(item.get("source") or item.get("sender") or item.get("caller") or "")
    rate         = str(item.get("rate") or "")
    raw_message  = str(item.get("message") or item.get("text") or item.get("body") or "")
    message_time = str(item.get("received_at") or item.get("messageTime") or item.get("createdAt") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with get_db_connection() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO processed_otps
                    (id, source, country, number, otp_code, raw_message, rate, message_time, chat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (mid, source, country, masked_num, otp_code, raw_message, rate, message_time, chat_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"DB save error: {e}")
    return False

def get_total_processed_count() -> int:
    try:
        with get_db_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM processed_otps;")
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0

def cleanup_old_messages(max_age_days: int = 7):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM processed_otps WHERE forwarded_at < datetime('now', ?);",
                (f"-{max_age_days} days",)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"DB cleanup error: {e}")

# ==========================================
# 7. KSI API Client (OTPMAN 2)
# ==========================================
def generate_message_key(item: Dict[str, Any]) -> str:
    """
    Build a deterministic SHA-256 key for KSI messages:
    sha256(number | received_at | source | message)
    """
    if item.get("id"):
        return str(item["id"]).strip()
    num = str(item.get("number") or item.get("destinationNumber") or "").strip()
    ts  = str(item.get("received_at") or item.get("receivedAt") or "").strip()
    src = str(item.get("source") or item.get("sender") or "").strip()
    msg = str(item.get("message") or item.get("text") or item.get("body") or "").strip()
    raw = f"{num}|{ts}|{src}|{msg}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class KSIClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0):
        self.base_url  = base_url.rstrip("/")
        self.api_key   = api_key.strip()
        self.timeout   = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self.last_request_ts: float = 0.0
        # Dynamic rate limit pacer: default 12.0s or adjusted from headers
        self.interval: float = POLL_INTERVAL_SECONDS

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept":        "application/json",
                    "User-Agent":    "OTPMan2-KSI-Bot/1.0",
                },
            )
        return self._client

    async def fetch_incoming_messages(self) -> List[Dict[str, Any]]:
        try:
            client = self._get_http_client()
            now = datetime.now(timezone.utc)
            start_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")
            end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            url = f"{self.base_url}/api/v1/iprn/messages"
            msg_type = os.getenv("MESSAGE_TYPE", "").strip().lower()
            params: Dict[str, Any] = {
                "per_page": 200,
                "start_date": start_date,
                "end_date": end_date,
            }
            if msg_type in ["a2p", "p2p"]:
                params["type"] = msg_type

            self.last_request_ts = asyncio.get_event_loop().time()
            res = await client.get(url, params=params)

            # Parse official rate limit headers
            limit_val     = res.headers.get("X-RateLimit-Limit")
            remaining_val = res.headers.get("X-RateLimit-Remaining")
            reset_ts_val  = res.headers.get("X-RateLimit-Reset")

            if res.status_code == 429:
                retry_hdr = res.headers.get("Retry-After")
                try:
                    data = res.json()
                    wait_sec = float(retry_hdr or data.get("error", {}).get("retry_after") or 45.0)
                except Exception:
                    wait_sec = float(retry_hdr or 45.0)
                logger.warning(f"⚠️ OTPMAN 2 (KSI) Rate Limit reached. Waiting exact {wait_sec:.0f}s cooldown...")
                await asyncio.sleep(wait_sec + 0.5)
                return []

            if remaining_val is not None and str(remaining_val).isdigit() and int(remaining_val) == 0:
                if reset_ts_val and str(reset_ts_val).isdigit():
                    now_epoch = datetime.now(timezone.utc).timestamp()
                    sleep_until_reset = max(float(reset_ts_val) - now_epoch + 1.0, 5.0)
                    logger.info(f"⏳ Rate limit window active. Resting {sleep_until_reset:.1f}s until reset...")
                    await asyncio.sleep(sleep_until_reset)

            if res.is_success:
                data = res.json()
                items = data.get("data") if isinstance(data, dict) and "data" in data else (
                    data.get("rows") if isinstance(data, dict) and "rows" in data else (
                        data if isinstance(data, list) else []
                    )
                )
                seen_in_batch = set()
                out: List[Dict[str, Any]] = []
                for item in items:
                    if isinstance(item, dict):
                        key = generate_message_key(item)
                        if key not in seen_in_batch:
                            seen_in_batch.add(key)
                            item["_key"] = key
                            out.append(item)
                return out
            else:
                logger.warning(f"OTPMAN 2 (KSI) API error {res.status_code}: {res.text[:120]}")
        except Exception as e:
            logger.warning(f"OTPMAN 2 (KSI) API fetch exception: {e}")
        return []

# ==========================================
# 8. Country ISO Alpha-2 Lookup (150+ countries)
# ==========================================
COUNTRY_ISO_DATA: Dict[str, Tuple[str, str]] = {
    # Asia & Middle East
    "sri lanka": ("🇱🇰", "LK"), "lk": ("🇱🇰", "LK"),
    "indonesia": ("🇮🇩", "ID"), "id": ("🇮🇩", "ID"),
    "india":     ("🇮🇳", "IN"), "in": ("🇮🇳", "IN"),
    "bangladesh":("🇧🇩", "BD"), "bd": ("🇧🇩", "BD"),
    "pakistan":  ("🇵🇰", "PK"), "pk": ("🇵🇰", "PK"),
    "vietnam":   ("🇻🇳", "VN"), "vn": ("🇻🇳", "VN"),
    "philippines":("🇵🇭","PH"), "ph": ("🇵🇭", "PH"),
    "thailand":  ("🇹🇭", "TH"), "th": ("🇹🇭", "TH"),
    "malaysia":  ("🇲🇾", "MY"), "my": ("🇲🇾", "MY"),
    "cambodia":  ("🇰🇭", "KH"), "kh": ("🇰🇭", "KH"),
    "myanmar":   ("🇲🇲", "MM"), "mm": ("🇲🇲", "MM"),
    "nepal":     ("🇳🇵", "NP"), "np": ("🇳🇵", "NP"),
    "china":     ("🇨🇳", "CN"), "cn": ("🇨🇳", "CN"),
    "taiwan":    ("🇹🇼", "TW"), "tw": ("🇹🇼", "TW"),
    "japan":     ("🇯🇵", "JP"), "jp": ("🇯🇵", "JP"),
    "south korea":("🇰🇷","KR"), "kr": ("🇰🇷", "KR"),
    "singapore": ("🇸🇬", "SG"), "sg": ("🇸🇬", "SG"),
    "hong kong": ("🇭🇰", "HK"), "hk": ("🇭🇰", "HK"),
    "russia":    ("🇷🇺", "RU"), "ru": ("🇷🇺", "RU"),
    "ukraine":   ("🇺🇦", "UA"), "ua": ("🇺🇦", "UA"),
    "turkey":    ("🇹🇷", "TR"), "tr": ("🇹🇷", "TR"),
    "saudi arabia":("🇸🇦","SA"),"sa": ("🇸🇦", "SA"),
    "uae":       ("🇦🇪", "AE"), "ae": ("🇦🇪", "AE"),
    "united arab emirates":("🇦🇪","AE"),
    "iran":      ("🇮🇷", "IR"), "ir": ("🇮🇷", "IR"),
    "iraq":      ("🇮🇶", "IQ"), "iq": ("🇮🇶", "IQ"),
    "israel":    ("🇮🇱", "IL"), "il": ("🇮🇱", "IL"),
    "jordan":    ("🇯🇴", "JO"), "jo": ("🇯🇴", "JO"),
    "kuwait":    ("🇰🇼", "KW"), "kw": ("🇰🇼", "KW"),
    "lebanon":   ("🇱🇧", "LB"), "lb": ("🇱🇧", "LB"),
    "oman":      ("🇴🇲", "OM"), "om": ("🇴🇲", "OM"),
    "qatar":     ("🇶🇦", "QA"), "qa": ("🇶🇦", "QA"),
    "syria":     ("🇸🇾", "SY"), "sy": ("🇸🇾", "SY"),
    "yemen":     ("🇾🇪", "YE"), "ye": ("🇾🇪", "YE"),
    "bahrain":   ("🇧🇭", "BH"), "bh": ("🇧🇭", "BH"),
    "uzbekistan":("🇺🇿","UZ"), "uz": ("🇺🇿", "UZ"),
    "kazakhstan":("🇰🇿","KZ"), "kz": ("🇰🇿", "KZ"),
    "kyrgyzstan":("🇰🇬","KG"), "kg": ("🇰🇬", "KG"),
    "tajikistan":("🇹🇯","TJ"), "tj": ("🇹🇯", "TJ"),
    "turkmenistan":("🇹🇲","TM"), "tm": ("🇹🇲", "TM"),
    "afghanistan":("🇦🇫","AF"), "af": ("🇦🇫", "AF"),
    "azerbaijan":("🇦🇿","AZ"), "az": ("🇦🇿", "AZ"),
    "armenia":   ("🇦🇲", "AM"), "am": ("🇦🇲", "AM"),
    "georgia":   ("🇬🇪", "GE"), "ge": ("🇬🇪", "GE"),
    "laos":      ("🇱🇦", "LA"), "la": ("🇱🇦", "LA"),
    "bhutan":    ("🇧🇹", "BT"), "bt": ("🇧🇹", "BT"),
    "maldives":  ("🇲🇻", "MV"), "mv": ("🇲🇻", "MV"),

    # Africa
    "ivory coast":("🇨🇮","CI"), "cote d'ivoire":("🇨🇮","CI"), "ci":("🇨🇮","CI"),
    "egypt":     ("🇪🇬", "EG"), "eg": ("🇪🇬", "EG"),
    "nigeria":   ("🇳🇬", "NG"), "ng": ("🇳🇬", "NG"),
    "kenya":     ("🇰🇪", "KE"), "ke": ("🇰🇪", "KE"),
    "ghana":     ("🇬🇭", "GH"), "gh": ("🇬🇭", "GH"),
    "south africa":("🇿🇦","ZA"),"za": ("🇿🇦", "ZA"),
    "morocco":   ("🇲🇦", "MA"), "ma": ("🇲🇦", "MA"),
    "algeria":   ("🇩🇿", "DZ"), "dz": ("🇩🇿", "DZ"),
    "tunisia":   ("🇹🇳", "TN"), "tn": ("🇹🇳", "TN"),
    "libya":     ("🇱🇾", "LY"), "ly": ("🇱🇾", "LY"),
    "tanzania":  ("🇹🇿", "TZ"), "tz": ("🇹🇿", "TZ"),
    "uganda":    ("🇺🇬", "UG"), "ug": ("🇺🇬", "UG"),
    "ethiopia":  ("🇪🇹", "ET"), "et": ("🇪🇹", "ET"),
    "somalia":   ("🇸🇴", "SO"), "so": ("🇸🇴", "SO"),
    "sudan":     ("🇸🇩", "SD"), "sd": ("🇸🇩", "SD"),
    "senegal":   ("🇸🇳", "SN"), "sn": ("🇸🇳", "SN"),
    "cameroon":  ("🇨🇲", "CM"), "cm": ("🇨🇲", "CM"),
    "rwanda":    ("🇷🇼", "RW"), "rw": ("🇷🇼", "RW"),
    "zambia":    ("🇿🇲", "ZM"), "zm": ("🇿🇲", "ZM"),
    "zimbabwe":  ("🇿🇼", "ZW"), "zw": ("🇿🇼", "ZW"),
    "mozambique":("🇲🇿","MZ"), "mz": ("🇲🇿", "MZ"),
    "angola":    ("🇦🇴", "AO"), "ao": ("🇦🇴", "AO"),
    "mali":      ("🇲🇱", "ML"), "ml": ("🇲🇱", "ML"),
    "burkina faso":("🇧🇫","BF"),"bf": ("🇧🇫", "BF"),
    "guinea":    ("🇬🇳", "GN"), "gn": ("🇬🇳", "GN"),
    "benin":     ("🇧🇯", "BJ"), "bj": ("🇧🇯", "BJ"),
    "togo":      ("🇹🇬", "TG"), "tg": ("🇹🇬", "TG"),
    "madagascar":("🇲🇬","MG"), "mg": ("🇲🇬", "MG"),
    "mauritius": ("🇲🇺", "MU"), "mu": ("🇲🇺", "MU"),
    "botswana":  ("🇧🇼", "BW"), "bw": ("🇧🇼", "BW"),
    "namibia":   ("🇳🇦", "NA"), "na": ("🇳🇦", "NA"),

    # Europe
    "kosovo":    ("🇽🇰", "XK"), "xk": ("🇽🇰", "XK"),
    "united kingdom":("🇬🇧","GB"),"uk": ("🇬🇧", "GB"), "gb": ("🇬🇧", "GB"),
    "germany":   ("🇩🇪", "DE"), "de": ("🇩🇪", "DE"),
    "france":    ("🇫🇷", "FR"), "fr": ("🇫🇷", "FR"),
    "italy":     ("🇮🇹", "IT"), "it": ("🇮🇹", "IT"),
    "spain":     ("🇪🇸", "ES"), "es": ("🇪🇸", "ES"),
    "poland":    ("🇵🇱", "PL"), "pl": ("🇵🇱", "PL"),
    "netherlands":("🇳🇱","NL"), "nl": ("🇳🇱", "NL"),
    "portugal":  ("🇵🇹", "PT"), "pt": ("🇵🇹", "PT"),
    "sweden":    ("🇸🇪", "SE"), "se": ("🇸🇪", "SE"),
    "norway":    ("🇳🇴", "NO"), "no": ("🇳🇴", "NO"),
    "denmark":   ("🇩🇰", "DK"), "dk": ("🇩🇰", "DK"),
    "finland":   ("🇫🇮", "FI"), "fi": ("🇫🇮", "FI"),
    "switzerland":("🇨🇭","CH"), "ch": ("🇨🇭", "CH"),
    "austria":   ("🇦🇹", "AT"), "at": ("🇦🇹", "AT"),
    "belgium":   ("🇧🇪", "BE"), "be": ("🇧🇪", "BE"),
    "greece":    ("🇬🇷", "GR"), "gr": ("🇬🇷", "GR"),
    "ireland":   ("🇮🇪", "IE"), "ie": ("🇮🇪", "IE"),
    "czech":     ("🇨🇿", "CZ"), "cz": ("🇨🇿", "CZ"), "czech republic":("🇨🇿","CZ"),
    "romania":   ("🇷🇴", "RO"), "ro": ("🇷🇴", "RO"),
    "hungary":   ("🇭🇺", "HU"), "hu": ("🇭🇺", "HU"),
    "albania":   ("🇦🇱", "AL"), "al": ("🇦🇱", "AL"),
    "serbia":    ("🇷🇸", "RS"), "rs": ("🇷🇸", "RS"),
    "croatia":   ("🇭🇷", "HR"), "hr": ("🇭🇷", "HR"),
    "bulgaria":  ("🇧🇬", "BG"), "bg": ("🇧🇬", "BG"),
    "slovakia":  ("🇸🇰", "SK"), "sk": ("🇸🇰", "SK"),
    "slovenia":  ("🇸🇮", "SI"), "si": ("🇸🇮", "SI"),
    "estonia":   ("🇪🇪", "EE"), "ee": ("🇪🇪", "EE"),
    "latvia":    ("🇱🇻", "LV"), "lv": ("🇱🇻", "LV"),
    "lithuania": ("🇱🇹", "LT"), "lt": ("🇱🇹", "LT"),
    "belarus":   ("🇧🇾", "BY"), "by": ("🇧🇾", "BY"),
    "moldova":   ("🇲🇩", "MD"), "md": ("🇲🇩", "MD"),
    "bosnia":    ("🇧🇦", "BA"), "ba": ("🇧🇦", "BA"),
    "north macedonia":("🇲🇰","MK"),"mk": ("🇲🇰", "MK"),
    "cyprus":    ("🇨🇾", "CY"), "cy": ("🇨🇾", "CY"),
    "malta":     ("🇲🇹", "MT"), "mt": ("🇲🇹", "MT"),
    "iceland":   ("🇮🇸", "IS"), "is": ("🇮🇸", "IS"),
    "luxembourg":("🇱🇺","LU"), "lu": ("🇱🇺", "LU"),

    # Americas
    "united states":("🇺🇸","US"),"us": ("🇺🇸", "US"), "usa": ("🇺🇸", "US"),
    "canada":    ("🇨🇦", "CA"), "ca": ("🇨🇦", "CA"),
    "brazil":    ("🇧🇷", "BR"), "br": ("🇧🇷", "BR"),
    "mexico":    ("🇲🇽", "MX"), "mx": ("🇲🇽", "MX"),
    "colombia":  ("🇨🇴", "CO"), "co": ("🇨🇴", "CO"),
    "argentina": ("🇦🇷", "AR"), "ar": ("🇦🇷", "AR"),
    "peru":      ("🇵🇪", "PE"), "pe": ("🇵🇪", "PE"),
    "chile":     ("🇨🇱", "CL"), "cl": ("🇨🇱", "CL"),
    "venezuela": ("🇻🇪", "VE"), "ve": ("🇻🇪", "VE"),
    "ecuador":   ("🇪🇨", "EC"), "ec": ("🇪🇨", "EC"),
    "guatemala": ("🇬🇹", "GT"), "gt": ("🇬🇹", "GT"),
    "cuba":      ("🇨🇺", "CU"), "cu": ("🇨🇺", "CU"),
    "bolivia":   ("🇧🇴", "BO"), "bo": ("🇧🇴", "BO"),
    "dominican republic":("🇩🇴","DO"),"do": ("🇩🇴", "DO"),
    "honduras":  ("🇭🇳", "HN"), "hn": ("🇭🇳", "HN"),
    "paraguay":  ("🇵🇾", "PY"), "py": ("🇵🇾", "PY"),
    "el salvador":("🇸🇻","SV"),"sv": ("🇸🇻", "SV"),
    "nicaragua": ("🇳🇮", "NI"), "ni": ("🇳🇮", "NI"),
    "costa rica":("🇨🇷","CR"), "cr": ("🇨🇷", "CR"),
    "panama":    ("🇵🇦", "PA"), "pa": ("🇵🇦", "PA"),
    "uruguay":   ("🇺🇾", "UY"), "uy": ("🇺🇾", "UY"),
    "jamaica":   ("🇯🇲", "JM"), "jm": ("🇯🇲", "JM"),
    "haiti":     ("🇭🇹", "HT"), "ht": ("🇭🇹", "HT"),

    # Oceania
    "australia": ("🇦🇺", "AU"), "au": ("🇦🇺", "AU"),
    "new zealand":("🇳🇿","NZ"), "nz": ("🇳🇿", "NZ"),
    "fiji":      ("🇫🇯", "FJ"), "fj": ("🇫🇯", "FJ"),
    "papua new guinea":("🇵🇬","PG"),"pg": ("🇵🇬", "PG"),
    "celtel":    ("🇱🇰", "LK"),
}

PREFIX_ISO_MAP: Dict[str, Tuple[str, str]] = {
    # 1-digit
    "1":   ("🇺🇸", "US"), "7":   ("🇷🇺", "RU"),

    # 2-digit
    "20":  ("🇪🇬", "EG"), "27":  ("🇿🇦", "ZA"), "30":  ("🇬🇷", "GR"),
    "31":  ("🇳🇱", "NL"), "32":  ("🇧🇪", "BE"), "33":  ("🇫🇷", "FR"),
    "34":  ("🇪🇸", "ES"), "36":  ("🇭🇺", "HU"), "39":  ("🇮🇹", "IT"),
    "40":  ("🇷🇴", "RO"), "41":  ("🇨🇭", "CH"), "43":  ("🇦🇹", "AT"),
    "44":  ("🇬🇧", "GB"), "45":  ("🇩🇰", "DK"), "46":  ("🇸🇪", "SE"),
    "47":  ("🇳🇴", "NO"), "48":  ("🇵🇱", "PL"), "49":  ("🇩🇪", "DE"),
    "51":  ("🇵🇪", "PE"), "52":  ("🇲🇽", "MX"), "53":  ("🇨🇺", "CU"),
    "54":  ("🇦🇷", "AR"), "55":  ("🇧🇷", "BR"), "56":  ("🇨🇱", "CL"),
    "57":  ("🇨🇴", "CO"), "58":  ("🇻🇪", "VE"), "60":  ("🇲🇾", "MY"),
    "61":  ("🇦🇺", "AU"), "62":  ("🇮🇩", "ID"), "63":  ("🇵🇭", "PH"),
    "64":  ("🇳🇿", "NZ"), "65":  ("🇸🇬", "SG"), "66":  ("🇹🇭", "TH"),
    "81":  ("🇯🇵", "JP"), "82":  ("🇰🇷", "KR"), "84":  ("🇻🇳", "VN"),
    "86":  ("🇨🇳", "CN"), "90":  ("🇹🇷", "TR"), "91":  ("🇮🇳", "IN"),
    "92":  ("🇵🇰", "PK"), "93":  ("🇦🇫", "AF"), "94":  ("🇱🇰", "LK"),
    "95":  ("🇲🇲", "MM"), "98":  ("🇮🇷", "IR"),

    # 3-digit Africa
    "212": ("🇲🇦", "MA"), "213": ("🇩🇿", "DZ"), "216": ("🇹🇳", "TN"),
    "218": ("🇱🇾", "LY"), "220": ("🇬🇲", "GM"), "221": ("🇸🇳", "SN"),
    "222": ("🇲🇷", "MR"), "223": ("🇲🇱", "ML"), "224": ("🇬🇳", "GN"),
    "225": ("🇨🇮", "CI"), "226": ("🇧🇫", "BF"), "227": ("🇳🇪", "NE"),
    "228": ("🇹🇬", "TG"), "229": ("🇧🇯", "BJ"), "230": ("🇲🇺", "MU"),
    "231": ("🇱🇷", "LR"), "232": ("🇸🇱", "SL"), "233": ("🇬🇭", "GH"),
    "234": ("🇳🇬", "NG"), "235": ("🇹🇩", "TD"), "236": ("🇨🇫", "CF"),
    "237": ("🇨🇲", "CM"), "238": ("🇨🇻", "CV"), "239": ("🇸🇹", "ST"),
    "240": ("🇬🇶", "GQ"), "241": ("🇬🇦", "GA"), "242": ("🇨🇬", "CG"),
    "243": ("🇨🇩", "CD"), "244": ("🇦🇴", "AO"), "245": ("🇬🇼", "GW"),
    "248": ("🇸🇨", "SC"), "249": ("🇸🇩", "SD"), "250": ("🇷🇼", "RW"),
    "251": ("🇪🇹", "ET"), "252": ("🇸🇴", "SO"), "253": ("🇩🇯", "DJ"),
    "254": ("🇰🇪", "KE"), "255": ("🇹🇿", "TZ"), "256": ("🇺🇬", "UG"),
    "257": ("🇧🇮", "BI"), "258": ("🇲🇿", "MZ"), "260": ("🇿🇲", "ZM"),
    "261": ("🇲🇬", "MG"), "263": ("🇿🇼", "ZW"), "264": ("🇳🇦", "NA"),
    "265": ("🇲🇼", "MW"), "266": ("🇱🇸", "LS"), "267": ("🇧🇼", "BW"),
    "268": ("🇸🇿", "SZ"),

    # 3-digit Europe & Middle East
    "350": ("🇬🇮", "GI"), "351": ("🇵🇹", "PT"), "352": ("🇱🇺", "LU"),
    "353": ("🇮🇪", "IE"), "354": ("🇮🇸", "IS"), "355": ("🇦🇱", "AL"),
    "356": ("🇲🇹", "MT"), "357": ("🇨🇾", "CY"), "358": ("🇫🇮", "FI"),
    "359": ("🇧🇬", "BG"), "370": ("🇱🇹", "LT"), "371": ("🇱🇻", "LV"),
    "372": ("🇪🇪", "EE"), "373": ("🇲🇩", "MD"), "374": ("🇦🇲", "AM"),
    "375": ("🇧🇾", "BY"), "376": ("🇦🇩", "AD"), "377": ("🇲🇨", "MC"),
    "380": ("🇺🇦", "UA"), "381": ("🇷🇸", "RS"), "382": ("🇲🇪", "ME"),
    "383": ("🇽🇰", "XK"), "385": ("🇭🇷", "HR"), "386": ("🇸🇮", "SI"),
    "387": ("🇧🇦", "BA"), "389": ("🇲🇰", "MK"), "420": ("🇨🇿", "CZ"),
    "421": ("🇸🇰", "SK"), "852": ("🇭🇰", "HK"), "853": ("🇲🇴", "MO"),
    "855": ("🇰🇭", "KH"), "856": ("🇱🇦", "LA"), "880": ("🇧🇩", "BD"),
    "886": ("🇹🇼", "TW"), "960": ("🇲🇻", "MV"), "961": ("🇱🇧", "LB"),
    "962": ("🇯🇴", "JO"), "963": ("🇸🇾", "SY"), "964": ("🇮🇶", "IQ"),
    "965": ("🇰🇼", "KW"), "966": ("🇸🇦", "SA"), "967": ("🇾🇪", "YE"),
    "968": ("🇴🇲", "OM"), "970": ("🇵🇸", "PS"), "971": ("🇦🇪", "AE"),
    "972": ("🇮🇱", "IL"), "973": ("🇧🇭", "BH"), "974": ("🇶🇦", "QA"),
    "975": ("🇧🇹", "BT"), "976": ("🇲🇳", "MN"), "977": ("🇳🇵", "NP"),
    "992": ("🇹🇯", "TJ"), "993": ("🇹🇲", "TM"), "994": ("🇦🇿", "AZ"),
    "995": ("🇬🇪", "GE"), "996": ("🇰🇬", "KG"), "998": ("🇺🇿", "UZ"),

    # 3-digit Americas & Caribbean
    "501": ("🇧🇿", "BZ"), "502": ("🇬🇹", "GT"), "503": ("🇸🇻", "SV"),
    "504": ("🇭🇳", "HN"), "505": ("🇳🇮", "NI"), "506": ("🇨🇷", "CR"),
    "507": ("🇵🇦", "PA"), "509": ("🇭🇹", "HT"), "591": ("🇧🇴", "BO"),
    "592": ("🇬🇾", "GY"), "593": ("🇪🇨", "EC"), "595": ("🇵🇾", "PY"),
    "597": ("🇸🇷", "SR"), "598": ("🇺🇾", "UY"), "675": ("🇵🇬", "PG"),
    "679": ("🇫🇯", "FJ"),
}

def get_country_iso_display(item: Dict[str, Any]) -> str:
    for field in ["countryCode", "iso", "iso2", "country"]:
        val = str(item.get(field) or "").strip().lower()
        if val in COUNTRY_ISO_DATA:
            flag, code = COUNTRY_ISO_DATA[val]
            return f"{flag} {code}"

    raw_range = str(item.get("rangeName") or item.get("destinationName") or item.get("country") or "").strip()
    if raw_range:
        parts = re.split(r"[-–—,:/]", raw_range)
        name_key = parts[0].strip().lower()
        if name_key in COUNTRY_ISO_DATA:
            flag, code = COUNTRY_ISO_DATA[name_key]
            return f"{flag} {code}"
        for country_name, (flag, code) in COUNTRY_ISO_DATA.items():
            if len(country_name) > 3 and country_name in raw_range.lower():
                return f"{flag} {code}"

    raw_number = str(
        item.get("number") or item.get("destinationNumber") or
        item.get("rangeTemplate") or item.get("template") or
        item.get("dst") or ""
    ).strip()
    digits = re.sub(r"\D", "", raw_number)
    for p_len in [4, 3, 2, 1]:
        prefix = digits[:p_len]
        if prefix in PREFIX_ISO_MAP:
            flag, code = PREFIX_ISO_MAP[prefix]
            return f"{flag} {code}"

    return "🌐 XX"

def mask_phone_number(num_str: str) -> str:
    if not num_str:
        return ""
    clean = str(num_str).strip()
    length = len(clean)
    if length <= 4:
        return clean
    if length <= 6:
        return clean[:2] + "****" + clean[-2:]
    return f"{clean[:4]}****{clean[-3:]}"

def extract_otp_code(text: str) -> str:
    if not text:
        return ""
    kw_match = re.search(
        r"(?:code|otp|pin|passcode|secret|verif\w*|kod\w*|c[oó]digo|clave|is)[:\s\-]+([A-Za-z0-9\-]{3,10})\b",
        text, re.IGNORECASE,
    )
    if kw_match:
        code = kw_match.group(1).strip()
        if any(c.isdigit() for c in code):
            return code
    hyphen_match = re.findall(r"\b\d{3}-\d{3}\b|\b\d{3}-\d{4}\b|\b\d{4}-\d{4}\b", text)
    if hyphen_match:
        return hyphen_match[0]
    digits_match = re.findall(r"\b[0-9]{4,8}\b", text)
    if digits_match:
        return digits_match[0]
    return ""

def parse_message_timestamp(time_str: str) -> float:
    if not time_str:
        return 0.0
    clean = str(time_str).strip()
    try:
        if "T" in clean:
            clean_iso = clean.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        dt = datetime.strptime(clean[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

def format_otp_notification(item: Dict[str, Any]) -> str:
    source          = html.escape(str(item.get("source") or item.get("sender") or item.get("caller") or "SMS Service"))
    country_display = html.escape(get_country_iso_display(item))
    raw_number      = str(item.get("number") or item.get("destinationNumber") or "")
    masked_number   = html.escape(mask_phone_number(raw_number)) if raw_number else ""
    raw_message     = str(item.get("message") or item.get("text") or item.get("body") or "")
    escaped_msg     = html.escape(raw_message)
    msg_time        = str(item.get("received_at") or item.get("messageTime") or item.get("createdAt") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    if "T" in msg_time:
        msg_time = msg_time.replace("T", " ")[:19] + " UTC"
    elif msg_time and "UTC" not in msg_time:
        msg_time = msg_time[:19] + " UTC"
        
    otp_code    = extract_otp_code(raw_message)
    otp_header  = f"\n🔑 <b>OTP CODE:</b> <code>{otp_code}</code>\n" if otp_code else "\n"
    number_line = f"• <b>Number:</b> <code>{masked_number}</code>\n" if masked_number else ""

    return (
        f"⚡ <b>NEW OTP / SMS RECEIVED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━{otp_header}"
        f"• <b>Service:</b> <code>{source}</code>\n"
        f"• <b>Country:</b> <b>{country_display}</b>\n"
        f"{number_line}"
        f"• <b>Time:</b> <code>{html.escape(msg_time)}</code>\n\n"
        f"💬 <b>Message Content:</b>\n"
        f"<code>{escaped_msg}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ==========================================
# 9. Telegram Bot Engine
# ==========================================
total_forwarded_count: int = 0
country_forwarded_counts: Dict[str, int] = {}
client = KSIClient(
    base_url=KSI_BASE_URL,
    api_key=KSI_API_KEY,
    timeout=20.0,
)

async def send_with_retry(bot: Bot, chat_id: int, text: str, max_retries: int = 3) -> bool:
    for attempt in range(1, max_retries + 1):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                read_timeout=30.0,
                write_timeout=30.0,
                connect_timeout=30.0,
            )
            return True
        except RetryAfter as r_err:
            wait_time = r_err.retry_after + 1
            logger.warning(f"Telegram rate-limit. Waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
        except (TimedOut, NetworkError) as net_err:
            logger.warning(f"Network error sending to {chat_id}: {net_err}. Retry {attempt}/{max_retries}...")
            await asyncio.sleep(3.0)
        except Exception as e:
            err_str = str(e).lower()
            if "can't parse entities" in err_str or "parse" in err_str:
                try:
                    # Strip HTML and send plain text so message is never dropped
                    plain = re.sub(r"<[^>]+>", "", text)
                    await bot.send_message(chat_id=chat_id, text=plain)
                    return True
                except Exception:
                    pass
            logger.error(f"❌ Cannot send to {chat_id}: {e}")
            return False
    return False

def _get_otp_dest_ids() -> Set[int]:
    dest: Set[int] = set()
    for gid in get_target_group_chat_ids():
        if gid:
            dest.add(gid)
    return dest

async def _deliver_item(bot: Bot, item: Dict[str, Any], dest_ids: Set[int]) -> bool:
    mid            = generate_message_key(item)
    formatted_text = format_otp_notification(item)
    sent_to_any    = False

    for cid in dest_ids:
        try:
            ok = await send_with_retry(bot, cid, formatted_text)
            if ok:
                sent_to_any = True
        except Exception as e:
            logger.warning(f"Delivery error to {cid}: {e}")

    if sent_to_any:
        raw_num     = str(item.get("number") or item.get("destinationNumber") or "")
        num         = mask_phone_number(raw_num)
        raw_msg     = str(item.get("message") or item.get("text") or item.get("body") or "")
        otp         = extract_otp_code(raw_msg)
        gid         = get_linked_group_chat_id()
        country_iso = get_country_iso_display(item)
        country_forwarded_counts[country_iso] = country_forwarded_counts.get(country_iso, 0) + 1
        save_processed_message(item, gid or 0, country_iso, num, otp)
        logger.info(f"✅ Forwarded Live OTP (ID: {mid[:12]}...) to Groups [{country_iso}]")
    else:
        logger.error(f"❌ Failed to deliver OTP (ID: {mid[:12]}...)")

    return sent_to_any

async def poll_incoming_messages(application: Application):
    global total_forwarded_count, _gist_dirty
    init_db()
    bot_start_time = datetime.now(timezone.utc).timestamp()
    logger.info(f"🚀 OTPMAN 2 (KSI) polling engine started at epoch {bot_start_time:.0f}.")

    # 1. Ensure Gist exists (auto-creates if GIST_ID not set)
    if gist_storage.enabled:
        await gist_storage.ensure_gist()
        gist_seen = await gist_storage.load_seen()
        for k, ts in gist_seen.items():
            seen_message_ids.add(k)
            seen_timestamps[k] = ts
        logger.info(f"☁️ Restored {len(gist_seen)} persistent message IDs from GitHub Gist.")

    # 2. Preload known IDs from local DB
    try:
        with get_db_connection() as conn:
            for row in conn.execute("SELECT id FROM processed_otps ORDER BY forwarded_at DESC LIMIT 10000;"):
                mid = str(row["id"])
                seen_message_ids.add(mid)
                if mid not in seen_timestamps:
                    seen_timestamps[mid] = bot_start_time
        logger.info(f"Preloaded {len(seen_message_ids)} total seen message keys.")
    except Exception as e:
        logger.warning(f"Preload error: {e}")

    # 3. Startup pass: baseline history, mark ALL existing messages as seen (NEVER forward old history)
    try:
        initial_msgs = await client.fetch_incoming_messages()
        baselined    = 0
        for item in initial_msgs:
            mid = generate_message_key(item)
            if not mid:
                continue
            seen_message_ids.add(mid)
            seen_timestamps[mid] = bot_start_time
            raw_num = str(item.get("number") or item.get("destinationNumber") or "")
            num     = mask_phone_number(raw_num)
            raw_msg = str(item.get("message") or item.get("text") or item.get("body") or "")
            otp     = extract_otp_code(raw_msg)
            gid     = get_linked_group_chat_id()
            iso     = get_country_iso_display(item)
            save_processed_message(item, gid or 0, iso, num, otp)
            baselined += 1
        if baselined > 0 and gist_storage.enabled:
            await gist_storage.save_seen(seen_timestamps)
        logger.info(f"✅ Startup: {baselined} historical messages baselined (0 old messages forwarded).")
    except Exception as e:
        logger.warning(f"Startup pass error: {e}")

    # Live Polling Loop - ONLY forwards new messages that arrive AFTER startup
    while True:
        try:
            dest_ids = _get_otp_dest_ids()
            if dest_ids:
                messages = await client.fetch_incoming_messages()
                new_items = []
                for m in messages:
                    k = generate_message_key(m)
                    if not k or is_message_seen(k):
                        continue
                    # Timestamp check: ignore any SMS older than bot startup time
                    msg_ts = parse_message_timestamp(str(m.get("received_at") or m.get("createdAt") or m.get("messageTime") or ""))
                    if msg_ts > 0 and msg_ts < (bot_start_time - 15.0):
                        seen_message_ids.add(k)
                        seen_timestamps[k] = msg_ts
                        continue
                    new_items.append(m)
                    seen_message_ids.add(k)  # Mark seen immediately
                    seen_timestamps[k] = datetime.now(timezone.utc).timestamp()
                    _gist_dirty = True

                if new_items:
                    logger.info(f"🔔 {len(new_items)} new SMS/OTP(s) detected from OTPMAN 2 (KSI)!")
                    for item in reversed(new_items):
                        ok = await _deliver_item(application.bot, item, dest_ids)
                        if ok:
                            total_forwarded_count += 1

        except (TimedOut, NetworkError) as net_err:
            logger.warning(f"⚠️ Network hiccup: {net_err}. Retrying in 3s...")
            await asyncio.sleep(3.0)
        except Exception as e:
            logger.error(f"⚠️ Polling error: {e}. Continuing in 3s...")
            await asyncio.sleep(3.0)

        # Micro-yield (0.1s) since fetch_incoming_messages already handles exact rate-limit timing
        await asyncio.sleep(0.1)

# ==========================================
# 10. Bot Commands & Announcements
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat    = update.effective_chat
    user    = update.effective_user
    msg_obj = update.effective_message
    if not chat or not msg_obj:
        return
    user_id = user.id if user else 0
    if not is_user_authorized(user_id):
        await msg_obj.reply_text("⛔ <b>Access Restricted</b>: Admins only.", parse_mode=ParseMode.HTML)
        return
    group_ids = get_target_group_chat_ids()
    db_count  = get_total_processed_count()
    group_text = f"{len(group_ids)} Linked Groups ✅" if len(group_ids) > 1 else ("Linked ✅" if group_ids else "Not Linked ⚠️")

    country_lines = ""
    if country_forwarded_counts:
        sorted_countries = sorted(country_forwarded_counts.items(), key=lambda x: x[1], reverse=True)
        country_lines = "\n🌍 <b>OTPs by Country (this session):</b>\n"
        for idx, (iso_display, cnt) in enumerate(sorted_countries[:15], 1):
            country_lines += f"  {idx}. {iso_display} — <code>{cnt}</code>\n"
        country_lines += "━━━━━━━━━━━━━━━━━━━━\n"

    gist_status = f"Connected ({GIST_ID[:8]}...) ☁️" if gist_storage.enabled else "Local Storage"
    msg = (
        f"👑 <b>OTPMAN 2 (Admin Panel)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Platform:</b> <code>KSI IPRN ({KSI_BASE_URL})</code>\n"
        f"• <b>Status:</b> <code>Active & Running ✅</code>\n"
        f"• <b>Storage:</b> <code>{gist_status}</code>\n"
        f"• <b>Target Groups:</b> <code>{group_text}</code>\n"
        f"• <b>OTPs Forwarded:</b> <code>{total_forwarded_count} (this session)</code>\n"
        f"• <b>Database:</b> <code>{db_count} total OTPs stored</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{country_lines}"
        f"🔔 Real-time dual-group monitoring active."
    )
    await msg_obj.reply_text(msg, parse_mode=ParseMode.HTML)

async def send_startup_announcement(application: Application):
    """
    Sends the startup / restart alert ONLY to the Admin private chat (DM).
    NEVER sends startup alerts to the Telegram groups, keeping groups 100% clean for OTPs only.
    """
    is_restart = (STARTUP_TYPE == "schedule")
    status_header = "🔄 <b>OTPMAN 2 AUTO-REFRESH COMPLETED</b>" if is_restart else "🚀 <b>OTPMAN 2 ONLINE (Admin Alert)</b>"

    admin_msg = (
        f"{status_header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Status:</b> <code>Active & Monitoring Live OTPs ✅</code>\n"
        f"• <b>Platform:</b> <code>KSI IPRN ({KSI_BASE_URL})</code>\n"
        f"• <b>Storage:</b> <code>28h Memory Active ☁️</code>\n"
        f"🔔 <i>All incoming OTPs are forwarded directly to your group in real-time.</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    for aid in ADMIN_USER_IDS:
        if aid:
            try:
                await send_with_retry(application.bot, aid, admin_msg)
                logger.info(f"✅ Startup/restart alert sent to admin private chat {aid}")
            except Exception as e:
                logger.warning(f"Startup alert failed for admin {aid}: {e}")

async def periodic_db_cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        cleanup_old_messages(max_age_days=7)
        logger.info("🧹 Old OTP records cleaned up (>7 days).")

async def periodic_gist_sync_loop():
    global _gist_dirty
    while True:
        await asyncio.sleep(30.0)
        if _gist_dirty and gist_storage.enabled:
            _gist_dirty = False
            await gist_storage.save_seen(seen_timestamps)

# ==========================================
# 11. Diagnostics (--test mode)
# ==========================================
async def run_diagnostics():
    print("\n=======================================================")
    print("             OTPMAN 2 SYSTEM DIAGNOSTICS")
    print("=======================================================")

    print("[1/5] Checking Telegram Bot Token...")
    try:
        req = HTTPXRequest(connection_pool_size=4)
        bot = Bot(token=TELEGRAM_BOT_TOKEN, request=req)
        me  = await bot.get_me()
        print(f"  -> SUCCESS! Bot: @{me.username} (ID: {me.id})")
    except Exception as e:
        print(f"  -> FAILED: {e}")
        return

    print("\n[2/5] Checking Linked Groups...")
    group_ids = get_target_group_chat_ids()
    if group_ids:
        for idx, gid in enumerate(group_ids, 1):
            try:
                chat = await bot.get_chat(gid)
                tag = "Primary" if idx == 1 else f"Secondary #{idx-1}"
                print(f"  -> SUCCESS! [{tag}] Group: '{chat.title}' (ID: {gid})")
            except Exception as e:
                print(f"  -> WARNING: Could not fetch group ID {gid} ({e})")
    else:
        print("  -> WARNING: No group chat IDs configured.")

    print("\n[3/5] Checking OTPMAN 2 (KSI) API Connection...")
    init_db()
    try:
        msgs = await client.fetch_incoming_messages()
        print(f"  -> SUCCESS! Connected to {KSI_BASE_URL}")
        print(f"  -> Total recent live messages fetched: {len(msgs)}")
        if msgs:
            m = msgs[0]
            print(f"  -> Latest SMS Sample: Key {m.get('_key', '')[:12]}... | Sender: {m.get('source')} | Number: {m.get('number')}")
            print(f"  -> Message Preview: \"{str(m.get('message',''))[:80]}\"")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    print("\n[4/5] Checking GitHub Gist Cloud Storage (28h Retention)...")
    if gist_storage.enabled:
        try:
            data = await gist_storage.load_seen()
            print(f"  -> SUCCESS! Connected to GitHub Gist: '{GIST_ID}'")
            print(f"  -> Stored 28h seen message count: {len(data)}")
        except Exception as e:
            print(f"  -> WARNING: Gist check failed ({e})")
    else:
        print("  -> INFO: GitHub Gist storage not configured (using local SQLite database).")

    print("\n[5/5] Checking Local SQLite Database...")
    try:
        count = get_total_processed_count()
        print(f"  -> SUCCESS! Database connected: '{DB_FILE}'")
        print(f"  -> Total stored OTP records: {count}")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    await bot.shutdown()
    print("\n=======================================================")
    print("    >>> ALL SYSTEMS ARE PROPERLY CONFIGURED! <<<")
    print("=======================================================\n")

# ==========================================
# 12. Main Entry Point
# ==========================================
def validate_config():
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is missing")
    if not KSI_API_KEY:
        errors.append("KSI_API_KEY is missing (or OTPMAN2_API_KEY / PANEL_API_KEY)")
    if not TELEGRAM_GROUP_CHAT_ID and not ADMIN_USER_IDS:
        errors.append("Either TELEGRAM_GROUP_CHAT_ID or ADMIN_USER_IDS must be set")
    if not GIST_TOKEN:
        errors.append("GIST_TOKEN is missing — required for 28h persistent storage (GitHub token with 'gist' scope)")
    if errors:
        print("\n❌ Configuration errors:")
        for err in errors:
            print(f"  - {err}")
        print("\nSet these in your .env file or GitHub Secrets.\n")
        sys.exit(1)

async def main():
    parser = argparse.ArgumentParser(description="OTPMAN 2 (KSI IPRN) Bot")
    parser.add_argument("--test", action="store_true", help="Run diagnostics and exit")
    args = parser.parse_args()

    validate_config()

    if args.test:
        await run_diagnostics()
        return

    logger.info("⚡ OTPMAN 2 starting up...")

    req = HTTPXRequest(connection_pool_size=8)
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(req)
        .build()
    )
    application.add_handler(CommandHandler("start", start_command))

    try:
        await application.initialize()
        await application.start()
        asyncio.create_task(send_startup_announcement(application))
        asyncio.create_task(poll_incoming_messages(application))
        asyncio.create_task(periodic_db_cleanup_loop())
        asyncio.create_task(periodic_gist_sync_loop())
        try:
            await application.bot.set_my_commands([("start", "📊 Bot status & admin panel")])
        except Exception:
            pass
        logger.info("✅ OTPMAN 2 is fully online and monitoring incoming messages...")

        for attempt in range(1, 6):
            try:
                await application.updater.start_polling(drop_pending_updates=True)
                break
            except Conflict:
                logger.warning(f"⚠️ Telegram conflict (previous session still releasing). Waiting 4s (attempt {attempt}/5)...")
                await asyncio.sleep(4.0)
            except Exception as poll_err:
                logger.warning(f"Telegram polling warning on attempt {attempt}: {poll_err}")
                await asyncio.sleep(3.0)

        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keepalive loop warning: {e}")
                await asyncio.sleep(5)
    finally:
        if _gist_dirty and gist_storage.enabled:
            await gist_storage.save_seen(seen_timestamps)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user or system.")
    except Exception as fatal_err:
        logger.error(f"Fatal error in bot main: {fatal_err}")
        sys.exit(2)
