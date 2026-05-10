"""
Google Calendar + Google Tasks writer for the morning brief.

Reuses the same OAuth client as gmail_client.py (credentials/gmail_credentials.json),
but stores its own token file at credentials/calendar_tasks_token.json with the
calendar.events + tasks scopes. First run opens a browser consent flow; subsequent
runs are non-interactive thanks to the cached refresh token.

Idempotency: every event/task we create stamps a private property
`source_email_id` (events) or a task title prefix tagged with the email id.
On repeat runs we look those up and skip already-created records, so the
brief running twice a day will not produce duplicates.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config


_TASK_TAG_PREFIX = "[brief:"  # task notes start with [brief:<email_id>] for idempotency


def _get_credentials() -> Credentials:
    creds = None
    if config.CALENDAR_TASKS_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(config.CALENDAR_TASKS_TOKEN_FILE), config.CALENDAR_TASKS_SCOPES
            )
        except (ValueError, json.JSONDecodeError):
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
        if not creds or not creds.valid:
            if not config.GMAIL_CREDENTIALS_FILE.exists():
                raise RuntimeError(
                    f"OAuth client JSON missing at {config.GMAIL_CREDENTIALS_FILE}. "
                    "Calendar/Tasks reuses the Gmail OAuth client."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GMAIL_CREDENTIALS_FILE), config.CALENDAR_TASKS_SCOPES
            )
            creds = flow.run_local_server(port=0)
        config.CALENDAR_TASKS_TOKEN_FILE.write_text(creds.to_json())
        try:
            config.CALENDAR_TASKS_TOKEN_FILE.chmod(0o600)
        except OSError:
            pass

    return creds


def _build_services():
    creds = _get_credentials()
    cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
    tasks = build("tasks", "v1", credentials=creds, cache_discovery=False)
    return cal, tasks


# ---- Calendar ----

def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Python 3.9 fromisoformat doesn't handle trailing "Z"
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ensure_end(start: datetime, end_raw: str, title: str) -> datetime:
    end_dt = _parse_iso(end_raw)
    if end_dt and end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=start.tzinfo or ZoneInfo(config.USER_TIMEZONE))
    if end_dt and end_dt > start:
        return end_dt
    title_lc = title.lower()
    minutes = 30 if any(word in title_lc for word in ("call", "stand-up", "standup", "1:1", "check-in")) else 60
    return start + timedelta(minutes=minutes)


def _event_fingerprint(title: str, start_dt: datetime) -> tuple:
    """Stable (title, start-minute-UTC) key so re-delivered emails don't double-book."""
    minute = start_dt.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
    return (title.strip().lower(), minute)


def _existing_event_keys(service, after: datetime) -> tuple[set, set]:
    """Return (source_email_ids, (title, start-minute) fingerprints) already on calendar."""
    ids: set = set()
    fps: set = set()
    try:
        page_token = None
        while True:
            resp = service.events().list(
                calendarId=config.GOOGLE_CALENDAR_ID,
                timeMin=after.astimezone(timezone.utc).isoformat(),
                singleEvents=True,
                pageToken=page_token,
            ).execute()
            for ev in resp.get("items", []):
                src = (ev.get("extendedProperties", {}).get("private", {}) or {}).get("source_email_id")
                if src:
                    ids.add(src)
                title = ev.get("summary") or ""
                start_raw = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
                start_dt = _parse_iso(start_raw or "")
                if title and start_dt:
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=ZoneInfo(config.USER_TIMEZONE))
                    fps.add(_event_fingerprint(title, start_dt))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        print(f"[Calendar] could not list existing events: {exc}")
    return ids, fps


