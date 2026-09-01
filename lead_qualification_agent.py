#!/usr/bin/env python3
"""
Lead Qualification Agent (v2 — evidence-gathering)
-----------------------------------------------------
Gathers evidence across the stack for each lead into a persistent
"brain" file (brain/<lead>.json + a human-readable .md rendering),
and makes a fit/intent call from the accumulated evidence — not a
one-off snapshot. Run it again later with fresh data and it updates
the same file, so you can see a lead's intent trending up or down
over multiple runs.

Usage:
    python lead_qualification_agent.py --input sample_leads.csv
    python lead_qualification_agent.py --show "Acme Robotics"
    python lead_qualification_agent.py --history "Acme Robotics"
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

BRAIN_DIR = "brain"

ICP_PROFILE = {
    "target_industries": {"Manufacturing", "SaaS", "Healthcare", "Energy", "Financial Services"},
    "min_company_size": 200,
    "ideal_titles": {"vp", "director", "head of", "chief", "cmo", "cro", "vp marketing", "vp sales"},
}

ROUTING_THRESHOLDS = {
    "AE_OWNED": {"fit": 70, "intent": 60},
    "SDR_ASSISTED": {"fit": 40, "intent": 30},
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unknown"


def load_brain(slug: str) -> dict:
    path = os.path.join(BRAIN_DIR, f"{slug}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {
        "company": None,
        "contact_name": None,
        "contact_title": None,
        "industry": None,
        "company_size": 0,
        "signals": {
            "pages_visited_7d": 0,
            "content_downloads": 0,
            "trial_started": False,
            "g2_comparison_visit": False,
            "demo_requested": False,
        },
        "evidence_log": [],
        "verdict_history": [],
    }


def save_brain(slug: str, brain: dict):
    os.makedirs(BRAIN_DIR, exist_ok=True)
    json_path = os.path.join(BRAIN_DIR, f"{slug}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(brain, f, indent=2)
    render_markdown(slug, brain)


def render_markdown(slug: str, brain: dict):
    md_path = os.path.join(BRAIN_DIR, f"{slug}.md")
    lines = [f"# {brain['company']}", ""]
    lines.append("## Profile")
    lines.append(f"- Contact: {brain.get('contact_name') or 'Unknown'} ({brain.get('contact_title') or 'Unknown'})")
    lines.append(f"- Industry: {brain.get('industry') or 'Unknown'}")
    lines.append(f"- Company size: {brain.get('company_size') or 'Unknown'}")
    lines.append("")
    lines.append("## Accumulated signals")
    for key, value in brain["signals"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Evidence log")
    for entry in brain["evidence_log"]:
        lines.append(f"- {entry['date']}: {entry['note']}")
    lines.append("")
    if brain.get("latest_verdict"):
        v = brain["latest_verdict"]
        lines.append(f"## Latest verdict ({v['date']})")
        lines.append(f"- Fit: {v['fit_score']}/100")
        lines.append(f"- Intent: {v['intent_score']}/100")
        lines.append(f"- Routing: {v['routing_tier']}")
        lines.append(f"- Reasoning: {v['brief']}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ingest_row(brain: dict, row: dict, today: str) -> list:
    """Merge a new observation into the brain, accumulating numeric
    signals and OR-ing booleans, and logging what changed."""
    changes = []

    brain["company"] = row["company"]
    brain["contact_name"] = row["contact_name"]
    brain["contact_title"] = row["contact_title"]
    brain["industry"] = row["industry"]
    brain["company_size"] = int(row["company_size"])

    for key in ("pages_visited_7d", "content_downloads"):
        added = int(row[key])
        if added:
            brain["signals"][key] += added
            changes.append(f"+{added} {key.replace('_', ' ')}")

    for key in ("trial_started", "g2_comparison_visit", "demo_requested"):
        val = str(row[key]).strip().lower() == "true"
        if val and not brain["signals"][key]:
            brain["signals"][key] = True
            changes.append(key.replace("_", " "))

    if changes:
        brain["evidence_log"].append({"date": today, "note": ", ".join(changes)})
    else:
        brain["evidence_log"].append({"date": today, "note": "checked in, no new signals"})

    return changes


def score_fit(brain: dict) -> int:
    score = 0
    if brain["industry"] in ICP_PROFILE["target_industries"]:
        score += 35
    if brain["company_size"] >= ICP_PROFILE["min_company_size"]:
        score += 35
    elif brain["company_size"] >= ICP_PROFILE["min_company_size"] * 0.25:
        score += 15
    title = (brain["contact_title"] or "").lower()
    if any(t in title for t in ICP_PROFILE["ideal_titles"]):
        score += 30
    return min(score, 100)


def score_intent(brain: dict) -> int:
    s = brain["signals"]
    score = 0
    score += min(s["pages_visited_7d"] * 5, 25)
    score += min(s["content_downloads"] * 10, 20)
    score += 20 if s["trial_started"] else 0
    score += 20 if s["g2_comparison_visit"] else 0
    score += 15 if s["demo_requested"] else 0
    return min(score, 100)


def route(fit: int, intent: int) -> str:
    ae = ROUTING_THRESHOLDS["AE_OWNED"]
    sdr = ROUTING_THRESHOLDS["SDR_ASSISTED"]
    if fit >= ae["fit"] and intent >= ae["intent"]:
        return "AE_OWNED"
    if fit >= sdr["fit"] and intent >= sdr["intent"]:
        return "SDR_ASSISTED"
    return "PLG_SELF_SERVE"


def generate_brief(brain: dict, fit: int, intent: int, tier: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    evidence_count = len(brain["evidence_log"])

    if not api_key:
        return (
            f"{brain['company']} scores {fit}/100 fit, {intent}/100 intent "
            f"across {evidence_count} logged evidence entries -> {tier}. "
            f"(Set ANTHROPIC_API_KEY for an AI-generated brief.)"
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        history = "; ".join(e["note"] for e in brain["evidence_log"][-5:])
        prompt = (
            f"Write a 2-3 sentence account brief for a sales rep. Company: "
            f"{brain['company']}, contact: {brain['contact_name']} "
            f"({brain['contact_title']}), industry: {brain['industry']}, "
            f"size: {brain['company_size']}. Fit: {fit}/100, intent: "
            f"{intent}/100, routed {tier}. Recent evidence log: {history}. "
            f"Explain why, referencing the accumulated evidence, and "
            f"recommend a next action."
        )
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:  # pragma: no cover
        return f"(Brief generation failed: {exc})"


def process_row(row: dict, today: str):
    slug = slugify(row["company"])
    brain = load_brain(slug)
    changes = ingest_row(brain, row, today)

    fit = score_fit(brain)
    intent = score_intent(brain)
    tier = route(fit, intent)
    brief = generate_brief(brain, fit, intent, tier)

    brain["latest_verdict"] = {
        "date": today,
        "fit_score": fit,
        "intent_score": intent,
        "routing_tier": tier,
        "brief": brief,
    }
    brain["verdict_history"].append(brain["latest_verdict"])
    save_brain(slug, brain)

    print(f"\nLead: {brain['company']} ({brain['contact_name']}, {brain['contact_title']})")
    print(f"New evidence this run: {', '.join(changes) if changes else '(none)'}")
    print(f"Fit: {fit}/100 | Intent: {intent}/100 (from {len(brain['evidence_log'])} total evidence entries)")
    print(f"Routing: {tier}")
    print(f"Brief: {brief}")
    print(f"Brain file: {BRAIN_DIR}/{slug}.md")


def show_company(name: str):
    slug = slugify(name)
    path = os.path.join(BRAIN_DIR, f"{slug}.md")
    if not os.path.exists(path):
        print(f"No brain file found for '{name}'. Run --input against a CSV containing this lead first.")
        return
    with open(path, encoding="utf-8") as f:
        print(f.read())


def show_history(name: str):
    slug = slugify(name)
    brain = load_brain(slug)
    if not brain.get("verdict_history"):
        print(f"No history found for '{name}'.")
        return
    print(f"VERDICT HISTORY — {brain['company']}\n")
    for v in brain["verdict_history"]:
        print(f"{v['date']}: fit {v['fit_score']}/100, intent {v['intent_score']}/100 -> {v['routing_tier']}")


def main():
    parser = argparse.ArgumentParser(description="Gather evidence on leads and make a qualification call.")
    parser.add_argument("--input", help="Path to a leads CSV file (ingests as new evidence)")
    parser.add_argument("--show", help="Show the accumulated brain file for a company")
    parser.add_argument("--history", help="Show verdict history over time for a company")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")

    if args.show:
        show_company(args.show)
    elif args.history:
        show_history(args.history)
    elif args.input:
        if not os.path.exists(args.input):
            print(f"Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                process_row(row, today)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
