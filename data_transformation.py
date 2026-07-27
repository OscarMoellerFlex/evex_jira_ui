import json
import os
from datetime import time

import holidays
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from jira import JIRA

load_dotenv(override=True)

JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_PASSWORD = os.getenv("JIRA_API_KEY")
jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USERNAME, JIRA_PASSWORD))
# jira = JIRA(server=JIRA_URL, token_auth=JIRA_API_KEY)
# read json from data/jira-servicedesk-schema-objects.json
# with open('data/jira-servicedesk-schema-objects.json', 'r') as f:
#    schema = json.load(f)
# object_id_to_name = {v['id']: v['name'] for v in schema['values']}
BUS_START = time(8, 0)
BUS_END = time(18, 0)
TZ = "Europe/Berlin"


def enrich_jira_time_metrics(
    df: pd.DataFrame,
    tz: str = "Europe/Berlin",
    done_value: str = "Fertig",
    status_col: str = "currentstatus_name",
    created_col: str = "created",
    updated_col: str = "updated",
    status_date_col: str = "currentstatus_date",
    business_start: time = time(8, 0),
    business_end: time = time(18, 0),
    subdiv: (
        str | None
    ) = None,  # e.g. "BE", "BY", "NW", ...; None = federal holidays only
    bins: list[float] | None = None,
) -> pd.DataFrame:
    """
    Returns a copy of df with standardized timestamp columns and resolution KPIs.
    Requires: pip install holidays
    Expects: status_col contains "Fertig" for done tickets.
    """
    out = df.copy()

    # ---------- defaults ----------
    if bins is None:
        bins = [0, 1, 2, 4, 8, 24, 48, 72, 7 * 24, 14 * 24, 21 * 24]

    # ---------- parse timestamps ----------
    for c in [created_col, updated_col, status_date_col]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce", utc=True).dt.tz_convert(tz)

    # ---------- done + resolved_at ----------
    if status_col not in out.columns:
        raise KeyError(f"Missing status column '{status_col}'")
    if created_col not in out.columns:
        raise KeyError(f"Missing created column '{created_col}'")
    if status_date_col not in out.columns:
        raise KeyError(f"Missing status date column '{status_date_col}'")

    out["is_done"] = out[status_col].astype("string") == done_value
    out["resolved_at"] = out[status_date_col].where(out["is_done"], pd.NaT)

    # ---------- simple elapsed hours ----------
    out["time_to_resolution_h"] = (
        out["resolved_at"] - out[created_col]
    ).dt.total_seconds() / 3600.0

    # ---------- calendar days (0 if same calendar day; only for done) ----------
    out["time_to_resolution_calendar_days"] = (
        out["resolved_at"].dt.normalize() - out[created_col].dt.normalize()
    ).dt.days
    out.loc[~out["is_done"], "time_to_resolution_calendar_days"] = np.nan

    out["resolution"] = np.where(
        out["is_done"],
        np.where(out["time_to_resolution_calendar_days"] < 1, "Same day", "> 1 day"),
        "Not done",
    )

    # ---------- holidays (Germany) ----------
    # Determine year range from created/resolved/updated (whatever is present)
    year_series = []
    for c in [created_col, updated_col, "resolved_at"]:
        if c in out.columns:
            year_series.append(out[c])
    years_stack = pd.concat(year_series, axis=0)

    min_year = int(years_stack.dt.year.min())
    max_year = int(years_stack.dt.year.max())
    de = holidays.Germany(years=range(min_year, max_year + 1), subdiv=subdiv)

    holiday_set = set(de.keys())  # datetime.date for biz-hour logic
    holiday_dates = np.array(
        [np.datetime64(d) for d in de.keys()], dtype="datetime64[D]"
    )  # for np.busday_count

    # ---------- business hours helper ----------
    def business_seconds_between(start: pd.Timestamp, end: pd.Timestamp) -> float:
        if pd.isna(start) or pd.isna(end) or end <= start:
            return 0.0

        total = 0.0
        # iterate days in tz (timestamps already tz-aware)
        for day in pd.date_range(
            start.normalize(), end.normalize(), freq="D", tz=start.tz
        ):
            d = day.date()
            if day.weekday() >= 5 or d in holiday_set:
                continue

            day_start = pd.Timestamp.combine(d, business_start).tz_localize(start.tz)
            day_end = pd.Timestamp.combine(d, business_end).tz_localize(start.tz)

            a = max(start, day_start)
            b = min(end, day_end)
            if b > a:
                total += (b - a).total_seconds()
        return total

    # ---------- business hours/days to resolution ----------
    out["time_to_resolution_biz_hours"] = np.where(
        out["is_done"],
        out.apply(
            lambda r: business_seconds_between(r[created_col], r["resolved_at"])
            / 3600.0,
            axis=1,
        ),
        np.nan,
    )
    out["time_to_resolution_biz_days"] = out["time_to_resolution_biz_hours"] / (
        (
            pd.Timestamp.combine(pd.Timestamp.today().date(), business_end)
            - pd.Timestamp.combine(pd.Timestamp.today().date(), business_start)
        ).total_seconds()
        / 3600.0
    )

    # ---------- bins on elapsed hours (real time) ----------
    labels = [f"{int(bins[i])}–{int(bins[i+1])}" for i in range(len(bins) - 1)]
    out["time_to_resolution_bin"] = pd.cut(
        out["time_to_resolution_h"], bins=bins, labels=labels, include_lowest=True
    )

    # ---------- business day counts including holidays ----------
    # busday_count wants "datetime64[D]" without tz; normalize via tz_localize(None)
    created_days = out[created_col].dt.tz_localize(None).to_numpy(dtype="datetime64[D]")

    if updated_col in out.columns:
        updated_days = (
            out[updated_col].dt.tz_localize(None).to_numpy(dtype="datetime64[D]")
        )
        out["business_days_created_to_updated"] = np.busday_count(
            created_days, updated_days, weekmask="1111100", holidays=holiday_dates
        )
    else:
        out["business_days_created_to_updated"] = np.nan

    resolved_days = (
        out["resolved_at"].dt.tz_localize(None).to_numpy(dtype="datetime64[D]")
    )
    # For unresolved rows, busday_count will error if NaT -> convert to NaN afterwards
    # Workaround: compute only for done rows
    out["business_days_created_to_resolved"] = np.nan
    mask = out["is_done"] & out["resolved_at"].notna()
    out.loc[mask, "business_days_created_to_resolved"] = np.busday_count(
        created_days[mask.to_numpy()],
        resolved_days[mask.to_numpy()],
        weekmask="1111100",
        holidays=holiday_dates,
    )

    # ---------- helper strings ----------
    out["created_string"] = out[created_col].dt.strftime("%Y-%m-%d")
    if updated_col in out.columns:
        out["updated_string"] = out[updated_col].dt.strftime("%Y-%m-%d")
    else:
        out["updated_string"] = np.nan

    out["year"] = out[created_col].dt.year
    out["month"] = out[created_col].dt.month
    out["week_number"] = out[created_col].dt.isocalendar().week.astype(int)
    out["week_string"] = out[created_col].dt.strftime("%G-W%V")
    out["month_string"] = out[created_col].dt.strftime("%Y-%m")

    return out


