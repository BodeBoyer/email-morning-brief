#!/usr/bin/env python3
"""Morning email brief — fetches Gmail + Outlook, ranks with Claude, opens HTML summary."""

import subprocess

import config
import gmail_client
import outlook_client
import summarizer
import renderer
import sports_client
import canvas_client


def main():
    print("=== Morning Brief ===")
    print(f"Looking back {config.LOOKBACK_HOURS} hours...\n")

    gmail_emails = []
    outlook_emails = []
    sports = {}
    canvas = {}

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

    try:
        print("Fetching sports...")
        sports = sports_client.fetch_sports_brief()
        sports_count = sum(len(g.get("items", [])) for g in sports.get("groups", []))
        print(f"  {sports_count} sports items")
    except Exception as e:
        print(f"  Sports error: {e}")

    try:
        print("Fetching Canvas...")
        canvas = canvas_client.fetch_assignments()
        canvas_count = sum(len(g.get("items", [])) for g in canvas.get("groups", []))
        print(f"  {canvas_count} Canvas items")
    except Exception as e:
        print(f"  Canvas error: {e}")

    if not all_emails:
        print("\nNo emails found. Rendering brief with sports and Canvas sections.")
        ranked = []
    else:
        print(f"\nRanking {len(all_emails)} emails with Claude...")
        try:
            ranked = summarizer.rank_and_summarize(all_emails)
        except Exception as e:
            print(f"  Claude ranking error: {e}")
            ranked = all_emails
            for email in ranked:
                email["importance"] = 3 if email.get("unread") else 1
                email["category"] = "FYI"
                email["one_liner"] = str(email.get("snippet", ""))[:120]

    # Drop spam / clearly-unimportant emails entirely
    filtered = [
        e for e in ranked
        if e.get("category") != "Spam/Promo" and e.get("importance", 2) > 1
    ]
    dropped = len(ranked) - len(filtered)
    if dropped:
        print(f"Filtered out {dropped} spam/low-importance emails")

    print(f"Rendering brief to {config.OUTPUT_HTML}...")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    renderer.render(filtered, config.OUTPUT_HTML, sports=sports, canvas=canvas)

    print("Opening in browser...")
    subprocess.run(["open", str(config.OUTPUT_HTML)], check=False)
    print("Done.")


if __name__ == "__main__":
    main()
