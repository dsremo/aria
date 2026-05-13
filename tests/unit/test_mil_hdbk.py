"""Tests for MIL-HDBK-217F failure rate module.

Validates that extracted values from the handbook are consistent,
lookup functions work correctly, and the integration with printer
BOMs produces reasonable results.
"""

import math
import pytest

from aria.simulation.mil_hdbk_217f import (
    MIL_HDBK_217F_RATES,
    PI_E_ENVIRONMENT,
    PRINTER_BOM,
    get_base_failure_rate,
    get_failure_rate,
    get_mtbf_hours,
    get_mtbf_years,
    get_pi_e,
    list_components,
    list_environments,
    printer_annual_degradation_rate,
    printer_failure_rate,
    system_failure_rate,
    system_mtbf_hours,
)


class TestBaseFailureRates:
    """Verify extracted lambda_b values match MIL-HDBK-217F tables."""

    def test_resistor_composition_rate(self):
        """Section 9.1, p.9-1: RC style lambda_b = 0.0017."""
        rate = MIL_HDBK_217F_RATES["resistor_fixed_composition"]
        assert rate["lambda_b"] == 0.0017
        assert rate["section"] == "9.1"

    def test_resistor_film_rate(self):
        """Section 9.1, p.9-1: RL style lambda_b = 0.0037."""
        assert MIL_HDBK_217F_RATES["resistor_fixed_film"]["lambda_b"] == 0.0037

    def test_capacitor_ceramic_rate(self):
        """Section 10.1, p.10-1: CK style lambda_b = 0.00099."""
        assert MIL_HDBK_217F_RATES["capacitor_ceramic_fixed"]["lambda_b"] == 0.00099

    def test_capacitor_electrolytic_aluminum_rate(self):
        """Section 10.1, p.10-2: CU style lambda_b = 0.00012."""
        assert MIL_HDBK_217F_RATES["capacitor_electrolytic_aluminum"]["lambda_b"] == 0.00012

    def test_diode_general_purpose_rate(self):
        """Section 6.1, p.6-2: General Purpose Analog lambda_b = 0.0038."""
        assert MIL_HDBK_217F_RATES["diode_general_purpose"]["lambda_b"] == 0.0038

    def test_relay_mechanical_rate(self):
        """Section 13.1, p.13-1: lambda_b = 0.0059 at 85C/25C."""
        assert MIL_HDBK_217F_RATES["relay_mechanical"]["lambda_b"] == 0.0059

    def test_connector_circular_rate(self):
        """Section 15.1, p.15-1: Circular lambda_b = 0.0010."""
        assert MIL_HDBK_217F_RATES["connector_circular"]["lambda_b"] == 0.0010

    def test_motor_stepper_highest_a_factor(self):
        """Section 12.1, p.12-2: Stepper has A=11, highest motor factor."""
        stepper = MIL_HDBK_217F_RATES["motor_stepper"]
        general = MIL_HDBK_217F_RATES["motor_general_electrical"]
        # Stepper motor failure rate should be significantly higher
        assert stepper["lambda_b"] > general["lambda_b"]
        assert stepper["lambda_b"] == 46.0

    def test_transformer_power_rate(self):
        """Section 11.1, p.11-1: High Power lambda_b = 0.049."""
        assert MIL_HDBK_217F_RATES["transformer_power"]["lambda_b"] == 0.049

    def test_all_rates_have_required_fields(self):
        """Every rate entry must have lambda_b, section, page, and notes."""
        for key, entry in MIL_HDBK_217F_RATES.items():
            assert "lambda_b" in entry, f"{key} missing lambda_b"
            assert "section" in entry, f"{key} missing section"
            assert "page" in entry, f"{key} missing page"
            assert "notes" in entry, f"{key} missing notes"
            assert isinstance(entry["lambda_b"], (int, float)), \
                f"{key} lambda_b is not numeric"
            assert entry["lambda_b"] > 0, f"{key} lambda_b must be positive"


