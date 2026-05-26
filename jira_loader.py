import pandas as pd
from jira import JIRA
from dotenv import load_dotenv
import os
import json

load_dotenv(override=True)


JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD")
print(JIRA_USERNAME, JIRA_PASSWORD)

jira = JIRA(
    server=JIRA_URL,
    basic_auth=(JIRA_USERNAME, JIRA_PASSWORD)
)


def fetch_jira_issues(start_dt, end_dt, max_issues=1000, project="SDIPR"):
        
    jira = JIRA(
        server=JIRA_URL,
        basic_auth=(JIRA_USERNAME, JIRA_PASSWORD)
    )
    start_str = start_dt.strftime("%Y-%m-%d %H:%M")
    end_str   = end_dt.strftime("%Y-%m-%d %H:%M")
    all_issues = []
    jql = f"project = {project} AND created >= '{start_str}' AND created <= '{end_str}' ORDER BY created DESC"
    next_token = None
    counter = 0
    b_max_results = 100
    while True:

        page = jira.enhanced_search_issues(
            jql_str=jql,
            maxResults=b_max_results,         # per API call
            nextPageToken=next_token,
            json_result=True,
            expand="*all,customfield_10673,customfield_10674",
        )
        all_issues.extend(page.get("issues", []))

        next_token = page.get("nextPageToken")

        if not next_token:  # no more pages
            break
        counter += b_max_results
        if counter >= max_issues:
            break

    print("Total issues fetched:", len(all_issues))
    # save all_issues to json file
    with open('data/jira_issues.json', 'w') as f:
        json.dump(all_issues, f, indent=4)
    #dates = [issue["created"] for issue in all_issues]
    #dates = [datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z") for date in dates]
    #dates = [date.date() for date in dates]
    #dates = [date.strftime("%Y-%m-%d") for date in dates]
    

    return all_issues



def parse_clone_links(issue):
    """
    Extract clone relationships from a JIRA issue.
    Returns a dictionary with lists: 'clones' and 'cloned_by'.
    """

    result = {
        "clones": [],      # issues this issue clones
        "cloned_by": []    # issues that clone this one
    }

    links = issue.get("fields", {}).get("issuelinks", [])
    if not links:
        return result

    for link in links:
        try:
            result["clones"].append(link['outwardIssue']['key'])
        except:
            pass
        try:
            result["cloned_by"].append(link['inwardIssue']['key'])
        except:
            pass

    return result