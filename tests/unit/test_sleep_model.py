"""Tests for crew sleep model based on NASA LSDA actigraphy data."""

from aria.simulation.sleep_model import (
    CrewSleepSimulator,
    CrewSleepState,
    LSDA_SLEEP_STATS,
    PERF_SENSITIVITY,
)


class TestLSDAData:
    def test_in_flight_stats_present(self):
        stats = LSDA_SLEEP_STATS["in_flight"]
        assert stats["n_records"] == 166
        assert 7.0 < stats["duration_hrs_mean"] < 7.5

    def test_efficiency_drops_in_flight(self):
        pre = LSDA_SLEEP_STATS["pre_flight"]["efficiency_pct_mean"]
        inf = LSDA_SLEEP_STATS["in_flight"]["efficiency_pct_mean"]
        assert pre > inf  # Sleep gets worse in space

    def test_latency_increases_in_flight(self):
        pre = LSDA_SLEEP_STATS["pre_flight"]["latency_min_mean"]
        inf = LSDA_SLEEP_STATS["in_flight"]["latency_min_mean"]
        assert inf > pre  # Takes longer to fall asleep


class TestSleepSimulator:
    def test_creates(self):
        sim = CrewSleepSimulator(crew_size=100, seed=42)
        assert sim.state.avg_sleep_efficiency_pct > 0

    def test_baseline_near_lsda(self):
        """At default conditions, efficiency should be near ISS baseline."""
        sim = CrewSleepSimulator(gravity_g=0.0, seed=42)  # 0g like ISS
        sim.simulate_year(1.0, noise_db=40.0, circadian_disruption=0.0)
        # With countermeasures, should be slightly better than raw 81.6%
        assert 80 < sim.state.avg_sleep_efficiency_pct < 95

    def test_noise_degrades_sleep(self):
        sim_quiet = CrewSleepSimulator(seed=42)
        sim_quiet.simulate_year(1.0, noise_db=30.0)
        sim_loud = CrewSleepSimulator(seed=42)
        sim_loud.simulate_year(1.0, noise_db=60.0)
        assert sim_quiet.state.avg_sleep_efficiency_pct > sim_loud.state.avg_sleep_efficiency_pct

    def test_partial_gravity_helps(self):
        """Ship at 0.56g should sleep better than ISS at 0g."""
        sim_0g = CrewSleepSimulator(gravity_g=0.0, seed=42)
        sim_0g.simulate_year(1.0)
        sim_056g = CrewSleepSimulator(gravity_g=0.56, seed=42)
        sim_056g.simulate_year(1.0)
        assert sim_056g.state.avg_sleep_efficiency_pct > sim_0g.state.avg_sleep_efficiency_pct

    def test_cognitive_performance_bounded(self):
        sim = CrewSleepSimulator(seed=42)
        sim.simulate_year(1.0, noise_db=70.0, circadian_disruption=0.8)
        assert 0.5 <= sim.state.cognitive_performance <= 1.0

    def test_efficiency_bounded(self):
        sim = CrewSleepSimulator(seed=42)
        sim.simulate_year(1.0, noise_db=80.0, circadian_disruption=1.0)
        assert 50 <= sim.state.avg_sleep_efficiency_pct <= 95

    def test_events_on_poor_sleep(self):
        sim = CrewSleepSimulator(gravity_g=0.0, seed=42)
        events = sim.simulate_year(1.0, noise_db=65.0, circadian_disruption=0.8)
        assert len(events) > 0

    def test_report_keys(self):
        sim = CrewSleepSimulator(seed=42)
        sim.simulate_year(1.0)
        report = sim.get_report()
        assert "avg_sleep_efficiency_pct" in report
        assert "cognitive_performance" in report
        assert "data_source" in report
        assert "LSDA" in report["data_source"]

    def test_deterministic(self):
        sim1 = CrewSleepSimulator(seed=42)
        sim1.simulate_year(1.0)
        sim2 = CrewSleepSimulator(seed=42)
        sim2.simulate_year(1.0)
        assert sim1.state.avg_sleep_efficiency_pct == sim2.state.avg_sleep_efficiency_pct
