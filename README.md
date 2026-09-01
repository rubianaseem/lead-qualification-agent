# Lead Qualification Agent

A lightweight AI agent that scores inbound leads on **fit** (ICP match) and **intent** (behavioural/engagement signals), then outputs a routing decision — self-serve, SDR-assisted, or AE-owned.

This mirrors the signal-triggered routing agent I built in production at Speechmatics: ingest signals → score against an ICP model → route with an AI-generated account brief.

## What it does

1. Takes a lead/account record (company size, role, source, engagement signals)
2. Scores **fit** (0-100) against a configurable ICP profile
3. Scores **intent** (0-100) from behavioural signals (page visits, content downloads, trial activity, G2/intent data)
4. Combines both into a routing tier: `PLG_SELF_SERVE`, `SDR_ASSISTED`, or `AE_OWNED`
5. Generates a one-paragraph account brief explaining the "why" behind the score, using an LLM

## Quick start

```bash
git clone https://github.com/rubianaseem/lead-qualification-agent.git
cd lead-qualification-agent
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY or OPENAI_API_KEY
python lead_qualification_agent.py --input sample_leads.csv
```

## Cost note

Each lead costs roughly one small LLM call (~500-800 tokens) to generate the account brief. Fit/intent scoring itself is rule-based and free — only the brief generation calls the model, so cost scales with qualified leads, not raw volume.

## Example output

```
Lead: Acme Robotics (Jane Doe, VP Marketing)
Fit score: 82/100 | Intent score: 71/100
Routing: AE_OWNED
Brief: Acme Robotics matches ICP on company size (500-2000) and industry
(manufacturing). Recent G2 comparison page visits and a demo request in
the last 48h indicate active buying intent — recommend AE outreach within
2 hours citing their comparison research.
```

## Customising for your stack

- Edit `ICP_PROFILE` in `lead_qualification_agent.py` to match your ideal customer profile
- Swap `sample_leads.csv` for a live feed (HubSpot/Salesforce export, Clay enrichment output, or a webhook)
- Routing tiers and thresholds are configurable at the top of the script
