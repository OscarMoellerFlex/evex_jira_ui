"""Refresh registered desks independently while retaining failed desks' cached rows."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from service_desks import DESKS


@dataclass
class RefreshResult:
    frame: pd.DataFrame
    counts: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    asset_failures: dict = field(default_factory=dict)


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as handle:
            temporary = handle.name
            json.dump(value, handle)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def refresh_desks(
    old, start, end, *, fetch=None, transform=None, raw_path="data/jira_issues.json"
):
    from data_transformation import load_project_issues, upsert_jira_data

    if fetch is None:
        from jira_loader import fetch_jira_issues

        fetch = fetch_jira_issues
    transform = transform or load_project_issues
    result = RefreshResult(old.copy() if old is not None else pd.DataFrame())
    frames, raw = [], []
    for desk in DESKS:
        try:
            issues = fetch(
                start, end, max_issues=100000, project=desk.key, save_path=None
            )
            frame = transform(desk.key, issues) if issues else pd.DataFrame()
            if not frame.empty:
                frames.append(frame)
            raw.extend(issues)
            result.counts[desk.key] = len(issues)
            result.asset_failures[desk.key] = sum(
                bool(i.get("asset_errors")) for i in issues
            )
        except Exception as exc:  # noqa: BLE001 - report optional/isolated failures
            result.errors[desk.key] = str(exc)
    if frames:
        result.frame = upsert_jira_data(
            result.frame, pd.concat(frames, ignore_index=True)
        )
    if not result.errors and raw_path is not None:
        write_json_atomic(raw_path, raw)
    return result
