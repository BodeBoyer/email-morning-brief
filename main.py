#!/usr/bin/env python3
"""Morning email brief — fetches Gmail + Outlook, ranks with Claude, opens HTML summary."""

import subprocess
import sys
from pathlib import Path

import config
import gmail_client
import outlook_client
import summarizer
import renderer


def main():
    print("=== Morning Brief ===")
    print(f"Looking back {config.LOOKBACK_HOURS} hours...\n")

    gmail_emails = []
    outlook_emails = []

    try:
        print("Fetching Gmail...")
        gmail_emails = gmail_client.fetch_emails(config.LOOKBACK_HOURS)
        print(f"  {len(gmail_emails)} emails from Gmail")
    except Exception as e:
        print(f"  Gmail error: {e}")

    try:
        print("Fetching Outlook...")
        outlook_emails = outlook_client.fetch_emails(config.LOOKBACK_HOURS)
        print(f"  {len(outlook_emails)} emails from Outlook")
    except Exception as e:
        print(f"  Outlook error: {e}")

    all_emails = gmail_emails + outlook_emails

    if not all_emails:
        print("\nNo emails found. Check credentials and try again.")
        sys.exit(0)

    print(f"\nRanking {len(all_emails)} emails with Claude...")
    ranked = summarizer.rank_and_summarize(all_emails)

    print(f"Rendering brief to {config.OUTPUT_HTML}...")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    renderer.render(ranked, config.OUTPUT_HTML)

    print("Opening in browser...")
    subprocess.run(["open", str(config.OUTPUT_HTML)], check=False)
    print("Done.")


if __name__ == "__main__":
    main()
