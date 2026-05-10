import json
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import config


_SYSTEM_PROMPT_TEMPLATE = """You are an executive assistant helping a college student starting an internship next week.
Your job: read a list of emails from the past 24 hours and produce a structured morning brief.

Today is {today_human} ({today_iso}) in timezone {tz}. Use this to resolve relative dates
like "tomorrow", "next Monday", "this Friday at 3pm" into absolute ISO 8601 timestamps.

Return a JSON object with FOUR keys:

- "summary": a 2-4 sentence plain-English overview of what arrived in the user's inbox. Lead with
  anything urgent or action-required (replies needed, deadlines, interviews, grade changes with the
  actual grade). Then briefly note what else is in the inbox (e.g. "plus a few class announcements
  and newsletters"). Skip spam. Write to the user directly ("You got...", "Your..."). No headers,
  no bullets — just sentences.

- "emails": an array, one object per email, each containing:
    - "id": the original email id
    - "importance": integer 1-5 (5 = urgent/critical, 1 = newsletter/junk)
    - "category": one of ["Action Required", "FYI", "Meeting", "Internship", "School", "Spam/Promo"]
    - "one_liner": one short sentence capturing what the email is about and what (if anything) needs to happen

- "events": an array of TIMED commitments the user must attend (meetings, calls, interviews,
  required attendance with a specific start time). Only include items with a concrete start
  date AND time. Each event:
    - "source_id": the originating email id
    - "title": short event title (e.g. "Internship onboarding call with Sarah")
    - "start": ISO 8601 datetime with timezone offset (e.g. "2026-05-16T10:00:00-04:00")
    - "end": ISO 8601 datetime with timezone offset; if email gives no end time, default to
      start + 30 minutes for calls, start + 60 minutes for meetings/interviews
    - "location": physical address, room number, OR full meeting link (Zoom/Teams/Meet) if present;
      empty string if none given
    - "description": 1-2 sentence summary of why this event matters and any prep notes the
      email mentions (agenda, what to bring, who's attending). Include the sender so the user
      knows who scheduled it.

- "tasks": an array of action items WITHOUT a specific time-of-day commitment — replies needed,
  forms to submit, items to buy, reading to do, deadlines without a meeting attached. Each task:
    - "source_id": the originating email id
    - "title": imperative phrasing (e.g. "Submit I-9 form to HR", "Reply to professor about grade")
    - "due": ISO 8601 date (YYYY-MM-DD) if a deadline is mentioned in the email; null otherwise.
      Date-only — these aren't time-blocked commitments.
    - "notes": 1-2 sentence context (who asked, what specifically is needed, link/reference if any)

DO NOT create both an event AND a task for the same thing. If it has a specific time, it is an
event. If not, it is a task. If the email is purely informational (newsletter, FYI, grade
notification with no required follow-up), do not create either.

High importance signals: your name mentioned, direct question, deadline, manager/recruiter/professor sending,
words like "offer", "start date", "onboarding", "urgent", "please confirm", "interview", "grades".
Low importance signals: newsletters, marketing, automated notifications, social media alerts.

Grade-related emails (subject or body mentioning "grade changed", "grade posted", "final course score",
"final grade", or a Canvas/Sakai grade notification) are ALWAYS important — set importance >= 3 and
category "School". For these, the one_liner MUST extract the concrete grade detail from the body:
the course/assignment name and the actual score or letter (e.g. "COMP 211 final exam: 92/100",
"COMP 110 final course score: A-", "Grade changed on Project 2: 85 -> 95"). Do not just say
"a grade was posted" — pull the number or letter out of the body so the user can see their grade
without opening the email. The top-level summary should also call out any grade changes by name and value.
Grade emails do NOT need an event or task unless the user must explicitly act (e.g. dispute a grade)."""


def _build_system_prompt() -> str:
    tz_name = getattr(config, "USER_TIMEZONE", "America/New_York")
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now()
        tz_name = "local"
    return _SYSTEM_PROMPT_TEMPLATE.format(
        today_human=now_local.strftime("%A, %B %-d, %Y"),
        today_iso=now_local.date().isoformat(),
        tz=tz_name,
    )

_VALID_CATEGORIES = {"Action Required", "FYI", "Meeting", "Internship", "School", "Spam/Promo"}


def _sort_emails(emails: list[dict]) -> None:
    def importance(email: dict) -> int:
        try:
            return int(email.get("importance", 2))
        except (TypeError, ValueError):
            return 2

    def received_ts(email: dict) -> float:
        try:
            return float(email.get("received_ts", 0))
        except (TypeError, ValueError):
            return 0

    emails.sort(
        key=lambda x: (
            -importance(x),
            not x.get("unread", False),
            -received_ts(x),
        )
    )


