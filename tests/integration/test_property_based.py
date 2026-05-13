from __future__ import annotations

from hypothesis import given, settings, strategies as st

from aria.knowledge import LessonRecord, TfIdfIndex
from aria.physics.eps.power_dynamics import (
    BatteryAgingModel,
    CellThermalNode,
    MpptController,
    PlasmaLatchupSimulator,
)
from aria.replay.action_translator import (
    ActionRegistry,
    make_default_registry,
)
from aria.replay.noise import overlay_noise
from aria.replay.apollo13_cryo_stir import TelemetrySample


@settings(max_examples=80, deadline=None)
@given(
    proposed_action=st.text(
        alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
        min_size=0, max_size=64,
    ),
)
def test_action_translator_never_raises(proposed_action: str) -> None:
    registry = make_default_registry()
    result = registry.translate(proposed_action)
    assert result.status in {"applied", "deferred", "refused"}


@settings(max_examples=50, deadline=None)
@given(
    proposed_action=st.sampled_from([
        "vent_crew_quarters", "abort_mission", "deorbit",
        "delete_audit_log", "wipe_telemetry", "disable_failsafe",
    ]),
)
def test_safety_blocked_actions_never_apply(proposed_action: str) -> None:
    registry = make_default_registry()
    result = registry.translate(proposed_action)
    assert result.status == "refused"
    assert result.hal_command is None


@settings(max_examples=30, deadline=None)
@given(
    soc=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    temp=st.floats(min_value=240.0, max_value=350.0, allow_nan=False),
)
def test_cell_thermal_node_bounded(soc: float, temp: float) -> None:
    node = CellThermalNode(cell_temp_k=temp, sink_temp_k=temp)
    new_temp = node.step(joule_heat_w=2.0, irradiance_w_m2=0.0, dt_s=10.0)
    assert 150.0 <= new_temp <= 400.0


@settings(max_examples=50, deadline=None)
@given(
    cycles=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False),
    days=st.floats(min_value=0.0, max_value=3650.0, allow_nan=False),
)
def test_aging_factor_monotonic_decrease(cycles: float, days: float) -> None:
    model = BatteryAgingModel()
    factor_initial = model.capacity_fade_factor
    model.step(equivalent_full_cycles=cycles, dt_days=days, temperature_c=25.0)
    factor_after = model.capacity_fade_factor
    assert factor_after <= factor_initial
    assert 0.6 <= factor_after <= 1.0


@settings(max_examples=30, deadline=None)
@given(power_w=st.floats(min_value=0.0, max_value=200.0, allow_nan=False))
def test_mppt_duty_cycle_in_range(power_w: float) -> None:
    controller = MpptController()
    controller.update(current_power_w=power_w)
    assert 0.10 <= controller.duty_cycle <= 0.90


@settings(max_examples=30, deadline=None)
@given(
    n=st.integers(min_value=10, max_value=200),
    seed=st.integers(min_value=0, max_value=999),
)
def test_plasma_latchup_baseline_low_rate(n: int, seed: int) -> None:
    sim = PlasmaLatchupSimulator(rng_seed=seed)
    events = 0
    for _ in range(n):
        if sim.step(dt_s=60.0, in_saa=False, spe_active=False) is not None:
            events += 1
    assert events <= max(2, n // 5)


@settings(max_examples=50, deadline=None)
@given(
    parameter=st.text(min_size=1, max_size=24),
    value=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    seed=st.integers(min_value=0, max_value=999),
)
def test_overlay_noise_never_raises(
    parameter: str, value: float, seed: int,
) -> None:
    sample = TelemetrySample(
        get_seconds=0.0, parameter=parameter, value=value, units="x",
    )
    out = overlay_noise((sample,), rng_seed=seed)
    assert len(out) == 1


@settings(max_examples=30, deadline=None)
@given(
    record_id=st.text(min_size=1, max_size=24),
    title=st.text(min_size=1, max_size=64),
    summary=st.text(min_size=1, max_size=512),
)
def test_tfidf_index_handles_arbitrary_records(
    record_id: str, title: str, summary: str,
) -> None:
    index = TfIdfIndex()
    index.add(LessonRecord(
        record_id=record_id, title=title, summary=summary,
    ))
    hits = index.search(title[:32], top_k=5)
    assert isinstance(hits, tuple)
    for hit in hits:
        assert hit.score >= 0.0
