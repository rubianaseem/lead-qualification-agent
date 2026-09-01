#!/usr/bin/env python3
"""
Lead Qualification Agent
-------------------------
Scores inbound leads on fit (ICP match) and intent (behavioural signals),
then routes them to PLG_SELF_SERVE, SDR_ASSISTED, or AE_OWNED — with an
AI-generated one-paragraph brief explaining why.

Usage:
    python lead_qualification_agent.py --input sample_leads.csv
    python lead_qualification_agent.py --source hubspot
    python lead_qualification_agent.py --source salesforce

See SETUP.md for how to connect HubSpot or Salesforce.
"""

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# 1. Configure your ICP here
# --------------------------------------------------------------------------
ICP_PROFILE = {
    "target_industries": {"Manufacturing", "SaaS", "Healthcare", "Energy", "Financial Services"},
    "min_company_size": 200,
    "ideal_titles": {"vp", "director", "head of", "chief", "cmo", "cro", "vp marketing", "vp sales"},
}

# Routing thresholds — tune these to your pipeline capacity
ROUTING_THRESHOLDS = {
    "AE_OWNED": {"fit": 70, "intent": 60},
    "SDR_ASSISTED": {"fit": 40, "intent": 30},
    # anything below SDR_ASSISTED thresholds -> PLG_SELF_SERVE
}


@dataclass
class Lead:
    company: str
    contact_name: str
    contact_title: str
    company_size: int
    industry: str
    source: str
    pages_visited_7d: int
    content_downloads: int
    trial_started: bool
    g2_comparison_visit: bool
    demo_requested: bool
    fit_score: int = field(default=0)
    intent_score: int = field(default=0)
    routing_tier: str = field(default="")
    brief: str = field(default="")

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        return cls(
            company=d["company"],
            contact_name=d["contact_name"],
            contact_title=d["contact_title"],
            company_size=int(d["company_size"]),
            industry=d["industry"],
            source=d["source"],
            pages_visited_7d=int(d["pages_visited_7d"]),
            content_downloads=int(d["content_downloads"]),
            trial_started=str(d["trial_started"]).strip().lower() == "true",
            g2_comparison_visit=str(d["g2_comparison_visit"]).strip().lower() == "true",
            demo_requested=str(d["demo_requested"]).strip().lower() == "true",
        )


def score_fit(lead: Lead) -> int:
    """Rule-based fit score against the configured ICP. 0-100, no LLM call needed."""
    score = 0

    if lead.industry in ICP_PROFILE["target_industries"]:
        score += 35

    if lead.company_size >= ICP_PROFILE["min_company_size"]:
        score += 35
    elif lead.company_size >= ICP_PROFILE["min_company_size"] * 0.25:
        score += 15

    title = lead.contact_title.lower()
    if any(t in title for t in ICP_PROFILE["ideal_titles"]):
        score += 30

    return min(score, 100)


def score_intent(lead: Lead) -> int:
    """Rule-based intent score from behavioural/engagement signals. 0-100."""
    score = 0
    score += min(lead.pages_visited_7d * 5, 25)
    score += min(lead.content_downloads * 10, 20)
    score += 20 if lead.trial_started else 0
    score += 20 if lead.g2_comparison_visit else 0
    score += 15 if lead.demo_requested else 0
    return min(score, 100)


def route(fit: int, intent: int) -> str:
    ae = ROUTING_THRESHOLDS["AE_OWNED"]
    sdr = ROUTING_THRESHOLDS["SDR_ASSISTED"]

    if fit >= ae["fit"] and intent >= ae["intent"]:
        return "AE_OWNED"
    if fit >= sdr["fit"] and intent >= sdr["intent"]:
        return "SDR_ASSISTED"
    return "PLG_SELF_SERVE"


def generate_brief(lead: Lead) -> str:
    """Generate a one-paragraph account brief. Falls back to a templated
    brief if no API key is set, so the script always runs end-to-end."""
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return (
            f"{lead.company} scores {lead.fit_score}/100 on fit and "
            f"{lead.intent_score}/100 on intent -> routed {lead.routing_tier}. "
            f"(Set ANTHROPIC_API_KEY for an AI-generated brief.)"
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Write a 2-3 sentence GTM account brief for a sales rep. "
            f"Company: {lead.company}, contact: {lead.contact_name} "
            f"({lead.contact_title}), industry: {lead.industry}, size: "
            f"{lead.company_size}, source: {lead.source}. Fit score: "
            f"{lead.fit_score}/100, intent score: {lead.intent_score}/100. "
            f"Signals: {lead.pages_visited_7d} pages visited in 7 days, "
            f"{lead.content_downloads} content downloads, trial started: "
            f"{lead.trial_started}, viewed G2 comparison: "
            f"{lead.g2_comparison_visit}, demo requested: {lead.demo_requested}. "
            f"Routing tier: {lead.routing_tier}. Explain briefly why, and "
            f"recommend a next action and timeframe."
        )
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:  # pragma: no cover - network/env dependent
        return f"(Brief generation failed: {exc})"


def load_leads_from_csv(path: str) -> list[Lead]:
    leads = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(Lead.from_dict(row))
    return leads


def load_leads(args) -> list[Lead]:
    if args.source == "hubspot":
        from crm_loaders import load_leads_from_hubspot

        return [Lead.from_dict(d) for d in load_leads_from_hubspot()]

    if args.source == "salesforce":
        from crm_loaders import load_leads_from_salesforce

        return [Lead.from_dict(d) for d in load_leads_from_salesforce()]

    # default: csv
    if not args.input:
        print("--input is required when --source csv (the default) is used", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    return load_leads_from_csv(args.input)


def main():
    parser = argparse.ArgumentParser(description="Score and route inbound leads.")
    parser.add_argument("--input", help="Path to a leads CSV file (used when --source csv)")
    parser.add_argument(
        "--source",
        choices=["csv", "hubspot", "salesforce"],
        default="csv",
        help="Where to pull leads from. Defaults to csv. See SETUP.md for hubspot/salesforce.",
    )
    args = parser.parse_args()

    leads = load_leads(args)

    if not leads:
        print("No leads found.")
        return

    for lead in leads:
        lead.fit_score = score_fit(lead)
        lead.intent_score = score_intent(lead)
        lead.routing_tier = route(lead.fit_score, lead.intent_score)
        lead.brief = generate_brief(lead)

        print(f"\nLead: {lead.company} ({lead.contact_name}, {lead.contact_title})")
        print(f"Fit score: {lead.fit_score}/100 | Intent score: {lead.intent_score}/100")
        print(f"Routing: {lead.routing_tier}")
        print(f"Brief: {lead.brief}")


if __name__ == "__main__":
    main()
