"""Tests for the ESA OPS-SAT data loader.

Uses mock data to test without requiring the actual 3.7GB dataset.
"""

from __future__ import annotations

import csv
import pickle
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aria.dsremo.ingest.esa_loader import (
    ChannelMeta,
    ESADataLoader,
    LabeledAnomaly,
)


@pytest.fixture
def esa_data_dir(tmp_path: Path) -> Path:
    """Create a minimal mock ESA dataset directory."""
    data_dir = tmp_path / "ESA-Mission1"
    channels_dir = data_dir / "channels"
    channels_dir.mkdir(parents=True)

    # Write channels.csv (using real ESA subsystem names)
    with open(data_dir / "channels.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["Channel", "Subsystem", "Physical Unit", "Group", "Target"]
        )
        writer.writeheader()
        writer.writerow({
            "Channel": "channel_1",
            "Subsystem": "subsystem_1",
            "Physical Unit": "V",
            "Group": 1,
            "Target": "YES",
        })
        writer.writerow({
            "Channel": "channel_2",
            "Subsystem": "subsystem_5",
            "Physical Unit": "°C",
            "Group": 2,
            "Target": "NO",
        })
        writer.writerow({
            "Channel": "channel_3",
            "Subsystem": "subsystem_3",
            "Physical Unit": "deg/s",
            "Group": 1,
            "Target": "YES",
        })

    # Write anomaly_types.csv
    with open(data_dir / "anomaly_types.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ID", "Class", "Subclass", "Category",
                "Dimensionality", "Locality", "Length",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "ID": "A001",
            "Class": "ContextualAnomaly",
            "Subclass": "Spike",
            "Category": "Anomaly",
            "Dimensionality": "Univariate",
            "Locality": "Local",
            "Length": "Point",
        })
        writer.writerow({
            "ID": "A002",
            "Class": "PointAnomaly",
            "Subclass": "Dropout",
            "Category": "Rare Event",
            "Dimensionality": "Multivariate",
            "Locality": "Global",
            "Length": "Subsequence",
        })

    # Create pickle channel data (simulating real ESA format)
    dates = pd.date_range("2005-01-01", periods=1000, freq="10min")
    rng = np.random.default_rng(42)

    for ch_name in ["channel_1", "channel_2", "channel_3"]:
        values = rng.normal(0, 1, 1000)
        df = pd.DataFrame({ch_name: values}, index=dates)
        # Save as extracted pickle (no zip)
        df.to_pickle(channels_dir / ch_name)

    return data_dir


@pytest.fixture
def loader(esa_data_dir: Path) -> ESADataLoader:
    """Create and initialize an ESA loader with mock data."""
    loader = ESADataLoader(data_dir=esa_data_dir)
    loader.load_metadata()
    return loader


class TestESAMetadata:
    def test_loads_channel_metadata(self, loader: ESADataLoader):
        assert len(loader.channel_names) == 3
        assert "channel_1" in loader.channel_names

    def test_target_channels_identified(self, loader: ESADataLoader):
        targets = loader.target_channels
        assert "channel_1" in targets
        assert "channel_3" in targets
        assert "channel_2" not in targets

    def test_anomaly_labels_loaded(self, loader: ESADataLoader):
        labels = loader.anomaly_labels
        assert len(labels) == 2
        assert labels[0].id == "A001"
        assert labels[0].category == "Anomaly"
        assert labels[1].category == "Rare Event"

    def test_missing_channels_file_raises(self, tmp_path: Path):
        loader = ESADataLoader(data_dir=tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="channels.csv"):
            loader.load_metadata()

    def test_subsystem_map(self, loader: ESADataLoader):
        subsystems = loader.get_subsystem_map()
        assert "eps" in subsystems       # subsystem_1 → eps
        assert "thermal" in subsystems   # subsystem_5 → thermal
        assert "channel_1" in subsystems["eps"]

    def test_summary(self, loader: ESADataLoader):
        summary = loader.summary()
        assert summary["total_channels"] == 3
        assert summary["target_channels"] == 2
        assert summary["anomaly_labels"] == 2
        assert "eps" in summary["subsystems"]


class TestESAChannelLoading:
    def test_load_channel_returns_dataframe(self, loader: ESADataLoader):
        df = loader.load_channel("channel_1")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1000

    def test_load_channel_from_zip(self, esa_data_dir: Path):
        """Test loading from a .zip archive (how ESA distributes them)."""
        channels_dir = esa_data_dir / "channels"

        # Create a zipped channel
        dates = pd.date_range("2005-01-01", periods=500, freq="10min")
        df = pd.DataFrame({"channel_zip": np.random.default_rng(99).normal(0, 1, 500)}, index=dates)

        # Pickle to bytes, then write into a zip
        zip_path = channels_dir / "channel_zip.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            import io
            buf = io.BytesIO()
            df.to_pickle(buf)
            zf.writestr("channel_zip", buf.getvalue())

        loader = ESADataLoader(data_dir=esa_data_dir)
        loader.load_metadata()
        result = loader.load_channel("channel_zip")
        assert len(result) == 500

    def test_load_nonexistent_channel_raises(self, loader: ESADataLoader):
        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load_channel("channel_999")


class TestESAStreaming:
    def test_stream_channel_yields_telemetry_points(self, loader: ESADataLoader):
        points = list(loader.stream_channel("channel_1", max_points=10))
        assert len(points) == 10
        assert all(p.satellite_id == "ESA-MISSION1" for p in points)
        assert all(p.subsystem == "eps" for p in points)  # subsystem_1 → eps
        assert all(p.parameter == "channel_1" for p in points)
        assert all(p.unit == "V" for p in points)
        assert all(p.quality == 1.0 for p in points)

    def test_stream_with_sample_rate(self, loader: ESADataLoader):
        # sample_rate=10 means every 10th point
        points = list(loader.stream_channel("channel_1", sample_rate=10, max_points=5))
        assert len(points) == 5

    def test_stream_timestamps_are_utc(self, loader: ESADataLoader):
        points = list(loader.stream_channel("channel_1", max_points=3))
        for p in points:
            assert p.timestamp.tzinfo is not None

    def test_stream_unknown_channel_raises(self, loader: ESADataLoader):
        with pytest.raises(ValueError, match="Unknown channel"):
            list(loader.stream_channel("nonexistent_channel"))

    def test_stream_custom_satellite_id(self, loader: ESADataLoader):
        points = list(loader.stream_channel(
            "channel_1", satellite_id="MY-SAT-01", max_points=3
        ))
        assert all(p.satellite_id == "MY-SAT-01" for p in points)


class TestESAMatrix:
    def test_load_matrix(self, loader: ESADataLoader):
        df, cols = loader.load_channels_as_matrix(
            channel_names=["channel_1", "channel_2"],
            sample_rate=10,
        )
        assert isinstance(df, pd.DataFrame)
        assert len(cols) == 2
        assert "channel_1" in cols
        assert "channel_2" in cols

    def test_matrix_no_channels_raises(self, esa_data_dir: Path):
        loader = ESADataLoader(data_dir=esa_data_dir)
        loader.load_metadata()
        # Remove all channel files
        for f in (esa_data_dir / "channels").iterdir():
            f.unlink()
        with pytest.raises(ValueError, match="No channels"):
            loader.load_channels_as_matrix(channel_names=["channel_1"])
