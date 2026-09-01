#!/usr/bin/env python3
"""
Adaptive Scoring Analyzer — Lead Qualification Agent
-------------------------------------------------------
This is NOT self-learning AI. It's a lightweight feedback-loop tool:
you log the real outcome of leads you scored (won/lost), and this
script compares average signal values between won and lost leads to
suggest which signals in INTENT_WEIGHTS look predictive vs. not.

Suggestions are printed for you to review and manually apply to
lead_qualification_agent.py — nothing is changed automatically.

Usage:
    # 1. Log an outcome for a lead you previously scored
    python adaptive_scoring.py --record-outcome --company "Acme Robotics" \
        --pages_visited_7d 6 --content_downloads 2 --trial_started false \
        --g2_comparison_visit true --demo_requested true --outcome won

    # 2. Once you have a decent number logged, analyze them
    python adaptive_scoring.py --analyze
"""

import argparse
import csv
import os

OUTCOMES_FILE = "outcomes_log.csv"

SIGNAL_FIELDS = [
    "pages_visited_7d",
    "content_downloads",
    "trial_started",
    "g2_comparison_visit",
    "demo_requested",
]

CURRENT_WEIGHTS = {
    "pages_visited_7d": 5,
    "content_downloads": 10,
    "trial_started": 20,
    "g2_comparison_visit": 20,
    "demo_requested": 15,
}


def record_outcome(args):
    file_exists = os.path.exists(OUTCOMES_FILE)
    with open(OUTCOMES_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["company"] + SIGNAL_FIELDS + ["outcome"])
        writer.writerow(
            [
                args.company,
                args.pages_visited_7d,
                args.content_downloads,
                args.trial_started,
                args.g2_comparison_visit,
                args.demo_requested,
                args.outcome,
            ]
        )
    print(f"Logged outcome for {args.company}: {args.outcome}")


def to_number(value: str) -> float:
    v = value.strip().lower()
    if v in ("true", "yes", "1"):
        return 1.0
    if v in ("false", "no", "0", ""):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def analyze():
    if not os.path.exists(OUTCOMES_FILE):
        print(f"No {OUTCOMES_FILE} found yet. Log some outcomes first with --record-outcome.")
        return

    with open(OUTCOMES_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    won = [r for r in rows if r["outcome"].strip().lower() == "won"]
    lost = [r for r in rows if r["outcome"].strip().lower() == "lost"]

    print(f"ADAPTIVE SCORING ANALYSIS — {len(rows)} outcomes logged ({len(won)} won, {len(lost)} lost)\n")

    if len(won) < 3 or len(lost) < 3:
        print("Not enough data yet for a meaningful comparison — log at least a few won AND a few lost leads.")
        return

    print(f"{'Signal':<25}{'Avg (Won)':<14}{'Avg (Lost)':<14}Lift")
    lifts = {}
    for field in SIGNAL_FIELDS:
        won_avg = sum(to_number(r[field]) for r in won) / len(won)
        lost_avg = sum(to_number(r[field]) for r in lost) / len(lost)
        if lost_avg == 0:
            lift = float("inf") if won_avg > 0 else 0.0
        else:
            lift = (won_avg - lost_avg) / lost_avg * 100
        lifts[field] = lift
        lift_str = "+inf%" if lift == float("inf") else f"{lift:+.0f}%"
        print(f"{field:<25}{won_avg:<14.2f}{lost_avg:<14.2f}{lift_str}")

    print("\nSUGGESTED WEIGHT ADJUSTMENTS (current -> suggested):")
    for field, lift in lifts.items():
        current = CURRENT_WEIGHTS[field]
        if lift == float("inf") or lift > 50:
            suggested = round(current * 1.3)
            note = "increase — strong predictor"
        elif lift > 10:
            suggested = round(current * 1.1)
            note = "slight increase"
        elif lift < -10:
            suggested = round(current * 0.8)
            note = "decrease — weak/negative predictor"
        else:
            suggested = current
            note = "no change — weak signal"
        print(f"  {field}: {current} -> {suggested} ({note})")

    print(
        f"\nThese are suggestions based on {len(rows)} logged outcomes — review before "
        f"manually applying them to the weights in lead_qualification_agent.py's "
        f"score_intent() function. Nothing is applied automatically."
    )


def main():
    parser = argparse.ArgumentParser(description="Log outcomes and get suggested scoring weight adjustments.")
    parser.add_argument("--record-outcome", action="store_true", help="Log a lead's real outcome")
    parser.add_argument("--analyze", action="store_true", help="Analyze logged outcomes and suggest weight changes")
    parser.add_argument("--company", help="Company name (for --record-outcome)")
    parser.add_argument("--pages_visited_7d", type=int, default=0)
    parser.add_argument("--content_downloads", type=int, default=0)
    parser.add_argument("--trial_started", default="false")
    parser.add_argument("--g2_comparison_visit", default="false")
    parser.add_argument("--demo_requested", default="false")
    parser.add_argument("--outcome", choices=["won", "lost"], help="Real outcome of this lead")
    args = parser.parse_args()

    if args.record_outcome:
        if not args.company or not args.outcome:
            parser.error("--record-outcome requires --company and --outcome")
        record_outcome(args)
    elif args.analyze:
        analyze()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