def _apply_fallback(emails: list[dict], default_importance: int = 2) -> tuple:
    for e in emails:
        e["importance"] = 3 if e.get("unread") else default_importance
        e["category"] = "FYI"
        e["one_liner"] = str(e.get("snippet", ""))[:120]
    _sort_emails(emails)
    return emails, "", [], []


def _coerce_importance(value) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        return 2
    return min(5, max(1, importance))


def _clean_events(raw_events, valid_email_ids: set) -> list:
    """Validate and clean event records returned by Claude."""
    out = []
    for ev in raw_events or []:
        if not isinstance(ev, dict):
            continue
        title = str(ev.get("title", "")).strip()
        start = str(ev.get("start", "")).strip()
        if not title or not start:
            continue
        # Only accept events tied to a real email — drops hallucinated entries
        source_id = str(ev.get("source_id", "")).strip()
        if not source_id or source_id not in valid_email_ids:
            continue
        out.append({
            "source_id": source_id,
            "title": title[:200],
            "start": start,
            "end": str(ev.get("end", "")).strip(),
            "location": str(ev.get("location", "")).strip()[:300],
            "description": str(ev.get("description", "")).strip()[:1000],
        })
    return out


def _clean_tasks(raw_tasks, valid_email_ids: set) -> list:
    """Validate and clean task records returned by Claude."""
    out = []
    for t in raw_tasks or []:
        if not isinstance(t, dict):
            continue
        title = str(t.get("title", "")).strip()
        if not title:
            continue
        source_id = str(t.get("source_id", "")).strip()
        if not source_id or source_id not in valid_email_ids:
            continue
        due_raw = t.get("due")
        due = str(due_raw).strip() if due_raw not in (None, "", "null") else ""
        out.append({
            "source_id": source_id,
            "title": title[:200],
            "due": due,
            "notes": str(t.get("notes", "")).strip()[:1000],
        })
    return out


def rank_and_summarize(emails: list[dict]) -> tuple:
    """Return (emails_with_ranking, overall_summary_text, events, tasks)."""
    if not emails:
        return [], "", [], []

    if not config.ANTHROPIC_API_KEY:
        print("[Claude] ANTHROPIC_API_KEY not set — skipping AI ranking, using unread as proxy")
        return _apply_fallback(emails, default_importance=1)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Interleave by recency so both sources get ranked when > MAX_EMAILS_TO_RANK total
    candidates = sorted(emails, key=lambda x: -x["received_ts"])[: config.MAX_EMAILS_TO_RANK]
    valid_email_ids = {str(e["id"]) for e in candidates}

    # Build compact email list for Claude — keep cost low
    email_list = []
    for e in candidates:
        email_list.append({
            "id": e["id"],
            "from": e["from"],
            "subject": e["subject"],
            "snippet": e["snippet"][:300],
            "body_preview": str(e.get("body_preview", ""))[:500],
            "source": e["source"],
            "unread": e.get("unread", False),
            "received_at": e.get("received_at", ""),
        })

    user_message = (
        "Here are the emails from the past 24 hours. "
        "Return ONLY a JSON object with keys 'summary', 'emails', 'events', 'tasks' "
        "as described in the system prompt — no prose, no markdown fences:\n\n"
        + json.dumps(email_list, indent=2)
    )

    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=6144,
            system=_build_system_prompt(),
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
    except Exception as exc:
        print(f"[Claude] API error ({exc}) — falling back to snippet defaults")
        return _apply_fallback(emails)

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip("` \n")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[Claude] Failed to parse response as JSON ({exc}) — falling back to snippet defaults")
        return _apply_fallback(emails)

    if isinstance(parsed, dict):
        ranked = parsed.get("emails", [])
        summary = str(parsed.get("summary", "")).strip()
        events = _clean_events(parsed.get("events", []), valid_email_ids)
        tasks = _clean_tasks(parsed.get("tasks", []), valid_email_ids)
    elif isinstance(parsed, list):
        # Backwards-compatible: old prompt shape
        ranked = parsed
        summary = ""
        events = []
        tasks = []
    else:
        print("[Claude] Response was not a JSON object or array — falling back to snippet defaults")
        return _apply_fallback(emails)

    ranked_by_id = {
        str(r.get("id")): r
        for r in ranked
        if isinstance(r, dict) and r.get("id") is not None
    }
    for e in emails:
        info = ranked_by_id.get(str(e.get("id")), {})
        category = info.get("category", "FYI")
        one_liner = info.get("one_liner", e.get("snippet", "")[:120])
        e["importance"] = _coerce_importance(info.get("importance", 2))
        e["category"] = category if category in _VALID_CATEGORIES else "FYI"
        e["one_liner"] = str(one_liner)[:200]

    # Sort: importance desc, then unread first, then recency
    _sort_emails(emails)
    return emails, summary, events, tasks
