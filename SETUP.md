# Setup Guide

This covers three things: where the tool lives on your machine, how to run it with the sample data, and how to connect it to a real CRM (HubSpot or Salesforce) instead of a CSV.

## 1. Where this installs

This is a plain Python script, not an app — there's nothing to "install" system-wide. You just:

1. Clone (or download) the repo folder to anywhere on your computer, e.g. `~/Projects/lead-qualification-agent`
2. Create a Python virtual environment inside that folder (keeps its dependencies separate from everything else on your machine)
3. Install the few packages it needs into that virtual environment

Step by step:

```bash
git clone https://github.com/rubianaseem/lead-qualification-agent.git
cd lead-qualification-agent

# create a virtual environment (one-time)
python3 -m venv venv

# activate it (do this every time you open a new terminal to use the tool)
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# install dependencies into the virtual environment
pip install -r requirements.txt
```

You'll know the virtual environment is active because your terminal prompt shows `(venv)` at the start of the line. To leave it later, just type `deactivate`.

## 2. Run it with sample data (no setup needed)

```bash
python lead_qualification_agent.py --input sample_leads.csv
```

This runs entirely offline against the mock CSV — good for checking it works before connecting anything real.

## 3. Add your API key for AI-generated briefs (optional)

Without this, the tool still runs and gives you fit/intent scores + routing — just with a templated (non-AI) explanation instead of a written brief.

```bash
cp .env.example .env
```

Open `.env` and add:

```
ANTHROPIC_API_KEY=your_key_here
```

Get a key at https://console.anthropic.com/ (Settings → API Keys). Costs roughly $0.0005-0.001 per lead brief on Claude Haiku — a few cents for 50 leads.

## 4. Connect to HubSpot (instead of CSV)

**What you need:** a HubSpot Private App access token with read access to contacts.

1. In HubSpot, go to **Settings → Integrations → Private Apps**
2. Click **Create a private app**
3. Name it something like "Lead Qualification Agent"
4. Under the **Scopes** tab, find and enable: `crm.objects.contacts.read`
5. Click **Create app**, then copy the generated **Access token**
6. Add it to your `.env` file:

```
HUBSPOT_ACCESS_TOKEN=your_token_here
```

7. Run:

```bash
python lead_qualification_agent.py --source hubspot
```

This pulls your 50 most recent contacts and scores them. To change which contacts it pulls or which properties it reads, edit `load_leads_from_hubspot()` in `crm_loaders.py` — for example, filter by lifecycle stage or a specific list.

**Note:** HubSpot doesn't natively track "trial started" or "G2 comparison visit" as standard fields — if you track these as custom contact properties, map them in `crm_loaders.py` where it currently sets them to `False`.

## 5. Connect to Salesforce (instead of CSV)

**What you need:** your Salesforce instance URL and an access token.

The simplest way to get an access token for a personal script is via a **Connected App** with the OAuth 2.0 username-password flow:

1. In Salesforce Setup, go to **App Manager → New Connected App**
2. Fill in the basic info (name, contact email)
3. Under **API (Enable OAuth Settings)**, check "Enable OAuth Settings"
4. Set the callback URL to `https://login.salesforce.com/services/oauth2/success` (not used in this flow, but required)
5. Under **Selected OAuth Scopes**, add "Access and manage your data (api)"
6. Save — Salesforce takes a few minutes to activate the Connected App
7. Once active, note the **Consumer Key** and **Consumer Secret** from the app's settings

Then get an access token (replace the placeholders):

```bash
curl -X POST https://login.salesforce.com/services/oauth2/token \
  -d "grant_type=password" \
  -d "client_id=YOUR_CONSUMER_KEY" \
  -d "client_secret=YOUR_CONSUMER_SECRET" \
  -d "username=YOUR_SALESFORCE_USERNAME" \
  -d "password=YOUR_PASSWORD_PLUS_SECURITY_TOKEN"
```

(Your security token is emailed to you from Salesforce, or reset it under your personal Settings → Reset My Security Token. Append it directly to your password with no space.)

The response includes `access_token` and `instance_url`. Add both to your `.env`:

```
SF_ACCESS_TOKEN=your_access_token_here
SF_INSTANCE_URL=https://your-instance.my.salesforce.com
```

Then run:

```bash
python lead_qualification_agent.py --source salesforce
```

**Note:** access tokens from this flow expire after a while (typically 2 hours to a few days depending on your org's session settings). If you get an authentication error, just regenerate the token with the same curl command and update `.env`.

## 6. Customising the scoring logic

All of this lives in `lead_qualification_agent.py`, no need to touch the CRM loaders:

- `ICP_PROFILE` — edit target industries, minimum company size, and job titles that count as decision-makers
- `ROUTING_THRESHOLDS` — edit the fit/intent cutoffs for AE_OWNED vs SDR_ASSISTED vs PLG_SELF_SERVE
- `score_fit()` / `score_intent()` — edit the point values if you want certain signals to matter more

## Troubleshooting

- **"ModuleNotFoundError"** — you probably forgot to activate the virtual environment (`source venv/bin/activate`) or run `pip install -r requirements.txt`
- **HubSpot 401 error** — your access token is wrong or the private app doesn't have the `crm.objects.contacts.read` scope enabled
- **Salesforce "INVALID_SESSION_ID"** — your access token expired, regenerate it (see step 5)
- **Script runs but briefs look templated, not AI-written** — you haven't set `ANTHROPIC_API_KEY` in `.env`, or the `.env` file isn't being loaded (make sure it's in the same folder as the script)
