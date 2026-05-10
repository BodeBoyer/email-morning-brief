import os
import plistlib
from pathlib import Path

BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
OUTPUT_DIR = BASE_DIR / "output"


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith("replace_with_")


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return default if _is_placeholder(value) else value


# Load credentials/secrets.env as fallback when env vars aren't set (e.g. terminal runs)
_secrets_file = CREDENTIALS_DIR / "secrets.env"
if _secrets_file.exists():
    for _line in _secrets_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _key = _k.strip()
            _existing = os.environ.get(_key, "")
            if _is_placeholder(_existing):
                os.environ[_key] = _v.strip()

_plist_file = BASE_DIR / "com.bodeb.morningbrief.plist"
if _plist_file.exists():
    try:
        _plist_env = plistlib.loads(_plist_file.read_bytes()).get("EnvironmentVariables", {})
    except (plistlib.InvalidFileException, ValueError, TypeError):
        _plist_env = {}
    for _key, _value in _plist_env.items():
        if _key == "PATH":
            continue
        _existing = os.environ.get(_key, "")
        if _is_placeholder(_existing):
            os.environ[_key] = str(_value).strip()

# Gmail OAuth2 - set after Google Cloud Console setup
GMAIL_CREDENTIALS_FILE = CREDENTIALS_DIR / "gmail_credentials.json"
GMAIL_TOKEN_FILE = CREDENTIALS_DIR / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Microsoft Graph - set after Azure Portal setup
OUTLOOK_CLIENT_ID = _env("OUTLOOK_CLIENT_ID")
OUTLOOK_TENANT_ID = "common"  # allows personal + work/school accounts
OUTLOOK_SCOPES = ["Mail.Read", "offline_access"]
OUTLOOK_TOKEN_FILE = CREDENTIALS_DIR / "outlook_token.json"

# Canvas LMS - set CANVAS_BASE_URL and CANVAS_TOKEN in credentials/secrets.env
CANVAS_BASE_URL = _env("CANVAS_BASE_URL").rstrip("/")
CANVAS_TOKEN = _env("CANVAS_TOKEN") or _env("CANVAS_API_TOKEN")

# Anthropic - set ANTHROPIC_API_KEY in environment
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# How many hours back to look for emails
LOOKBACK_HOURS = 24

# Max emails to send to Claude for ranking (keeps cost low)
MAX_EMAILS_TO_RANK = 40

OUTPUT_HTML = OUTPUT_DIR / "daily_brief.html"
