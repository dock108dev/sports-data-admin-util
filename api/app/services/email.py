"""Async email delivery via SMTP.

When SMTP_HOST is not configured the service logs the email body instead of
sending, which keeps local development frictionless.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


async def _send_smtp(msg: EmailMessage) -> None:
    """Deliver *msg* over SMTP using the configured credentials."""
    import aiosmtplib

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
    )


async def send_email(*, to: str, subject: str, html: str) -> None:
    """Send an HTML email to *to*.

    Falls back to logging when SMTP is not configured.
    """
    if not settings.smtp_host:
        logger.warning(
            "email_not_sent (SMTP not configured)",
            extra={"to": to, "subject": subject},
        )
        logger.debug("email_body", extra={"html": html})
        return

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(html, subtype="html")

    try:
        await _send_smtp(msg)
        logger.info("email_sent", extra={"to": to, "subject": subject})
    except Exception:
        logger.exception("email_send_failed", extra={"to": to, "subject": subject})
        raise


# ---------------------------------------------------------------------------
# Pre-built email helpers
# ---------------------------------------------------------------------------

async def send_password_reset_email(*, to: str, token: str) -> None:
    """Send a password-reset email with a link containing *token*."""
    reset_url = f"{settings.frontend_url}/auth/reset-password?token={token}"
    html = f"""\
<h2>Reset your password</h2>
<p>Click the link below to choose a new password. This link expires in 30 minutes.</p>
<p><a href="{reset_url}">{reset_url}</a></p>
<p>If you didn't request this, you can safely ignore this email.</p>
"""
    await send_email(to=to, subject="Reset your password", html=html)


async def send_magic_link_email(*, to: str, token: str) -> None:
    """Send a magic-link login email."""
    login_url = f"{settings.frontend_url}/auth/magic-link?token={token}"
    html = f"""\
<h2>Sign in to TradeLens</h2>
<p>Click the link below to sign in. This link expires in 15 minutes.</p>
<p><a href="{login_url}">{login_url}</a></p>
<p>If you didn't request this, you can safely ignore this email.</p>
"""
    await send_email(to=to, subject="Your sign-in link", html=html)
