#!/usr/bin/env python
"""Backfill ``data/jira_data.pkl`` with a full range of SDIPR + SDAX issues.

Why this exists instead of the sidebar button: the Streamlit refresh runs the
fetch inline in a script run, so any browser interaction or reconnect reruns
the script and kills the fetch mid-flight. A year of issues takes long enough
that this is close to guaranteed. Run this from a terminal instead.

    uv run python backfill_jira.py                  # past year, both projects
    uv run python backfill_jira.py --days 60        # shorter window
    uv run python backfill_jira.py --resume         # reuse existing checkpoints
    uv run python backfill_jira.py --project SDIPR  # one project only

Each project's raw issues are checkpointed to ``data/backfill_<PROJECT>.json``
as soon as its fetch finishes, so a crash during the second project does not
throw away the first one's hours of work. ``--resume`` picks those back up.

The existing pickle is copied to ``data/jira_data.pkl.bak-<timestamp>`` before
anything is written, and the merge is an upsert: existing rows are updated in
place and unseen rows appended, so nothing already collected is lost.
"""

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from data_loading import DATA_PATH, load_data, save_data
from data_transformation import load_issues, load_issues_Amparex, upsert_jira_data
from jira_loader import fetch_jira_issues

# SDIPR rows go through load_issues; SDAX through the Amparex variant.
PROJECT_LOADERS = {"SDIPR": load_issues, "SDAX": load_issues_Amparex}

CHECKPOINT_TMPL = "data/backfill_{project}.json"


def _fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def _make_progress(project, started):
    """Print a one-line progress update per fetched page."""
    state = {"last": 0.0}

    def report(count):
        now = time.time()
        # Throttle to at most one line every 5s so long runs stay readable.
        if now - state["last"] < 5:
            return
        state["last"] = now
        elapsed = now - started
        rate = count / elapsed if elapsed else 0
        print(
            f"  [{project}] {count:>6} issues | {_fmt_duration(elapsed)} elapsed "
            f"| {rate:.1f} issues/s",
            flush=True,
        )

    return report


def fetch_project(project, start_dt, end_dt, resume):
    """Fetch one project's issues, using/creating a raw checkpoint file."""
    checkpoint = CHECKPOINT_TMPL.format(project=project)

    if resume and os.path.exists(checkpoint):
        with open(checkpoint) as f:
            saved = json.load(f)
        issues = saved["issues"]
        # A checkpoint from a different window is the one way --resume can
        # silently hand back the wrong data after an hours-long run, so say
        # what the file actually covers and refuse if it does not match.
        # Compared by date, not timestamp: end_dt is now(), so an exact match
        # would never hold and --resume would always refuse. Same-day resume
        # (the crash-and-rerun case) matches; a different window does not.
        same_range = (
            saved.get("start") == start_dt.date().isoformat()
            and saved.get("end") == end_dt.date().isoformat()
        )
        print(
            f"[{project}] checkpoint {checkpoint} holds {len(issues)} issues "
            f"for {saved.get('start', '?')} -> {saved.get('end', '?')}",
            flush=True,
        )
        if not same_range:
            raise SystemExit(
                f"[{project}] refusing to resume: checkpoint covers a different "
                f"window than the requested {start_dt.date()} -> {end_dt.date()}. "
                f"Delete {checkpoint} to refetch, or rerun with matching --days."
            )
        return issues

    print(f"[{project}] fetching {start_dt.date()} -> {end_dt.date()} ...", flush=True)
    started = time.time()
    issues = fetch_jira_issues(
        start_dt,
        end_dt,
        max_issues=1_000_000,
        project=project,
        # The app's default dumps every issue with indent=4, which ran to
        # multiple GB per call. Checkpoint compactly below instead.
        save_path=None,
        progress_cb=_make_progress(project, started),
    )
    print(
        f"[{project}] done: {len(issues)} issues in {_fmt_duration(time.time()-started)}",
        flush=True,
    )

    with open(checkpoint, "w") as f:
        json.dump(
            {
                "start": start_dt.date().isoformat(),
                "end": end_dt.date().isoformat(),
                "issues": issues,
            },
            f,
        )
    print(f"[{project}] checkpointed -> {checkpoint}", flush=True)
    return issues


def merge_into_pickle(frames):
    """Upsert freshly-loaded frames into the existing pickle, with a backup."""
    df_old = load_data()
    if df_old is None:
        df_old = pd.DataFrame()

    df_combined = pd.concat(frames, ignore_index=True)

    # Mirror app.py: align the two column sets before upserting so neither
    # side drops columns the other introduced.
    if not df_old.empty:
        columns_new = set(df_combined.columns)
        columns_old = set(df_old.columns)
        for column in columns_new - columns_old:
            df_old[column] = ""
        for column in columns_old - columns_new:
            df_combined[column] = ""
        df = upsert_jira_data(df_old, df_combined)
    else:
        df = df_combined

    if "clone_in_project" not in df.columns:
        df["clone_in_project"] = "-"

    if os.path.exists(DATA_PATH):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{DATA_PATH}.bak-{stamp}"
        shutil.copy2(DATA_PATH, backup)
        print(f"backed up existing pickle -> {backup}", flush=True)

    save_data(df)
    return df_old, df


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=365, help="how far back to fetch")
    ap.add_argument(
        "--project",
        action="append",
        choices=sorted(PROJECT_LOADERS),
        help="limit to one project (repeatable); default is both",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="reuse data/backfill_<PROJECT>.json instead of refetching",
    )
    args = ap.parse_args()

    projects = args.project or sorted(PROJECT_LOADERS)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)

    print(
        f"Backfilling {', '.join(projects)} over the last {args.days} days "
        f"({start_dt.date()} -> {end_dt.date()})",
        flush=True,
    )

    overall = time.time()
    frames = []
    for project in projects:
        issues = fetch_project(project, start_dt, end_dt, args.resume)
        if not issues:
            print(f"[{project}] no issues returned; skipping", flush=True)
            continue
        frames.append(PROJECT_LOADERS[project](issues))

    if not frames:
        print("Nothing fetched — pickle left untouched.")
        return 1

    df_old, df = merge_into_pickle(frames)

    print(f"\nMerged: {len(df_old)} existing -> {len(df)} rows in {DATA_PATH}")
    if "created" in df.columns:
        created = pd.to_datetime(df["created"], errors="coerce", utc=True)
        print(f"created range: {created.min()} -> {created.max()}")
    print(f"total time: {_fmt_duration(time.time()-overall)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
