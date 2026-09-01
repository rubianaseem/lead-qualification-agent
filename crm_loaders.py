"""
CRM Loaders
-----------
Pulls lead/contact records from HubSpot or Salesforce and converts them
into Lead objects the qualification agent can score. Falls back to CSV
if no CRM is configured (see lead_qualification_agent.py).

Each loader only needs read access to a handful of standard fields —
see SETUP.md for exactly which scopes/permissions to grant.
"""

import os

import requests


def load_leads_from_hubspot(limit: int = 50):
    """
    Pull recent contacts from HubSpot using a Private App access token.

    Required env var: HUBSPOT_ACCESS_TOKEN
    Required scope on the private app: crm.objects.contacts.read
    """
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set HUBSPOT_ACCESS_TOKEN in your .env file. See SETUP.md.")

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    params = {
        "limit": limit,
        "properties": ",".join(
            [
                "company",
                "firstname",
                "lastname",
                "jobtitle",
                "numemployees",
                "industry",
                "hs_analytics_source",
                "hs_analytics_num_page_views",
                "num_conversion_events",
            ]
        ),
    }
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])

    leads = []
    for r in results:
        p = r.get("properties", {})
        leads.append(
            {
                "company": p.get("company") or "Unknown",
                "contact_name": f"{p.get('firstname', '')} {p.get('lastname', '')}".strip() or "Unknown",
                "contact_title": p.get("jobtitle") or "",
                "company_size": int(p.get("numemployees") or 0),
                "industry": p.get("industry") or "Unknown",
                "source": p.get("hs_analytics_source") or "Unknown",
                "pages_visited_7d": int(p.get("hs_analytics_num_page_views") or 0),
                "content_downloads": int(p.get("num_conversion_events") or 0),
                # HubSpot doesn't expose these three out of the box —
                # map them to custom properties if you track them, or leave as False
                "trial_started": False,
                "g2_comparison_visit": False,
                "demo_requested": False,
            }
        )
    return leads


def load_leads_from_salesforce(limit: int = 50):
    """
    Pull recent Leads from Salesforce via SOQL using a Connected App
    (username-password OAuth flow, simplest to set up for a personal script).

    Required env vars: SF_INSTANCE_URL, SF_ACCESS_TOKEN
    (see SETUP.md for how to generate SF_ACCESS_TOKEN)
    """
    instance_url = os.getenv("SF_INSTANCE_URL")
    access_token = os.getenv("SF_ACCESS_TOKEN")
    if not instance_url or not access_token:
        raise RuntimeError(
            "Set SF_INSTANCE_URL and SF_ACCESS_TOKEN in your .env file. See SETUP.md."
        )

    query = (
        "SELECT Company, Name, Title, NumberOfEmployees, Industry, LeadSource "
        f"FROM Lead WHERE IsConverted = false ORDER BY CreatedDate DESC LIMIT {limit}"
    )
    url = f"{instance_url}/services/data/v59.0/query"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, params={"q": query}, timeout=30)
    resp.raise_for_status()
    records = resp.json().get("records", [])

    leads = []
    for r in records:
        leads.append(
            {
                "company": r.get("Company") or "Unknown",
                "contact_name": r.get("Name") or "Unknown",
                "contact_title": r.get("Title") or "",
                "company_size": int(r.get("NumberOfEmployees") or 0),
                "industry": r.get("Industry") or "Unknown",
                "source": r.get("LeadSource") or "Unknown",
                # Salesforce Lead object doesn't track these behavioural
                # signals natively — pull from your MAP (HubSpot/Pardot/Marketo)
                # or a CDP if you want real intent data here
                "pages_visited_7d": 0,
                "content_downloads": 0,
                "trial_started": False,
                "g2_comparison_visit": False,
                "demo_requested": False,
            }
        )
    return leads
