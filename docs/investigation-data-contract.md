# Usage Spike Investigation: data contract v1.0

This contract supports an explainable, deterministic investigation workflow.
It does not determine a root cause, notify a customer, or make an autonomous
operational decision. Every case must remain reviewable by an associate.

## Current source mapping

| Contract field | Current source field | Availability |
| --- | --- | --- |
| `customer_id` | `cust-id` | Available |
| `meter_id` | `meter-num` | Available |
| `trigger_read_at` | `current-meter-read-timestamp` | Available |
| `trigger_usage` | `usage-index` | Available |
| `baseline_mean` | `baseline-mean` | Available when analysis has sufficient history |
| `spike_threshold` | `spike-threshold` | Available when analysis has sufficient history |
| spike decision | `spike-flag` and `flag-reason` | Available |
| budget indicator | `budget indicator` | Available when source provides it |
| current-feed gap | derived from current-read timestamps | Available |
| premise ID | — | Not yet available |
| actual/estimated read type | — | Not yet available |
| meter replacement/event history | — | Not yet available |
| billing adjustment/history | — | Not yet available |
| weather-zone and weather history | — | Not yet available |

## Case lifecycle

```text
spike_detected
  -> validate_input
  -> data_unavailable     (required fields missing)
  -> compare_historical_baseline
  -> evaluate_read_continuity
  -> review_required
  -> associate action     (future phase)
  -> resolved | inconclusive
```

The state choice is deterministic: the same source run and rule version yield
the same case key, evidence, severity, and initial state.

## Data governance requirements before wider rollout

- Use canonical customer, meter, and future premise IDs with effective dates.
- Keep PII out of evidence payloads whenever an identifier is sufficient.
- Preserve the source-run ID, rule version, values, and timestamp for each
  decision so a case can be reproduced.
- Configure Supabase Row Level Security before exposing case data to associates.
- Keep the Supabase secret/service key only in Python or other server-side
  execution; never place it in the React build.
