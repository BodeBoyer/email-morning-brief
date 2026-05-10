import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

_IMPORTANCE_COLOR = {
    5: "#0f2a43",
    4: "#334155",
    3: "#64748b",
    2: "#94a3b8",
    1: "#cbd5e1",
}

_CATEGORY_BADGE = {
    "Action Required": "#0f2a43",
    "Internship":      "#475569",
    "Meeting":         "#475569",
    "School":          "#475569",
    "FYI":             "#64748b",
    "Spam/Promo":      "#94a3b8",
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


def _fmt_due(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        local = dt.astimezone()
        return local.strftime("%a, %b %-d at %-I:%M %p")
    except Exception:
        return ""


def _email_card(e: dict) -> str:
    imp = e.get("importance", 2)
    color = _IMPORTANCE_COLOR.get(imp, "#6b7280")
    cat = e.get("category", "FYI")
    badge_color = _CATEGORY_BADGE.get(cat, "#374151")
    source_icon = "G" if e["source"] == "Gmail" else "O"
    source_label = "Gmail" if e["source"] == "Gmail" else "Outlook"
    unread_dot = '<span class="unread-dot"></span>' if e.get("unread") else ""

    return f"""
    <article class="email-card" style="border-left-color: {color};">
      <div class="card-header">
        {unread_dot}
        <span class="from">{html.escape(e['from'][:60])}</span>
        <span class="time">{_fmt_time(e['received_at'])}</span>
      </div>
      <div class="subject">{html.escape(e['subject'])}</div>
      <div class="one-liner">{html.escape(e.get('one_liner', e.get('snippet', ''))[:200])}</div>
      <div class="meta-row">
        <span class="source-badge">{source_icon}</span>
        <span>{source_label}</span>
        <span class="meta-divider">/</span>
        <span class="badge" style="color:{badge_color}; border-color:{badge_color};">{html.escape(cat)}</span>
        <span class="meta-divider">/</span>
        <span class="imp-label" style="color:{color};">{_importance_label(imp)}</span>
      </div>
    </article>"""


def _safe_link(url: str, label: str) -> str:
    if not url:
        return ""
    escaped_url = html.escape(url, quote=True)
    return f'<a href="{escaped_url}">{html.escape(label)}</a>'


def _canvas_card(item: dict) -> str:
    due = _fmt_due(item.get("due_at", ""))
    points = item.get("points")
    points_text = f" / {points:g} pts" if isinstance(points, (int, float)) else ""
    link = _safe_link(item.get("url", ""), "Canvas")
    link_html = f'<span class="meta-divider">/</span><span>{link}</span>' if link else ""
    return f"""
    <article class="brief-card">
      <div class="item-title">{html.escape(item.get('title', ''))}</div>
      <div class="item-detail">{html.escape(item.get('course', 'Canvas'))}</div>
      <div class="meta-row">
        <span class="badge">{html.escape(item.get('kind', 'Assignment'))}</span>
        <span>{html.escape(due)}{html.escape(points_text)}</span>
        {link_html}
      </div>
    </article>"""


def _canvas_section(canvas: Optional[dict]) -> str:
    canvas = canvas or {}
    if not canvas.get("configured"):
        body = "<p class='empty'>Canvas is not configured. Add CANVAS_BASE_URL and CANVAS_TOKEN to credentials/secrets.env.</p>"
    elif canvas.get("error"):
        body = f"<p class='empty'>Canvas could not be fetched: {html.escape(canvas['error'])}</p>"
    else:
        group_html = []
        for group in canvas.get("groups", []):
            items = group.get("items", [])
            cards = "".join(_canvas_card(item) for item in items) or "<p class='empty'>Nothing in this group.</p>"
            group_html.append(
                f"""
                <div class="brief-group">
                  <h3>{html.escape(group.get('title', 'Canvas'))}</h3>
                  {cards}
                </div>"""
            )
        body = "".join(group_html) or "<p class='empty'>No unsubmitted Canvas work found.</p>"

    return f"""
      <section class="section">
        <h2>Canvas Assignments</h2>
        {body}
      </section>"""


def _summary_section(summary: str) -> str:
    if not summary or not summary.strip():
        return ""
    return f"""
      <section class="section summary-section">
        <h2>Email Summary</h2>
        <p class="summary-text">{html.escape(summary.strip())}</p>
      </section>"""


def _fmt_event_time(start_iso: str, end_iso: str) -> str:
    s = _parse_iso(start_iso)
    e = _parse_iso(end_iso)
    if not s:
        return ""
    s_local = s.astimezone()
    out = s_local.strftime("%a, %b %-d at %-I:%M %p")
    if e:
        e_local = e.astimezone()
        if e_local.date() == s_local.date():
            out += f" – {e_local.strftime('%-I:%M %p')}"
        else:
            out += f" – {e_local.strftime('%a, %b %-d at %-I:%M %p')}"
    return out


def _parse_iso(value: str):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _fmt_due_date(value: str) -> str:
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(value).date()
        return d.strftime("%a, %b %-d")
    except (ValueError, TypeError):
        return value


def _event_card(ev: dict) -> str:
    title = ev.get("title", "")
    when = _fmt_event_time(ev.get("start", ""), ev.get("end", ""))
    link = ev.get("html_link") or ""
    skipped = ev.get("skipped")
    error = ev.get("error")

    status_html = ""
    if skipped == "duplicate":
        status_html = '<span class="badge status-skip">Already on calendar</span>'
    elif skipped:
        status_html = f'<span class="badge status-skip">Skipped: {html.escape(skipped)}</span>'
    elif error:
        status_html = f'<span class="badge status-err">Error: {html.escape(str(error)[:60])}</span>'
    else:
        status_html = '<span class="badge status-ok">Added to Calendar</span>'

    link_html = ""
    if link:
        link_html = f'<span class="meta-divider">/</span><a href="{html.escape(link, quote=True)}">Open in Calendar</a>'

    return f"""
    <article class="brief-card">
      <div class="item-title">{html.escape(title)}</div>
      <div class="item-detail">{html.escape(when)}</div>
      <div class="meta-row">
        {status_html}
        {link_html}
      </div>
    </article>"""


def _task_card(t: dict) -> str:
    title = t.get("title", "")
    due = _fmt_due_date(t.get("due", ""))
    skipped = t.get("skipped")
    error = t.get("error")

    status_html = ""
    if skipped == "duplicate":
        status_html = '<span class="badge status-skip">Already in Tasks</span>'
    elif skipped:
        status_html = f'<span class="badge status-skip">Skipped: {html.escape(skipped)}</span>'
    elif error:
        status_html = f'<span class="badge status-err">Error: {html.escape(str(error)[:60])}</span>'
    else:
        status_html = '<span class="badge status-ok">Added to Tasks</span>'

    due_html = f"<span>Due {html.escape(due)}</span>" if due else "<span>No due date</span>"

    return f"""
    <article class="brief-card">
      <div class="item-title">{html.escape(title)}</div>
      <div class="meta-row">
        {due_html}
        <span class="meta-divider">/</span>
        {status_html}
      </div>
    </article>"""


def _events_section(events: Optional[list]) -> str:
    if not events:
        return ""
    cards = "".join(_event_card(e) for e in events)
    return f"""
      <section class="section">
        <h2>Calendar Events</h2>
        {cards}
      </section>"""


def _tasks_section(tasks: Optional[list]) -> str:
    if not tasks:
        return ""
    cards = "".join(_task_card(t) for t in tasks)
    return f"""
      <section class="section">
        <h2>To-Dos</h2>
        {cards}
      </section>"""


def render(
    emails: list[dict],
    output_path: Path,
    canvas: Optional[dict] = None,
    summary: str = "",
    events: Optional[list] = None,
    tasks: Optional[list] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%A, %B %-d")
    time_str = now.strftime("%-I:%M %p")

    urgent = [e for e in emails if e.get("importance", 0) >= 4]
    rest   = [e for e in emails if e.get("importance", 0) < 4]

    urgent_html = "".join(_email_card(e) for e in urgent) or "<p class='empty'>Nothing urgent.</p>"
    rest_html   = "".join(_email_card(e) for e in rest)   or "<p class='empty'>No other emails.</p>"
    canvas_html = _canvas_section(canvas)
    summary_html = _summary_section(summary)
    events_html  = _events_section(events)
    tasks_html   = _tasks_section(tasks)

    total = len(emails)
    unread = sum(1 for e in emails if e.get("unread"))
    important = sum(1 for e in emails if e.get("importance", 0) >= 4)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Morning Brief - {date_str}</title>
<style>
  :root {{
    --page: #f6f7f9;
    --surface: #ffffff;
    --text: #172033;
    --muted: #64748b;
    --faint: #e5e7eb;
    --accent: #0f2a43;
    --accent-soft: #eef3f7;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 15px;
    line-height: 1.6;
    padding: 32px 18px;
  }}
  .container {{
    width: 100%;
    max-width: 640px;
    margin: 0 auto;
    background: var(--surface);
    border: 1px solid var(--faint);
  }}
  .inner {{ padding: 34px 38px 40px; }}
  .brief-header {{
    border-bottom: 1px solid var(--faint);
    padding-bottom: 22px;
    margin-bottom: 24px;
  }}
  .eyebrow {{
    color: var(--accent);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .08em;
    margin: 0 0 7px;
    text-transform: uppercase;
  }}
  h1 {{
    color: var(--text);
    font-size: 28px;
    font-weight: 650;
    letter-spacing: 0;
    line-height: 1.2;
    margin: 0;
  }}
  .subtitle {{
    color: var(--muted);
    font-size: 14px;
    margin: 8px 0 0;
  }}
  .stats {{
    border-bottom: 1px solid var(--faint);
    color: var(--muted);
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(3, 1fr);
    margin: 0 0 30px;
    padding-bottom: 24px;
  }}
  .stat {{
    min-width: 0;
  }}
  .stat b {{
    color: var(--accent);
    display: block;
    font-size: 20px;
    font-weight: 650;
    line-height: 1.1;
  }}
  .stat span {{
    display: block;
    font-size: 12px;
    letter-spacing: .02em;
    margin-top: 4px;
    text-transform: uppercase;
  }}
  h2 {{
    align-items: center;
    color: var(--accent);
    display: flex;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: .08em;
    line-height: 1.3;
    margin: 0 0 14px;
    text-transform: uppercase;
  }}
  h2:after {{
    background: var(--faint);
    content: "";
    flex: 1;
    height: 1px;
    margin-left: 14px;
  }}
  .section {{ margin-bottom: 34px; }}
  .section:last-child {{ margin-bottom: 0; }}
  .summary-section {{
    background: var(--accent-soft);
    border: 1px solid #d7e0e8;
    border-radius: 8px;
    padding: 18px 20px 16px;
  }}
  .summary-section h2 {{ margin-bottom: 10px; }}
  .summary-section h2:after {{ background: #c5d3df; }}
  .summary-text {{
    color: var(--text);
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
  }}
  .email-card {{
    background: #fff;
    border: 1px solid var(--faint);
    border-left: 3px solid var(--accent);
    border-radius: 6px;
    margin-bottom: 12px;
    padding: 15px 17px 16px;
  }}
  .brief-group {{
    margin-bottom: 18px;
  }}
  .brief-group:last-child {{
    margin-bottom: 0;
  }}
  h3 {{
    color: #475569;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.35;
    margin: 0 0 9px;
  }}
  .brief-card {{
    background: #fff;
    border: 1px solid var(--faint);
    border-radius: 6px;
    margin-bottom: 10px;
    padding: 13px 15px 14px;
  }}
  .item-title {{
    color: var(--text);
    font-size: 15px;
    font-weight: 650;
    line-height: 1.4;
    margin-bottom: 5px;
  }}
  .item-detail {{
    color: #475569;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 9px;
  }}
  a {{
    color: var(--accent);
    text-decoration: none;
  }}
  .card-header {{
    align-items: center;
    display: flex;
    gap: 8px;
    margin-bottom: 5px;
  }}
  .source-badge {{
    align-items: center;
    background: var(--accent-soft);
    border: 1px solid #d7e0e8;
    border-radius: 4px;
    color: var(--accent);
    display: inline-flex;
    font-size: 11px;
    font-weight: 700;
    height: 20px;
    justify-content: center;
    line-height: 1;
    width: 20px;
  }}
  .unread-dot {{
    background: var(--accent);
    border-radius: 50%;
    flex-shrink: 0;
    height: 7px;
    width: 7px;
  }}
  .from {{
    color: #475569;
    flex: 1;
    font-size: 13px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .time {{
    color: var(--muted);
    flex-shrink: 0;
    font-size: 12px;
  }}
  .subject {{
    color: var(--text);
    font-size: 16px;
    font-weight: 650;
    line-height: 1.4;
    margin-bottom: 5px;
  }}
  .one-liner {{
    color: #475569;
    font-size: 14px;
    line-height: 1.55;
    margin-bottom: 11px;
  }}
  .meta-row {{
    align-items: center;
    color: var(--muted);
    display: flex;
    flex-wrap: wrap;
    font-size: 12px;
    gap: 7px;
    line-height: 1.3;
  }}
  .meta-divider {{
    color: #cbd5e1;
  }}
  .badge {{
    border: 1px solid currentColor;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 650;
    padding: 2px 8px;
  }}
  .imp-label {{
    font-size: 12px;
    font-weight: 700;
  }}
  .status-ok {{
    background: #dcfce7;
    border-color: #16a34a;
    color: #166534;
  }}
  .status-skip {{
    background: #f1f5f9;
    border-color: #94a3b8;
    color: #475569;
  }}
  .status-err {{
    background: #fee2e2;
    border-color: #dc2626;
    color: #991b1b;
  }}
  .empty {{
    color: var(--muted);
    font-size: 14px;
    margin: 0;
    padding: 4px 0 12px;
  }}
  @media (max-width: 520px) {{
    body {{ padding: 0; }}
    .container {{ border-left: 0; border-right: 0; }}
    .inner {{ padding: 26px 20px 32px; }}
    .stats {{ grid-template-columns: 1fr; }}
    h1 {{ font-size: 25px; }}
  }}
</style>
</head>
<body>
  <div class="container">
    <div class="inner">
      <header class="brief-header">
        <p class="eyebrow">{date_str}</p>
        <h1>Morning Brief</h1>
        <p class="subtitle">Generated at {time_str}</p>
      </header>

      <div class="stats">
        <div class="stat"><b>{total}</b><span>Emails in last 24h</span></div>
        <div class="stat"><b>{unread}</b><span>Unread</span></div>
        <div class="stat"><b>{important}</b><span>Needs attention</span></div>
      </div>

      {summary_html}

      {events_html}

      {tasks_html}

      {canvas_html}

      <section class="section urgent-section">
        <h2>Needs Attention</h2>
        {urgent_html}
      </section>

      <section class="section">
        <h2>Everything Else</h2>
        {rest_html}
      </section>
    </div>
  </div>
</body>
</html>"""

    output_path.write_text(html_out, encoding="utf-8")
