import json
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

import msal
import requests

import config


_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_token() -> str | None:
    if not config.OUTLOOK_CLIENT_ID:
        print("[Outlook] OUTLOOK_CLIENT_ID not set — skipping Outlook")
        return None

    cache = msal.SerializableTokenCache()
    if config.OUTLOOK_TOKEN_FILE.exists():
        cache.deserialize(config.OUTLOOK_TOKEN_FILE.read_text())

    app = msal.PublicClientApplication(
        config.OUTLOOK_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{config.OUTLOOK_TENANT_ID}",
        token_cache=cache,
    )

    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(config.OUTLOOK_SCOPES, account=accounts[0])

    if not result:
        # Device-code flow works even when redirect URIs are restricted
        flow = app.initiate_device_flow(scopes=config.OUTLOOK_SCOPES)
        if "error" in flow:
            print(f"[Outlook] Device flow init failed: {flow.get('error_description', flow['error'])}")
            return None
        print("\n[Outlook] To authenticate, visit:", flow["verification_uri"])
        print("[Outlook] Enter code:", flow["user_code"])
        result = app.acquire_token_by_device_flow(flow)

    if config.OUTLOOK_TOKEN_FILE.parent.exists():
        config.OUTLOOK_TOKEN_FILE.write_text(cache.serialize())

    if "access_token" not in result:
        print("[Outlook] Auth failed:", result.get("error_description"))
        return None

    return result["access_token"]


def fetch_emails(lookback_hours: int = 24) -> list[dict]:
    token = _get_token()
    if not token:
        return []

    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    auth_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {
        "$filter": f"receivedDateTime ge {since}",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
        "$orderby": "receivedDateTime desc",
        "$top": 50,
    }

    resp = requests.get(
        f"{_GRAPH_BASE}/me/mailFolders/inbox/messages",
        headers=auth_headers,
        params=params,
    )
    if resp.status_code != 200:
        print(f"[Outlook] API error {resp.status_code}: {resp.text[:200]}")
        return []

    emails = []
    data = resp.json()

    while True:
        for msg in data.get("value", []):
            sender = msg.get("from", {}).get("emailAddress", {})
            received_dt = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
            emails.append({
                "source": "Outlook",
                "id": msg["id"],
                "from": f"{sender.get('name', '')} <{sender.get('address', '')}>",
                "subject": msg.get("subject", "(no subject)"),
                "snippet": msg.get("bodyPreview", ""),
                "body_preview": msg.get("bodyPreview", ""),
                "received_at": received_dt.isoformat(),
                "received_ts": received_dt.timestamp(),
                "unread": not msg.get("isRead", True),
            })

        next_link = data.get("@odata.nextLink")
        if not next_link or len(emails) >= 200:
            break
        resp = requests.get(next_link, headers=auth_headers)
        if resp.status_code != 200:
            break
        data = resp.json()

    return emails
