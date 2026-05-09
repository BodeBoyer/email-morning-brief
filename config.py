import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
OUTPUT_DIR = BASE_DIR / "output"

# Gmail OAuth2 - set after Google Cloud Console setup
GMAIL_CREDENTIALS_FILE = CREDENTIALS_DIR / "gmail_credentials.json"
GMAIL_TOKEN_FILE = CREDENTIALS_DIR / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Microsoft Graph - set after Azure Portal setup
OUTLOOK_CLIENT_ID = os.environ.get("OUTLOOK_CLIENT_ID", "")
OUTLOOK_TENANT_ID = "common"  # allows personal + work/school accounts
OUTLOOK_SCOPES = ["Mail.Read", "offline_access"]
OUTLOOK_TOKEN_FILE = CREDENTIALS_DIR / "outlook_token.json"

# Anthropic - set ANTHROPIC_API_KEY in environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# How many hours back to look for emails
LOOKBACK_HOURS = 24

# Max emails to send to Claude for ranking (keeps cost low)
MAX_EMAILS_TO_RANK = 40

OUTPUT_HTML = OUTPUT_DIR / "daily_brief.html"