"""
def business_seconds_between(start: pd.Timestamp,
                             end: pd.Timestamp,
                             holiday_set: set) -> float:
    if pd.isna(start) or pd.isna(end):
        return float("nan")
    if end <= start:
        return 0.0

    # iterate day by day, sum overlaps with business window
    total = 0.0
    for day in pd.date_range(start.normalize(), end.normalize(), freq="D", tz=start.tz):
        d = day.date()
        # weekday: Mon=0..Sun=6
        if day.weekday() >= 5 or d in holiday_set:
            continue

        day_start = pd.Timestamp.combine(d, BUS_START).tz_localize(start.tz)
        day_end   = pd.Timestamp.combine(d, BUS_END).tz_localize(start.tz)

        overlap_start = max(start, day_start)
        overlap_end   = min(end, day_end)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds()
    return total"""

# read object_id_to_name from json file
with open("data/object_id_to_name.json", "r") as f:  #
    object_id_to_name = json.load(f)


def load_clone_of_clone(key):
    clones = []
    clone_types = []
    try:
        issue_raw = jira.issue(key).raw
        links = issue_raw["fields"].get("issuelinks", [])
        for link in links:
            if "outwardIssue" in link:
                clone_key = link["outwardIssue"]["key"]
                clone_type = link["type"]["name"]
                clones.append(clone_key)
                clone_types.append(clone_type)
    except Exception as e:
        print(f"Error for clone_of_clone: {e!r}")
    return ",".join(clones), ",".join(clone_types)


