import json
import os
from dotenv import load_dotenv
from jira import JIRA

load_dotenv(override=True)


JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD")

# Fail fast on a missing token. Jira answers an unauthenticated search with
# HTTP 401 *and an empty result page* rather than an error, so without this the
# app silently fetches 0 issues and only blows up later in the transform step.
if not (JIRA_PASSWORD or "").strip():
    raise RuntimeError(
        "JIRA_PASSWORD is not set. Add it to .env before starting the app."
    )

jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USERNAME, JIRA_PASSWORD))

CLOUD_ID = "242cf880-c51a-4277-9381-781d5ae181df"
SANDBOX_CLOUD_ID = "8a3828c5-f874-43ce-9367-3d9b73c02832"

WORKSPACE_ID = "9926cb30-3f07-4fb2-9c83-aa4fc551c721"
SANDBOX_WORKSPACE_ID = "8a799a44-1189-445f-9b88-56372496d3f0"


def jira_request(url, params=None, timeout=30):
    """Helper function to make authenticated requests to the JIRA API."""
    response = requests.get(
        url,
        auth=(JIRA_USERNAME, JIRA_PASSWORD),
        headers={"Accept": "application/json"},
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=None)
def fetch_asset_object(
    cloud_id: str = CLOUD_ID, workspace_id: str = WORKSPACE_ID, object_id: str = None
):
    """Fetch a Jira Assets (Insight) object via the Atlassian Cloud Assets REST API."""
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/jsm/assets/workspace/{workspace_id}/v1/object/{object_id}"
    # url = f"{JIRA_URL.rstrip('/')}/gateway/api/jsm/assets/workspace/{workspace_id}/v1/object/{object_id}"
    return jira_request(url)


def get_workspace_id(workspace_name):
    """Fetch the workspace ID for a given workspace name."""
    url = f"https://api.atlassian.com/ex/jira/{SANDBOX_CLOUD_ID}/jsm/assets/workspace/list"
    workspaces = jira_request(url).get("values", [])
    for ws in workspaces:
        if ws.get("name", "").lower() == workspace_name.lower():
            return ws.get("id")
    raise ValueError(f"Workspace '{workspace_name}' not found")


def get_workspaces():
    # https://<Assets Site Name>.atlassian.net/rest/servicedeskapi/assets/workspace
    url = "https://amparex.atlassian.net/rest/servicedeskapi/assets/workspace"
    # url = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/jsm/assets/workspace/list"
    return jira_request(url)


def fetch_object_schema_list(
    start_at=0, max_results=50, include_counts=False, workspace_id=SANDBOX_WORKSPACE_ID
):
    """Fetch a page of Jira Assets object schemas via the Atlassian Cloud Assets REST API."""
    url = (
        f"https://api.atlassian.com/ex/jira/{SANDBOX_CLOUD_ID}/jsm/assets/workspace/"
        f"{workspace_id}/v1/objectschema/list"
    )
    return jira_request(
        url,
        params={
            "startAt": start_at,
            "maxResults": max_results,
            "includeCounts": str(include_counts).lower(),
        },
        timeout=30,
    )


def fetch_all_object_schemas(workspace_id, max_results=50, include_counts=False):
    """Fetch all Jira Assets object schemas, paging through the list endpoint."""
    schemas = []
    start_at = 0
    while True:
        page = fetch_object_schema_list(
            workspace_id=workspace_id,
            start_at=start_at,
            max_results=max_results,
            include_counts=include_counts,
        )
        values = page.get("values", [])
        schemas.extend(values)
        if not values or start_at + len(values) >= page.get("total", 0):
            break
        start_at += max_results
    return schemas


def get_asset_attribute(asset, attribute_name):
    """Return the displayValue of a named attribute on an Asset object response."""
    for attr in asset.get("attributes", []):
        name = attr.get("objectTypeAttribute", {}).get("name", "")
        if name.lower() == attribute_name.lower():
            for value in attr.get("objectAttributeValues", []):
                display = value.get("displayValue") or value.get("value")
                if display:
                    return display
    return None


def _issue_updated_ts(issue):
    """Sort key for 'recency': the issue's fields.updated (ISO 8601) or ''."""
    return issue.get("fields", {}).get("updated") or ""


