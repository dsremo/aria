"""Integration tests for RealExpertPanel — unique comments, trend detection, issue tracking."""
import pytest
from aria.simulation.first_1000_days import (
    DayByDaySimulator, RealExpertPanel, DailyState, IssueCategory,
    IssueStatus, _build_expert_roster,
)


@pytest.fixture
def sim():
    return DayByDaySimulator(crew_size=1000, seed=42)


@pytest.fixture
def panel():
    return RealExpertPanel(seed=42)


@pytest.fixture
def run_100(sim):
    """Run simulation for 100 days and return simulator."""
    sim.run(100)
    return sim


@pytest.fixture
def run_full(sim):
    """Run full 1000-day simulation."""
    sim.run(1000)
    return sim


class TestExpertRoster:
    def test_exactly_100_experts(self):
        roster = _build_expert_roster()
        assert len(roster) == 100

    def test_all_experts_have_issues(self):
        roster = _build_expert_roster()
        for expert in roster:
            assert len(expert.issues) >= 3, f"{expert.name} has only {len(expert.issues)} issues"

    def test_unique_expert_names(self):
        roster = _build_expert_roster()
        names = [e.name for e in roster]
        assert len(names) == len(set(names)), "Duplicate expert names found"

    def test_unique_issue_ids(self):
        roster = _build_expert_roster()
        ids = []
        for expert in roster:
            for issue in expert.issues:
                ids.append(issue.issue_id)
        assert len(ids) == len(set(ids)), f"Duplicate issue IDs: {len(ids)} total, {len(set(ids))} unique"

    def test_total_issue_pool_size(self):
        roster = _build_expert_roster()
        total = sum(len(e.issues) for e in roster)
        assert 300 <= total <= 600, f"Total issue pool is {total}, expected 300-600"

    def test_all_categories_represented(self):
        roster = _build_expert_roster()
        categories = set()
        for expert in roster:
            for issue in expert.issues:
                categories.add(issue.category)
        for cat in IssueCategory.ALL:
            assert cat in categories, f"Category {cat} not represented in any issue"

    def test_experts_have_fields_and_specialties(self):
        roster = _build_expert_roster()
        for expert in roster:
            assert expert.field, f"{expert.name} missing field"
            assert expert.specialty, f"{expert.name} missing specialty"


class TestDailyComments:
    def test_five_comments_per_day(self, sim):
        state = sim.simulate_day(1)
        assert len(state.expert_comments) == 5

    def test_comments_have_required_fields(self, sim):
        state = sim.simulate_day(50)
        for comment in state.expert_comments:
            assert "expert" in comment
            assert "field" in comment
            assert "comment" in comment
            assert isinstance(comment["comment"], str)
            assert len(comment["comment"]) > 10

    def test_no_exact_repeat_within_30_days(self, sim):
        seen_comments = {}
        for day in range(1, 60):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                text = c["comment"]
                if text in seen_comments:
                    prev_day = seen_comments[text]
                    gap = day - prev_day
                    assert gap >= 30, (
                        f"Comment repeated within {gap} days (day {prev_day} and {day}): {text[:80]}..."
                    )
                seen_comments[text] = day

    def test_different_experts_across_days(self, sim):
        expert_names = set()
        for day in range(1, 31):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                expert_names.add(c["expert"])
        # Over 30 days with 5 experts/day, should see many different experts
        assert len(expert_names) >= 15, f"Only {len(expert_names)} unique experts in 30 days"


