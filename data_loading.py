import os
import pickle  # nosec B403

DATA_PATH = "data/jira_data.pkl"


def save_data(df):
    with open(DATA_PATH, "wb") as f:
        pickle.dump(df, f)


def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "rb") as f:
            # bandit B301: DATA_PATH is written by save_data() on this machine,
            # so it is not untrusted input. If the cache ever becomes something
            # a third party can supply, switch to a non-executable format
            # (e.g. parquet) instead of suppressing this.
            return pickle.load(f)  # nosec B301
    return None
