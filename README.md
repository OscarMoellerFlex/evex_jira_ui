# Jira Analytics Dashboard

Streamlit analytics for the service desks on `amparex.atlassian.net`:

| Company | Project | Jira project ID        | Service desk ID        |
| ------- | ------- | ---------------------- | ---------------------- |
| Ipro    | SDIPR   | Existing configuration | Existing configuration |
| Amparex | SDAX    | Existing configuration | Existing configuration |
| Euronet | SDEU    | 12521                  | 219                    |

The company multiselect starts with all three companies selected. Choose any
combination to filter the analysis. Selecting none shows a prompt instead of charts.
The refresh button always fetches all three desks for the selected creation-date
window; it reports each desk separately and retains cached tickets if a desk fails.

## Run locally

Use Python 3.12 or newer and the pinned runtime dependencies:

```sh
uv venv
uv pip install -r requirements.runtime.txt
uv run --no-sync streamlit run app.py
```

Provide `JIRA_URL=https://amparex.atlassian.net`, `JIRA_USERNAME`, and
`JIRA_PASSWORD` (the account's API token) through the environment or an untracked
`.env` file. Cached analysis does not require a live Jira connection. The existing
code loads `.env` with override enabled. Never commit credentials or ticket caches.

## Euronet import

Euronet uses the existing Amparex custom-field IDs and `Fertig` completion logic.
It has no configured escalation targets. Generic issue links remain visible.
Reporting retains Berlin time, weekdays 08:00–18:00, and German federal holidays.
The current Erstlösequote view classifies same-calendar-day resolution.

The earliest allowed Euronet creation date is **1 September 2026, 00:00 Berlin**.
This applies to dashboard refresh, backfill, and resumed checkpoints. The cutoff
is enforced after Jira search as well as in the query, regardless of the API
account's timezone. Earlier tickets are excluded even when requesting 365 days.

```sh
# Initial Euronet import; ends at the time the command runs
uv run --no-sync python backfill_jira.py --project SDEU --start 2026-09-01

# All three desks; existing desks use 365 days, Euronet is clamped to its cutoff
uv run --no-sync python backfill_jira.py

# Any project combination and a shorter period
uv run --no-sync python backfill_jira.py --project SDAX --project SDEU --days 7

# Reuse a matching checkpoint and fetch the remaining time interval
uv run --no-sync python backfill_jira.py --project SDEU --start 2026-09-01 --resume
```

`--start` and `--days` are mutually exclusive. Checkpoints are per project and
record the effective window and Assets provenance. Old date-only checkpoints are
refetched; matching modern checkpoints are filtered, re-enriched if necessary,
and extended through the current import time. A valid zero-ticket result succeeds
without changing the cache. Partial project failures return a nonzero exit status
while successful project results are merged.

## Normal Assets workspace

All active enrichment and country-export calls use the normal workspace configured
in `jira_loader.py`:

- Cloud: `242cf880-c51a-4277-9381-781d5ae181df`
- Workspace: `9926cb30-3f07-4fb2-9c83-aa4fc551c721`

Asset references must match this workspace. Inaccessible or mismatched objects
produce explicit errors and `Unbekannt` category labels; there is no sandbox
fallback. Fresh imports resolve category labels directly from normal Assets and
retain `assets_cloud_id`, `assets_workspace_id`, and `asset_errors` in raw data.
The static category map is only a compatibility fallback for unenriched legacy
inputs, not for any normal-workspace fetch.

To refresh category labels already stored in the local cache:

```sh
uv run --no-sync python asset_migration.py
```

This resolves the distinct category IDs originally copied from production issue
fields. It preserves ticket rows, customer/branch IDs, non-Assets fields, and date
coverage. It writes `category_assets_cloud_id`, `category_assets_workspace_id`,
and `category_asset_errors`. Customer/branch columns in the legacy dataframe are
raw reference IDs, so they require no label migration. The command creates a
`data/jira_data.pkl.bak-assets-*` backup and refuses to overwrite a cache that
changed during its API reads. Correct Assets permissions and rerun to recover
labels previously marked unknown.

## Storage and validation

The dashboard reads `data/jira_data.pkl`. Backfills use key-based upserts with
backups; saves use atomic file replacement. Avoid refreshing the dashboard while
a CLI import or cache migration is writing. To roll back a migration, stop writers
and restore its backup to `data/jira_data.pkl`.

A fully successful dashboard refresh writes all desks' fetched raw results once
to `data/jira_issues.json`. A project failure preserves the previous raw snapshot.
This JSON represents the fetched window, not the full historical pickle cache.

```sh
uv run --no-sync python -m unittest discover -s tests
```

Tests cover company subsets and Streamlit rendering, import timezone boundaries,
checkpoint reuse, partial failures, Assets routing, legacy transformation fixtures,
Euronet escalation flags, upsert behavior, and failed cache writes. They use
synthetic records and replace external API calls; no live account is required.

See [the implementation plan](docs/euronet-service-desk-plan.md) and
[validation results](docs/euronet-validation.md) for the rollout record.