class TestEnvironmentFactors:
    """Verify pi_E values match handbook tables."""

    def test_resistor_space_flight_pi_e(self):
        """Section 9.1, p.9-3: Resistor S_F = 0.5."""
        assert PI_E_ENVIRONMENT["resistor"]["S_F"] == 0.5

    def test_resistor_ground_benign_pi_e(self):
        """Section 9.1, p.9-3: Resistor G_B = 1.0."""
        assert PI_E_ENVIRONMENT["resistor"]["G_B"] == 1.0

    def test_capacitor_space_pi_e(self):
        """Section 10.1, p.10-5: Capacitor S_F = 0.5."""
        assert PI_E_ENVIRONMENT["capacitor"]["S_F"] == 0.5

    def test_connector_space_pi_e(self):
        """Section 15.1, p.15-2: Connector S_F = 0.5."""
        assert PI_E_ENVIRONMENT["connector"]["S_F"] == 0.5

    def test_space_flight_is_benign_for_electronics(self):
        """Space S_F pi_E should be <= G_B for most electronic component types.

        MIL-HDBK-217F recognizes that space (controlled environment,
        no humidity, no vibration after launch) is actually gentle
        on electronics compared to ground environments.
        Motors are excluded: they have engineering-estimated pi_E (not from
        the handbook's standard pi_E tables, since motors use a Weibull model).
        """
        # Motor category uses estimated values, not standard pi_E tables
        skip_categories = {"motor"}
        for cat, env_table in PI_E_ENVIRONMENT.items():
            if cat in skip_categories:
                continue
            if "S_F" in env_table and "G_B" in env_table:
                sf = env_table["S_F"]
                gb = env_table["G_B"]
                if sf is not None and gb is not None:
                    assert sf <= gb, (
                        f"{cat}: S_F={sf} should be <= G_B={gb}"
                    )

    def test_cannon_launch_is_harshest(self):
        """C_L (Cannon Launch) should have the highest pi_E where defined."""
        for cat, env_table in PI_E_ENVIRONMENT.items():
            cl = env_table.get("C_L")
            if cl is None:
                continue
            for key, val in env_table.items():
                if key.startswith("_") or val is None:
                    continue
                assert cl >= val, (
                    f"{cat}: C_L={cl} should be >= {key}={val}"
                )


class TestGetFailureRate:
    """Test the get_failure_rate() public API."""

    def test_resistor_space_flight(self):
        """Resistor in space: lambda_b=0.0037, pi_E=0.5 -> 1.85e-9 F/hr."""
        fr = get_failure_rate("resistor", "space_flight")
        expected = 0.0037 * 0.5 / 1_000_000
        assert fr == pytest.approx(expected, rel=1e-6)

    def test_cpu_ground_benign(self):
        """CPU in ground benign: lambda_b=2.13, pi_E=0.5."""
        fr = get_failure_rate("cpu", "ground_benign")
        expected = 2.13 * 0.5 / 1_000_000
        assert fr == pytest.approx(expected, rel=1e-6)

    def test_motor_stepper_space(self):
        """Stepper motor in space: lambda_b=46.0, pi_E=2.0."""
        fr = get_failure_rate("motor_stepper", "space_flight")
        expected = 46.0 * 2.0 / 1_000_000
        assert fr == pytest.approx(expected, rel=1e-6)

    def test_unknown_component_raises(self):
        with pytest.raises(KeyError, match="Unknown component"):
            get_failure_rate("flux_capacitor")

    def test_unknown_environment_raises(self):
        with pytest.raises(KeyError, match="Unknown environment"):
            get_failure_rate("resistor", "underwater_volcano")


class TestGetMTBF:
    """Test MTBF calculation functions."""

    def test_mtbf_hours_inverse_of_failure_rate(self):
        """MTBF = 1 / failure_rate."""
        fr = get_failure_rate("resistor", "space_flight")
        mtbf = get_mtbf_hours("resistor", "space_flight")
        assert mtbf == pytest.approx(1.0 / fr, rel=1e-6)

    def test_mtbf_years_conversion(self):
        """MTBF years = MTBF hours / 8760."""
        mtbf_h = get_mtbf_hours("capacitor_ceramic", "space_flight")
        mtbf_y = get_mtbf_years("capacitor_ceramic", "space_flight")
        assert mtbf_y == pytest.approx(mtbf_h / 8760.0, rel=1e-6)

    def test_resistor_mtbf_extremely_high(self):
        """A single resistor in space should have MTBF > 50,000 years.

        MIL-HDBK-217F: lambda_b=0.0037, pi_E(S_F)=0.5
        -> 0.00185 F/10^6 hr -> MTBF ~61,700 years.
        """
        mtbf_y = get_mtbf_years("resistor", "space_flight")
        assert mtbf_y > 50_000

    def test_motor_stepper_mtbf_reasonable(self):
        """Stepper motor MTBF should be ~1-15 years (high failure rate)."""
        mtbf_y = get_mtbf_years("motor_stepper", "space_flight")
        assert 0.5 < mtbf_y < 15.0


