import smtplib

import pytest

from services import email_service
from services.email_service import send_email


class FakeSMTP:
    """Stands in for smtplib.SMTP as a context manager, recording the calls
    send_email is expected to make (starttls, login, sendmail)."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def sendmail(self, from_addr, to_addrs, message):
        self.calls.append(("sendmail", from_addr, to_addrs, message))


@pytest.fixture(autouse=True)
def _reset_fake_smtp_instances():
    FakeSMTP.instances.clear()


@pytest.fixture()
def smtp_configured(monkeypatch):
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(email_service.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", "someone@gmail.com")
    monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(email_service.settings, "SMTP_FROM_EMAIL", "someone@gmail.com")


class TestSendEmail:
    def test_skips_the_send_entirely_when_credentials_are_not_set(self, monkeypatch):
        monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", None)
        monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", None)
        monkeypatch.setattr(smtplib, "SMTP", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not connect")))

        result = send_email("Subject", "<p>hi</p>", "someone@example.com")

        assert result is False

    def test_returns_true_on_a_successful_send(self, smtp_configured, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is True

    def test_sends_the_expected_envelope_and_content(self, smtp_configured, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

        send_email("Weekly digest", "<p>content</p>", "someone@example.com")

        smtp = FakeSMTP.instances[0]
        assert smtp.host == "smtp.gmail.com"
        assert smtp.port == 587
        assert ("starttls",) in smtp.calls
        assert ("login", "someone@gmail.com", "app-password") in smtp.calls

        sendmail_call = next(c for c in smtp.calls if c[0] == "sendmail")
        _, from_addr, to_addrs, message = sendmail_call
        assert from_addr == "someone@gmail.com"
        assert to_addrs == ["someone@example.com"]
        assert "Weekly digest" in message
        assert "<p>content</p>" in message

    def test_returns_false_when_authentication_fails(self, smtp_configured, monkeypatch):
        class RejectingSMTP(FakeSMTP):
            def login(self, username, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        monkeypatch.setattr(smtplib, "SMTP", RejectingSMTP)

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is False

    def test_returns_false_on_a_connection_error(self, smtp_configured, monkeypatch):
        def raise_connection_error(*args, **kwargs):
            raise OSError("network is down")

        monkeypatch.setattr(smtplib, "SMTP", raise_connection_error)

        assert send_email("Subject", "<p>hi</p>", "someone@example.com") is False
