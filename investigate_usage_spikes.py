#!/usr/bin/env python3
"""Create deterministic usage-spike investigation cases from dashboard data.

The command is preview-only by default.  ``--apply`` requires the existing
server-only Supabase configuration and persists cases idempotently.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app_config import AppConfig
from investigation_context import SupabaseInvestigationContext
from investigation_engine import generate_investigations, investigation_payload
from investigation_store import InvestigationStoreError, SupabaseInvestigationStore
from repository_factory import create_repository


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist cases to configured Supabase.")
    parser.add_argument("--input-feed", action="store_true", help="Investigate protected input-feed spike candidates and auto-create tickets.")
    parser.add_argument("--json", action="store_true", help="Print the generated case payload as JSON.")
    args = parser.parse_args()

    try:
        config = AppConfig.from_environment(root)
        from dashboard import build_data

        repository = create_repository(config)
        data = build_data(repository)
        source_run_id = config.analysis_run_id or "csv-analysis-unversioned"
        if args.input_feed:
            if config.data_backend != "supabase":
                raise ValueError("--input-feed requires DATA_BACKEND=supabase.")
            source_run_id = "input-feed-auto-backfill"
            context_reader = SupabaseInvestigationContext(
                config.supabase_url or "", config.supabase_secret_key or "",
                weather_enabled=config.weather_investigation_enabled,
                premise_source_enabled=config.premise_source_enabled,
                premise_source_base_url=config.premise_source_base_url,
                premise_source_api_key=config.premise_source_api_key,
                premise_source_name=config.premise_source_name,
            )
            cases = []
            for candidate in data["inputFeedSpikeCandidates"]:
                context = context_reader.for_read(
                    str(candidate["cust-id"]), str(candidate["meter-num"]),
                    str(candidate["current-meter-read-timestamp"]),
                    repository.latest_historical_read_at(
                        str(candidate["meter-num"]),
                        str(candidate["current-meter-read-timestamp"]),
                    ),
                )
                cases.extend(generate_investigations([{**candidate, **context}], [], source_run_id))
        else:
            cases = generate_investigations(data["current"], data["missingReadGaps"], source_run_id)
        payload = investigation_payload(cases)
        payload["persistence"] = "preview"
        if args.apply:
            if config.data_backend != "supabase":
                raise ValueError("--apply requires DATA_BACKEND=supabase; CSV mode is preview-only.")
            store = SupabaseInvestigationStore(config.supabase_url or "", config.supabase_secret_key or "")
            store.save(cases, source_run_id, create_tickets=args.input_feed)
            payload["persistence"] = "supabase"
    except (OSError, ValueError, RuntimeError, InvestigationStoreError) as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Generated {payload['caseCount']} investigation case(s) ({payload['persistence']}).")
        for case in payload["cases"]:
            print(f"- {case['case_id']} | {case['severity']} | {case['state']} | {case['customer_id']}")


if __name__ == "__main__":
    main()
