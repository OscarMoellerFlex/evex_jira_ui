import os
import pickle  # nosec B403
import tempfile
from pathlib import Path

DATA_PATH = "data/jira_data.pkl"


def save_data(df):
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
            return pickle.load(f)  # nosec B301
    return None
