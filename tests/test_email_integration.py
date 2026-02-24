"""Tests for zeus_email_integration_v2.py -- Email Integration System.

Covers: ZeusEmailIntegration init, process_zeus_alert, subject/body building,
        recipient routing, attachments, send_email (dry-run & SMTP), webhook,
        and status report generation.
"""
from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta
from typing import Dict
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from zeus_email_integration_v2 import ZeusEmailIntegration


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def zeus():
    """Fresh ZeusEmailIntegration instance with env vars cleared."""
    with patch.dict(os.environ, {}, clear=True):
        return ZeusEmailIntegration()


@pytest.fixture
def zeus_configured():
    """Instance with SMTP and webhook env vars set."""
    env = {
        "SMTP_SERVER": "smtp.test.com",
        "SMTP_PORT": "465",
        "SMTP_USERNAME": "test@example.com",
        "SMTP_PASSWORD": "secret",
        "SMTP_USE_TLS": "true",
        "N8N_WEBHOOK_URL": "https://n8n.example.com/webhook/test",
        "SMTP_MAX_RETRIES": "2",
        "SMTP_RETRY_DELAY": "0.01",
    }
    with patch.dict(os.environ, env, clear=True):
        return ZeusEmailIntegration()


@pytest.fixture
def sample_alert():
    return {"protocol_num": "214142", "severity": "CRITICAL"}


# ===================================================================
# Init & Configuration Tests
# ===================================================================

class TestInit:
    """Test ZeusEmailIntegration.__init__ defaults."""

    def test_default_smtp_server(self, zeus):
        assert zeus.smtp_server == "smtp.gmail.com"

    def test_default_smtp_port(self, zeus):
        assert zeus.smtp_port == 587

    def test_smtp_use_tls_default(self, zeus):
        assert zeus.smtp_use_tls is True

    def test_monitored_protocols_count(self, zeus):
        assert len(zeus.MONITORED_PROTOCOLS) == 5

    def test_monitored_protocol_keys(self, zeus):
        expected = {"214142", "ND0113", "10690", "5534", "051340"}
        assert set(zeus.MONITORED_PROTOCOLS.keys()) == expected

    def test_recipient_groups_tiers(self, zeus):
        assert "TIER_1_ENFORCEMENT" in zeus.RECIPIENT_GROUPS
        assert "TIER_2_OVERSIGHT" in zeus.RECIPIENT_GROUPS
        assert "TIER_3_INTERNATIONAL" in zeus.RECIPIENT_GROUPS
        assert "RECORD_KEEPING" in zeus.RECIPIENT_GROUPS

    def test_case_references_present(self, zeus):
        for key in ("FBI_IC3", "IRS_CID", "EPPO", "SENATE", "OLAF"):
            assert key in zeus.CASE_REFERENCES

    def test_agency_patterns_present(self, zeus):
        for key in ("AADE", "Ktimatologio", "Dimos Spetson", "DESYP", "Cybercrime Unit"):
            assert key in zeus.AGENCY_PATTERNS

    def test_configured_smtp(self, zeus_configured):
        assert zeus_configured.smtp_server == "smtp.test.com"
        assert zeus_configured.smtp_port == 465
        assert zeus_configured.smtp_username == "test@example.com"

    def test_max_retries_from_env(self, zeus_configured):
        assert zeus_configured.smtp_max_retries == 2


# ===================================================================
# Protocol Processing Tests
# ===================================================================

