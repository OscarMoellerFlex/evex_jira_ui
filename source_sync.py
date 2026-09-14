"""Refresh missing ticket origins without restricting ticket creation dates."""

import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv


def fetch_issue_sources(keys):
    """Read just the source field, leaving absent/inaccessible issues untouched."""
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", key) for key in keys):
        raise ValueError("Invalid Jira ticket key in the cache.")

    load_dotenv(Path(__file__).with_name(".env"), override=True)
    base = (os.getenv("JIRA_URL") or "").rstrip("/")
    username = os.getenv("JIRA_USERNAME")
    password = os.getenv("JIRA_PASSWORD")
    if not all((base, username, password)):
        raise RuntimeError("Jira-Zugangsdaten fehlen in der Konfiguration.")

    sources = {}
    with requests.Session() as session:
        session.auth = (username, password)
        for offset in range(0, len(keys), 100):
            batch = keys[offset : offset + 100]
            payload = {
                "jql": f"key in ({','.join(batch)}) ORDER BY key",
                "fields": ["customfield_10675"],
                "maxResults": 100,
            }
            while True:
                response = session.post(
                    f"{base}/rest/api/3/search/jql", json=payload, timeout=30
                )
                response.raise_for_status()
                page = response.json()
                for issue in page.get("issues", []):
                    fields = issue.get("fields", {})
                    if "customfield_10675" in fields:
                        sources[issue["key"]] = (fields["customfield_10675"] or {}).get(
                            "value", ""
                        )
                token = page.get("nextPageToken")
                if not token:
                    break
                payload["nextPageToken"] = token
    return sources


def refresh_missing_sources(df, fetch_sources=fetch_issue_sources):
    """Fill cached blanks from Jira, preserving existing values and other fields."""
    result = df.copy()
    if result.empty:
        return result, 0
    missing = result["source"].astype("string").fillna("").str.strip().eq("")
    if not missing.any():
        return result, 0
    sources = fetch_sources(result.loc[missing, "key"].tolist())
    values = result["key"].map(sources)
    filled = missing & values.astype("string").fillna("").str.strip().ne("")
    result.loc[filled, "source"] = values.loc[filled]
    return result, int(filled.sum())
