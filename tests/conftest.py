"""Shared pytest fixtures for zeus-myaade-monitor test suite."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure sensitive env vars are NOT leaked during tests."""
    for var in (
        "MYAADE_USERNAME", "MYAADE_PASSWORD", "MYAADE_TAXISNET_CODE",
        "SLACK_WEBHOOK_URL", "DISCORD_WEBHOOK_URL", "WEBHOOK_URL",
        "SMTP_USERNAME", "SMTP_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def env_with_creds(monkeypatch):
    """Set dummy credentials for tests that need them."""
    monkeypatch.setenv("MYAADE_USERNAME", "test_user")
    monkeypatch.setenv("MYAADE_PASSWORD", "test_pass")
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("HEADLESS_MODE", "true")
    monkeypatch.setenv("TRACKED_PROTOCOLS", "214142,051340")


@pytest.fixture
def env_smtp(monkeypatch):
    """Set dummy SMTP credentials."""
    monkeypatch.setenv("SMTP_USERNAME", "test@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app_password_123")
    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with schema."""
    from myaade_monitor_zeus import init_database
    db_path = tmp_path / "test_monitor.db"
    conn = init_database(db_path)
    yield conn
    conn.close()


@pytest.fixture
def tmp_screenshot_dir(tmp_path):
    """Temporary directory for screenshots."""
    d = tmp_path / "screenshots"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Mock browser fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_driver():
    """Return a MagicMock pretending to be a Selenium WebDriver."""
    driver = MagicMock()
    driver.page_source = "<html><body>test page</body></html>"
    driver.current_url = "https://www1.aade.gr/taxisnet/protocols"
    driver.save_screenshot = MagicMock(return_value=True)
    driver.find_elements = MagicMock(return_value=[])
    return driver


@pytest.fixture
def mock_requests(monkeypatch):
    """Patch the requests module used for webhooks."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post = MagicMock(return_value=mock_resp)
    monkeypatch.setattr("myaade_monitor_zeus.requests", MagicMock(post=mock_post))
    return mock_post
