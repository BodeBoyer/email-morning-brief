from __future__ import annotations

import re
import time as _time
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests

import config

_LOCAL_TZ = ZoneInfo("America/New_York")

_TEST_RE = re.compile(r"\bquiz\b|\btest\b|\bexam\b|\bmidterm\b|\bfinal\b")
_PROJECT_RE = re.compile(r"\bproject\b|\bfp\d|\bgp\d|\bpaper\b|\bpresentation\b|\bproposal\b|\bdraft\b|\bmilestone\b")


def _canvas_get(path: str, params: Optional[dict] = None) -> list:
    url = f"{config.CANVAS_BASE_URL}/api/v1{path}"
    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}
    results = []
    while url:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=45)
                resp.raise_for_status()
                break
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                _time.sleep(2 ** attempt)
        else:
            raise last_exc  # type: ignore[misc]
        results.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None
    return results


def _kind(name: str) -> str:
    n = name.lower()
    if _TEST_RE.search(n):
        return "Exam"
    if _PROJECT_RE.search(n):
        return "Project"
    return "Assignment"


def _is_submitted(assignment: dict) -> bool:
    submission = assignment.get("submission") or {}
    workflow_state = submission.get("workflow_state")
    return workflow_state in {"submitted", "graded", "pending_review"}


def _get_assignments() -> list[dict]:
    courses = _canvas_get("/courses", {"enrollment_state": "active", "per_page": 100})
    # Hide unsubmitted work that's been overdue for more than 3 weeks — stale to-dos clutter the brief.
    stale_cutoff = datetime.now(_LOCAL_TZ) - timedelta(days=21)
    items = []
    for course in courses:
        if not isinstance(course, dict) or "id" not in course or "name" not in course:
            continue
        assignment_params = {"per_page": 100, "include[]": ["submission"]}
        for a in _canvas_get(f"/courses/{course['id']}/assignments", assignment_params):
            if not a.get("due_at"):
                continue
            if _is_submitted(a):
                continue
            due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00")).astimezone(_LOCAL_TZ)
            if due < stale_cutoff:
                continue
            items.append({
                "title": a.get("name", "Untitled"),
                "course": course["name"],
                "due_at": due.isoformat(),
                "url": a.get("html_url", ""),
                "kind": _kind(a.get("name", "")),
                "points": a.get("points_possible"),
            })
    return sorted(items, key=lambda x: x["due_at"])


def fetch_assignments() -> dict:
    configured = bool(config.CANVAS_BASE_URL and config.CANVAS_TOKEN)
    empty = {
        "configured": configured,
        "error": "",
        "groups": [
            {"title": "Due Today / Overdue", "items": []},
            {"title": "Due in the Next 3 Days", "items": []},
            {"title": "Tests / Quizzes / Exams to Study For", "items": []},
            {"title": "Project Milestones", "items": []},
        ],
    }

    if not configured:
        return empty

    try:
        items = _get_assignments()
    except Exception as exc:
        empty["error"] = str(exc)
        return empty

    now = datetime.now(_LOCAL_TZ)
    tomorrow = datetime.combine(now.date(), time.min, tzinfo=_LOCAL_TZ) + timedelta(days=1)
    three_days = now + timedelta(days=3)
    seven_days = now + timedelta(days=7)

    due_today, next_three, tests, projects = [], [], [], []
    for item in items:
        due = datetime.fromisoformat(item["due_at"])
        kind = item["kind"]
        if due < tomorrow:
            due_today.append(item)
        elif due <= three_days:
            next_three.append(item)
        if kind == "Exam" and due <= seven_days:
            tests.append(item)
        if kind == "Project" and due <= seven_days:
            projects.append(item)

    return {
        "configured": True,
        "error": "",
        "groups": [
            {"title": "Due Today / Overdue", "items": due_today[:8]},
            {"title": "Due in the Next 3 Days", "items": next_three[:8]},
            {"title": "Tests / Quizzes / Exams to Study For", "items": tests[:6]},
            {"title": "Project Milestones", "items": projects[:6]},
        ],
    }
