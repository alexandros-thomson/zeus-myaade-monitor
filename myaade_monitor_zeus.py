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
Date: February 22, 2026
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
    HEADLESS: bool = os.getenv("HEADLESS_MODE", "true").lower() == "true"
    CHROME_BINARY: str = os.getenv("CHROME_BINARY", "/usr/bin/chromium")
    CHROMEDRIVER_PATH: str = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

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

    # MyAADE URLs
    MYAADE_BASE: str = "https://www1.aade.gr/taxisnet"
    MYAADE_LOGIN: str = "https://login.gsis.gr/myaade/login.jsp"
    MYAADE_PROTOCOLS: str = "https://www1.aade.gr/taxisnet/protocols"

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

# ---------------------------------------------------------------------------
# Deflection Analysis Engine
# ---------------------------------------------------------------------------
def analyze_deflection(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Analyze text for deflection patterns. Returns (type, severity, description)."""
    text_lower = text.lower()
    for pattern_name, pattern in DEFLECTION_PATTERNS.items():
        for keyword in pattern["keywords_el"] + pattern["keywords_en"]:
            if keyword.lower() in text_lower:
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
        if config.CHROME_BINARY:
            options.binary_location = config.CHROME_BINARY

        service = Service(executable_path=config.CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(10)
        logger.info("WebDriver created (headless=%s)", config.HEADLESS)
        return driver

    def _login_taxisnet(self) -> bool:
        """Authenticate via TaxisNet OAuth (GSIS login)."""
        if not config.MYAADE_USERNAME or not config.MYAADE_PASSWORD:
            logger.error("Missing MYAADE credentials")
            return False

        try:
            logger.info("Navigating to MyAADE login...")
            self.driver.get(config.MYAADE_LOGIN)
            wait = WebDriverWait(self.driver, 30)

            # Wait for username field
            username_field = wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            username_field.clear()
            username_field.send_keys(config.MYAADE_USERNAME)

            # Password field
            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(config.MYAADE_PASSWORD)

            # Submit login form
            submit_btn = self.driver.find_element(By.ID, "loginBtn")
            submit_btn.click()

            # Wait for redirect to MyAADE dashboard
            wait.until(lambda d: "taxisnet" in d.current_url or "myaade" in d.current_url)
            logger.info("TaxisNet login successful")
            return True

        except TimeoutException:
            logger.error("Login timed out -- check credentials or portal availability")
            capture_screenshot(self.driver, "login_failure", config.SCREENSHOT_DIR)
            return False
        except Exception as e:
            logger.error("Login failed: %s", e)
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
            self.driver.get(config.MYAADE_PROTOCOLS)
            wait = WebDriverWait(self.driver, 20)

            # Search for the protocol number
            try:
                search_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input[type='text'], input[name*='protocol'], #protocolSearch")
                    )
                )
                search_input.clear()
                search_input.send_keys(protocol_num)

                # Click search button
                search_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "button[type='submit'], .search-btn, #searchBtn"
                )
                search_btn.click()
                time.sleep(3)  # Wait for results to load

            except (TimeoutException, NoSuchElementException):
                logger.warning("Protocol search UI not found, reading page directly")

            # Get page content for analysis
            page_source = self.driver.page_source
            status.raw_html_length = len(page_source)
            status.page_source_hash = hashlib.sha256(page_source.encode()).hexdigest()

            # Extract status text from common elements
            try:
                status_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, ".status, .protocol-status, td, .result-text, .response"
                )
                texts = [el.text.strip() for el in status_elements if el.text.strip()]
                combined_text = " ".join(texts)
                status.status_text = combined_text[:500]  # Truncate for storage
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

        # Log the run
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

            # Save the check
            self._save_check(status)

            # Generate alerts if needed
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

        # Update run record
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

        # Initialize database
        self.db = init_database(config.DB_PATH)

        # Create directories
        config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Create browser
        self.driver = self._create_driver()

        # Login
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
            send_alerts(
                f"Zeus Monitor FAILED to login after {config.MAX_RETRIES} attempts",
                "CRITICAL",
            )
            self.shutdown()
            return

        # Send startup notification
        send_alerts(
            f"Zeus Monitor ONLINE -- tracking {len(config.TRACKED_PROTOCOLS)} protocols",
            "INFO",
        )

        # Main monitoring loop
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

                # Wait for next cycle
                logger.info(
                    "Next check in %d seconds (%s)",
                    config.CHECK_INTERVAL,
                    (datetime.now(timezone.utc) + timedelta(seconds=config.CHECK_INTERVAL)
                     ).strftime("%H:%M:%S UTC")
                )

                # Interruptible sleep
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

    # Run stats
    runs = conn.execute(
        "SELECT COUNT(*), MAX(completed_at) FROM monitor_runs WHERE status='completed'"
    ).fetchone()

    # Protocol check stats
    checks = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT protocol_number) FROM protocol_checks"
    ).fetchone()

    # Alert stats
    alerts = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN severity='CRITICAL' THEN 1 ELSE 0 END) FROM alerts"
    ).fetchone()

    # Changes detected
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

    # Recent alerts
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

    # Validate credentials
    if not config.MYAADE_USERNAME or not config.MYAADE_PASSWORD:
        logger.error("MYAADE_USERNAME and MYAADE_PASSWORD must be set")
        logger.error("Copy .env.example to .env and fill in credentials")
        sys.exit(1)

    monitor = ZeusMonitor()

    if args.once:
        # Single cycle mode
        monitor.db = init_database(args.db)
        monitor.driver = monitor._create_driver()
        if monitor._login_taxisnet():
            result = monitor.run_check_cycle()
            print(json.dumps(result, indent=2, default=str))
        monitor.shutdown()
    else:
        # Continuous monitoring
        monitor.start()


if __name__ == "__main__":
    main()
