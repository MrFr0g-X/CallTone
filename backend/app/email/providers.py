from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    message_id: str | None
    raw: dict


def parse_sender(raw: str) -> tuple[str | None, str]:
    raw = (raw or "").strip()
    match = re.match(r"^(?P<name>.*?)\s*<(?P<email>[^>]+)>$", raw)
    if match:
        name = match.group("name").strip() or None
        return name, match.group("email").strip()
    return None, raw


class NullProvider:
    name = "null"

    def send_email(self, *, to: str, subject: str, html: str, text: str, category: str) -> EmailSendResult:
        return EmailSendResult(provider=self.name, message_id="null-delivery", raw={"success": True})


class MailtrapProvider:
    name = "mailtrap"

    def __init__(self) -> None:
        self.token = os.getenv("MAILTRAP_API_TOKEN", "").strip()
        self.url = os.getenv("MAILTRAP_API_URL", "https://send.api.mailtrap.io/api/send").strip()
        if not self.token:
            raise RuntimeError("MAILTRAP_API_TOKEN is not configured")

    def send_email(self, *, to: str, subject: str, html: str, text: str, category: str) -> EmailSendResult:
        sender_name, sender_email = parse_sender(os.getenv("MAIL_FROM", "CallTone Support <support@calltone.tech>"))
        payload = {
            "from": {"email": sender_email, **({"name": sender_name} if sender_name else {})},
            "to": [{"email": to}],
            "subject": subject,
            "html": html,
            "text": text,
            "category": category,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": os.getenv(
                    "MAIL_USER_AGENT",
                    "CallTone/1.0 (production notification service; https://calltone.tech)",
                ),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Mailtrap returned HTTP {exc.code}: {detail}") from exc

        result = json.loads(body or "{}")
        if result.get("success") is not True:
            raise RuntimeError(f"Mailtrap send failed: {result}")
        message_ids = result.get("message_ids") or []
        return EmailSendResult(
            provider=self.name,
            message_id=str(message_ids[0]) if message_ids else None,
            raw=result,
        )


class SmtpProvider:
    name = "smtp"

    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "").strip()
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME", "").strip()
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}
        if not self.host:
            raise RuntimeError("SMTP_HOST is not configured")

    def send_email(self, *, to: str, subject: str, html: str, text: str, category: str) -> EmailSendResult:
        sender_name, sender_email = parse_sender(os.getenv("MAIL_FROM", "CallTone Support <support@calltone.tech>"))
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        msg["To"] = to
        msg["X-CallTone-Category"] = category
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return EmailSendResult(provider=self.name, message_id=None, raw={"success": True})


def configured_provider_name() -> str:
    return os.getenv("MAIL_PROVIDER", "null").strip().lower() or "null"


def is_mail_enabled() -> bool:
    return os.getenv("MAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def build_provider():
    provider = configured_provider_name()
    if provider == "mailtrap":
        return MailtrapProvider()
    if provider == "smtp":
        return SmtpProvider()
    return NullProvider()
