# Meter usage dashboard

## Start it

Open PowerShell in this folder and run:

```powershell
python .\dashboard.py
```

Then open <http://127.0.0.1:8000>. Press `Ctrl+C` in PowerShell to stop the local server.

The server binds to `127.0.0.1` by default, so the dashboard is available only on this computer. It reads these files from this folder:

- `meter_usage_5cust_3years (1).csv` — historical meter readings
- `simulated_current_meter_usage.csv` — current-read input (currently simulated)
- `usage_spike_results.csv` — output from the spike analysis script

When current readings change, run the analyzer and refresh the dashboard:

```powershell
python .\usage_spike_prototype.py --history '.\meter_usage_5cust_3years (1).csv' --current '.\simulated_current_meter_usage.csv' --output '.\usage_spike_results.csv'
```

## Dashboard contents

- Daily mean `usage-index` trend for each customer, with 90-day, 12-month, and all-history ranges. Click the graph to open daily totals; click a date point to expand that date into its recorded four-hour readings.
- Current usage-index values alongside each read's historical threshold.
- A table showing the current reading, baseline, threshold, and spike result.
- A monthly spike-percentage chart. Its percentage is `(usage-index - spike threshold) / spike threshold * 100`; click a month to list spikes in that month, or a y-axis percentage band to list spikes in that band.
- A missing-read widget that lists customer-months with no incoming readings between the first and last months in the current feed. The demo feed intentionally omits CUST0005 for February and March 2026.
- Clickable customer IDs throughout the dashboard. Selecting one opens that customer's full history; select a date point to expand it into individual four-hour readings.
- A local data assistant for questions about customer history, current reads, high readings, flags, and recent 30-day trends.

The assistant uses data-grounded question patterns and calculations in the local dashboard. It does not call a hosted language model, so it does not provide open-ended generative answers. The current-read flag is taken from `usage_spike_results.csv`; rerun the analyzer after updating current reads.

## Deterministic usage-spike investigations

The investigation foundation turns already-flagged reads into explainable,
associate-reviewable cases. It uses only the existing spike output, current
read continuity, and budget indicator; it does not use an LLM, contact a
customer, or claim a root cause.

Preview cases without writing anything:

```powershell
python .\investigate_usage_spikes.py --json
```

The same non-mutating payload is available from `/api/investigations`. Apply
[`db/002_investigation_foundation.sql`](db/002_investigation_foundation.sql)
after the initial schema, then persist cases only from the trusted server-side
job:

```powershell
$env:DATA_BACKEND = 'supabase'
python .\investigate_usage_spikes.py --apply
```

The job is idempotent: the same customer, meter, and trigger timestamp map to
the same case key. See [the investigation data contract](docs/investigation-data-contract.md)
for the current source mapping, lifecycle, and data required for later
meter-event, billing, weather, and premise checks.

## Latest four-hour reading intake

The React header includes a **Submit latest reading** action for authorized
operator use. It validates the known customer-to-meter mapping, non-negative
numeric readings, UTC four-hour slot alignment, and duplicates before any
write. Form submissions are disabled by default so an unauthenticated
deployment cannot become a public data-write surface.

Apply [`db/003_input_feed_ingestion.sql`](db/003_input_feed_ingestion.sql) in
Supabase after the earlier migrations. For local testing, enable the guarded
workflow in the PowerShell session:

```powershell
$env:ENABLE_FEED_SUBMISSIONS = 'true'
```

With `DATA_BACKEND=csv`, a form submission is validation-only and never edits
the CSV source files. With `DATA_BACKEND=supabase`, it uses the separate
`SUPABASE_INPUT_FEED_BATCH_ID` (`input-feed-screening` by default): a `TRUE`
candidate is written only to `meter_reads_temp`, while a within-range or
insufficient-history reading is written only to `input_feed_submissions` as an
audit entry. The form never writes to `meter_reads`. Before allowing real
customers to use this form, add application authentication and enforce
associate/customer roles with Supabase Row Level Security; the current dashboard
does not implement identity management.

### Input-feed spike queue

Apply [`db/004_input_feed_spike_queue.sql`](db/004_input_feed_spike_queue.sql)
and then [`db/005_input_feed_audit_without_meter_read.sql`](db/005_input_feed_audit_without_meter_read.sql)
after migrations 001 through 003. The intake service compares the new reading
to the same customer, meter, and four-hour slot in the preceding 90 days. It
needs at least 30 comparable readings and flags only usage above `mean + 3 ×
standard deviations`.

