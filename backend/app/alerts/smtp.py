from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings

log = logging.getLogger(__name__)


def send_email(settings: Settings, to: str, subject: str, body: str) -> bool:
    """Blocking SMTP send — call via asyncio.to_thread from async code."""
    if not settings.smtp_host or not to:
        log.info("SMTP not configured or no recipient; skipping email %r", subject)
        return False
    msg = EmailMessage()
    msg["From"] = settings.alert_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001
        log.exception("failed to send alert email")
        return False
