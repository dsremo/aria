"""ESA OPS-SAT dataset loader — real satellite telemetry integration.

Loads the ESA Anomaly Detection Benchmark (Mission1) dataset:
  - 76 telemetry channels from a real spacecraft
  - 6 subsystems, 13 years of operations (2000-2013)
  - 200 labeled anomalies (Anomaly + Rare Event categories)
  - Pandas pickle format, DatetimeIndex

This loader converts ESA's format into Dsremo's TelemetryPoint stream,
making the real satellite data flow through our detection pipeline
exactly like simulator data or customer data would.

Dataset structure:
  Resources/ESA-Mission1/channels.csv      — channel metadata
  Resources/ESA-Mission1/anomaly_types.csv — labeled anomalies
  Resources/ESA-Mission1/channels/channel_N.zip → channel_N (pickle)
"""

from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
import structlog

from aria.dsremo.core.models import TelemetryPoint
from aria.dsremo.ingest.connector import DataConnector
from aria.dsremo.ingest.utils import ensure_utc_series, validated_resample

logger = structlog.get_logger()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "Resources" / "ESA-Mission1"

# ESA uses generic subsystem names — map to Dsremo's standard names.
# The exact mapping is based on the ESA OPS-SAT documentation and channel groupings.
_ESA_SUBSYSTEM_MAP: dict[str, str] = {
    "subsystem_1": "eps",       # power/electrical
    "subsystem_2": "eps",       # power secondary
    "subsystem_3": "adcs",      # attitude/orbit control
    "subsystem_4": "adcs",      # attitude secondary
    "subsystem_5": "thermal",   # thermal control
    "subsystem_6": "comms",     # communications/payload
}


@dataclass(frozen=True, slots=True)
class ChannelMeta:
    """Metadata for a single ESA telemetry channel."""

    name: str
    subsystem: str
    unit: str
    group: int
    is_target: bool  # True if this channel has labeled anomalies


@dataclass(frozen=True, slots=True)
class LabeledAnomaly:
    """A labeled anomaly from the ESA dataset — ground truth."""

    id: str
    anomaly_class: str
    subclass: str
    category: str        # "Anomaly", "Rare Event", "Communication Gap"
    dimensionality: str  # "Univariate" or "Multivariate"
    locality: str        # "Local" or "Global"
    length: str          # "Point" or "Subsequence"


