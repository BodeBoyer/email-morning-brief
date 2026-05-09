import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
OUTPUT_DIR = BASE_DIR / "output"

# Load credentials/secrets.env as fallback when env vars aren't set (e.g. terminal runs)
_secrets_file = CREDENTIALS_DIR / "secrets.env"
if _secrets_file.exists():
    for _line in _secrets_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Gmail OAuth2 - set after Google Cloud Console setup
GMAIL_CREDENTIALS_FILE = CREDENTIALS_DIR / "gmail_credentials.json"
GMAIL_TOKEN_FILE = CREDENTIALS_DIR / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Microsoft Graph - set after Azure Portal setup
OUTLOOK_CLIENT_ID = os.environ.get("OUTLOOK_CLIENT_ID", "")
OUTLOOK_TENANT_ID = "common"  # allows personal + work/school accounts
OUTLOOK_SCOPES = ["Mail.Read"]
OUTLOOK_TOKEN_FILE = CREDENTIALS_DIR / "outlook_token.json"

# Anthropic - set ANTHROPIC_API_KEY in environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# How many hours back to look for emails
LOOKBACK_HOURS = 24

# Max emails to send to Claude for ranking (keeps cost low)
MAX_EMAILS_TO_RANK = 40

OUTPUT_HTML = OUTPUT_DIR / "daily_brief.html"
