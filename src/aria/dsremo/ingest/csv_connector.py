"""CSVConnector — load wide-format CSV telemetry into Dsremo DB.

CSV format (wide):
    timestamp,param1,param2,...
    2024-01-01T00:00:00Z,1.2,3.4,...

The timestamp column is the DatetimeIndex; every other column is a
telemetry parameter.  Naive timestamps are localized to UTC automatically.

Accepts either a file path *or* a file-like object (``io.BytesIO``) so the
REST upload endpoint can pass in-memory bytes without writing a temp file.

Typical CLI usage::

    connector = CSVConnector("telemetry.csv", satellite_id="MYSAT-1", subsystem="eps")
    totals = await connector.bulk_load_to_db(resample_minutes=5)

REST upload usage::

    connector = CSVConnector(io.BytesIO(raw_bytes), satellite_id="MYSAT-1")
    totals = await connector.bulk_load_to_db()
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

import pandas as pd
import structlog

from aria.dsremo.db import queries
from aria.dsremo.ingest.bulk_loader import bulk_insert_channel, check_channel_row_count
from aria.dsremo.ingest.connector import DataConnector
from aria.dsremo.ingest.utils import prepare_series, validated_resample, validated_satellite_id

logger = structlog.get_logger()

# Type alias accepted by the source parameter
_Source = Union[Path, str, io.IOBase]


class CSVConnector(DataConnector):
    """Load wide-format CSV telemetry into the Dsremo DB.

    Args:
        source:         File path (``Path`` or ``str``) *or* any file-like
                        object (``io.BytesIO``, ``io.StringIO``, open file).
                        Pandas ``read_csv`` handles both transparently.
        satellite_id:   Dsremo satellite identifier written to every DB row.
                        Must not be empty.
        subsystem:      Subsystem label for all parameters in this file.
                        Use a separate connector per subsystem for mixed files.
        timestamp_col:  Column that contains timestamps (default: ``"timestamp"``).
    """

    def __init__(
        self,
        source: _Source,
        satellite_id: str,
        subsystem: str = "unknown",
        timestamp_col: str = "timestamp",
    ) -> None:
        self.satellite_id = validated_satellite_id(satellite_id)
        self.subsystem = subsystem
        self.timestamp_col = timestamp_col

        if isinstance(source, io.IOBase):
            self._source: _Source = source
            self.file_path = Path(f"<upload:{satellite_id}>")
        else:
            self._source = Path(source)
            self.file_path = self._source  # type: ignore[assignment]

    @property
    def source_name(self) -> str:
        return f"csv:{self.file_path.name}"

    async def bulk_load_to_db(
        self,
        *,
        resample_minutes: int = 1,
        skip_if_rows_gte: int = 50_000,
    ) -> dict[str, int]:
        """Parse the CSV and bulk-insert each parameter column into the DB.

        Per-column pipeline:
          1. Skip if the channel already has >= ``skip_if_rows_gte`` rows.
          2. Coerce to numeric (non-numeric → NaN), normalize timezone → UTC,
             resample (median), drop NaN via ``prepare_series()``.
          3. Skip columns that are entirely NaN / non-numeric after prep
             (logged as a warning so operators can diagnose malformed columns).
          4. Register satellite + channel in the channel registry
             (``upsert_satellite_seen`` + ``upsert_channel_seen``).
          5. Insert via ``bulk_insert_channel`` (UNNEST batches, idempotent).

        Returns:
            ``{parameter_name: rows_inserted_or_existing}`` for every column
            that was processed.  Skipped-threshold channels are included with
            their existing row count.
        """
        resample_minutes = validated_resample(resample_minutes)

        df = self._read_csv()
        if df is None or df.empty:
            logger.info("csv_empty_file", source=str(self.file_path))
            return {}

        totals: dict[str, int] = {}
        dropped_cols: int = 0

        for col in df.columns:
            # Coerce to numeric — non-numeric columns become NaN-filled and are skipped.
            numeric = pd.to_numeric(df[col], errors="coerce")
            series = prepare_series(numeric, resample_minutes)

            if series.empty:
                dropped_cols += 1
                logger.warning(
                    "csv_column_skipped_empty",
                    param=col,
                    satellite=self.satellite_id,
                    hint="column may be non-numeric or all-NaN after resampling",
                )
                continue

            existing = await check_channel_row_count(self.satellite_id, col)
            if existing >= skip_if_rows_gte:
                logger.info(
                    "csv_channel_skipped",
                    satellite=self.satellite_id,
                    param=col,
                    existing_rows=existing,
                )
                totals[col] = existing
                continue

            # Register satellite + channel so the channel registry stays consistent.
            # (SatNOGS and ESA do this; CSV was missing these calls — now fixed.)
            await queries.upsert_satellite_seen(
                self.satellite_id, series.index[0].to_pydatetime()
            )
            await queries.upsert_channel_seen(self.satellite_id, col, self.subsystem, "")

            inserted = await bulk_insert_channel(
                satellite_id=self.satellite_id,
                channel_name=col,
                subsystem=self.subsystem,
                unit="",
                series=series,
            )
            totals[col] = inserted
            logger.info(
                "csv_channel_loaded",
                satellite=self.satellite_id,
                param=col,
                rows_inserted=inserted,
            )

        if dropped_cols:
            logger.info(
                "csv_columns_dropped",
                count=dropped_cols,
                satellite=self.satellite_id,
                reason="non-numeric or all-NaN after resampling",
            )

        return totals

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_csv(self) -> pd.DataFrame | None:
        """Read the CSV source with informative errors on common failures."""
        try:
            return pd.read_csv(
                self._source,
                parse_dates=[self.timestamp_col],
                index_col=self.timestamp_col,
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"CSV file not found: {self._source!r}. "
                "Check the path and try again."
            )
        except KeyError:
            raise KeyError(
                f"Timestamp column {self.timestamp_col!r} not found in CSV. "
                "Use --timestamp-col to specify the correct column name."
            )
        except pd.errors.ParserError as exc:
            raise ValueError(
                f"Malformed CSV ({self.file_path.name}): {exc}. "
                "Ensure the file is valid comma-separated text."
            ) from exc
        except ValueError as exc:
            # pandas raises ValueError (not KeyError) when parse_dates column is absent
            if "parse_dates" in str(exc) or self.timestamp_col in str(exc):
                raise KeyError(
                    f"Timestamp column {self.timestamp_col!r} not found in CSV. "
                    "Use --timestamp-col to specify the correct column name."
                ) from exc
            raise ValueError(
                f"Malformed CSV ({self.file_path.name}): {exc}."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Unexpected error reading CSV {self.file_path.name}: {exc}"
            ) from exc
