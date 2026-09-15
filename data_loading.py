import os
import pickle  # nosec B403
import tempfile
from pathlib import Path

DATA_PATH = "data/jira_data.pkl"

# Written by earlier versions of the loader and the category migration. They are
# constant (cloud/workspace ids) or diagnostics that belong in the refresh log,
# not per ticket, so they are dropped on the way in and out of the cache.
OBSOLETE_COLUMNS = (
    "assets_cloud_id",
    "assets_workspace_id",
    "asset_errors",
    "category_assets_cloud_id",
    "category_assets_workspace_id",
    "category_asset_errors",
)


def drop_obsolete_columns(df):
    """Return df without the obsolete asset bookkeeping columns."""
    if df is None:
        return df
    present = [column for column in OBSOLETE_COLUMNS if column in df.columns]
    return df.drop(columns=present) if present else df


def save_data(df):
    df = drop_obsolete_columns(df)
    path = Path(DATA_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = f.name
            pickle.dump(df, f)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "rb") as f:
            # bandit B301: DATA_PATH is written by save_data() on this machine,
            # so it is not untrusted input. If the cache ever becomes something
            # a third party can supply, switch to a non-executable format
            # (e.g. parquet) instead of suppressing this.
            return drop_obsolete_columns(pickle.load(f))  # nosec B301
    return None