def load_clones(links):
    clones = []
    clone_types = []
    clones_of_clones = []
    clone_types_of_clones = []
    try:
        for link in links:
            if "outwardIssue" in link:
                clone_key = link["outwardIssue"]["key"]
                clone_type = link["type"]["name"]
                clones.append(clone_key)
                clone_types.append(clone_type)
                cc, ctc = load_clone_of_clone(clone_key)
                clones_of_clones.append(cc)
                clone_types_of_clones.append(ctc)
    except Exception as e:
        print(f"Error for clones: {e!r}")

    return (
        ",".join(clones),
        ",".join(clone_types),
        len(clones),
        ",".join(clones_of_clones),
        ",".join(clone_types_of_clones),
    )


def load_issues(issues):
    df = {
        "key": [],
        "summary": [],
        "description": [],
        "status": [],
        "status_category": [],
        "created": [],
        "updated": [],
        "labels": [],
        "source": [],
        "priority": [],
        "category": [],
        "issuetype": [],
        "main_category_id": [],
        "sub_category_id": [],
        "currentstatus_name": [],
        "currentstatus_date": [],
        "comments": [],
        "request_type": [],
        "clones": [],
        "clone_types": [],
        "cloned_by": [],
        "n_clones": [],
        "zentrale": [],
        "filiale": [],
        "Link": [],
        "clones_of_clones": [],
        "clone_types_of_clones": [],
    }
    for issue in issues:
        df["key"].append(issue["key"])
        df["summary"].append(issue["fields"]["summary"])
        df["description"].append(issue["fields"]["description"])
        df["status"].append(issue["fields"]["status"]["name"])
        df["status_category"].append(
            issue["fields"]["status"]["statusCategory"]["name"]
        )
        # df['creator'].append(issue['fields']['creator']['displayName'])
        df["issuetype"].append(issue["fields"]["issuetype"]["name"])
        df["created"].append(issue["fields"]["created"])
        df["updated"].append(issue["fields"]["updated"])
        df["labels"].append(issue["fields"]["labels"])
        df["priority"].append(issue["fields"]["priority"]["name"])
        df["category"].append(issue["fields"]["customfield_10065"])

        if issue["fields"]["customfield_10010"] is not None:
            df["request_type"].append(
                issue["fields"]["customfield_10010"]["requestType"]["name"]
            )
        else:
            df["request_type"].append("")
        if issue["fields"]["comment"] is not None:
            df["comments"].append(
                "\n\n".join([c["body"] for c in issue["fields"]["comment"]["comments"]])
            )
        else:
            df["comments"].append([])

        try:
            df["currentstatus_name"].append(
                issue["fields"]["customfield_10010"]["currentStatus"]["status"]
            )
            df["currentstatus_date"].append(
                issue["fields"]["customfield_10010"]["currentStatus"]["statusDate"][
                    "jira"
                ]
            )
        except Exception:
            df["currentstatus_name"].append("")
            df["currentstatus_date"].append("")

        try:
            v = issue["fields"]["customfield_10675"]["value"]
            df["source"].append(v)
        except Exception:
            df["source"].append("")

        cf = issue["fields"]["customfield_10680"]
        if len(cf) > 0:
            df["main_category_id"].append(cf[0]["objectId"])
        else:
            df["main_category_id"].append("")
        cf = issue["fields"]["customfield_10679"]
        if len(cf) > 0:
            df["sub_category_id"].append(cf[0]["objectId"])
        else:
            df["sub_category_id"].append("")

        if "issuelinks" in issue["fields"] and len(issue["fields"]["issuelinks"]) > 0:
            clones, clone_types, n_clones, clones_of_clones, clone_types_of_clones = (
                load_clones(issue["fields"]["issuelinks"])
            )
            df["clones"].append(clones)
            df["clone_types"].append(clone_types)
            df["n_clones"].append(n_clones)
            df["clones_of_clones"].append(clones_of_clones)
            df["clone_types_of_clones"].append(clone_types_of_clones)
        else:
            df["clones"].append("")
            df["clone_types"].append("")
            df["n_clones"].append(0)
            df["clones_of_clones"].append("")
            df["clone_types_of_clones"].append("")

        try:
            df["cloned_by"].append(
                issue["fields"]["issuelinks"][0]["inwardIssue"]["key"]
            )
        except Exception:
            df["cloned_by"].append("")

        try:
            df["zentrale"].append(
                "ID_" + str(issue["fields"]["customfield_10673"][0]["objectId"])
            )
        except Exception:
            df["zentrale"].append("")
        try:
            df["filiale"].append(
                "ID_" + str(issue["fields"]["customfield_10674"][0]["objectId"])
            )
        except Exception:
            df["filiale"].append("")
        try:
            df["Link"].append(issue["fields"]["customfield_10010"]["_links"]["agent"])
        except Exception:
            df["Link"].append("")

    df = pd.DataFrame(df)
    DT_COLS = ["created", "updated", "currentstatus_date"]
    for c in DT_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_convert(TZ)
    df = enrich_jira_time_metrics(df)

    df["Hauptkategorie"] = df["main_category_id"].map(object_id_to_name)
    df["Unterkategorie"] = df["sub_category_id"].map(object_id_to_name).fillna("NA")

    df["zentrale"] = df["zentrale"].astype(str)
    df["filiale"] = df["filiale"].astype(str)
    df["firma"] = "IPRO"

    df["clone_in_project"] = df["clones"].apply(
        lambda x: ",".join([y.split("-")[0] for y in x.split(",")]) if x else "-"
    )
    df["has_exax_clone"] = df["clone_in_project"].str.contains("EXIPR")
    df["has_axt_clone_clone"] = ""

    # move firma column to the front
    df = df[["firma", *[col for col in df.columns if col != "firma"]]]

    return df