class TestSystemLevel:
    """Test system-level failure rate calculations."""

    def test_system_failure_rate_additive(self):
        """System failure rate = sum of component failure rates."""
        bom = {"resistor": 100, "capacitor_ceramic": 50}
        sys_fr = system_failure_rate(bom, "space_flight")
        manual = (
            100 * get_failure_rate("resistor", "space_flight")
            + 50 * get_failure_rate("capacitor_ceramic", "space_flight")
        )
        assert sys_fr == pytest.approx(manual, rel=1e-6)

    def test_system_mtbf_is_inverse(self):
        bom = {"resistor": 100, "cpu": 2}
        fr = system_failure_rate(bom, "space_flight")
        mtbf = system_mtbf_hours(bom, "space_flight")
        assert mtbf == pytest.approx(1.0 / fr, rel=1e-6)

    def test_more_components_lower_mtbf(self):
        """More components in series = lower system MTBF."""
        small = system_mtbf_hours({"resistor": 10}, "space_flight")
        large = system_mtbf_hours({"resistor": 1000}, "space_flight")
        assert large < small


class TestPrinterIntegration:
    """Test printer BOM-based failure rate calculations."""

    def test_all_printer_types_have_bom(self):
        for ptype in ("FDM", "SLM", "DLP", "CIRCUIT"):
            assert ptype in PRINTER_BOM

    def test_slm_has_laser_diode(self):
        """SLM printer BOM must include laser diode (critical component)."""
        assert "laser_diode" in PRINTER_BOM["SLM"]
        assert PRINTER_BOM["SLM"]["laser_diode"] >= 1

    def test_printer_degradation_rates_ordered(self):
        """SLM should degrade fastest (laser diode is high-criticality)."""
        rates = {
            pt: printer_annual_degradation_rate(pt)
            for pt in PRINTER_BOM
        }
        # SLM has laser diode (lambda_b=5.0, weight=1.0) -> highest degradation
        assert rates["SLM"] > rates["DLP"]

    def test_printer_degradation_rate_plausible(self):
        """Annual degradation should be between 0.5% and 15%."""
        for pt in PRINTER_BOM:
            rate = printer_annual_degradation_rate(pt)
            assert 0.005 <= rate <= 0.15, (
                f"{pt} degradation rate {rate:.4f} out of plausible range"
            )

    def test_fdm_degradation_near_original(self):
        """FDM MIL-HDBK rate should be in the same order of magnitude as the
        original 0.02 hardcoded rate.  The criticality-weighted approach
        yields rates in the 0.5%-15% range."""
        rate = printer_annual_degradation_rate("FDM")
        # Should be within the plausible range
        assert 0.005 <= rate <= 0.15


class TestListFunctions:
    """Test enumeration helpers."""

    def test_list_components_nonempty(self):
        comps = list_components()
        assert len(comps) > 30

    def test_list_environments_has_space(self):
        envs = list_environments()
        assert "S_F" in envs

    def test_all_listed_components_resolve(self):
        """Every component from list_components() should work with get_failure_rate."""
        for comp in list_components():
            fr = get_failure_rate(comp, "space_flight")
            assert fr > 0


class TestEnvironmentAliases:
    """Test that human-readable environment names work."""

    def test_space_flight_alias(self):
        r1 = get_failure_rate("resistor", "space_flight")
        r2 = get_failure_rate("resistor", "S_F")
        assert r1 == r2

    def test_ground_benign_alias(self):
        r1 = get_failure_rate("resistor", "ground_benign")
        r2 = get_failure_rate("resistor", "G_B")
        assert r1 == r2
