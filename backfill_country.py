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
from resolution_bands import classify_bands

DEFAULT_INPUT = "data/jira_data.pkl"

# The two inputs classify_bands needs. Both already live in the stored pickle
# for tickets processed by a prior Jira refresh; nothing here calls Jira.
HOURS_COLUMN = "time_to_resolution_biz_hours"
DONE_COLUMN = "is_done"
BAND_COLUMN = "resolution_band"


def add_resolution_band(df):
    """Return a copy of df with 'resolution_band' added, if inputs allow it.

    classify_bands only needs HOURS_COLUMN and DONE_COLUMN, both of which are
    already stored in the pickle by a prior Jira refresh - no credentials, no
    Jira call, no Assets API. When either input is missing, the Länder tab
    simply keeps showing its data-missing hint until the next refresh, so we
    warn and continue rather than crash.
    """
    missing = [c for c in (HOURS_COLUMN, DONE_COLUMN) if c not in df.columns]
    if missing:
        print(
            f"  ! column(s) absent, resolution_band NOT computed: {', '.join(missing)} "
            "- the Länder tab will keep showing its data-missing hint until the "
            "next full Jira refresh."
        )
        return df

    out = df.copy()
    # app.py's upsert fills columns missing on either side with "" (see
    # app.py:147-152), so a slice of otherwise-numeric hours can hold empty
    # strings. Coerce to NaN rather than letting classify_bands see a str.
    hours = pd.to_numeric(out[HOURS_COLUMN], errors="coerce")
    out[BAND_COLUMN] = classify_bands(hours, out[DONE_COLUMN])
    return out


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
    df = add_resolution_band(df)

    counts = df["Land"].value_counts()
    buckets = int(counts.get(NO_COUNTRY_ON_ASSET, 0)) + int(
        counts.get(NO_ASSETS_LINKED, 0)
    )
    print(f"  countries resolved  : {len(df) - buckets}")
    print(f"  {NO_COUNTRY_ON_ASSET} : {int(counts.get(NO_COUNTRY_ON_ASSET, 0))}")
    print(f"  {NO_ASSETS_LINKED}  : {int(counts.get(NO_ASSETS_LINKED, 0))}")

    if BAND_COLUMN in df.columns:
        print(f"  {BAND_COLUMN} counts:")
        for band, count in df[BAND_COLUMN].value_counts().items():
            print(f"    {band} : {int(count)}")
        print(
            "  note: bands derive from the stored time_to_resolution_biz_hours, "
            "which reflects whatever holiday calendar was in force when it was "
            "computed; a Jira refresh recomputes it with subdiv='BW' "
            "(measured difference: 12 tickets)."
        )

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
