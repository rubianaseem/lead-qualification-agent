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

## How this runs today (and what production would add)

**Trigger:** none built in — this is a one-shot script you run manually (`python lead_qualification_agent.py --input ...`) or point a scheduler at (cron, n8n, Zapier). It doesn't listen for new leads on its own.

**Action taken:** prints fit/intent scores, routing tier, and the brief to your terminal. It does **not** write anything back to HubSpot/Salesforce, and does not post to Slack — you'd see the recommendation here, but a human (or another automation step) still has to act on it.

**Self-learning:** no. Scoring is hand-configured rules (`ICP_PROFILE`, routing thresholds) — there's no model training on outcomes or feedback loop. You tune the rules yourself as you learn what predicts pipeline.

**Loop:** no persistent process — it reads the input once, scores every lead in it, prints, and exits.

**What a production version would add:**
- A scheduler (cron/n8n) or a webhook trigger fired when a new lead lands in HubSpot/Salesforce
- A write-back step: update a custom "Lead Score" / "Routing Tier" property on the HubSpot contact or Salesforce lead via their API
- A Slack notification for AE_OWNED leads via an incoming webhook
- Optionally, logging routing decisions and outcomes somewhere queryable, so thresholds can be revisited based on what actually converted

## Adaptive scoring (feedback loop, not "self-learning AI")

To be precise about what this is: it's not a machine learning model that trains itself. It's a lightweight feedback loop — `adaptive_scoring.py` lets you log the real outcome of leads you scored (won/lost), then compares average signal values between the two groups to suggest which signals in the scoring logic actually predict conversion, and which don't.

```bash
# log outcomes as deals close
python adaptive_scoring.py --record-outcome --company "Acme Robotics" \
  --pages_visited_7d 6 --content_downloads 2 --trial_started false \
  --g2_comparison_visit true --demo_requested true --outcome won

# once you've logged a handful of both won and lost leads
python adaptive_scoring.py --analyze
```

```
ADAPTIVE SCORING ANALYSIS — 6 outcomes logged (3 won, 3 lost)

Signal                   Avg (Won)     Avg (Lost)    Lift
pages_visited_7d         6.00          1.00          +500%
content_downloads        2.00          0.33          +500%
g2_comparison_visit      1.00          0.00          +inf%
demo_requested           0.67          0.00          +inf%

SUGGESTED WEIGHT ADJUSTMENTS (current -> suggested):
  pages_visited_7d: 5 -> 6 (increase — strong predictor)
  g2_comparison_visit: 20 -> 26 (increase — strong predictor)
```

Suggestions are printed for you to review — nothing gets applied to `lead_qualification_agent.py` automatically. Treat it as a periodic health-check on whether your scoring rules still match reality, not an autonomous system.
