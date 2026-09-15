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
Reporting retains Berlin time and weekdays 08:00–18:00. Holidays are the German
public holidays for **Baden-Württemberg** (`subdiv="BW"`), set once in
`_load_service_desk_issues` and therefore shared by every desk, Euronet included.
Beyond the federal holidays this adds Heilige Drei Könige, Fronleichnam and
Allerheiligen; measured against the stored data it shifts business hours for
about 2% of tickets and moves 12 across a reporting band.
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

## Country resolution (Länder tab)

A ticket's country escalates Ansprechpartner → Filiale → Zentrale; the first
asset carrying a `Land` attribute wins. Only asset references from the normal
workspace are used — an objectId from another workspace is discarded rather
than resolved, because the country cache is keyed by objectId alone and a
foreign id would otherwise borrow an unrelated site's country.

The cache lives in `data/asset_country.json` as `{object_id: country_or_null}`.
A dashboard refresh fills `Land` from that cache without calling the Assets
API, so refreshed tickets are charted immediately. Assets the cache has never
seen become **`Land noch nicht ermittelt`** — distinct from `Kein Land am
Asset`, which means the asset was fetched and genuinely carries no country.
The Länder tab reports how many tickets are in that state.

```sh
# Resolve every asset the cache does not know yet, then write Land back
uv run --no-sync python backfill_country.py --dry-run
uv run --no-sync python backfill_country.py

# Re-resolve ids cached as null by older versions, which stored a failed
# lookup the same way as "this asset has no Land" and never retried it
uv run --no-sync python backfill_country.py --retry-unknown
```

Writing over the input takes a `data/jira_data.pkl.bak-*` backup first.

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