class TestProcessZeusAlert:
    """Test process_zeus_alert method."""

    def test_valid_protocol_returns_dict(self, zeus, sample_alert):
        result = zeus.process_zeus_alert(sample_alert)
        assert result is not None
        assert isinstance(result, dict)

    def test_result_has_required_keys(self, zeus, sample_alert):
        result = zeus.process_zeus_alert(sample_alert)
        for key in ("to", "cc", "subject", "body_plain", "body_html",
                     "attachments", "protocol_num", "severity"):
            assert key in result

    def test_unknown_protocol_returns_none(self, zeus):
        result = zeus.process_zeus_alert({"protocol_num": "UNKNOWN"})
        assert result is None

    def test_severity_from_alert_data(self, zeus):
        result = zeus.process_zeus_alert(
            {"protocol_num": "214142", "severity": "HIGH"}
        )
        assert result["severity"] == "HIGH"

    def test_protocol_num_in_result(self, zeus, sample_alert):
        result = zeus.process_zeus_alert(sample_alert)
        assert result["protocol_num"] == "214142"

    def test_all_protocols_processable(self, zeus):
        for pnum in zeus.MONITORED_PROTOCOLS:
            result = zeus.process_zeus_alert({"protocol_num": pnum})
            assert result is not None, f"Protocol {pnum} failed to process"


# ===================================================================
# Subject & Body Building Tests
# ===================================================================

class TestBuildSubject:
    """Test _build_subject method."""

    def test_subject_contains_protocol_number(self, zeus):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        subject = zeus._build_subject("214142", info, "CRITICAL")
        assert "214142" in subject

    def test_critical_label_in_subject(self, zeus):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        subject = zeus._build_subject("214142", info, "CRITICAL")
        assert "[CRITICAL]" in subject

    def test_high_label_in_subject(self, zeus):
        info = zeus.MONITORED_PROTOCOLS["ND0113"]
        subject = zeus._build_subject("ND0113", info, "HIGH")
        assert "[HIGH]" in subject

    def test_legal_notification_in_subject(self, zeus):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        subject = zeus._build_subject("214142", info, "CRITICAL")
        assert "LEGAL NOTIFICATION" in subject


class TestBuildEmailBody:
    """Test _build_email_body method."""

    def test_body_contains_protocol_number(self, zeus, sample_alert):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        body = zeus._build_email_body("214142", info, sample_alert)
        assert "214142" in body

    def test_body_contains_stamatina(self, zeus, sample_alert):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        body = zeus._build_email_body("214142", info, sample_alert)
        assert "Stamatina Kyprianos" in body

    def test_body_contains_statutory_basis(self, zeus, sample_alert):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        body = zeus._build_email_body("214142", info, sample_alert)
        assert info["statutory_basis"] in body

    def test_expired_protocol_shows_expired(self, zeus):
        info = zeus.MONITORED_PROTOCOLS["051340"]
        body = zeus._build_email_body("051340", info, {"protocol_num": "051340"})
        assert "EXPIRED" in body

    def test_body_contains_case_references(self, zeus, sample_alert):
        info = zeus.MONITORED_PROTOCOLS["214142"]
        body = zeus._build_email_body("214142", info, sample_alert)
        assert zeus.CASE_REFERENCES["FBI_IC3"] in body
        assert zeus.CASE_REFERENCES["EPPO"] in body


# ===================================================================
# HTML Conversion Tests
# ===================================================================

class TestPlainToHtml:
    """Test _plain_to_html static method."""

    def test_returns_string(self):
        result = ZeusEmailIntegration._plain_to_html("Hello world")
        assert isinstance(result, str)

    def test_html_escaping(self):
        result = ZeusEmailIntegration._plain_to_html("<script>alert('xss')</script>")
        assert "<script>" not in result

    def test_preserves_content(self):
        result = ZeusEmailIntegration._plain_to_html("Protocol 214142")
        assert "Protocol 214142" in result


# ===================================================================
# Recipient Routing Tests
# ===================================================================

class TestGetRecipients:
    """Test _get_recipients severity-based routing."""

    def test_critical_includes_tier1_to(self, zeus):
        result = zeus._get_recipients("CRITICAL")
        assert len(result["to"]) > 0
        for addr in zeus.RECIPIENT_GROUPS["TIER_1_ENFORCEMENT"]:
            assert addr in result["to"]

    def test_critical_includes_tier2_cc(self, zeus):
        result = zeus._get_recipients("CRITICAL")
        for addr in zeus.RECIPIENT_GROUPS["TIER_2_OVERSIGHT"]:
            assert addr in result["cc"]

    def test_critical_includes_tier3_cc(self, zeus):
        result = zeus._get_recipients("CRITICAL")
        for addr in zeus.RECIPIENT_GROUPS["TIER_3_INTERNATIONAL"]:
            assert addr in result["cc"]

    def test_high_includes_tier1(self, zeus):
        result = zeus._get_recipients("HIGH")
        assert len(result["to"]) > 0

    def test_medium_no_tier3(self, zeus):
        result = zeus._get_recipients("MEDIUM")
        for addr in zeus.RECIPIENT_GROUPS["TIER_3_INTERNATIONAL"]:
            assert addr not in result["cc"]

    def test_low_includes_record_keeping(self, zeus):
        result = zeus._get_recipients("LOW")
        assert len(result["cc"]) > 0


