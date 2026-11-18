"""Ways to send an e-mail. ``console`` (dev) only logs it; ``smtp`` talks to a server."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger("app.modules.notifications")


class SendFailed(Exception):
    pass


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleSender:
    sent: list[tuple[str, str, str]] = []  # noqa: RUF012  (tests read it)

    async def send(self, to: str, subject: str, body: str) -> None:
        ConsoleSender.sent.append((to, subject, body))
        logger.info("email (console)", extra={"extra_fields": {"to": to, "subject": subject}})


class SmtpSender:
    async def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
        msg.set_content(body)

        def _send() -> None:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                if s.smtp_starttls:
                    smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)

        try:
            await asyncio.to_thread(_send)
        except (OSError, smtplib.SMTPException) as exc:
            raise SendFailed(str(exc)) from exc


_override: EmailSender | None = None


def use_sender(sender: EmailSender | None) -> None:
    global _override
    _override = sender


def get_sender() -> EmailSender:
    if _override is not None:
        return _override
    return SmtpSender() if get_settings().email_backend == "smtp" else ConsoleSender()
