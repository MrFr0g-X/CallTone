from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import settings
from app.models import Call, EmailEvent, QaReport, User
from app.email.providers import build_provider, configured_provider_name, is_mail_enabled, parse_sender
from app.email.templates import (
    RenderedEmail,
    render_account_activated_email,
    render_call_completed_email,
    render_call_failed_email,
    render_context_ticket_email,
    render_invite_email,
    render_role_changed_email,
    render_status_changed_email,
    render_test_email,
)


def app_url() -> str:
    return os.getenv("MAIL_APP_BASE_URL", settings.FRONTEND_URL).rstrip("/")


def api_url() -> str:
    return os.getenv("MAIL_API_BASE_URL", "").strip()


def mail_status(db: Session) -> dict[str, Any]:
    last = db.query(EmailEvent).order_by(EmailEvent.created_at.desc()).first()
    sender_name, sender_email = parse_sender(os.getenv("MAIL_FROM", "CallTone Support <support@calltone.tech>"))
    enabled = is_mail_enabled()
    provider = configured_provider_name()
    configured = provider == "null" or bool(os.getenv("MAILTRAP_API_TOKEN") or os.getenv("SMTP_HOST"))
    return {
        "enabled": enabled,
        "configured": configured,
        "provider": provider,
        "fromEmail": sender_email,
        "fromName": sender_name,
        "replyTo": os.getenv("MAIL_REPLY_TO", "support@calltone.tech"),
        "appBaseUrl": app_url(),
        "apiBaseUrl": api_url(),
        "logoUrl": os.getenv("MAIL_LOGO_URL", f"{settings.FRONTEND_URL.rstrip('/')}/favicon.png"),
        "lastEvent": _event_to_public(last) if last else None,
    }


def _event_to_public(event: EmailEvent | None) -> dict[str, Any] | None:
    if not event:
        return None
    return {
        "id": event.id,
        "eventType": event.event_type,
        "recipientEmail": event.recipient_email,
        "subject": event.subject,
        "status": event.status,
        "provider": event.provider,
        "providerMessageId": event.provider_message_id,
        "error": event.error,
        "createdAt": event.created_at.isoformat() if event.created_at else None,
        "sentAt": event.sent_at.isoformat() if event.sent_at else None,
    }


def send_rendered(
    db: Session,
    *,
    event_type: str,
    recipient_email: str,
    rendered: RenderedEmail,
    recipient_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> EmailEvent:
    event = EmailEvent(
        event_type=event_type,
        recipient_email=recipient_email.strip().lower(),
        recipient_user_id=recipient_user_id,
        subject=rendered.subject,
        status="queued",
        provider=configured_provider_name(),
        metadata_json=metadata or {},
    )
    db.add(event)
    db.flush()

    if not is_mail_enabled():
        event.status = "suppressed"
        event.error = "MAIL_ENABLED=false"
        db.commit()
        db.refresh(event)
        return event

    try:
        provider = build_provider()
        result = provider.send_email(
            to=event.recipient_email,
            subject=rendered.subject,
            html=rendered.html,
            text=rendered.text,
            category=event_type,
        )
        event.provider = result.provider
        event.provider_message_id = result.message_id
        event.status = "sent"
        event.sent_at = datetime.now(timezone.utc)
        event.error = None
    except Exception as exc:
        event.status = "failed"
        event.error = str(exc)[:1000]

    db.commit()
    db.refresh(event)
    return event


def send_test_email(db: Session, *, user: User) -> EmailEvent:
    rendered = render_test_email(recipient_name=user.full_name, app_url=app_url())
    return send_rendered(
        db,
        event_type="mail.test",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"actor_user_id": user.id},
    )


def send_invite_email(db: Session, *, user: User, invite_url: str, invited_by: User) -> EmailEvent:
    rendered = render_invite_email(
        name=user.full_name,
        role=user.role.display_name if user.role else "User",
        invite_url=invite_url,
        invited_by=invited_by.full_name,
    )
    return send_rendered(
        db,
        event_type="account.invite",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"invited_by_user_id": invited_by.id, "target_role": user.role.name if user.role else None},
    )


def send_account_activated_email(db: Session, *, user: User) -> EmailEvent:
    rendered = render_account_activated_email(name=user.full_name, app_url=app_url())
    return send_rendered(
        db,
        event_type="account.activated",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"user_id": user.id},
    )


def send_role_changed_email(db: Session, *, user: User, old_role: str | None, new_role: str, actor: User) -> EmailEvent:
    rendered = render_role_changed_email(
        name=user.full_name,
        old_role=old_role,
        new_role=new_role,
        actor=actor.full_name,
        app_url=app_url(),
    )
    return send_rendered(
        db,
        event_type="account.role_changed",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"actor_user_id": actor.id, "old_role": old_role, "new_role": new_role},
    )


def send_status_changed_email(db: Session, *, user: User, new_status: str, actor: User) -> EmailEvent:
    rendered = render_status_changed_email(
        name=user.full_name,
        status=new_status,
        actor=actor.full_name,
        app_url=app_url(),
    )
    return send_rendered(
        db,
        event_type="account.status_changed",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"actor_user_id": actor.id, "new_status": new_status},
    )


def send_call_completed_email(db: Session, *, user: User, call: Call, report: QaReport) -> EmailEvent:
    rendered = render_call_completed_email(
        name=user.full_name,
        call_id=call.id,
        filename=call.original_filename,
        score=report.overall_score,
        severity=report.severity,
        app_url=app_url(),
    )
    return send_rendered(
        db,
        event_type="call.completed",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"call_id": call.id, "score": report.overall_score, "severity": report.severity},
    )


def send_call_failed_email(db: Session, *, user: User, call: Call, error: str) -> EmailEvent:
    rendered = render_call_failed_email(
        name=user.full_name,
        call_id=call.id,
        filename=call.original_filename,
        error=error,
        app_url=app_url(),
    )
    return send_rendered(
        db,
        event_type="call.failed",
        recipient_email=user.email,
        recipient_user_id=user.id,
        rendered=rendered,
        metadata={"call_id": call.id},
    )


def send_context_ticket_email(
    db: Session,
    *,
    recipient: User,
    title: str,
    company: str,
    field: str,
    status: str,
    actor: User,
    ticket_id: str,
) -> EmailEvent:
    rendered = render_context_ticket_email(
        title=title,
        company=company,
        field=field,
        status=status,
        actor=actor.full_name,
        app_url=app_url(),
    )
    return send_rendered(
        db,
        event_type="context.ticket",
        recipient_email=recipient.email,
        recipient_user_id=recipient.id,
        rendered=rendered,
        metadata={"ticket_id": ticket_id, "company": company, "field": field, "status": status},
    )


def notify_admins(db: Session, *, event_type: str, rendered: RenderedEmail, metadata: dict[str, Any] | None = None) -> list[EmailEvent]:
    admin_roles = {"owner", "super_admin", "admin"}
    users = (
        db.query(User)
        .join(User.role)
        .filter(User.is_active == True)
        .all()
    )
    events: list[EmailEvent] = []
    for user in users:
        if user.role and user.role.name in admin_roles:
            events.append(
                send_rendered(
                    db,
                    event_type=event_type,
                    recipient_email=user.email,
                    recipient_user_id=user.id,
                    rendered=rendered,
                    metadata=metadata,
                )
            )
    return events