Only a `TRUE` spike candidate enters `meter_reads_temp` with
`spike_indicator = TRUE`. The input-feed workflow never writes to
`meter_reads`. Within-range and insufficient-history readings are stored only
in `input_feed_submissions` as screening audit records. The **Input-feed spike
candidates** dashboard card reads the review queue. A candidate needs associate
investigation—it is not a customer notification or a confirmed root cause.

### Automated deterministic investigations and tickets

Apply [`db/009_automated_investigation_tickets.sql`](db/009_automated_investigation_tickets.sql)
after migrations 001 through 008. A new input-feed spike then triggers a
server-side investigation immediately after it is saved to `meter_reads_temp`.
The engine creates a case, retains every evidence check, assigns a team, and
creates an open ticket in `investigation_tickets`. The generated evidence is
retained separately from associate-owned routing, remediation, notes, and
comments.

#### Associate ticket workspace

Apply [`db/011_ticket_workspace.sql`](db/011_ticket_workspace.sql) after
migration 010. It adds a system-generated detailed report plus a durable
associate comment trail. The ticket workspace lets an associate update the
status, assigned team, title, possible cause, recommended solution, and an
associate assessment. It does not allow the retained deterministic evidence to
be edited. Re-running the investigation backfills a missing system report but
does not overwrite associate ticket updates.

The engine uses the same-slot historical threshold, submitted meter status,
actual-versus-estimated read type, and any approved meter-event and billing
records. Weather is retrieved for the interval from the meter's latest
historical read through the incoming reading after a premise has valid
coordinates and the server is explicitly enabled:

```powershell
$env:ENABLE_WEATHER_INVESTIGATION = 'true'
```

Weather calls use the configured server-side adapter and snapshots are retained
in `weather_snapshots`. Until an approved premise location or source record is
available, the report explicitly says `Needs data`; it never invents an
explanation.

#### Internal service-premise integration

Apply [`db/010_internal_premise_resolution.sql`](db/010_internal_premise_resolution.sql)
after migration 009 to retain verified coordinates and audit metadata. MeterIQ
does **not** copy or store a service address. When enabled, it requests the
authoritative internal source at:

```text
GET {PREMISE_SOURCE_BASE_URL}/customers/{customer_id}/service-premise
```

The source must return either the object below or wrap it in
`servicePremise`. `recordId`, `postalCode`, and `countryCode` are required;
the raw address is used only in the source system and is not part of this
contract.

```json
{
  "recordId": "authoritative-premise-id",
  "postalCode": "12345",
  "city": "Example City",
  "region": "OH",
  "countryCode": "US",
  "updatedAt": "2026-10-22T10:00:00Z"
}
```

Configure it only in the server process:

```powershell
$env:ENABLE_PREMISE_SOURCE_RESOLUTION = 'true'
$env:PREMISE_SOURCE_BASE_URL = 'https://your-internal-service/api'
$env:PREMISE_SOURCE_API_KEY = 'server-only-secret'
$env:PREMISE_SOURCE_NAME = 'customer-service-premise'
$env:ENABLE_WEATHER_INVESTIGATION = 'true'
```

The resolver uses country-filtered postcode geocoding. It stores the selected
coordinates only when one exact postcode match is returned; otherwise it saves
`needs_review` and weather remains unavailable rather than selecting an
ambiguous location.

To create cases and tickets for candidates that were already in the protected
queue before migration 009, run the idempotent recovery once:

```powershell
python .\investigate_usage_spikes.py --input-feed --apply
```

Apply [`db/008_protect_input_feed_operational_reads.sql`](db/008_protect_input_feed_operational_reads.sql)
to add a database-level guardrail. It rejects any attempt to write a form-intake
batch into `meter_reads`, including an accidental write from an outdated server.

### Reset the legacy demonstration spike data

To start the intake workflow with no legacy current-feed spikes, run
[`db/006_reset_legacy_spike_demo_data.sql`](db/006_reset_legacy_spike_demo_data.sql)
after migrations 001 through 005. This is a one-time destructive operation. It
preserves the historical baseline batch (`history-csv-initial`) but removes the
simulated current batch, its analysis output, investigation artifacts, intake
audit records, and the `meter_reads_temp` spike-review queue.

