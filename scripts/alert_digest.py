#!/usr/bin/env python3
"""Portfolio alert digest — Phase 1 (MacBook).

ONE daily email that reports anything broken across the portfolio, so failures
stop rotting silently. Reads the dashboard's live alerts, filters noise via a
per-machine ignore list, renders an email sectioned by machine, and sends it via
Resend to Erik.

Design (locked, see PROGRESS.md):
  - One email, sectioned by machine (MacBook real / Mac Mini pending until Phase 3).
  - Reads http://localhost:8000/api/alerts. The dashboard is a KeepAlive launchd
    job so it's reliably up; if it is NOT reachable after retries, that is itself
    a failure worth an email — we send a degraded notice rather than going silent.
  - Never crashes. Silence must never mask a problem.
  - Secrets from Doppler only (RESEND_API_KEY, synth-insight-labs/prd). No fallbacks.

Run:  doppler run --project synth-insight-labs --config prd -- \
        python scripts/alert_digest.py [--dry-run]

--dry-run prints the rendered email to stdout and does NOT send.
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Config -----------------------------------------------------------------

ALERTS_URL = os.environ.get("PT_ALERTS_URL", "http://localhost:8000/api/alerts")
RECIPIENT = os.environ.get("ALERT_DIGEST_TO", "spudlogic@gmail.com")
FROM_ADDR = os.environ.get(
    "ALERT_DIGEST_FROM", "Project Alerts <alerts@send.synthinsightlabs.com>"
)
RESEND_URL = "https://api.resend.com/emails"
# api.resend.com sits behind Cloudflare, which 403s Python's default urllib
# User-Agent (error code 1010). A browser-ish UA gets through. Same trick lives
# in scaffold/alerts.py for the Discord path.
BROWSER_UA = "Mozilla/5.0 (portfolio-alert-digest)"

REPO_ROOT = Path(__file__).resolve().parent.parent
IGNORE_FILE = REPO_ROOT / "scripts" / "alert_digest_ignore.json"
LOG_FILE = REPO_ROOT / "logs" / "alert_digest.log"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 3

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SEVERITY_DOT = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


# --- Small helpers ----------------------------------------------------------

def log(msg: str) -> None:
    """Append a timestamped line to the digest log. Best-effort; never raises."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} {msg}"
    print(line, file=sys.stderr)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # file logging is best-effort; stderr above always fired


def current_machine() -> str:
    """Return 'mac-mini' or 'macbook' from the hostname."""
    host = socket.gethostname().lower()
    return "mac-mini" if "mini" in host else "macbook"


def load_ignore_list(machine: str) -> set:
    """Read the per-machine ignore list. Missing/broken file → empty set (fail open)."""
    try:
        data = json.loads(IGNORE_FILE.read_text())
        return set(data.get(machine, []))
    except FileNotFoundError:
        log(f"WARN ignore file not found at {IGNORE_FILE}; ignoring nothing")
        return set()
    except Exception as exc:
        log(f"WARN could not parse ignore file ({exc}); ignoring nothing")
        return set()


# --- Data fetch -------------------------------------------------------------