def create_events(events: list[dict]) -> list[dict]:
    """Create Calendar events. Returns list of result dicts (with link or skip reason)."""
    if not events:
        return []
    if not config.PUSH_TO_CALENDAR:
        return [{"skipped": "PUSH_TO_CALENDAR=0", **e} for e in events]

    try:
        cal_service, _ = _build_services()
    except Exception as exc:
        print(f"[Calendar] auth failed: {exc}")
        return [{"error": str(exc), **e} for e in events]

    tz_name = config.USER_TIMEZONE
    # Look back at least the mail window so events created on a prior run from
    # emails still inside today's lookback are seen by the duplicate scan.
    earliest = datetime.now(ZoneInfo(tz_name)) - timedelta(hours=max(config.LOOKBACK_HOURS, 24))
    already_ids, already_fps = _existing_event_keys(cal_service, earliest)

    results = []
    for ev in events:
        if ev["source_id"] and ev["source_id"] in already_ids:
            results.append({"skipped": "duplicate", **ev})
            continue

        start_dt = _parse_iso(ev["start"])
        if not start_dt:
            results.append({"error": f"bad start datetime {ev['start']!r}", **ev})
            continue
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=ZoneInfo(tz_name))

        fp = _event_fingerprint(ev["title"], start_dt)
        if fp in already_fps:
            results.append({"skipped": "duplicate", **ev})
            continue

        end_dt = _ensure_end(start_dt, ev.get("end", ""), ev["title"])

        body = {
            "summary": ev["title"],
            "description": ev.get("description") or "",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
            "extendedProperties": {
                "private": {
                    "created_by": "email-morning-brief",
                    "source_email_id": ev.get("source_id", ""),
                }
            },
            "reminders": {"useDefault": True},
        }
        if ev.get("location"):
            body["location"] = ev["location"]

        try:
            created = cal_service.events().insert(
                calendarId=config.GOOGLE_CALENDAR_ID, body=body
            ).execute()
            already_fps.add(fp)
            results.append({
                "created": True,
                "title": ev["title"],
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "html_link": created.get("htmlLink"),
                "id": created.get("id"),
                "source_id": ev.get("source_id", ""),
            })
        except HttpError as exc:
            results.append({"error": str(exc), **ev})
    return results


# ---- Tasks ----

def _task_fingerprint(title: str, due_iso: str) -> tuple:
    """Stable (title, due-date) key. Empty string if no due date."""
    due_key = ""
    if due_iso:
        try:
            due_key = datetime.fromisoformat(due_iso.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            due_key = due_iso
    return (title.strip().lower(), due_key)


def _existing_task_keys(service) -> tuple[set, set]:
    """Return (source_ids tagged in notes, (title, due) fingerprints). Includes completed/hidden tasks."""
    ids: set = set()
    fps: set = set()
    try:
        page_token = None
        while True:
            resp = service.tasks().list(
                tasklist=config.GOOGLE_TASKLIST_ID,
                showCompleted=True,
                showHidden=True,
                maxResults=100,
                pageToken=page_token,
            ).execute()
            for t in resp.get("items", []):
                notes = t.get("notes") or ""
                if notes.startswith(_TASK_TAG_PREFIX):
                    end = notes.find("]")
                    if end > 0:
                        ids.add(notes[len(_TASK_TAG_PREFIX):end])
                title = t.get("title") or ""
                if title:
                    fps.add(_task_fingerprint(title, t.get("due", "")))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        print(f"[Tasks] could not list existing tasks: {exc}")
    return ids, fps


def create_tasks(tasks: list[dict]) -> list[dict]:
    """Create Google Tasks. Returns list of result dicts."""
    if not tasks:
        return []
    if not config.PUSH_TO_TASKS:
        return [{"skipped": "PUSH_TO_TASKS=0", **t} for t in tasks]

    try:
        _, tasks_service = _build_services()
    except Exception as exc:
        print(f"[Tasks] auth failed: {exc}")
        return [{"error": str(exc), **t} for t in tasks]

    already_ids, already_fps = _existing_task_keys(tasks_service)

    results = []
    for t in tasks:
        if t["source_id"] and t["source_id"] in already_ids:
            results.append({"skipped": "duplicate", **t})
            continue

        fp = _task_fingerprint(t["title"], t.get("due", ""))
        if fp in already_fps:
            results.append({"skipped": "duplicate", **t})
            continue

        notes_parts = [f"{_TASK_TAG_PREFIX}{t.get('source_id', '')}]"]
        if t.get("notes"):
            notes_parts.append(t["notes"])
        body = {
            "title": t["title"],
            "notes": "\n\n".join(notes_parts),
        }
        if t.get("due"):
            # Google Tasks API: due is RFC3339 timestamp; date-only -> midnight UTC of that date.
            # The API ignores the time portion and only uses the date.
            try:
                d = datetime.fromisoformat(t["due"]).date()
                body["due"] = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass  # skip due if we can't parse

        try:
            created = tasks_service.tasks().insert(
                tasklist=config.GOOGLE_TASKLIST_ID, body=body
            ).execute()
            already_fps.add(fp)
            results.append({
                "created": True,
                "title": t["title"],
                "due": t.get("due", ""),
                "id": created.get("id"),
                "self_link": created.get("selfLink"),
                "source_id": t.get("source_id", ""),
            })
        except HttpError as exc:
            results.append({"error": str(exc), **t})
    return results
