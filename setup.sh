#!/bin/bash
# Morning Brief — one-time setup script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Morning Brief Setup ==="
echo ""

# Create log dir
mkdir -p logs output credentials

if [ ! -f com.bodeb.morningbrief.plist ] && [ -f com.bodeb.morningbrief.plist.template ]; then
  cp com.bodeb.morningbrief.plist.template com.bodeb.morningbrief.plist
fi

# Create Python venv
echo "Creating Python virtual environment..."
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
echo "Using $($PYTHON_BIN --version)"
"$PYTHON_BIN" -m venv venv
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "Dependencies installed."
echo ""

# Remind about credentials
echo "Next steps:"
echo ""
echo "1. GMAIL SETUP"
echo "   a) Go to: https://console.cloud.google.com/"
echo "   b) Create a project → Enable 'Gmail API'"
echo "   c) Create OAuth 2.0 Client ID (Desktop app type)"
echo "   d) Download JSON → save as: $DIR/credentials/gmail_credentials.json"
echo ""
echo "2. OUTLOOK SETUP (UNC Microsoft 365)"
echo "   a) Go to: https://portal.azure.com/"
echo "   b) Azure Active Directory → App registrations → New registration"
echo "   c) Name: 'Morning Brief', Accounts: 'Accounts in any org directory + personal'"
echo "   d) Redirect URI: add 'https://login.microsoftonline.com/common/oauth2/nativeclient'"
echo "   e) After creation, go to API permissions → Add → Microsoft Graph → Delegated"
echo "      → add: Mail.Read, offline_access"
echo "   f) Copy the Application (client) ID"
echo "   g) Add OUTLOOK_CLIENT_ID to credentials/secrets.env, or edit com.bodeb.morningbrief.plist"
echo ""
echo "3. ANTHROPIC API KEY"
echo "   a) Get key from: https://console.anthropic.com/"
echo "   b) Add ANTHROPIC_API_KEY to credentials/secrets.env, or edit com.bodeb.morningbrief.plist"
echo ""
echo "4. OPTIONAL CANVAS SETUP"
echo "   cp credentials/secrets.env.template credentials/secrets.env"
echo "   Edit credentials/secrets.env with CANVAS_BASE_URL and CANVAS_TOKEN"
echo ""
echo "5. INSTALL LAUNCH AGENT (runs at login + 7:30 AM and 6:00 PM daily)"
echo "   cp \"$DIR/com.bodeb.morningbrief.plist\" ~/Library/LaunchAgents/"
echo "   launchctl load ~/Library/LaunchAgents/com.bodeb.morningbrief.plist"
echo ""
echo "6. FIRST RUN (triggers OAuth login for each account)"
echo "   source venv/bin/activate && python main.py"
echo ""
echo "Setup complete. Follow the steps above, then run 'python main.py' to test."
