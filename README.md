# Morning Brief

A personal daily email summary tool that fetches Gmail + Outlook (UNC Microsoft 365), ranks emails by importance using Claude AI, and opens a formatted HTML brief in your browser at login every morning.

## What it does

- Pulls the last 24 hours of email from **Gmail** and **Outlook (Microsoft 365)**
- Sends email subjects/snippets to **Claude Sonnet** to rank by importance (1–5) and categorize
- Extracts **timed commitments** (meetings, calls, interviews) and writes them to your **Google Calendar**
- Extracts **action items** (replies, deadlines, forms) and writes them to your **Google Tasks**
- Fetches unsubmitted **Canvas** assignments, quizzes, exams, and project milestones by urgency
- Generates a formatted **HTML page** that opens automatically in your browser
- Runs at login and at 7:30 AM daily via macOS LaunchAgent
- Idempotent — emails arriving twice (e.g. forwarded copies) won't duplicate Calendar events or Tasks

## Setup

```bash
cd ~/email-morning-brief
bash setup.sh
```

Follow the printed instructions to:
1. Create a Google Cloud project → enable Gmail API → download `credentials/gmail_credentials.json`
2. Register an Azure app → get your client ID
3. Add your Anthropic API key
4. Optional: copy `credentials/secrets.env.template` to `credentials/secrets.env` and add Canvas credentials
5. Install the LaunchAgent
6. Run `python main.py` once to trigger OAuth flows for both accounts

## Project structure

```
main.py           # Entry point
gmail_client.py   # Gmail API (OAuth2)
outlook_client.py # Microsoft Graph API (MSAL device-code flow)
sports_client.py  # ESPN/NBA.com/CBSSports sports fetchers
canvas_client.py  # Canvas LMS assignments fetcher
summarizer.py     # Claude AI ranking
renderer.py       # HTML generation
config.py         # All settings in one place
setup.sh          # One-time setup guide
com.bodeb.morningbrief.plist  # macOS LaunchAgent
```

## Credentials (never committed)

- `credentials/gmail_credentials.json` — downloaded from Google Cloud Console
- `credentials/gmail_token.json` — auto-generated after first OAuth login
- `credentials/outlook_token.json` — auto-generated after first device-code login
- `credentials/secrets.env` — local environment fallback for API keys/config

`credentials/secrets.env` supports:

```bash
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-sonnet-4-6
OUTLOOK_CLIENT_ID=...
CANVAS_BASE_URL=https://canvas.unc.edu
CANVAS_TOKEN=...

# Calendar + Tasks (defaults shown — override only if needed)
PUSH_TO_CALENDAR=1
PUSH_TO_TASKS=1
GOOGLE_CALENDAR_ID=primary
GOOGLE_TASKLIST_ID=@default
USER_TIMEZONE=America/New_York
```

Canvas uses the Canvas LMS REST API with a user access token and scans active courses for unsubmitted work.

## Calendar + Tasks integration

In the same Google Cloud project as the Gmail OAuth client (the one your `gmail_credentials.json` was downloaded from):

1. **APIs & Services → Library** → enable **Google Calendar API**
2. **APIs & Services → Library** → enable **Google Tasks API**
3. **OAuth consent screen → Add or remove scopes** → add:
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/tasks`

The first run after enabling these will open a browser consent flow for the new scopes; the resulting refresh token is cached at `credentials/calendar_tasks_token.json` so subsequent runs are non-interactive.

To temporarily disable either side, set `PUSH_TO_CALENDAR=0` or `PUSH_TO_TASKS=0` in `credentials/secrets.env`. Items are tagged with the source email id, so re-runs against the same email don't duplicate.
