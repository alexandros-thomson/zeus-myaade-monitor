#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
myaade_monitor_zeus.py -- Zeus MyAADE Protocol Monitor

Selenium-based 24/7 monitoring system for the MyAADE (AADE TaxisNet) portal.
Detects bureaucratic deflection patterns, tracks protocol statuses,
captures evidence screenshots, and sends instant alerts.

Part of the Justice for John Automation System.
Case: EPPO PP.00179/2026/EN | FBI IC3 | IRS CI Art. 26

Author: Kostas Kyprianos / Kypria Technologies
Date: February 25, 2026
License: MIT
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import sqlite3
import sys
import time
import traceback
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        WebDriverException, StaleElementReferenceException,
    )
except ImportError:
    print("FATAL: selenium not installed. Run: pip install selenium")
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("FATAL: webdriver-manager not installed. Run: pip install webdriver-manager")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("zeus-monitor")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
class Config:
    """Configuration loaded from environment variables."""
    MYAADE_USERNAME: str = os.getenv("MYAADE_USERNAME", "")
    MYAADE_PASSWORD: str = os.getenv("MYAADE_PASSWORD", "")
    MYAADE_TAXISNET_CODE: str = os.getenv("MYAADE_TAXISNET_CODE", "")

    # Monitoring intervals
    CHECK_INTERVAL: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY_SECONDS", "60"))

    # Browser config
    HEADLESS: bool = os.getenv("HEADLESS_MODE", "true").lower() not in ["false", "0", "no"]
    CHROME_BINARY: str = os.getenv("CHROME_BINARY", "")

    # Protocol tracking
    TRACKED_PROTOCOLS: List[str] = [
        p.strip() for p in os.getenv("TRACKED_PROTOCOLS", "214142").split(",")
        if p.strip()
    ]
    TRACK_ALL: bool = os.getenv("TRACK_ALL_PROTOCOLS", "true").lower() == "true"

    # Notification webhooks
    SLACK_WEBHOOK: str = os.getenv("SLACK_WEBHOOK_URL", "")
    DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    GENERIC_WEBHOOK: str = os.getenv("WEBHOOK_URL", "")

    # Paths (container paths by default)
    DB_PATH: Path = Path(os.getenv("MYAADE_DB_PATH", "/app/data/myaade_monitor.db"))
    SCREENSHOT_DIR: Path = Path(os.getenv("SCREENSHOT_DIR", "/app/screenshots"))
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", "/app/logs"))

    # AFMs to monitor
    AFM_STAMATINA: str = "044594747"
    AFM_JOHN_DECEASED: str = "051422558"

    # Δ210 submission tracking
    D210_PROTOCOL_ID: str = os.getenv("D210_PROTOCOL_ID", "")
    D210_DB_PATH: Path = Path(os.getenv("D210_DB_PATH", "/app/data/d210_tracker.db"))

    # MyAADE URLs -- GSIS OAuth login portal
    MYAADE_BASE: str = "https://www1.aade.gr/taxisnet"
    MYAADE_LOGIN_ENTRY: str = "https://www1.aade.gr/taxisnet/mytaxisnet"
    MYAADE_INBOX: str = "https://www1.aade.gr/taxisnet/mymessages/protected/inbox.htm"
    MYAADE_VIEW_MESSAGE: str = "https://www1.aade.gr/taxisnet/mymessages/protected/viewMessage.htm"
    MYAADE_APPLICATIONS: str = "https://www1.aade.gr/taxisnet/mytaxisnet/protected/applications.htm"

config = Config()