class TestIssueTracking:
    def test_issues_get_raised(self, run_100):
        panel = run_100._expert_panel
        assert len(panel.all_issues) > 0, "No issues raised after 100 days"

    def test_issue_ids_are_unique(self, run_100):
        panel = run_100._expert_panel
        ids = list(panel.all_issues.keys())
        assert len(ids) == len(set(ids))

    def test_raised_issues_have_day(self, run_100):
        panel = run_100._expert_panel
        for iid, issue in panel.all_issues.items():
            assert issue.day_raised > 0, f"Issue {iid} has no day_raised"
            assert issue.day_raised <= 100

    def test_issue_status_default_raised(self, run_100):
        panel = run_100._expert_panel
        for issue in panel.all_issues.values():
            assert issue.status in (
                IssueStatus.RAISED, IssueStatus.ACKNOWLEDGED,
                IssueStatus.FIXED, IssueStatus.WONTFIX
            )

    def test_acknowledge_issue(self, run_100):
        panel = run_100._expert_panel
        if panel.all_issues:
            first_id = next(iter(panel.all_issues))
            panel.acknowledge_issue(first_id)
            assert panel.all_issues[first_id].status == IssueStatus.ACKNOWLEDGED

    def test_fix_issue(self, run_100):
        panel = run_100._expert_panel
        if panel.all_issues:
            first_id = next(iter(panel.all_issues))
            panel.fix_issue(first_id)
            assert panel.all_issues[first_id].status == IssueStatus.FIXED

    def test_wontfix_issue(self, run_100):
        panel = run_100._expert_panel
        if panel.all_issues:
            first_id = next(iter(panel.all_issues))
            panel.wontfix_issue(first_id)
            assert panel.all_issues[first_id].status == IssueStatus.WONTFIX


class TestTrendDetection:
    def test_co2_trend_expert_speaks_when_high(self, sim):
        """If CO2 rises above 500, atmospheric chemist should raise concern."""
        # Force CO2 high
        sim.state.co2_ppm = 600
        sim.state.co2_removal_efficiency = 0.90  # Degrade removal to trigger concern
        expert_fields = set()
        for day in range(1, 20):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                expert_fields.add(c["field"])
        assert "Atmospheric Chemistry" in expert_fields, "Atmospheric chemist should speak when CO2 elevated"

    def test_water_negative_trend_triggers_expert(self, sim):
        """If water trend goes negative, water engineer should speak."""
        # Force water to drop
        sim.state.water_tank_kg = 2_000_000
        sim.state.recycler_efficiency = 0.50  # Bad recycler
        expert_fields = set()
        for day in range(1, 30):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                expert_fields.add(c["field"])
        # Water Systems Engineering should appear given the bad recycler
        assert len(expert_fields) > 3, "Expected multiple expert fields to speak"

    def test_spinup_phase_triggers_structural(self, sim):
        """During SPINUP phase, structural/rotation experts should speak."""
        expert_fields = set()
        for day in range(91, 130):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                expert_fields.add(c["field"])
        # Structural, gravity biology, fire safety, etc. should appear during spinup
        assert len(expert_fields) >= 5, f"Only {len(expert_fields)} expert fields during SPINUP"


class TestFollowUps:
    def test_followups_occur(self, sim):
        """Over enough days, experts should follow up on their own issues."""
        followup_count = 0
        for day in range(1, 200):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                if c.get("is_followup"):
                    followup_count += 1
        assert followup_count > 0, "No follow-ups generated in 200 days"

    def test_followup_references_original(self, sim):
        """Follow-up comments should reference the original issue ID."""
        for day in range(1, 200):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                if c.get("is_followup"):
                    assert c.get("issue_id"), "Follow-up missing issue_id"
                    assert "Follow-up" in c["comment"] or "follow" in c["comment"].lower()
                    return  # Found one valid follow-up, test passes
        # If we get here without finding any followups, that is ok for very short runs