def fetch_alerts() -> list:
    """Fetch alerts from the dashboard with retries.

    Returns a list of alert dicts. Raises RuntimeError only after all retries
    are exhausted — the caller turns that into a degraded email.
    """
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                ALERTS_URL, headers={"User-Agent": BROWSER_UA}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            alerts = payload.get("alerts", [])
            log(f"fetched {len(alerts)} alerts (attempt {attempt})")
            return alerts
        except Exception as exc:  # noqa: BLE001 — resilience is the point
            last_err = exc
            log(f"WARN fetch attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"dashboard unreachable after {MAX_RETRIES} attempts: {last_err}")


# --- Rendering --------------------------------------------------------------

def _summary_counts(alerts: list) -> dict:
    return {
        "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
        "warning": sum(1 for a in alerts if a.get("severity") == "warning"),
        "info": sum(1 for a in alerts if a.get("severity") == "info"),
    }


def build_subject(alerts: list) -> str:
    c = _summary_counts(alerts)
    if not alerts:
        return "[Project Alerts] ✅ All clear"
    parts = []
    if c["critical"]:
        parts.append(f"🔴 {c['critical']} critical")
    if c["warning"]:
        parts.append(f"🟡 {c['warning']} warning" + ("s" if c["warning"] != 1 else ""))
    if c["info"]:
        parts.append(f"🔵 {c['info']} info")
    return "[Project Alerts] " + ", ".join(parts)


def _render_alert_rows(alerts: list) -> str:
    rows = []
    for a in sorted(
        alerts,
        key=lambda x: (SEVERITY_ORDER.get(x.get("severity"), 3), x.get("project_name", "")),
    ):
        dot = SEVERITY_DOT.get(a.get("severity"), "⚪")
        name = a.get("project_name", "unknown")
        message = a.get("message", "")
        details = a.get("details", "")
        rows.append(
            f'<tr>'
            f'<td style="padding:6px 10px;vertical-align:top;white-space:nowrap;">{dot}</td>'
            f'<td style="padding:6px 10px;vertical-align:top;"><strong>{name}</strong><br>'
            f'<span style="color:#333;">{message}</span>'
            f'<br><span style="color:#888;font-size:12px;">{details}</span></td>'
            f'</tr>'
        )
    return "\n".join(rows)


def render_html(macbook_alerts: list, degraded_reason: str | None, sent_at: str) -> str:
    """Render the full email. One email, sectioned by machine."""
    if degraded_reason:
        macbook_body = (
            f'<div style="background:#fff3f3;border:1px solid #e0b4b4;border-radius:6px;'
            f'padding:12px;color:#8a1f1f;">'
            f'<strong>⚠️ Could not read alerts on this machine.</strong><br>'
            f'{degraded_reason}<br>'
            f'<span style="font-size:12px;color:#a55;">The dashboard being unreachable is '
            f'itself a problem — check that the project-tracker launchd job is running.</span>'
            f'</div>'
        )
    elif not macbook_alerts:
        macbook_body = (
            '<div style="color:#2e7d32;padding:8px 0;">✅ Nothing broken. All quiet.</div>'
        )
    else:
        macbook_body = (
            '<table style="border-collapse:collapse;width:100%;">'
            + _render_alert_rows(macbook_alerts)
            + '</table>'
        )

    return f"""\
<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
             color:#222;max-width:640px;margin:0 auto;padding:16px;">
  <h2 style="margin:0 0 4px;">Portfolio Alert Digest</h2>
  <div style="color:#888;font-size:13px;margin-bottom:20px;">{sent_at}</div>

  <h3 style="border-bottom:2px solid #333;padding-bottom:4px;">💻 MacBook</h3>
  {macbook_body}

  <h3 style="border-bottom:2px solid #ccc;padding-bottom:4px;color:#999;margin-top:28px;">
    🖥️ Mac Mini
  </h3>
  <div style="color:#999;padding:8px 0;">
    Pending — cross-machine reporting arrives in Phase 3.
  </div>

  <div style="color:#bbb;font-size:11px;margin-top:32px;border-top:1px solid #eee;padding-top:8px;">
    Sent by the portfolio alert digest · edit noise filters in
    <code>scripts/alert_digest_ignore.json</code>
  </div>
</body>
</html>
"""


# --- Send -------------------------------------------------------------------

def send_email(subject: str, html: str) -> None:
    """Send via Resend. Retries; raises after exhausting attempts."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        # Secrets come from Doppler. If it's missing, crash loudly — do not
        # invent a fallback and do not send from nowhere.
        raise RuntimeError(
            "RESEND_API_KEY not set — run under "
            "`doppler run --project synth-insight-labs --config prd --`"
        )

    body = json.dumps(
        {"from": FROM_ADDR, "to": [RECIPIENT], "subject": subject, "html": html}
    ).encode("utf-8")

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                RESEND_URL,
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": BROWSER_UA,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.getcode()
                if code in (200, 201):
                    log(f"email sent (HTTP {code}): {subject}")
                    return
                raise RuntimeError(f"Resend returned HTTP {code}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_err = f"HTTP {exc.code}: {detail}"
            log(f"WARN send attempt {attempt}/{MAX_RETRIES} failed: {last_err}")
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            log(f"WARN send attempt {attempt}/{MAX_RETRIES} failed: {last_err}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"failed to send after {MAX_RETRIES} attempts: {last_err}")


# --- Main -------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Portfolio alert digest (Phase 1).")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the email instead of sending."
    )
    args = parser.parse_args()

    machine = current_machine()
    ignore = load_ignore_list(machine)
    sent_at = datetime.now().strftime("%A, %B %d %Y · %-I:%M %p")

    degraded_reason = None
    alerts = []
    try:
        raw = fetch_alerts()
        alerts = [a for a in raw if a.get("project_id") not in ignore]
        dropped = len(raw) - len(alerts)
        log(f"{len(alerts)} alerts after ignore filter ({dropped} dropped)")
    except Exception as exc:  # noqa: BLE001
        degraded_reason = str(exc)
        log(f"ERROR entering degraded mode: {exc}")

    subject = "[Project Alerts] ⚠️ Digest degraded" if degraded_reason else build_subject(alerts)
    html = render_html(alerts, degraded_reason, sent_at)

    if args.dry_run:
        print(f"Subject: {subject}\nTo: {RECIPIENT}\nFrom: {FROM_ADDR}\n")
        print(html)
        return 0

    try:
        send_email(subject, html)
    except Exception as exc:  # noqa: BLE001
        log(f"ERROR could not send digest: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