# ---------------------------------------------------------------------------
# Deflection Detection Patterns
# ---------------------------------------------------------------------------
DEFLECTION_PATTERNS = {
    "forwarded": {
        "keywords_el": ["διαβιβάστηκε", "προωθήθηκε", "αρμόδια υπηρεσία"],
        "keywords_en": ["forwarded", "referred to", "competent authority"],
        "severity": "HIGH",
        "description": "Protocol forwarded to another agency (deflection)",
    },
    "under_review": {
        "keywords_el": ["εξετάζεται", "υπό επεξεργασία", "σε εξέλιξη"],
        "keywords_en": ["under review", "processing", "in progress"],
        "severity": "WATCH",
        "description": "Generic 'under review' status (possible stalling)",
    },
    "no_jurisdiction": {
        "keywords_el": ["αναρμόδιο", "δεν υπάγεται", "δεν εμπίπτει"],
        "keywords_en": ["no jurisdiction", "not competent", "outside scope"],
        "severity": "CRITICAL",
        "description": "Agency claims no jurisdiction (hard deflection)",
    },
    "responded": {
        "keywords_el": ["απαντήθηκε", "ολοκληρώθηκε", "διεκπεραιώθηκε"],
        "keywords_en": ["answered", "completed", "resolved"],
        "severity": "CRITICAL",
        "description": "Marked as 'answered' -- verify actual resolution",
    },
    "archived": {
        "keywords_el": ["αρχειοθετήθηκε", "τέθηκε στο αρχείο"],
        "keywords_en": ["archived", "filed away"],
        "severity": "CRITICAL",
        "description": "Protocol archived without resolution",
    },
    "doy_peiraia_redirect": {
        "keywords_el": [
            "δου κατοίκων εξωτερικού",
            "αρμόδια δου εξωτερικού",
            "κατοίκων εξωτερικού",
        ],
        "keywords_en": [
            "doy foreign residents",
            "residents abroad tax office",
            "not our doy",
        ],
        "severity": "CRITICAL",
        "description": "ΔΟΥ A' Peiraia deflection to ΔΟΥ Κατοίκων Εξωτερικού",
    },
}

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class ProtocolStatus:
    """Snapshot of a protocol's status at a point in time."""
    protocol_number: str
    status_text: str = ""
    status_date: str = ""
    agency: str = ""
    subject: str = ""
    response_text: str = ""
    deflection_type: Optional[str] = None
    deflection_severity: Optional[str] = None
    screenshot_path: Optional[str] = None
    screenshot_hash: Optional[str] = None
    page_source_hash: Optional[str] = None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_html_length: int = 0
    changed: bool = False

# ---------------------------------------------------------------------------
# Database Layer -- SQLite with WAL mode
# ---------------------------------------------------------------------------
CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS protocol_checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol_number TEXT NOT NULL,
    status_text     TEXT,
    status_date     TEXT,
    agency          TEXT,
    subject         TEXT,
    response_text   TEXT,
    deflection_type TEXT,
    deflection_severity TEXT,
    screenshot_path TEXT,
    screenshot_hash TEXT,
    page_source_hash TEXT,
    checked_at      TEXT NOT NULL,
    raw_html_length INTEGER DEFAULT 0,
    changed         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol_number TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    details         TEXT,
    sent_slack      INTEGER DEFAULT 0,
    sent_discord    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    protocols_checked INTEGER DEFAULT 0,
    alerts_generated INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_checks_protocol
    ON protocol_checks(protocol_number);
CREATE INDEX IF NOT EXISTS idx_checks_time
    ON protocol_checks(checked_at);
CREATE INDEX IF NOT EXISTS idx_alerts_protocol
    ON alerts(protocol_number);

CREATE TABLE IF NOT EXISTS d210_submissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id       TEXT UNIQUE,
    protocol_number     TEXT NOT NULL,
    submission_date     TEXT NOT NULL,
    submitting_doy      TEXT DEFAULT 'DOU A Peiraia',
    status              TEXT DEFAULT 'pending',
    doy_response        TEXT,
    deflection_type     TEXT,
    cover_letter_excerpt TEXT,
    slack_alerted       INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_d210_protocol
    ON d210_submissions(protocol_number);
CREATE INDEX IF NOT EXISTS idx_d210_status
    ON d210_submissions(status);
