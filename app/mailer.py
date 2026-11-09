"""Sends the verification code by email through Brevo's HTTPS API (free plan: 300 emails a day).

HTTPS is used on purpose: free hosts often block normal SMTP ports.
"""
import json
import logging
import urllib.error
import urllib.request

from . import config

log = logging.getLogger("mailer")

_SUBJECTS = {
    "verify": "Your {app} verification code: {code}",
    "reset": "Your {app} password reset code: {code}",
}
_LINES = {
    "verify": "Use this code to activate your account.",
    "reset": "Use this code to choose a new password.",
}


def send_code(to_email: str, to_name: str, code: str, purpose: str) -> bool:
    """True when the email was handed to the mail service."""
    if not config.BREVO_API_KEY or not config.SENDER_EMAIL:
        if config.DEV_ECHO_CODE:
            log.warning("DEV code for %s (%s): %s", to_email, purpose, code)
            print(f"[DEV] {purpose} code for {to_email}: {code}", flush=True)
            return True
        log.error("Email is not set up: add BREVO_API_KEY and SENDER_EMAIL")
        return False

    subject = _SUBJECTS[purpose].format(app=config.APP_NAME, code=code)
    html = f"""<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px;border:1px solid #dde;border-radius:14px">
<h2 style="color:#0F7B5C;margin:0 0 8px">{config.APP_NAME}</h2>
<p style="color:#333">Assalamu alaikum {_esc(to_name)},</p>
<p style="color:#333">{_LINES[purpose]}</p>
<p style="font-size:34px;letter-spacing:8px;font-weight:bold;text-align:center;margin:22px 0;color:#053D2E">{code}</p>
<p style="color:#666;font-size:13px">The code works for {config.CODE_MINUTES} minutes. If you did not ask for it, ignore this email.</p>
</div>"""
    body = {
        "sender": {"name": config.SENDER_NAME, "email": config.SENDER_EMAIL},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "htmlContent": html,
        "textContent": f"{_LINES[purpose]} Your code: {code} (valid {config.CODE_MINUTES} minutes).",
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(body).encode("utf-8"),
        headers={"api-key": config.BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        log.error("Brevo error %s: %s", e.code, e.read()[:300])
    except Exception as e:  # network problems
        log.error("Brevo request failed: %s", e)
    return False


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_KINDS = {"like": "Likes the app", "problem": "Report a problem", "mistake": "Mistake in content", "idea": "Idea / suggestion", "other": "Other"}


def send_contact(m: dict) -> bool:
    """Emails one Contact us message to the owner. Reply goes straight to the user (reply-to)."""
    if not config.BREVO_API_KEY or not config.SENDER_EMAIL:
        log.error("Email is not set up: add BREVO_API_KEY and SENDER_EMAIL")
        print(f"[CONTACT] {m}", flush=True)
        return False
    kind = _KINDS.get(m["kind"], m["kind"])
    rows = [("User ID", m["user_id"]), ("Name", m["name"]), ("Email", m["email"]), ("Phone", m["phone"]), ("Type", kind),
            ("Account email", m["account_email"]), ("Info", m["info"]), ("Sent (UTC)", m["when"])]
    table = "".join(f'<tr><td style="padding:4px 10px;color:#666">{_esc(str(k))}</td><td style="padding:4px 10px"><b>{_esc(str(v))}</b></td></tr>' for k, v in rows)
    html = (f'<div style="font-family:Arial,sans-serif;max-width:560px"><h2 style="color:#0F7B5C">{config.APP_NAME}: {_esc(kind)}</h2>'
            f'<table>{table}</table><p style="white-space:pre-wrap;border-left:4px solid #0F7B5C;padding:8px 12px;background:#f4f8f6">{_esc(m["message"])}</p></div>')
    text = "\n".join(f"{k}: {v}" for k, v in rows) + "\n\n" + m["message"]
    body = {
        "sender": {"name": config.SENDER_NAME, "email": config.SENDER_EMAIL},
        "to": [{"email": config.CONTACT_EMAIL, "name": "Al-Nur CodeFusion"}],
        "replyTo": {"email": m["email"], "name": m["name"]},
        "subject": f"[{config.APP_NAME}] {kind} · user #{m['user_id']} · {m['name']}",
        "htmlContent": html,
        "textContent": text,
    }
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(body).encode("utf-8"),
                                 headers={"api-key": config.BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        log.error("Brevo error %s: %s", e.code, e.read()[:300])
    except Exception as e:
        log.error("Brevo request failed: %s", e)
    return False