class ESADataLoader(DataConnector):
    """Loads and streams ESA OPS-SAT telemetry for Dsremo processing."""

    def __init__(
        self,
        data_dir: Path | None = None,
        channels: list[str] | None = None,
    ):
        self.data_dir = data_dir or _DEFAULT_DATA_DIR
        self._default_channels = channels
        self._channels_meta: dict[str, ChannelMeta] = {}
        self._anomalies: list[LabeledAnomaly] = []

    @property
    def source_name(self) -> str:
        return "esa-mission1"

    def load_metadata(self) -> None:
        """Load channel definitions and anomaly labels."""
        channels_file = self.data_dir / "channels.csv"
        anomalies_file = self.data_dir / "anomaly_types.csv"

        if not channels_file.exists():
            raise FileNotFoundError(
                f"ESA channels.csv not found at {channels_file}. "
                f"Extract ESA-Mission1.zip into Resources/"
            )

        # Load channel metadata
        with open(channels_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["Channel"]
                raw_subsystem = row["Subsystem"].strip().lower().replace(" ", "_")
                # Map ESA's generic subsystem names to Dsremo's standard names
                mapped_subsystem = _ESA_SUBSYSTEM_MAP.get(raw_subsystem, "eps")
                self._channels_meta[name] = ChannelMeta(
                    name=name,
                    subsystem=mapped_subsystem,
                    unit=row["Physical Unit"],
                    group=int(row["Group"]),
                    is_target=row["Target"] == "YES",
                )

        # Load anomaly labels
        if anomalies_file.exists():
            with open(anomalies_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._anomalies.append(LabeledAnomaly(
                        id=row["ID"],
                        anomaly_class=row["Class"],
                        subclass=row["Subclass"],
                        category=row.get("Category", ""),
                        dimensionality=row.get("Dimensionality", ""),
                        locality=row.get("Locality", ""),
                        length=row.get("Length", ""),
                    ))

        logger.info(
            "esa_metadata_loaded",
            channels=len(self._channels_meta),
            target_channels=sum(1 for c in self._channels_meta.values() if c.is_target),
            anomalies=len(self._anomalies),
        )

    @property
    def channel_names(self) -> list[str]:
        return list(self._channels_meta.keys())

    @property
    def target_channels(self) -> list[str]:
        """Channels that have labeled anomalies — most useful for benchmarking."""
        return [n for n, m in self._channels_meta.items() if m.is_target]

    @property
    def anomaly_labels(self) -> list[LabeledAnomaly]:
        return self._anomalies

    def load_channel(self, channel_name: str) -> pd.DataFrame:
        """Load a single channel's time-series data.

        Handles both pre-extracted pickle files and nested zips.
        Returns a DataFrame with DatetimeIndex and one float column.

        Hardening: ``channel_name`` must match a strict allow-list character
        set (alphanumeric + dash + underscore + dot, max 128 chars) so an
        attacker controlling the upstream cannot point us at an arbitrary
        pickle outside ``data_dir``. Operator must also have set
        ``ARIA_TRUST_LOCAL_PICKLE=1`` — pickle is RCE-equivalent and we
        refuse to deserialise unless the operator has explicitly opted in.
        """
        import os
        import re

        if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,128}", channel_name):
            raise ValueError(
                f"channel_name {channel_name!r} contains characters outside the "
                "allow-list — refusing to dereference a path"
            )
        # TT&C audit M-4: in production, env-var bypasses are refused
        # outright.  An attacker who can set environment variables can
        # already escalate; we just remove this convenient escalation.
        if os.environ.get("ARIA_ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "ESA pickle loader is permanently disabled when "
                "ARIA_ENVIRONMENT=production. Convert the bundle to "
                "parquet (see scripts/esa_pickle_to_parquet.py)."
            )
        if os.environ.get("ARIA_TRUST_LOCAL_PICKLE", "").strip() not in {"1", "true", "yes"}:
            raise RuntimeError(
                "ESA pickle loader is gated behind ARIA_TRUST_LOCAL_PICKLE=1 "
                "because pickle deserialisation is RCE-equivalent. Convert the "
                "ESA bundle to parquet or set the env var if the data dir is "
                "operator-trusted."
            )
        pickle_path = self.data_dir / "channels" / channel_name
        zip_path = self.data_dir / "channels" / f"{channel_name}.zip"

        if pickle_path.exists() and pickle_path.stat().st_size > 100:
            try:
                return pd.read_pickle(pickle_path)  # nosec B301 (env-gated by ARIA_TRUST_LOCAL_PICKLE; operator opt-in)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load ESA channel {channel_name!r} from pickle: {exc}. "
                    "Re-extract from ESA-Mission1.zip."
                ) from exc

        if zip_path.exists():
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    with zf.open(channel_name) as f:
                        return pd.read_pickle(f)  # nosec B301 (env-gated by ARIA_TRUST_LOCAL_PICKLE; operator opt-in)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load ESA channel {channel_name!r} from zip: {exc}. "
                    "Re-extract from ESA-Mission1.zip."
                ) from exc

        raise FileNotFoundError(
            f"Channel data not found: {channel_name}. "
            f"Extract from ESA-Mission1.zip first."
        )

    def stream_channel(
        self,
        channel_name: str,
        satellite_id: str = "ESA-MISSION1",
        sample_rate: int = 1,
        max_points: int | None = None,
    ) -> Iterator[TelemetryPoint]:
        """Stream a channel's data as TelemetryPoint objects.

        sample_rate: take every Nth point (1=all, 10=every 10th, etc.)
                     ESA data has 10M+ points per channel — sampling avoids OOM.
        max_points: stop after this many points (None=all)
        """
        meta = self._channels_meta.get(channel_name)
        if not meta:
            raise ValueError(f"Unknown channel: {channel_name}. Load metadata first.")

        df = self.load_channel(channel_name)
        count = 0

        for i, (ts, row) in enumerate(df.iterrows()):
            if i % sample_rate != 0:
                continue

            # Ensure timezone-aware timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            yield TelemetryPoint(
                satellite_id=satellite_id,
                timestamp=ts,
                subsystem=meta.subsystem,
                parameter=channel_name,
                value=float(row.iloc[0]),
                unit=meta.unit,
                quality=1.0,
            )

            count += 1
            if max_points and count >= max_points:
                break

    def load_channels_as_matrix(
        self,
        channel_names: list[str] | None = None,
        sample_rate: int = 100,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Load multiple channels into a single aligned DataFrame.

        Useful for multivariate Isolation Forest training.
        Channels are resampled to a common time grid via forward-fill.

        Returns (dataframe, column_names)
        """
        names = channel_names or self.target_channels[:10]  # default: first 10 target channels
        frames = {}

        for name in names:
            try:
                df = self.load_channel(name)
                # Sample to reduce memory
                sampled = df.iloc[::sample_rate]
                frames[name] = sampled.iloc[:, 0]
            except FileNotFoundError:
                logger.warning("esa_channel_not_found", channel=name)

        if not frames:
            raise ValueError("No channels could be loaded")

        combined = pd.DataFrame(frames)
        combined = combined.ffill().dropna()

        logger.info(
            "esa_matrix_loaded",
            channels=len(frames),
            samples=len(combined),
            date_range=f"{combined.index.min()} → {combined.index.max()}",
        )

        return combined, list(combined.columns)

    async def bulk_load_channels_to_db(
        self,
        channels: list[str],
        satellite_id: str = "ESA-MISSION1",
        resample_minutes: int = 60,
        insert_batch: int = 10_000,
        skip_if_rows_gte: int = 50_000,
    ) -> dict[str, int]:
        """Load ESA channels into PostgreSQL, skipping already-loaded channels.

        For each channel: reads zip → resamples to resample_minutes intervals
        (median aggregation) → bulk inserts via UNNEST batches.

        Idempotent: channels with >= skip_if_rows_gte existing rows are skipped
        so re-runs are safe.

        Returns {channel_name: rows_inserted_or_skipped}.
        """
        # Local imports keep esa_loader usable without a DB connection (e.g. in tests).
        from tqdm import tqdm

        from aria.dsremo.db import queries
        from aria.dsremo.ingest.bulk_loader import bulk_insert_channel, check_channel_row_count

        resample_minutes = validated_resample(resample_minutes)
        resample_rule = f"{resample_minutes}min"
        existing = {ch: await check_channel_row_count(satellite_id, ch) for ch in channels}
        to_load = [c for c in channels if existing[c] < skip_if_rows_gte]
        to_skip = [c for c in channels if existing[c] >= skip_if_rows_gte]

        if to_skip:
            print(f"  Skipping {len(to_skip)} channels already loaded"
                  f" (>= {skip_if_rows_gte:,} rows each)")
        print(f"  Loading {len(to_load)} channels @ {resample_minutes}-min resolution ...\n")

        totals: dict[str, int] = {ch: existing[ch] for ch in to_skip}

        for ch in tqdm(to_load, desc="Loading channels", unit="ch"):
            meta = self._channels_meta.get(ch)
            if meta is None:
                tqdm.write(f"  SKIP {ch} — no metadata")
                continue

            try:
                df = self.load_channel(ch)
            except (FileNotFoundError, RuntimeError) as exc:
                tqdm.write(f"  SKIP {ch} — {exc}")
                continue

            series = ensure_utc_series(df.iloc[:, 0].copy())
            resampled = series.resample(resample_rule).median().dropna()

            tqdm.write(
                f"  {ch}: {len(df):>12,} raw → {len(resampled):>7,} rows"
                f" @ {resample_minutes}-min"
            )

            await queries.upsert_satellite_seen(satellite_id, resampled.index[0].to_pydatetime())
            await queries.upsert_channel_seen(satellite_id, ch, meta.subsystem, meta.unit)

            with tqdm(total=len(resampled), desc=f"  {ch}", unit="pt", leave=False) as pbar:
                totals[ch] = await bulk_insert_channel(
                    satellite_id=satellite_id,
                    channel_name=ch,
                    subsystem=meta.subsystem,
                    unit=meta.unit,
                    series=resampled,
                    batch_size=insert_batch,
                    progress_cb=lambda n, p=pbar, last=[0]: (
                        p.update(n - last[0]), last.__setitem__(0, n)
                    ),
                )

        return totals

    async def bulk_load_to_db(  # type: ignore[override]
        self,
        *,
        resample_minutes: int = 60,
        skip_if_rows_gte: int = 50_000,
    ) -> dict[str, int]:
        """DataConnector interface — delegates to bulk_load_channels_to_db().

        Uses channels supplied at construction time, falling back to all
        target channels (those with labeled anomalies) if none were given.
        """
        channels = self._default_channels or self.target_channels
        return await self.bulk_load_channels_to_db(
            channels=channels,
            resample_minutes=resample_minutes,
            skip_if_rows_gte=skip_if_rows_gte,
        )

    def get_subsystem_map(self) -> dict[str, list[str]]:
        """Group channels by subsystem — matches Dsremo's subsystem concept."""
        groups: dict[str, list[str]] = {}
        for name, meta in self._channels_meta.items():
            groups.setdefault(meta.subsystem, []).append(name)
        return groups

    def summary(self) -> dict:
        """Return a human-readable summary of the loaded dataset."""
        subsystems = self.get_subsystem_map()
        categories = {}
        for a in self._anomalies:
            categories[a.category] = categories.get(a.category, 0) + 1

        return {
            "total_channels": len(self._channels_meta),
            "target_channels": len(self.target_channels),
            "subsystems": {k: len(v) for k, v in subsystems.items()},
            "anomaly_labels": len(self._anomalies),
            "anomaly_categories": categories,
            "data_dir": str(self.data_dir),
        }