"""

def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(CREATE_SCHEMA_SQL)
    conn.commit()
    logger.info("Database initialized: %s", db_path)
    return conn

# ---------------------------------------------------------------------------
# Screenshot & Evidence Capture
# ---------------------------------------------------------------------------
def capture_screenshot(driver, protocol_num: str, screenshot_dir: Path) -> tuple[Optional[str], Optional[str]]:
    """Capture a screenshot and return (path, sha256_hash)."""
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"protocol_{protocol_num}_{ts}.png"
    filepath = screenshot_dir / filename
    try:
        driver.save_screenshot(str(filepath))
        with open(filepath, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        logger.info("Screenshot saved: %s (SHA256: %s)", filename, file_hash[:16])
        return str(filepath), file_hash
    except Exception as e:
        logger.error("Screenshot failed for %s: %s", protocol_num, e)
        return None, None

def capture_html_error(driver, error_type: str, screenshot_dir: Path) -> str:
    """Capture the full HTML of an error page for diagnosis."""
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"error_{error_type}_{ts}.html"
    filepath = screenshot_dir / filename
    try:
        page_source = driver.page_source
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Error Capture: {error_type}</title>
    <meta charset="utf-8">
    <meta name="captured_at" content="{datetime.now(timezone.utc).isoformat()}">
    <meta name="current_url" content="{driver.current_url}">
    <meta name="page_title" content="{driver.title}">
</head>
<body>
    <h1>Error Capture Report</h1>
    <ul>
        <li><strong>Error Type:</strong> {error_type}</li>
        <li><strong>URL:</strong> {driver.current_url}</li>
        <li><strong>Page Title:</strong> {driver.title}</li>
        <li><strong>Captured:</strong> {datetime.now(timezone.utc).isoformat()}</li>
    </ul>
    <hr>
    <h2>Page Source:</h2>
    <pre>{page_source}</pre>
</body>
</html>""")
        logger.info("Error HTML saved: %s", filename)
        return str(filepath)
    except Exception as e:
        logger.error("Failed to capture error HTML: %s", e)
        return ""

