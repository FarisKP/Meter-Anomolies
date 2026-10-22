"""Runtime configuration for selecting the active meter-data backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppConfig:
    data_backend: str
    history_path: Path
    current_path: Path
    results_path: Path
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    history_batch_id: str = "history-csv-initial"
    current_batch_id: str = "current-csv-initial"
    input_feed_batch_id: str = "input-feed-screening"
    analysis_run_id: str | None = None
    feed_submissions_enabled: bool = False
    weather_investigation_enabled: bool = False
    premise_source_enabled: bool = False
    premise_source_base_url: str | None = None
    premise_source_api_key: str | None = None
    premise_source_name: str = "internal-service-premise"

    @classmethod
    def from_environment(
        cls, root: Path, environment: Mapping[str, str] | None = None
    ) -> "AppConfig":
        env = os.environ if environment is None else environment
        backend = env.get("DATA_BACKEND", "csv").lower()
        if backend not in {"csv", "supabase"}:
            raise ValueError("DATA_BACKEND must be either 'csv' or 'supabase'.")

        config = cls(
            data_backend=backend,
            history_path=root / "meter_usage_5cust_3years (1).csv",
            current_path=root / "simulated_current_meter_usage.csv",
            results_path=root / "usage_spike_results.csv",
            supabase_url=env.get("SUPABASE_URL"),
            supabase_secret_key=env.get("SUPABASE_SECRET_KEY"),
            history_batch_id=env.get("SUPABASE_HISTORY_BATCH_ID", "history-csv-initial"),
            current_batch_id=env.get("SUPABASE_CURRENT_BATCH_ID", "current-csv-initial"),
            input_feed_batch_id=env.get("SUPABASE_INPUT_FEED_BATCH_ID", "input-feed-screening"),
            analysis_run_id=env.get("SUPABASE_ANALYSIS_RUN_ID") or None,
            feed_submissions_enabled=env.get("ENABLE_FEED_SUBMISSIONS", "false").lower() == "true",
            weather_investigation_enabled=env.get("ENABLE_WEATHER_INVESTIGATION", "false").lower() == "true",
            premise_source_enabled=env.get("ENABLE_PREMISE_SOURCE_RESOLUTION", "false").lower() == "true",
            premise_source_base_url=env.get("PREMISE_SOURCE_BASE_URL") or None,
            premise_source_api_key=env.get("PREMISE_SOURCE_API_KEY") or None,
            premise_source_name=env.get("PREMISE_SOURCE_NAME", "internal-service-premise"),
        )
        if backend == "supabase":
            missing = [
                name
                for name, value in {
                    "SUPABASE_URL": config.supabase_url,
                    "SUPABASE_SECRET_KEY": config.supabase_secret_key,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Supabase mode requires: {', '.join(missing)}")
        return config
