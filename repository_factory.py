"""Construct the configured meter-data repository."""

from __future__ import annotations

from app_config import AppConfig
from meter_repository import CsvMeterRepository, MeterDataRepository
from supabase_repository import SupabaseMeterRepository


def create_repository(config: AppConfig) -> MeterDataRepository:
    if config.data_backend == "csv":
        return CsvMeterRepository(config.history_path, config.current_path, config.results_path)
    if config.data_backend == "supabase":
        return SupabaseMeterRepository(
            config.supabase_url or "",
            config.supabase_secret_key or "",
            config.history_batch_id,
            config.current_batch_id,
            config.analysis_run_id,
        )
    raise ValueError(f"Unsupported data backend: {config.data_backend}")
