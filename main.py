#!/usr/bin/env python3
"""Morning email brief — fetches Gmail + Outlook, ranks with Claude, opens HTML summary."""

import subprocess

import config
import gmail_client
import summarizer
import renderer
import canvas_client
import calendar_tasks_client

# Note: outlook_client.py is intentionally not imported. UNC IT blocks the
# Microsoft Graph device-code flow, so direct Outlook fetch is not viable.
# Instead, UNC Outlook forwards to the aggregator Gmail and gmail_client
# tags those messages as source="Outlook" by inspecting their Received chain.


def main():
    print("=== Morning Brief ===")
    print(f"Looking back {config.LOOKBACK_HOURS} hours...\n")

    canvas = {}

    print("Fetching mail...")
    try:
        all_emails = gmail_client.fetch_emails(config.LOOKBACK_HOURS)
    except Exception as e:
        print(f"  Mail fetch error: {e}")
        all_emails = []
    print(f"  {len(all_emails)} emails")

    try:
        print("Fetching Canvas...")
        canvas = canvas_client.fetch_assignments()
        canvas_count = sum(len(g.get("items", [])) for g in canvas.get("groups", []))
        print(f"  {canvas_count} Canvas items")
    except Exception as e:
        print(f"  Canvas error: {e}")

    summary = ""
    events_extracted = []
    tasks_extracted = []
    if not all_emails:
        print("\nNo emails found. Rendering brief with Canvas section.")
        ranked = []
    else:
        print(f"\nRanking {len(all_emails)} emails with Claude...")
        try:
            ranked, summary, events_extracted, tasks_extracted = summarizer.rank_and_summarize(all_emails)
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

    # Push to Google Calendar + Google Tasks
    event_results = []
    task_results = []
    if events_extracted:
        print(f"\nCreating {len(events_extracted)} Calendar event(s)...")
        try:
            event_results = calendar_tasks_client.create_events(events_extracted)
            for r in event_results:
                if r.get("created"):
                    print(f"  + Event: {r['title']} @ {r['start']}")
                elif r.get("skipped") == "duplicate":
                    print(f"  = Skipped (already exists): {r['title']}")
                elif r.get("skipped"):
                    print(f"  = Skipped ({r['skipped']}): {r['title']}")
                elif r.get("error"):
                    print(f"  ! Error on {r.get('title','?')}: {r['error']}")
        except Exception as e:
            print(f"  Calendar push error: {e}")
    if tasks_extracted:
        print(f"\nCreating {len(tasks_extracted)} Task(s)...")
        try:
            task_results = calendar_tasks_client.create_tasks(tasks_extracted)
            for r in task_results:
                if r.get("created"):
                    due_suffix = f" (due {r['due']})" if r.get("due") else ""
                    print(f"  + Task: {r['title']}{due_suffix}")
                elif r.get("skipped") == "duplicate":
                    print(f"  = Skipped (already exists): {r['title']}")
                elif r.get("skipped"):
                    print(f"  = Skipped ({r['skipped']}): {r['title']}")
                elif r.get("error"):
                    print(f"  ! Error on {r.get('title','?')}: {r['error']}")
        except Exception as e:
            print(f"  Tasks push error: {e}")

    print(f"\nRendering brief to {config.OUTPUT_HTML}...")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    renderer.render(
        filtered,
        config.OUTPUT_HTML,
        canvas=canvas,
        summary=summary,
        events=event_results,
        tasks=task_results,
    )

    print("Opening in browser...")
    subprocess.run(["open", str(config.OUTPUT_HTML)], check=False)
    print("Done.")


if __name__ == "__main__":
    main()
