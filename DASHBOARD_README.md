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

## Data backends

CSV remains the default backend. To use Supabase after applying the database schema and importing data, set these environment variables before starting the dashboard:

```powershell
$env:DATA_BACKEND = 'supabase'
$env:SUPABASE_URL = 'https://your-project.supabase.co'
$env:SUPABASE_SECRET_KEY = 'sb_secret_replace_me'
python .\dashboard.py
```

Keep `SUPABASE_SECRET_KEY` in the Python server environment only. Never add it to `dashboard.html`, commit it to Git, or share it with browser clients. Optional `SUPABASE_HISTORY_BATCH_ID` and `SUPABASE_CURRENT_BATCH_ID` select the initial-import batches; they default to the batch IDs created by the CSV import plan.

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
