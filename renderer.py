import html
from datetime import datetime, timezone
from pathlib import Path

import config

_IMPORTANCE_COLOR = {
    5: "#dc2626",  # red
    4: "#ea580c",  # orange
    3: "#2563eb",  # blue
    2: "#6b7280",  # gray
    1: "#9ca3af",  # light gray
}

_CATEGORY_BADGE = {
    "Action Required": "#dc2626",
    "Internship":      "#7c3aed",
    "Meeting":         "#0891b2",
    "School":          "#065f46",
    "FYI":             "#374151",
    "Spam/Promo":      "#9ca3af",
}


def _importance_label(n: int) -> str:
    return {5: "URGENT", 4: "High", 3: "Normal", 2: "Low", 1: "Minimal"}.get(n, "?")


def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        local = dt.astimezone()
        return local.strftime("%-I:%M %p")
    except Exception:
        return ""


def _email_card(e: dict) -> str:
    imp = e.get("importance", 2)
    color = _IMPORTANCE_COLOR.get(imp, "#6b7280")
    cat = e.get("category", "FYI")
    badge_color = _CATEGORY_BADGE.get(cat, "#374151")
    source_icon = "G" if e["source"] == "Gmail" else "O"
    source_color = "#ea4335" if e["source"] == "Gmail" else "#0078d4"
    unread_dot = '<span class="unread-dot"></span>' if e.get("unread") else ""

    return f"""
    <div class="email-card" style="border-left: 4px solid {color};">
      <div class="card-header">
        <span class="source-badge" style="background:{source_color}">{source_icon}</span>
        {unread_dot}
        <span class="from">{html.escape(e['from'][:60])}</span>
        <span class="time">{_fmt_time(e['received_at'])}</span>
      </div>
      <div class="subject">{html.escape(e['subject'])}</div>
      <div class="one-liner">{html.escape(e.get('one_liner', e.get('snippet', ''))[:200])}</div>
      <div class="badges">
        <span class="badge" style="background:{badge_color}">{html.escape(cat)}</span>
        <span class="imp-label" style="color:{color}">{_importance_label(imp)}</span>
      </div>
    </div>"""


def render(emails: list[dict], output_path: Path) -> None:
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d")
    time_str = now.strftime("%-I:%M %p")

    urgent = [e for e in emails if e.get("importance", 0) >= 4]
    rest   = [e for e in emails if e.get("importance", 0) < 4]

    urgent_html = "".join(_email_card(e) for e in urgent) or "<p class='empty'>Nothing urgent.</p>"
    rest_html   = "".join(_email_card(e) for e in rest)   or "<p class='empty'>No other emails.</p>"

    total = len(emails)
    unread = sum(1 for e in emails if e.get("unread"))
    gmail_count   = sum(1 for e in emails if e["source"] == "Gmail")
    outlook_count = sum(1 for e in emails if e["source"] == "Outlook")

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Morning Brief — {date_str}</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #f1f5f9; --muted: #94a3b8;
    --accent: #38bdf8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: var(--bg); color: var(--text); padding: 32px 24px; }}
  h1 {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .subtitle {{ color: var(--muted); margin-top: 4px; font-size: 0.9rem; }}
  .stats {{ display: flex; gap: 20px; margin: 20px 0 32px;
            font-size: 0.85rem; color: var(--muted); }}
  .stats span b {{ color: var(--text); }}
  h2 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 12px;
        text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }}
  .section {{ margin-bottom: 40px; }}
  .email-card {{
    background: var(--surface); border-radius: 8px; padding: 14px 16px;
    margin-bottom: 10px; border-left: 4px solid #6b7280;
  }}
  .card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
  .source-badge {{
    width: 20px; height: 20px; border-radius: 4px; font-size: 11px; font-weight: 700;
    color: #fff; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }}
  .unread-dot {{
    width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex-shrink: 0;
  }}
  .from {{ font-size: 0.85rem; color: var(--muted); flex: 1; white-space: nowrap;
           overflow: hidden; text-overflow: ellipsis; }}
  .time {{ font-size: 0.8rem; color: var(--muted); flex-shrink: 0; }}
  .subject {{ font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; }}
  .one-liner {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 8px; line-height: 1.4; }}
  .badges {{ display: flex; gap: 8px; align-items: center; }}
  .badge {{
    font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; color: #fff;
  }}
  .imp-label {{ font-size: 0.75rem; font-weight: 700; }}
  .empty {{ color: var(--muted); font-size: 0.9rem; padding: 12px 0; }}
  .urgent-section h2 {{ color: #fca5a5; }}
</style>
</head>
<body>
  <h1>Morning Brief</h1>
  <p class="subtitle">{date_str} &nbsp;·&nbsp; Generated at {time_str}</p>

  <div class="stats">
    <span><b>{total}</b> emails in last 24h</span>
    <span><b>{unread}</b> unread</span>
    <span><b>{gmail_count}</b> Gmail &nbsp; <b>{outlook_count}</b> Outlook</span>
  </div>

  <div class="section urgent-section">
    <h2>🔴 Needs Attention</h2>
    {urgent_html}
  </div>

  <div class="section">
    <h2>📬 Everything Else</h2>
    {rest_html}
  </div>
</body>
</html>"""

    output_path.write_text(html_out, encoding="utf-8")