## Data backends

CSV remains the default backend. To use Supabase after applying the database schema and importing data, set these environment variables before starting the dashboard:

```powershell
$env:DATA_BACKEND = 'supabase'
$env:SUPABASE_URL = 'https://your-project.supabase.co'
$env:SUPABASE_SECRET_KEY = 'sb_secret_replace_me'
python .\dashboard.py
```

Keep `SUPABASE_SECRET_KEY` in the Python server environment only. Never add it to `dashboard.html`, commit it to Git, or share it with browser clients. Optional `SUPABASE_HISTORY_BATCH_ID` and `SUPABASE_CURRENT_BATCH_ID` select the initial-import batches. `SUPABASE_INPUT_FEED_BATCH_ID` is separate and defaults to `input-feed-screening` so form intake cannot be confused with the operational feed.

## First Supabase import

1. In the Supabase SQL Editor, run [`db/001_initial_schema.sql`](db/001_initial_schema.sql). This creates the tables used by the importer and dashboard.
2. Set the project URL and server-only secret key in the current PowerShell session:

```powershell
$env:SUPABASE_URL = 'https://your-project.supabase.co'
$env:SUPABASE_SECRET_KEY = 'sb_secret_replace_me'
```

3. Validate the complete import without contacting Supabase. This is the default and safe to repeat:

```powershell
python .\supabase_import.py --json
```

4. When the dry-run counts are correct, perform the idempotent upsert import. The command uploads parent tables before dependent records, so the foreign keys remain valid:

```powershell
python .\supabase_import.py --apply
```

5. Confirm Supabase contains the same source keys, spike flags, and thresholds as the CSV files:

```powershell
python .\verify_supabase_import.py
```

On success, select Supabase for the dashboard and pin it to the imported analysis run:

```powershell
$env:DATA_BACKEND = 'supabase'
$env:SUPABASE_ANALYSIS_RUN_ID = 'csv-analysis-initial'
python .\dashboard.py
```

The startup line must say `Data backend: supabase`. The dashboard API also returns
the header `X-Data-Backend: supabase`; this is useful for confirming the active
source without exposing credentials to the browser.

To return to the original CSV mode in the same PowerShell session, stop the
dashboard with `Ctrl+C`, then run:

```powershell
$env:DATA_BACKEND = 'csv'
python .\dashboard.py
```

`supabase_import.py` never writes data unless `--apply` is specified. It uses stable read IDs and Supabase upserts, so rerunning it with the same CSV inputs is safe. For a later analysis run, choose a new `--run-id` and set `SUPABASE_ANALYSIS_RUN_ID` to that value before starting the dashboard.

## Deploy on Vercel

Deploy this repository as one Vercel project from the **repository root**.
`vercel.json` builds the React app from `frontend/`, serves `frontend/dist` at
the site root, and keeps the Python serverless functions under `api/`. Do not
set the Vercel Root Directory to `frontend`, because the API functions must
remain available from the repository root. Local development remains unchanged:
use `python .\dashboard.py` and `npm run dev` from `frontend`.

Before the first deployment, apply Supabase migrations through
[`db/011_ticket_workspace.sql`](db/011_ticket_workspace.sql). The deployment
exposes dashboard, history, investigation, input-feed, and ticket-update API
routes. The ticket update route is same-origin only: `/api/tickets/{ticketId}`.

In the Vercel project settings, add these environment variables for **Production**
and **Preview** before deploying:

```text
DATA_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=sb_secret_replace_me
SUPABASE_HISTORY_BATCH_ID=history-csv-initial
SUPABASE_CURRENT_BATCH_ID=current-csv-initial
SUPABASE_INPUT_FEED_BATCH_ID=input-feed-screening
SUPABASE_ANALYSIS_RUN_ID=csv-analysis-initial
ENABLE_FEED_SUBMISSIONS=true
ENABLE_WEATHER_INVESTIGATION=true
```

Mark `SUPABASE_SECRET_KEY` as sensitive. It is used only by the Python functions;
it is never sent to the React browser bundle or committed to Git. Do not give it
a `VITE_` prefix. After deployment, open the site and confirm the status badge
says **Supabase data loaded**. The dashboard currently exposes the loaded
operational data to anyone who can open the site, so enable Vercel Deployment
Protection or add application authentication before sharing a client-facing URL.
