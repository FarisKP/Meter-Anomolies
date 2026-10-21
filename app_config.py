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
    analysis_run_id: str | None = None

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
            analysis_run_id=env.get("SUPABASE_ANALYSIS_RUN_ID") or None,
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
