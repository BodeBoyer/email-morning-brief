import json
import anthropic
import config


_SYSTEM_PROMPT = """You are an executive assistant helping a college student starting an internship next week.
Your job: read a list of emails from the past 24 hours and produce a structured morning brief.

For each email return a JSON object with:
- "id": the original email id
- "importance": integer 1-5 (5 = urgent/critical, 1 = newsletter/junk)
- "category": one of ["Action Required", "FYI", "Meeting", "Internship", "School", "Spam/Promo"]
- "one_liner": one short sentence capturing what the email is about and what (if anything) needs to happen

High importance signals: your name mentioned, direct question, deadline, manager/recruiter/professor sending,
words like "offer", "start date", "onboarding", "urgent", "please confirm", "interview", "grades".
Low importance signals: newsletters, marketing, automated notifications, social media alerts."""


def rank_and_summarize(emails: list[dict]) -> list[dict]:
    if not emails:
        return []

    if not config.ANTHROPIC_API_KEY:
        print("[Claude] ANTHROPIC_API_KEY not set — skipping AI ranking, using unread as proxy")
        for e in emails:
            e["importance"] = 3 if e.get("unread") else 1
            e["category"] = "FYI"
            e["one_liner"] = e["snippet"][:120]
        return emails

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build compact email list for Claude — keep cost low
    email_list = []
    for e in emails[: config.MAX_EMAILS_TO_RANK]:
        email_list.append({
            "id": e["id"],
            "from": e["from"],
            "subject": e["subject"],
            "snippet": e["snippet"][:300],
            "source": e["source"],
            "unread": e.get("unread", False),
        })

    user_message = (
        "Here are the emails from the past 24 hours. "
        "Return ONLY a JSON array of objects as described, one per email, no prose:\n\n"
        + json.dumps(email_list, indent=2)
    )

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip("` \n")

    ranked = json.loads(raw)

    ranked_by_id = {r["id"]: r for r in ranked}
    for e in emails:
        info = ranked_by_id.get(e["id"], {})
        e["importance"] = info.get("importance", 2)
        e["category"] = info.get("category", "FYI")
        e["one_liner"] = info.get("one_liner", e["snippet"][:120])

    # Sort: importance desc, then unread first, then recency
    emails.sort(key=lambda x: (-x["importance"], not x.get("unread", False), -x["received_ts"]))
    return emails
