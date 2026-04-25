from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

from app.database import settings


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _mail_logo_url() -> str:
    explicit = os.getenv("MAIL_LOGO_URL", "").strip()
    if explicit:
        return explicit
    return f"{settings.FRONTEND_URL.rstrip('/')}/favicon.png"


def _plain(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _layout(*, eyebrow: str, title: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None) -> tuple[str, str]:
    logo_url = _mail_logo_url()
    safe_eyebrow = _escape(eyebrow)
    safe_title = _escape(title)
    cta = ""
    if cta_label and cta_url:
        cta = f"""
          <tr>
            <td style="padding:22px 0 4px;">
              <a href="{_escape(cta_url)}"
                 style="display:inline-block;padding:13px 18px;border-radius:14px;background:linear-gradient(135deg,#0ea5e9,#14b8a6);color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;letter-spacing:.01em;">
                {_escape(cta_label)}
              </a>
            </td>
          </tr>
        """

    html_doc = f"""<!doctype html>
<html>
  <body style="margin:0;background:#081120;padding:32px 18px;font-family:Inter,Segoe UI,Arial,sans-serif;color:#e5edf7;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;margin:0 auto;">
      <tr>
        <td style="padding:22px;border:1px solid rgba(20,184,166,.28);border-radius:28px;background:radial-gradient(circle at top right,rgba(20,184,166,.20),transparent 38%),linear-gradient(145deg,#0b1527,#0f1f35);box-shadow:0 24px 80px rgba(0,0,0,.35);">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding-bottom:24px;">
                <table role="presentation" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="width:52px;height:52px;border-radius:18px;background:rgba(20,184,166,.12);border:1px solid rgba(20,184,166,.28);text-align:center;vertical-align:middle;">
                      <img src="{_escape(logo_url)}" width="34" height="34" alt="CallTone" style="display:inline-block;vertical-align:middle;border:0;outline:none;text-decoration:none;">
                    </td>
                    <td style="padding-left:14px;">
                      <div style="font-size:18px;font-weight:800;letter-spacing:.01em;color:#f8fafc;">CallTone</div>
                      <div style="font-size:12px;color:#7dd3fc;letter-spacing:.08em;text-transform:uppercase;">AI call quality assurance</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td>
                <div style="display:inline-block;padding:7px 11px;border-radius:999px;background:rgba(14,165,233,.12);border:1px solid rgba(14,165,233,.24);color:#67e8f9;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">{safe_eyebrow}</div>
                <h1 style="margin:18px 0 12px;color:#f8fafc;font-size:28px;line-height:1.16;font-weight:800;">{safe_title}</h1>
              </td>
            </tr>
            <tr>
              <td style="font-size:15px;line-height:1.75;color:#cbd5e1;">
                {body_html}
              </td>
            </tr>
            {cta}
            <tr>
              <td style="padding-top:28px;">
                <div style="height:1px;background:linear-gradient(90deg,rgba(20,184,166,.35),rgba(14,165,233,.12),transparent);"></div>
                <p style="margin:18px 0 0;color:#64748b;font-size:12px;line-height:1.6;">
                  This is an automated CallTone operational email. Do not forward account activation links.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return html_doc, _plain(html_doc)


def render_test_email(*, recipient_name: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(recipient_name)},</p>
      <p style="margin:0 0 12px;">Mailtrap transactional delivery is configured for CallTone. This message confirms the backend can send branded operational email.</p>
      <p style="margin:0;">Provider: <strong style="color:#f8fafc;">Mailtrap Email API</strong></p>
    """
    html_doc, text = _layout(
        eyebrow="Mail system test",
        title="CallTone email delivery is online",
        body_html=html_body,
        cta_label="Open CallTone",
        cta_url=app_url,
    )
    return RenderedEmail("CallTone mail system test", html_doc, text)


def render_invite_email(*, name: str, role: str, invite_url: str, invited_by: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0 0 12px;">{_escape(invited_by)} invited you to join CallTone as <strong style="color:#f8fafc;">{_escape(role)}</strong>.</p>
      <p style="margin:0;">Use the secure activation button below to set your password. The link expires automatically.</p>
    """
    html_doc, text = _layout(
        eyebrow="Account invitation",
        title="Activate your CallTone account",
        body_html=html_body,
        cta_label="Activate account",
        cta_url=invite_url,
    )
    return RenderedEmail("Activate your CallTone account", html_doc, text)


def render_account_activated_email(*, name: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0;">Your CallTone account is active. You can now sign in and use the role-specific dashboard assigned to you.</p>
    """
    html_doc, text = _layout(
        eyebrow="Account activated",
        title="Your CallTone account is ready",
        body_html=html_body,
        cta_label="Sign in",
        cta_url=f"{app_url.rstrip('/')}/login",
    )
    return RenderedEmail("Your CallTone account is active", html_doc, text)


def render_role_changed_email(*, name: str, old_role: str | None, new_role: str, actor: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0 0 12px;">Your CallTone role was changed by {_escape(actor)}.</p>
      <p style="margin:0;">Previous role: <strong style="color:#f8fafc;">{_escape(old_role or 'unknown')}</strong><br>New role: <strong style="color:#f8fafc;">{_escape(new_role)}</strong></p>
    """
    html_doc, text = _layout(
        eyebrow="Access changed",
        title="Your CallTone role was updated",
        body_html=html_body,
        cta_label="Review account",
        cta_url=f"{app_url.rstrip('/')}/login",
    )
    return RenderedEmail("Your CallTone role was updated", html_doc, text)


def render_status_changed_email(*, name: str, status: str, actor: str, app_url: str) -> RenderedEmail:
    title = "Your CallTone account was enabled" if status == "active" else "Your CallTone account was disabled"
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0;">Your account status was changed to <strong style="color:#f8fafc;">{_escape(status)}</strong> by {_escape(actor)}.</p>
    """
    html_doc, text = _layout(
        eyebrow="Account status",
        title=title,
        body_html=html_body,
        cta_label="Open CallTone",
        cta_url=app_url,
    )
    return RenderedEmail(title, html_doc, text)


def render_call_completed_email(*, name: str, call_id: str, filename: str, score: object, severity: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0 0 12px;">Call analysis completed for <strong style="color:#f8fafc;">{_escape(filename)}</strong>.</p>
      <p style="margin:0;">Overall score: <strong style="color:#f8fafc;">{_escape(score)}</strong><br>Severity: <strong style="color:#f8fafc;">{_escape(severity)}</strong></p>
    """
    html_doc, text = _layout(
        eyebrow="QA report ready",
        title="A call analysis report is ready",
        body_html=html_body,
        cta_label="View report",
        cta_url=f"{app_url.rstrip('/')}/qa/call/{_escape(call_id)}",
    )
    return RenderedEmail("CallTone report ready", html_doc, text)


def render_call_failed_email(*, name: str, call_id: str, filename: str, error: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Hi {_escape(name)},</p>
      <p style="margin:0 0 12px;">The pipeline failed while processing <strong style="color:#f8fafc;">{_escape(filename)}</strong>.</p>
      <p style="margin:0;">Safe error summary: <strong style="color:#fecaca;">{_escape(error[:500])}</strong></p>
    """
    html_doc, text = _layout(
        eyebrow="Pipeline alert",
        title="Call analysis needs attention",
        body_html=html_body,
        cta_label="Open call",
        cta_url=f"{app_url.rstrip('/')}/qa/call/{_escape(call_id)}",
    )
    return RenderedEmail("CallTone pipeline failure", html_doc, text)


def render_context_ticket_email(*, title: str, company: str, field: str, status: str, actor: str, app_url: str) -> RenderedEmail:
    html_body = f"""
      <p style="margin:0 0 12px;">Context ticket update from {_escape(actor)}.</p>
      <p style="margin:0;">Company: <strong style="color:#f8fafc;">{_escape(company)}</strong><br>Field: <strong style="color:#f8fafc;">{_escape(field)}</strong><br>Status: <strong style="color:#f8fafc;">{_escape(status)}</strong></p>
    """
    html_doc, text = _layout(
        eyebrow="Context governance",
        title=title,
        body_html=html_body,
        cta_label="Open context",
        cta_url=f"{app_url.rstrip('/')}/qa/context",
    )
    return RenderedEmail(title, html_doc, text)

