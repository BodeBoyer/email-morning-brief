import base64
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config


def _get_credentials() -> Credentials:
    creds = None
    if config.GMAIL_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(config.GMAIL_TOKEN_FILE), config.GMAIL_SCOPES)
        except (ValueError, json.JSONDecodeError):
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GMAIL_CREDENTIALS_FILE), config.GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        config.GMAIL_TOKEN_FILE.write_text(creds.to_json())

    return creds


def _decode_body(payload: dict) -> str:
    """Extract plain text from a message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text

    return ""


def fetch_emails(lookback_hours: int = 24) -> list[dict]:
    if not config.GMAIL_CREDENTIALS_FILE.exists():
        print("[Gmail] credentials file not found — skipping Gmail")
        return []

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    after_ts = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp())
    query = f"after:{after_ts}"

    messages = []
    request = service.users().messages().list(userId="me", q=query, maxResults=50)
    while request and len(messages) < 200:
        results = request.execute()
        messages.extend(results.get("messages", []))
        request = service.users().messages().list_next(request, results)

    emails = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        snippet = msg.get("snippet", "")
        body_text = _decode_body(msg["payload"])[:500]

        date_str = headers.get("Date", "")
        try:
            # Parse RFC 2822 date
            from email.utils import parsedate_to_datetime
            received_at = parsedate_to_datetime(date_str)
        except Exception:
            received_at = datetime.now(timezone.utc)

        emails.append({
            "source": "Gmail",
            "id": msg_ref["id"],
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": snippet,
            "body_preview": body_text,
            "received_at": received_at.isoformat(),
            "received_ts": received_at.timestamp(),
            "unread": "UNREAD" in msg.get("labelIds", []),
        })

    return emails
