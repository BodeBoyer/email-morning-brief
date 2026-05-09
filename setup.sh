#!/bin/bash
# Morning Brief — one-time setup script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Morning Brief Setup ==="
echo ""

# Create log dir
mkdir -p logs output credentials

# Create Python venv
echo "Creating Python virtual environment..."
python3 -m venv venv
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
echo "   g) Edit com.bodeb.morningbrief.plist → replace REPLACE_WITH_YOUR_AZURE_CLIENT_ID"
echo ""
echo "3. ANTHROPIC API KEY"
echo "   a) Get key from: https://console.anthropic.com/"
echo "   b) Edit com.bodeb.morningbrief.plist → replace REPLACE_WITH_YOUR_ANTHROPIC_API_KEY"
echo ""
echo "4. INSTALL LAUNCH AGENT (runs at login + 7:30 AM daily)"
echo "   cp \"$DIR/com.bodeb.morningbrief.plist\" ~/Library/LaunchAgents/"
echo "   launchctl load ~/Library/LaunchAgents/com.bodeb.morningbrief.plist"
echo ""
echo "5. FIRST RUN (triggers OAuth login for each account)"
echo "   source venv/bin/activate && python main.py"
echo ""
echo "Setup complete. Follow the steps above, then run 'python main.py' to test."