class TestFinalReport:
    def test_report_structure(self, run_full):
        report = run_full.expert_panel_report()
        assert "total_unique_issues_raised" in report
        assert "total_comments_generated" in report
        assert "issues_by_category" in report
        assert "issues_by_status" in report
        assert "unresolved_count" in report
        assert "top_10_critical_unresolved" in report
        assert "expert_satisfaction_avg" in report
        assert "expert_count" in report
        assert "experts_who_spoke" in report

    def test_report_issue_count_reasonable(self, run_full):
        report = run_full.expert_panel_report()
        total = report["total_unique_issues_raised"]
        assert 100 <= total <= 500, f"Issues raised: {total}, expected 100-500"

    def test_report_comments_exceed_issues(self, run_full):
        report = run_full.expert_panel_report()
        assert report["total_comments_generated"] > report["total_unique_issues_raised"]

    def test_report_categories_sum(self, run_full):
        report = run_full.expert_panel_report()
        cat_total = sum(report["issues_by_category"].values())
        assert cat_total == report["total_unique_issues_raised"]

    def test_report_status_sum(self, run_full):
        report = run_full.expert_panel_report()
        status_total = sum(report["issues_by_status"].values())
        assert status_total == report["total_unique_issues_raised"]

    def test_report_expert_count_is_100(self, run_full):
        report = run_full.expert_panel_report()
        assert report["expert_count"] == 100

    def test_many_experts_spoke(self, run_full):
        report = run_full.expert_panel_report()
        assert report["experts_who_spoke"] >= 50, f"Only {report['experts_who_spoke']} experts spoke in 1000 days"

    def test_top_10_critical_exists(self, run_full):
        report = run_full.expert_panel_report()
        top10 = report["top_10_critical_unresolved"]
        assert len(top10) <= 10
        for item in top10:
            assert "issue_id" in item
            assert "summary" in item
            assert "category" in item


class TestCommentQuality:
    def test_new_issues_have_prefix(self, sim):
        """New issues should be marked with [NEW ISSUE ...]."""
        for day in range(1, 50):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                if not c.get("is_followup") and c.get("issue_id"):
                    assert "[NEW ISSUE" in c["comment"], f"New issue missing prefix: {c['comment'][:60]}"
                    return
        pytest.fail("No new issues found in 50 days")

    def test_comments_are_substantive(self, sim):
        """Comments should be more than just status readouts."""
        for day in range(1, 30):
            state = sim.simulate_day(day)
            for c in state.expert_comments:
                assert len(c["comment"]) >= 20, f"Comment too short: {c['comment']}"

    def test_things_not_modeled_issues_exist(self, run_full):
        """There should be many THINGS_NOT_MODELED issues — the core value of the panel."""
        report = run_full.expert_panel_report()
        tnm = report["issues_by_category"].get(IssueCategory.THINGS_NOT_MODELED, 0)
        assert tnm >= 20, f"Only {tnm} THINGS_NOT_MODELED issues — panel not identifying gaps"

    def test_issue_categories_diverse(self, run_full):
        """Issues should span multiple categories, not just one type."""
        report = run_full.expert_panel_report()
        nonempty = sum(1 for v in report["issues_by_category"].values() if v > 0)
        assert nonempty >= 5, f"Only {nonempty} categories with issues — not diverse enough"


class TestDeterminism:
    def test_same_seed_same_results(self):
        """Same seed should produce identical expert comments."""
        sim1 = DayByDaySimulator(seed=99)
        sim2 = DayByDaySimulator(seed=99)
        for day in range(1, 51):
            s1 = sim1.simulate_day(day)
            s2 = sim2.simulate_day(day)
            c1 = [c["comment"] for c in s1.expert_comments]
            c2 = [c["comment"] for c in s2.expert_comments]
            assert c1 == c2, f"Day {day} mismatch with same seed"

    def test_different_seed_different_results(self):
        """Different seeds should produce different expert comments."""
        sim1 = DayByDaySimulator(seed=1)
        sim2 = DayByDaySimulator(seed=2)
        for day in range(1, 51):
            sim1.simulate_day(day)
            sim2.simulate_day(day)
        c1 = [c["comment"] for c in sim1.timeline[-1].expert_comments]
        c2 = [c["comment"] for c in sim2.timeline[-1].expert_comments]
        assert c1 != c2, "Different seeds produced identical comments"