def dedupe_issues(issues, key_field="key"):
    """Return issues with a unique key, preferring the most recent push.

    When the same key appears more than once, the record with the newest
    ``fields.updated`` timestamp wins; ties fall back to the record that
    appears later in the input (i.e. the more recently pushed one, when the
    caller passes ``previous + new``). Records without a key are dropped.
    """
    best = {}
    for issue in issues:
        key = issue.get(key_field)
        if key is None:
            continue
        current = best.get(key)
        if current is None or _issue_updated_ts(issue) >= _issue_updated_ts(current):
            best[key] = issue
    return list(best.values())


def fetch_jira_issues(
    start_dt,
    end_dt,
    max_issues=1000,
    project="SDIPR",
    save_path="data/jira_issues.json",
    progress_cb=None,
):
    jira = JIRA(
        server=JIRA_URL,
        basic_auth=(JIRA_USERNAME, JIRA_PASSWORD),
    )
    start_str = start_dt.strftime("%Y-%m-%d %H:%M")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M")
    all_issues = []
    jql = f"project = {project} AND created >= '{start_str}' AND created <= '{end_str}' ORDER BY created DESC"
    next_token = None
    counter = 0
    b_max_results = 100
    print(f"Fetching issues with JQL: {jql}")
    while True:

        page = jira.enhanced_search_issues(
            jql_str=jql,
            maxResults=b_max_results,  # per API call
            nextPageToken=next_token,
            json_result=True,
            expand="*all,customfield_10673,customfield_10674",
        )
        for issue in page.get("issues", []):
            fields = issue.get("fields", {})
            customer_assets = fields.get("customfield_10673") or []
            country = None
            if customer_assets:
                last_asset = customer_assets[-1]
                workspace_id = last_asset.get("workspaceId")
                object_id = last_asset.get("objectId")
                if workspace_id and object_id:
                    try:
                        asset = fetch_asset_object(
                            SANDBOX_CLOUD_ID, SANDBOX_WORKSPACE_ID, object_id
                        )
                        country = get_asset_attribute(
                            asset, "Land"
                        ) or get_asset_attribute(asset, "Country")
                        issue["customer_country"] = country
                        issue["customer"] = asset
                    except requests.HTTPError as exc:
                        print(
                            f"Failed to fetch asset {workspace_id}:{object_id}: {exc} — body: {exc.response.text[:300]}"
                        )
                    except requests.RequestException as exc:
                        print(
                            f"Failed to fetch asset {workspace_id}:{object_id}: {exc}"
                        )
        all_issues.extend(page.get("issues", []))
        if progress_cb:
            progress_cb(len(all_issues))

        next_token = page.get("nextPageToken")

        if not next_token:  # no more pages
            break
        counter += b_max_results
        if counter >= max_issues:
            break

    print("Total issues fetched:", len(all_issues))
    # save all_issues to json file (pass save_path=None to skip, e.g. when
    # the caller merges the result into an existing store itself)
    if save_path:
        with open(save_path, "w") as f:
            json.dump(all_issues, f, indent=4)
    # dates = [issue["created"] for issue in all_issues]
    # dates = [datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z") for date in dates]
    # dates = [date.date() for date in dates]
    # dates = [date.strftime("%Y-%m-%d") for date in dates]

    return all_issues


def parse_clone_links(issue):
    """
    Extract clone relationships from a JIRA issue.
    Returns a dictionary with lists: 'clones' and 'cloned_by'.
    """

    result = {
        "clones": [],  # issues this issue clones
        "cloned_by": [],  # issues that clone this one
    }

    links = issue.get("fields", {}).get("issuelinks", [])
    if not links:
        return result

    for link in links:
        # A link carries an outwardIssue, an inwardIssue, or neither - probe
        # with .get() instead of swallowing KeyError with a bare except/pass.
        outward = link.get("outwardIssue") or {}
        if "key" in outward:
            result["clones"].append(outward["key"])

        inward = link.get("inwardIssue") or {}
        if "key" in inward:
            result["cloned_by"].append(inward["key"])

    return result
