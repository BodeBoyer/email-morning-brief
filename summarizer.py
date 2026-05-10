import json
import anthropic
import config


_SYSTEM_PROMPT = """You are an executive assistant helping a college student starting an internship next week.
Your job: read a list of emails from the past 24 hours and produce a structured morning brief.

Return a JSON object with two keys:
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

High importance signals: your name mentioned, direct question, deadline, manager/recruiter/professor sending,
words like "offer", "start date", "onboarding", "urgent", "please confirm", "interview", "grades".
Low importance signals: newsletters, marketing, automated notifications, social media alerts.

Grade-related emails (subject or body mentioning "grade changed", "grade posted", "final course score",
"final grade", or a Canvas/Sakai grade notification) are ALWAYS important — set importance >= 3 and
category "School". For these, the one_liner MUST extract the concrete grade detail from the body:
the course/assignment name and the actual score or letter (e.g. "COMP 211 final exam: 92/100",
"COMP 110 final course score: A-", "Grade changed on Project 2: 85 -> 95"). Do not just say
"a grade was posted" — pull the number or letter out of the body so the user can see their grade
without opening the email. The top-level summary should also call out any grade changes by name and value."""

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
    return emails, ""


def _coerce_importance(value) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        return 2
    return min(5, max(1, importance))


def rank_and_summarize(emails: list[dict]) -> tuple:
    """Return (emails_with_ranking, overall_summary_text)."""
    if not emails:
        return [], ""

    if not config.ANTHROPIC_API_KEY:
        print("[Claude] ANTHROPIC_API_KEY not set — skipping AI ranking, using unread as proxy")
        return _apply_fallback(emails, default_importance=1)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Interleave by recency so both sources get ranked when > MAX_EMAILS_TO_RANK total
    candidates = sorted(emails, key=lambda x: -x["received_ts"])[: config.MAX_EMAILS_TO_RANK]

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
        })

    user_message = (
        "Here are the emails from the past 24 hours. "
        "Return ONLY a JSON object with keys 'summary' and 'emails' as described, no prose:\n\n"
        + json.dumps(email_list, indent=2)
    )

    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
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
    elif isinstance(parsed, list):
        # Backwards-compatible: old prompt shape
        ranked = parsed
        summary = ""
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
    return emails, summary
