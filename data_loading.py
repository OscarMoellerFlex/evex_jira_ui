import os
import pickle

DATA_PATH = "data/jira_data.pkl"


def save_data(df):
    with open(DATA_PATH, "wb") as f:
        pickle.dump(df, f)


def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "rb") as f:
            return pickle.load(f)
    return None
