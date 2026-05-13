from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Protocol

from aria.replay.apollo13_cryo_stir import TelemetrySample


class TelemetrySink(Protocol):
    def __call__(self, sample: TelemetrySample) -> None: ...


@dataclass
class ReplayClock:
    accel: float = 60.0
    wall_t0: float = field(default_factory=time.time)
    sim_t0_s: float = 0.0

    def wait_until(self, sim_get_s: float) -> None:
        if self.accel <= 0:
            return
        sim_offset = sim_get_s - self.sim_t0_s
        wall_target = self.wall_t0 + sim_offset / self.accel
        delay = wall_target - time.time()
        if delay > 0:
            time.sleep(delay)


@dataclass
class ReplayStats:
    samples_emitted: int = 0
    samples_dropped: int = 0
    sim_t_first_s: float = 0.0
    sim_t_last_s: float = 0.0
    wall_elapsed_s: float = 0.0


class TelemetryReplayer:
    def __init__(
        self,
        samples: Iterable[TelemetrySample],
        *,
        sinks: Iterable[TelemetrySink] = (),
        clock: Optional[ReplayClock] = None,
    ) -> None:
        self._samples = sorted(samples, key=lambda sample: sample.get_seconds)
        if not self._samples:
            raise ValueError("at least one sample required")
        self._sinks = list(sinks)
        self._clock = clock if clock is not None else ReplayClock(accel=0.0)

    def add_sink(self, sink: TelemetrySink) -> None:
        self._sinks.append(sink)

    def run(
        self,
        *,
        get_start_s: Optional[float] = None,
        get_end_s: Optional[float] = None,
        on_tick: Optional[Callable[[float], None]] = None,
    ) -> ReplayStats:
        stats = ReplayStats()
        wall_t0 = time.time()
        first_emitted = False
        last_get = self._samples[0].get_seconds
        if self._clock is not None:
            self._clock.wall_t0 = wall_t0
            self._clock.sim_t0_s = self._samples[0].get_seconds
        for sample in self._samples:
            if get_start_s is not None and sample.get_seconds < get_start_s:
                continue
            if get_end_s is not None and sample.get_seconds > get_end_s:
                break
            if not first_emitted:
                stats.sim_t_first_s = sample.get_seconds
                first_emitted = True
            self._clock.wait_until(sample.get_seconds)
            for sink in self._sinks:
                try:
                    sink(sample)
                except Exception:
                    stats.samples_dropped += 1
                    continue
            stats.samples_emitted += 1
            last_get = sample.get_seconds
            if on_tick is not None:
                on_tick(sample.get_seconds)
        stats.sim_t_last_s = last_get
        stats.wall_elapsed_s = time.time() - wall_t0
        return stats
