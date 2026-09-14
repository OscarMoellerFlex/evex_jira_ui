"""One-off backfill: add a 'Land' column to the stored dashboard DataFrame.

The asset object ids are already in data/jira_data.pkl, so the country is
resolved without re-pulling anything from Jira. Only the asset -> Land mapping
is fetched, and only for ids the cache does not already know.

Usage:
  uv run python backfill_country.py --dry-run
  uv run python backfill_country.py
"""

import argparse
import shutil
from datetime import datetime

import pandas as pd

from asset_country import (
    CACHE_PATH,
    ESCALATION_COLUMNS,
    NO_ASSETS_LINKED,
    NO_COUNTRY_ON_ASSET,
    attach_country,
    load_cache,
    resolve_missing,
    save_cache,
)

DEFAULT_INPUT = "data/jira_data.pkl"


def collect_object_ids(df):
    """Every asset cell from the escalation columns present in the frame."""
    values = []
    for column in ESCALATION_COLUMNS:
        if column in df.columns:
            values.extend(df[column].tolist())
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=None, help="defaults to --input")
    parser.add_argument("--cache", default=CACHE_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output = args.output or args.input

    # Deserializing our own locally-generated pickle, not untrusted input.
    df = pd.read_pickle(args.input)  # nosec B301
    print(f"Loaded {len(df)} tickets from {args.input}")

    absent = [c for c in ESCALATION_COLUMNS if c not in df.columns]
    if absent:
        print(
            f"  ! columns absent, skipped: {', '.join(absent)} - tickets whose only "
            "asset is one of these cannot be told apart from tickets with no asset."
        )

    cache = load_cache(args.cache)
    print(f"Cache holds {len(cache)} assets")

    cache, resolved, failed = resolve_missing(collect_object_ids(df), cache)
    print(f"Newly resolved: {resolved}    failed lookups: {failed}")
    if failed:
        print("  ! failed lookups are NOT cached; rerun to retry them")

    df = attach_country(df, cache)

    counts = df["Land"].value_counts()
    buckets = int(counts.get(NO_COUNTRY_ON_ASSET, 0)) + int(
        counts.get(NO_ASSETS_LINKED, 0)
    )
    print(f"  countries resolved  : {len(df) - buckets}")
    print(f"  {NO_COUNTRY_ON_ASSET} : {int(counts.get(NO_COUNTRY_ON_ASSET, 0))}")
    print(f"  {NO_ASSETS_LINKED}  : {int(counts.get(NO_ASSETS_LINKED, 0))}")

    if args.dry_run:
        print("Dry run - nothing written.")
        return

    save_cache(cache, args.cache)
    if output == args.input:
        backup = f"{args.input}.bak-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(args.input, backup)
        print(f"Backup written to {backup}")
    df.to_pickle(output)
    print(f"Wrote {len(df)} tickets to {output}")


if __name__ == "__main__":
    main()