def upsert_jira_data(df_old, df_new, key_col="key"):
    df_old, df_new = df_old.align(df_new, join="outer", axis=1)

    df_old = df_old.set_index(key_col)
    df_new = df_new.set_index(key_col)

    df_old.update(df_new)

    new_rows = df_new.loc[df_new.index.difference(df_old.index)]
    df_combined = pd.concat([df_old, new_rows])

    return df_combined.reset_index()


def load_issues_Amparex(issues):
    df = {
        "key": [],
        "summary": [],
        "description": [],
        "status": [],
        "status_category": [],
        "created": [],
        "updated": [],
        "labels": [],
        "source": [],
        "priority": [],
        "category": [],
        "issuetype": [],
        "main_category_id": [],
        "sub_category_id": [],
        "currentstatus_name": [],
        "currentstatus_date": [],
        "comments": [],
        "request_type": [],
        "clones": [],
        "clone_types": [],
        "cloned_by": [],
        "n_clones": [],
        "zentrale": [],
        "filiale": [],
        "Link": [],
        "clones_of_clones": [],
        "clone_types_of_clones": [],
    }
    for issue in issues:
        df["key"].append(issue["key"])
        df["summary"].append(issue["fields"]["summary"])
        df["description"].append(issue["fields"]["description"])
        df["status"].append(issue["fields"]["status"]["name"])
        df["status_category"].append(
            issue["fields"]["status"]["statusCategory"]["name"]
        )
        # df['creator'].append(issue['fields']['creator']['displayName'])
        df["issuetype"].append(issue["fields"]["issuetype"]["name"])
        df["created"].append(issue["fields"]["created"])
        df["updated"].append(issue["fields"]["updated"])
        df["labels"].append(issue["fields"]["labels"])
        df["priority"].append(issue["fields"]["priority"]["name"])
        df["category"].append(issue["fields"]["customfield_10065"])

        if issue["fields"]["customfield_10010"] is not None:
            df["request_type"].append(
                issue["fields"]["customfield_10010"]["requestType"]["name"]
            )
        else:
            df["request_type"].append("")
        if issue["fields"]["comment"] is not None:
            df["comments"].append(
                "\n--------------------------------\n".join(
                    [c["body"] for c in issue["fields"]["comment"]["comments"]]
                )
            )
        else:
            df["comments"].append([])

        try:
            df["currentstatus_name"].append(
                issue["fields"]["customfield_10010"]["currentStatus"]["status"]
            )
            df["currentstatus_date"].append(
                issue["fields"]["customfield_10010"]["currentStatus"]["statusDate"][
                    "jira"
                ]
            )
        except Exception:
            df["currentstatus_name"].append("")
            df["currentstatus_date"].append("")

        try:
            v = issue["fields"]["customfield_10675"]["value"]
            df["source"].append(v)
        except Exception:
            df["source"].append("")

        cf = issue["fields"]["customfield_10680"]
        if len(cf) > 0:
            df["main_category_id"].append(cf[0]["objectId"])
        else:
            df["main_category_id"].append("")

        cf = issue["fields"]["customfield_10679"]
        if len(cf) > 0:
            df["sub_category_id"].append(cf[0]["objectId"])
        else:
            df["sub_category_id"].append("")

        if "issuelinks" in issue["fields"] and len(issue["fields"]["issuelinks"]) > 0:
            clones, clone_types, n_clones, clones_of_clones, clone_types_of_clones = (
                load_clones(issue["fields"]["issuelinks"])
            )
            df["clones"].append(clones)
            df["clone_types"].append(clone_types)
            df["n_clones"].append(n_clones)
            df["clones_of_clones"].append(clones_of_clones)
            df["clone_types_of_clones"].append(clone_types_of_clones)
        else:
            df["clones"].append("")
            df["clone_types"].append("")
            df["n_clones"].append(0)
            df["clones_of_clones"].append("")
            df["clone_types_of_clones"].append("")

        try:
            df["cloned_by"].append(
                issue["fields"]["issuelinks"][0]["inwardIssue"]["key"]
            )
        except Exception:
            df["cloned_by"].append("")

        try:
            df["zentrale"].append(
                "ID_" + str(issue["fields"]["customfield_10673"][0]["objectId"])
            )
        except Exception:
            df["zentrale"].append("")
        try:
            df["filiale"].append(
                "ID_" + str(issue["fields"]["customfield_10674"][0]["objectId"])
            )
        except Exception:
            df["filiale"].append("")

        try:
            df["Link"].append(issue["fields"]["customfield_10010"]["_links"]["agent"])
        except Exception:
            df["Link"].append("")
    df = pd.DataFrame(df)
    DT_COLS = ["created", "updated", "currentstatus_date"]
    for c in DT_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_convert(TZ)
    df = enrich_jira_time_metrics(df)

    df["Hauptkategorie"] = df["main_category_id"].map(object_id_to_name)
    df["Unterkategorie"] = df["sub_category_id"].map(object_id_to_name).fillna("NA")

    df["zentrale"] = df["zentrale"].astype(str)
    df["filiale"] = df["filiale"].astype(str)
    df["firma"] = "Amparex"
    df["clone_in_project"] = df["clones"].apply(
        lambda x: ",".join([y.split("-")[0] for y in x.split(",")]) if x else "-"
    )
    df["has_exax_clone"] = df["clone_in_project"].str.contains("EXAX")
    df["has_axt_clone_clone"] = df["clones_of_clones"].str.contains("AX")
    df = df[["firma", *[col for col in df.columns if col != "firma"]]]

    return df