# ===================================================================
# Attachments Tests
# ===================================================================

class TestGetAttachments:
    """Test _get_attachments method."""

    def test_base_attachments_count(self, zeus):
        attachments = zeus._get_attachments("214142")
        assert len(attachments) >= 5

    def test_protocol_051340_extra_attachment(self, zeus):
        attachments = zeus._get_attachments("051340")
        assert "protocol-051340.pdf" in attachments

    def test_other_protocol_no_extra(self, zeus):
        attachments = zeus._get_attachments("214142")
        assert "protocol-051340.pdf" not in attachments


# ===================================================================
# Send Email Tests
# ===================================================================

class TestSendEmail:
    """Test send_email with dry-run and SMTP mocking."""

    def test_dry_run_returns_true(self, zeus):
        email_config = zeus.process_zeus_alert(
            {"protocol_num": "214142", "severity": "CRITICAL"}
        )
        result = zeus.send_email(email_config, dry_run=True)
        assert result is True

    @patch("smtplib.SMTP")
    def test_send_real_email(self, mock_smtp_cls, zeus_configured):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        email_config = zeus_configured.process_zeus_alert(
            {"protocol_num": "214142", "severity": "CRITICAL"}
        )
        result = zeus_configured.send_email(email_config, dry_run=False)
        assert result is True

    @patch("smtplib.SMTP")
    def test_auth_failure_no_retry(self, mock_smtp_cls, zeus_configured):
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"Auth failed"
        )
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        email_config = zeus_configured.process_zeus_alert(
            {"protocol_num": "214142", "severity": "CRITICAL"}
        )
        result = zeus_configured.send_email(email_config, dry_run=False)
        assert result is False


# ===================================================================
# Webhook Tests
# ===================================================================

class TestSendWebhook:
    """Test send_webhook method."""

    def test_no_webhook_url_returns_false(self, zeus):
        zeus.n8n_webhook_url = ""
        result = zeus.send_webhook({"protocol_num": "214142"})
        assert result is False

    @patch("urllib.request.urlopen")
    def test_webhook_success(self, mock_urlopen, zeus_configured):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        email_config = zeus_configured.process_zeus_alert(
            {"protocol_num": "214142", "severity": "CRITICAL"}
        )
        result = zeus_configured.send_webhook(email_config)
        assert result is True
        mock_urlopen.assert_called_once()


# ===================================================================
# Status Report Tests
# ===================================================================

class TestGetStatusReport:
    """Test get_status_report method."""

    def test_report_has_timestamp(self, zeus):
        report = zeus.get_status_report()
        assert "timestamp" in report

    def test_report_protocol_count(self, zeus):
        report = zeus.get_status_report()
        assert report["monitored_protocols"] == 5

    def test_report_all_protocols_present(self, zeus):
        report = zeus.get_status_report()
        for pnum in zeus.MONITORED_PROTOCOLS:
            assert pnum in report["protocols"]

    def test_expired_protocol_status(self, zeus):
        report = zeus.get_status_report()
        assert report["protocols"]["051340"]["deadline_status"] == "EXPIRED"
        assert report["protocols"]["051340"]["days_remaining"] is None

    def test_report_protocol_has_required_fields(self, zeus):
        report = zeus.get_status_report()
        for pnum, info in report["protocols"].items():
            assert "name" in info
            assert "filing_date" in info
            assert "severity" in info
            assert "deadline_status" in info
