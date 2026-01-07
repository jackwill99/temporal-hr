import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from .config import (SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT,
                     SMTP_USERNAME)

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return all([SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM])


def send_notification_email(to_email: str, subject: str, body: str) -> Optional[str]:
    
    if not _smtp_configured():
        logger.info("SMTP not configured; skipping email to %s", to_email)
        return "smtp_not_configured"

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Sent notification email to %s", to_email)
        return None
    except Exception as exc:  # noqa: BLE001 - best effort logging
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return str(exc)