# ---------------------------------------------------------------------------
# Deflection Analysis Engine
# ---------------------------------------------------------------------------
def analyze_deflection(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Analyze text for deflection patterns. Returns (type, severity, description)."""
    def _norm(s: str) -> str:
        """Remove combining diacritics (Unicode category Mn = Mark, Nonspacing) and
        casefold for accent- and case-insensitive Greek/Latin matching."""
        return "".join(
            c for c in unicodedata.normalize("NFD", s.casefold())
            if unicodedata.category(c) != "Mn"  # Mn = Mark, Nonspacing (e.g. accent ά→α)
        )

    text_norm = _norm(text)
    for pattern_name, pattern in DEFLECTION_PATTERNS.items():
        for keyword in pattern["keywords_el"] + pattern["keywords_en"]:
            norm_kw = _norm(keyword)
            # Guard: skip if keyword normalizes to empty (avoids "" in text → always True)
            if norm_kw and norm_kw in text_norm:
                return pattern_name, pattern["severity"], pattern["description"]
    return None, None, None

# ---------------------------------------------------------------------------
# Notification System
# ---------------------------------------------------------------------------
def send_slack_alert(webhook_url: str, message: str, severity: str = "INFO") -> bool:
    """Send an alert to Slack via webhook."""
    if not webhook_url or not requests:
        return False
    color_map = {"CRITICAL": "#FF0000", "HIGH": "#FF6600", "WATCH": "#FFCC00", "INFO": "#0066FF"}
    payload = {
        "attachments": [{
            "color": color_map.get(severity, "#808080"),
            "title": f"Zeus Monitor Alert [{severity}]",
            "text": message,
            "footer": "Zeus MyAADE Monitor | Justice for John",
            "ts": int(time.time()),
        }]
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error("Slack notification failed: %s", e)
        return False

def send_discord_alert(webhook_url: str, message: str, severity: str = "INFO") -> bool:
    """Send an alert to Discord via webhook."""
    if not webhook_url or not requests:
        return False
    color_map = {"CRITICAL": 0xFF0000, "HIGH": 0xFF6600, "WATCH": 0xFFCC00, "INFO": 0x0066FF}
    payload = {
        "embeds": [{
            "title": f"Zeus Monitor Alert [{severity}]",
            "description": message,
            "color": color_map.get(severity, 0x808080),
            "footer": {"text": "Zeus MyAADE Monitor | Justice for John"},
        }]
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error("Discord notification failed: %s", e)
        return False

def send_alerts(message: str, severity: str = "INFO") -> None:
    """Send alerts to all configured notification channels."""
    if config.SLACK_WEBHOOK:
        send_slack_alert(config.SLACK_WEBHOOK, message, severity)
    if config.DISCORD_WEBHOOK:
        send_discord_alert(config.DISCORD_WEBHOOK, message, severity)
    if config.GENERIC_WEBHOOK and requests:
        try:
            requests.post(config.GENERIC_WEBHOOK, json={
                "severity": severity,
                "message": message,
                "source": "zeus-myaade-monitor",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, timeout=10)
        except Exception as e:
            logger.error("Generic webhook failed: %s", e)


# Δ210 cover letter excerpt displayed in Slack alerts
_D210_COVER_LETTER_EXCERPT = (
    "Υποβολή Δ210 — Αίτηση πλήρους ιστορικού ΕΝΦΙΑ για ΑΦΜ 051422558 (2020-2026). "
    "Αρμόδια ΔΟΥ: ΔΟΥ Α' Πειραιά. "
    "Τυχόν ανακατεύθυνση σε ΔΟΥ Κατοίκων Εξωτερικού αποτελεί παράνομη αποφυγή αρμοδιότητας "
    "και θα αναφερθεί στην EPPO, ΣΔΟΕ και FBI IC3."
)


def send_d210_slack_alert(
    webhook_url: str,
    protocol_number: str,
    status: str,
    doy_response: str = "",
    deflection_type: str = "",
    cover_letter_excerpt: str = _D210_COVER_LETTER_EXCERPT,
) -> bool:
    """Send a Δ210-specific Slack alert with embedded cover letter excerpt."""
    if not webhook_url or not requests:
        return False

    severity = "CRITICAL" if deflection_type == "doy_peiraia_redirect" else "HIGH"
    color_map = {"CRITICAL": "#FF0000", "HIGH": "#FF6600", "WATCH": "#FFCC00", "INFO": "#0066FF"}

    fields = [
        {"title": "Protocol", "value": protocol_number, "short": True},
        {"title": "Status", "value": status, "short": True},
    ]
    if deflection_type:
        fields.append({"title": "Deflection", "value": deflection_type, "short": True})
    if doy_response:
        fields.append({"title": "ΔΟΥ Response", "value": doy_response[:200], "short": False})

    payload = {
        "attachments": [{
            "color": color_map.get(severity, "#808080"),
            "title": f"Δ210 Status Change [{severity}] — Protocol {protocol_number}",
            "text": cover_letter_excerpt,
            "fields": fields,
            "footer": "Zeus MyAADE Monitor | Δ210 Tracker | Justice for John",
            "ts": int(time.time()),
        }]
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        success = resp.status_code == 200
        if success:
            logger.info("Δ210 Slack alert sent for protocol %s [%s]", protocol_number, severity)
        return success
    except Exception as e:
        logger.error("Δ210 Slack notification failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Zeus Monitor -- Core Engine
# ---------------------------------------------------------------------------
class ZeusMonitor:
    """24/7 MyAADE protocol monitoring engine using Selenium."""

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.db: Optional[sqlite3.Connection] = None
        self.running = True
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Handle graceful shutdown."""
        def _handler(signum, frame):
            logger.info("Shutdown signal received (signal %s)", signum)
            self.running = False
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def _create_driver(self) -> webdriver.Chrome:
        """Create a Selenium Chrome/Chromium WebDriver."""
        options = ChromeOptions()
        if config.HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=el-GR")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")

        # Use webdriver-manager to automatically download and manage ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(10)
        logger.info("WebDriver created (headless=%s)", config.HEADLESS)
        return driver

    def _find_login_button(self, wait: WebDriverWait):
        """Find the GSIS login submit button using multiple fallback selectors."""
        selectors = [
            (By.NAME, "btn_login"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "button.btn"),
            (By.ID, "loginBtn"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.XPATH, "//button[contains(text(),'Σύνδεση')]"),
            (By.XPATH, "//button[contains(text(),'Login')]"),
        ]
        for by, selector in selectors:
            try:
                element = wait.until(EC.element_to_be_clickable((by, selector)))
                logger.info("Login button found via %s='%s'", by, selector)
                return element
            except (TimeoutException, NoSuchElementException):
                continue
        raise NoSuchElementException(
            "Could not find login button with any known selector: "
            + ", ".join(f"{by}={sel}" for by, sel in selectors)
        )

    def _extract_bmctx(self) -> Optional[str]:
        """Extract the browser context (bmctx) from hidden form fields.
        
        GSIS generates a unique bmctx for each login session. We need to
        extract it from the login form before submitting credentials.
        """
        try:
            # Try to find the bmctx in hidden input fields
            hidden_inputs = self.driver.find_elements(
                By.CSS_SELECTOR, "input[type='hidden']"
            )
            for input_elem in hidden_inputs:
                name = input_elem.get_attribute("name")
                value = input_elem.get_attribute("value")
                if name == "bmctx" or "bmctx" in str(value):
                    logger.info("Extracted bmctx: %s", value[:20] + "...")
                    return value
            
            # Alternative: look in page source
            page_source = self.driver.page_source
            if "bmctx=" in page_source:
                start = page_source.find("bmctx=") + 6
                end = page_source.find("&", start)
                if end == -1:
                    end = page_source.find('"', start)
                bmctx = page_source[start:end]
                logger.info("Extracted bmctx from page source: %s", bmctx[:20] + "...")
                return bmctx
            
            logger.warning("Could not extract bmctx from form")
            return None
        except Exception as e:
            logger.error("Error extracting bmctx: %s", e)
            return None

    def _login_taxisnet(self) -> bool:
        """Authenticate via TaxisNet OAuth (GSIS login).
        
        GSIS login flow:
        1. Visit the login entry page
        2. Extract the dynamic bmctx (browser context) from the form
        3. Fill in username and password
        4. Submit the form
        5. Wait for redirect to taxisnet
        """
        if not config.MYAADE_USERNAME or not config.MYAADE_PASSWORD:
            logger.error("Missing MYAADE credentials in .env")
            return False

        try:
            logger.info("Navigating to GSIS login entry page...")
            self.driver.get(config.MYAADE_LOGIN_ENTRY)
            wait = WebDriverWait(self.driver, 30)

            # Wait for the login form to load
            wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            logger.info("Login form loaded, extracting bmctx...")

            # Extract the dynamic bmctx
            bmctx = self._extract_bmctx()
            if not bmctx:
                logger.warning("Could not extract bmctx, proceeding anyway...")

            # Fill username
            username_field = self.driver.find_element(By.ID, "username")
            username_field.clear()
            username_field.send_keys(config.MYAADE_USERNAME)
            logger.info("Username entered")

            # Fill password
            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(config.MYAADE_PASSWORD)
            logger.info("Password entered")

            # Find and click submit button
            submit_btn = self._find_login_button(wait)
            logger.info("Clicking login button...")
            submit_btn.click()
            logger.info("Login form submitted, waiting for redirect...")

            # Wait for successful redirect (45 second timeout)
            try:
                wait.until(
                    lambda d: any(kw in d.current_url for kw in [
                        "taxisnet", "myaade", "aade.gr", "applications.htm",
                    ]),
                    )
                logger.info("TaxisNet login successful (URL: %s)", self.driver.current_url)
                return True
            except TimeoutException:
                # Login failed - still at auth_cred_submit or error page
                current_url = self.driver.current_url
                page_title = self.driver.title
                page_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                
                logger.error("Login failed after 45 seconds")
                logger.error("Current URL: %s", current_url)
                logger.error("Page title: %s", page_title)
                logger.error("Page text (first 500 chars): %s", page_text)
                
                # Diagnose the error
                html = self.driver.page_source.lower()
                if "locked" in html or "κλειστ" in page_title.lower():
                    logger.error("[DIAGNOSIS] Account appears LOCKED")
                elif "invalid" in html or "άκυρ" in page_title.lower():
                    logger.error("[DIAGNOSIS] Invalid credentials detected")
                elif "expired" in html or "λήξη" in page_text.lower():
                    logger.error("[DIAGNOSIS] Password may be EXPIRED")
                else:
                    logger.error("[DIAGNOSIS] Unknown error at GSIS backend")
                
                # Capture error evidence
                error_file = capture_html_error(self.driver, "login_failed", config.SCREENSHOT_DIR)
                logger.error("Error HTML saved: %s", error_file)
                capture_screenshot(self.driver, "login_failed", config.SCREENSHOT_DIR)
                
                return False

        except TimeoutException:
            logger.error("Login form not found (page load timeout)")
            logger.error("Current URL: %s", self.driver.current_url)
            capture_screenshot(self.driver, "login_form_missing", config.SCREENSHOT_DIR)
            capture_html_error(self.driver, "login_form_timeout", config.SCREENSHOT_DIR)
            return False
        except NoSuchElementException as e:
            logger.error("Login element not found: %s", e)
            capture_screenshot(self.driver, "login_element_missing", config.SCREENSHOT_DIR)
            capture_html_error(self.driver, "login_element_missing", config.SCREENSHOT_DIR)
            return False
        except Exception as e:
            logger.error("Login failed: %s", e)
            logger.error(traceback.format_exc())
            capture_screenshot(self.driver, "login_exception", config.SCREENSHOT_DIR)
            capture_html_error(self.driver, "login_exception", config.SCREENSHOT_DIR)
            return False

    def _get_previous_status(self, protocol_num: str) -> Optional[str]:
        """Get the most recent page_source_hash for change detection."""
        cursor = self.db.execute(
            "SELECT page_source_hash FROM protocol_checks "
            "WHERE protocol_number = ? ORDER BY checked_at DESC LIMIT 1",
            (protocol_num,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _save_check(self, status: ProtocolStatus) -> int:
        """Save a protocol check result to the database."""
        cursor = self.db.execute(
            """INSERT INTO protocol_checks
            (protocol_number, status_text, status_date, agency, subject,
             response_text, deflection_type, deflection_severity,
             screenshot_path, screenshot_hash, page_source_hash,
             checked_at, raw_html_length, changed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (status.protocol_number, status.status_text, status.status_date,
             status.agency, status.subject, status.response_text,
             status.deflection_type, status.deflection_severity,
             status.screenshot_path, status.screenshot_hash,
             status.page_source_hash, status.checked_at,
             status.raw_html_length, int(status.changed)),
        )
        self.db.commit()
        return cursor.lastrowid

    def _save_alert(self, protocol_num: str, alert_type: str,
                    severity: str, message: str, details: str = "") -> int:
        """Save an alert to the database."""
        cursor = self.db.execute(
            """INSERT INTO alerts
            (protocol_number, alert_type, severity, message, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (protocol_num, alert_type, severity, message, details,
             datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()
        return cursor.lastrowid

    def check_protocol(self, protocol_num: str) -> ProtocolStatus:
        """Check a single protocol's status on MyAADE."""
        status = ProtocolStatus(protocol_number=protocol_num)

        try:
            # Navigate to protocols page
            self.driver.get(config.MYAADE_INBOX)
            wait = WebDriverWait(self.driver, 20)

            # Search for the protocol number
            try:
                search_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#searchResults td a, #searchResults td")
                    )
                )
                search_input.clear()
                search_input.send_keys(protocol_num)

                # Click search button
                search_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "#searchResults"
                )
                search_btn.click()
                time.sleep(3)

            except (TimeoutException, NoSuchElementException):
                logger.warning("Inbox table not found, reading page directly")

            # Get page content for analysis
            page_source = self.driver.page_source
            status.raw_html_length = len(page_source)
            status.page_source_hash = hashlib.sha256(page_source.encode()).hexdigest()

            # Extract status text from common elements
            try:
                status_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "#searchResults td, .message-body, .msg-content"
                )
                texts = [el.text.strip() for el in status_elements if el.text.strip()]
                combined_text = " ".join(texts)
                status.status_text = combined_text[:500]
            except Exception:
                status.status_text = "Unable to extract status text"

            # Detect deflection
            full_text = status.status_text + " " + page_source
            defl_type, defl_sev, defl_desc = analyze_deflection(full_text)
            if defl_type:
                status.deflection_type = defl_type
                status.deflection_severity = defl_sev
                logger.warning(
                    "DEFLECTION DETECTED for %s: %s (%s)",
                    protocol_num, defl_desc, defl_sev
                )

            # Check for changes vs previous
            prev_hash = self._get_previous_status(protocol_num)
            if prev_hash and prev_hash != status.page_source_hash:
                status.changed = True
                logger.info("STATUS CHANGE detected for protocol %s", protocol_num)

            # Capture evidence screenshot
            ss_path, ss_hash = capture_screenshot(
                self.driver, protocol_num, config.SCREENSHOT_DIR
            )
            status.screenshot_path = ss_path
            status.screenshot_hash = ss_hash

        except WebDriverException as e:
            logger.error("WebDriver error checking protocol %s: %s", protocol_num, e)
            status.status_text = f"ERROR: {str(e)[:200]}"
        except Exception as e:
            logger.error("Unexpected error checking protocol %s: %s", protocol_num, e)
            status.status_text = f"ERROR: {str(e)[:200]}"

        return status

    def run_check_cycle(self) -> Dict[str, Any]:
        """Run one complete monitoring cycle."""
        cycle_start = datetime.now(timezone.utc).isoformat()
        results = []
        alerts_count = 0
        errors = 0

        run_cursor = self.db.execute(
            "INSERT INTO monitor_runs (started_at) VALUES (?)",
            (cycle_start,)
        )
        run_id = run_cursor.lastrowid
        self.db.commit()

        protocols = config.TRACKED_PROTOCOLS
        logger.info("Starting check cycle: %d protocols", len(protocols))

        for protocol_num in protocols:
            if not self.running:
                break

            logger.info("Checking protocol: %s", protocol_num)
            status = self.check_protocol(protocol_num)

            self._save_check(status)

            if status.changed:
                msg = f"Protocol {protocol_num} status CHANGED"
                if status.deflection_type:
                    msg += f" -- DEFLECTION: {status.deflection_type}"
                self._save_alert(protocol_num, "status_change",
                                 status.deflection_severity or "INFO", msg)
                send_alerts(msg, status.deflection_severity or "INFO")
                alerts_count += 1

            if status.deflection_type and not status.changed:
                msg = (f"Protocol {protocol_num}: "
                       f"{status.deflection_type} ({status.deflection_severity})")
                self._save_alert(protocol_num, "deflection",
                                 status.deflection_severity, msg)
                send_alerts(msg, status.deflection_severity)
                alerts_count += 1

            if status.status_text.startswith("ERROR:"):
                errors += 1

            results.append(asdict(status))

        self.db.execute(
            """UPDATE monitor_runs SET
            completed_at = ?, protocols_checked = ?,
            alerts_generated = ?, errors = ?, status = 'completed'
            WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), len(results),
             alerts_count, errors, run_id),
        )
        self.db.commit()

        logger.info(
            "Cycle complete: %d checked, %d alerts, %d errors",
            len(results), alerts_count, errors
        )

        return {
            "run_id": run_id,
            "protocols_checked": len(results),
            "alerts": alerts_count,
            "errors": errors,
            "results": results,
        }

    def start(self) -> None:
        """Start the continuous monitoring loop."""
        logger.info("="*60)
        logger.info("ZEUS MYAADE MONITOR -- STARTING")
        logger.info("Tracked protocols: %s", config.TRACKED_PROTOCOLS)
        logger.info("Check interval: %d seconds", config.CHECK_INTERVAL)
        logger.info("Headless mode: %s", config.HEADLESS)
        logger.info("="*60)

        self.db = init_database(config.DB_PATH)

        config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)

        self.driver = self._create_driver()

        retry_count = 0
        while retry_count < config.MAX_RETRIES and self.running:
            if self._login_taxisnet():
                break
            retry_count += 1
            logger.warning("Login attempt %d/%d failed, retrying in %ds...",
                           retry_count, config.MAX_RETRIES, config.RETRY_DELAY)
            time.sleep(config.RETRY_DELAY)

        if retry_count >= config.MAX_RETRIES:
            logger.error("Login failed after %d attempts. Exiting.", config.MAX_RETRIES)
            logger.error("")
            logger.error("TROUBLESHOOTING:")
            logger.error("1. Verify MYAADE_USERNAME and MYAADE_PASSWORD in .env")
            logger.error("2. Check if account is locked (too many failed attempts)")
            logger.error("3. Check if password is expired (reset on GSIS if needed)")
            logger.error("4. Review error HTML files in %s", config.SCREENSHOT_DIR)
            logger.error("")
            send_alerts(
                f"Zeus Monitor FAILED to login after {config.MAX_RETRIES} attempts. "
                f"Check credentials, account status, and password expiration.",
                "CRITICAL",
            )
            self.shutdown()
            return

        send_alerts(
            f"Zeus Monitor ONLINE -- tracking {len(config.TRACKED_PROTOCOLS)} protocols",
            "INFO",
        )

        cycle_count = 0
        while self.running:
            try:
                cycle_count += 1
                logger.info("--- Cycle #%d ---", cycle_count)
                result = self.run_check_cycle()

                if result["alerts"] > 0:
                    logger.warning(
                        "Cycle #%d: %d ALERTS generated",
                        cycle_count, result["alerts"]
                    )

                logger.info(
                    "Next check in %d seconds (%s)",
                    config.CHECK_INTERVAL,
                    (datetime.now(timezone.utc) + timedelta(seconds=config.CHECK_INTERVAL)
                     ).strftime("%H:%M:%S UTC")
                )

                for _ in range(config.CHECK_INTERVAL):
                    if not self.running:
                        break
                    time.sleep(1)

            except WebDriverException as e:
                logger.error("WebDriver crashed: %s", e)
                logger.info("Attempting to recreate browser...")
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = self._create_driver()
                if not self._login_taxisnet():
                    logger.error("Re-login failed. Waiting before retry...")
                    time.sleep(config.RETRY_DELAY)

            except Exception as e:
                logger.error("Unexpected error in main loop: %s", e)
                logger.error(traceback.format_exc())
                time.sleep(30)

        self.shutdown()

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down Zeus Monitor...")
        send_alerts("Zeus Monitor shutting down", "INFO")
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self.db:
            self.db.close()
        logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Status Report
# ---------------------------------------------------------------------------
def print_status(db_path: Path) -> None:
    """Print a status report from the database."""
    if not db_path.exists():
        print(f"No database found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))

    runs = conn.execute(
        "SELECT COUNT(*), MAX(completed_at) FROM monitor_runs WHERE status='completed'"
    ).fetchone()

    checks = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT protocol_number) FROM protocol_checks"
    ).fetchone()

    alerts = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN severity='CRITICAL' THEN 1 ELSE 0 END) FROM alerts"
    ).fetchone()

    changes = conn.execute(
        "SELECT COUNT(*) FROM protocol_checks WHERE changed = 1"
    ).fetchone()

    print(f"\n{'='*60}")
    print(f"  ZEUS MYAADE MONITOR -- STATUS REPORT")
    print(f"  Date: {date.today()}")
    print(f"{'='*60}")
    print(f"  Completed runs:     {runs[0]}")
    print(f"  Last run:           {runs[1] or 'Never'}")
    print(f"  Total checks:       {checks[0]}")
    print(f"  Protocols tracked:  {checks[1]}")
    print(f"  Total alerts:       {alerts[0]}")
    print(f"  Critical alerts:    {alerts[1] or 0}")
    print(f"  Status changes:     {changes[0]}")
    print(f"{'='*60}")

    recent = conn.execute(
        "SELECT protocol_number, severity, message, created_at "
        "FROM alerts ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    if recent:
        print(f"\n  RECENT ALERTS:")
        for proto, sev, msg, ts in recent:
            print(f"    [{sev}] {proto}: {msg} ({ts[:19]})")
    print()
    conn.close()


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Zeus MyAADE Monitor -- 24/7 Protocol Status Tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "Examples:",
            "  python myaade_monitor_zeus.py              # Start monitoring",
            "  python myaade_monitor_zeus.py --status     # Show status report",
            "  python myaade_monitor_zeus.py --once       # Single check cycle",
            "  python myaade_monitor_zeus.py --dry-run    # Show config without running",
            "",
            "Justice for John. The deflection ends today.",
        ])
    )
    parser.add_argument("--status", action="store_true", help="Show status report")
    parser.add_argument("--once", action="store_true", help="Run a single check cycle")
    parser.add_argument("--dry-run", action="store_true", help="Show config only")
    parser.add_argument("--db", type=Path, default=config.DB_PATH, help="Database path")
    args = parser.parse_args()

    if args.status:
        print_status(args.db)
        return

    if args.dry_run:
        print(f"\nZeus MyAADE Monitor -- Configuration")
        print(f"{'='*50}")
        print(f"Username:        {'*' * len(config.MYAADE_USERNAME) if config.MYAADE_USERNAME else 'NOT SET'}")
        print(f"Headless:        {config.HEADLESS}")
        print(f"Check interval:  {config.CHECK_INTERVAL}s")
        print(f"Protocols:       {config.TRACKED_PROTOCOLS}")
        print(f"Track all:       {config.TRACK_ALL}")
        print(f"DB path:         {config.DB_PATH}")
        print(f"Screenshot dir:  {config.SCREENSHOT_DIR}")
        print(f"Slack webhook:   {'configured' if config.SLACK_WEBHOOK else 'not set'}")
        print(f"Discord webhook: {'configured' if config.DISCORD_WEBHOOK else 'not set'}")
        print(f"{'='*50}")
        return

    if not config.MYAADE_USERNAME or not config.MYAADE_PASSWORD:
        logger.error("MYAADE_USERNAME and MYAADE_PASSWORD must be set")
        logger.error("Copy .env.example to .env and fill in credentials")
        sys.exit(1)

    monitor = ZeusMonitor()

    if args.once:
        monitor.db = init_database(args.db)
        monitor.driver = monitor._create_driver()
        if monitor._login_taxisnet():
            result = monitor.run_check_cycle()
            print(json.dumps(result, indent=2, default=str))
        monitor.shutdown()
    else:
        monitor.start()


if __name__ == "__main__":
    main()
