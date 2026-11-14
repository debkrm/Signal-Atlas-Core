"""Unit Tests for Go/No-Go Decision Criteria and Statutory Rate Schedules.

Tests loading, Decimal validation, and date-aware resolution of official NSE circulars.
"""

import datetime
from decimal import Decimal
from pathlib import Path
import pytest

from signal_core.contracts.criteria import (
    CriteriaValidationError,
    EffectiveDatedExchangeFee,
    GoNoGoCriteria,
    load_go_no_go_criteria,
)


def test_load_committed_go_no_go_criteria():
    """Verify loading the committed configs/go_no_go_criteria.yaml file into typed contracts."""
    criteria = load_go_no_go_criteria()

    assert isinstance(criteria, GoNoGoCriteria)
    assert criteria.version == "1.1.0"
    assert criteria.market == "NSE_CASH_EQUITY"
    assert criteria.currency == "INR"

    # Anti-overfitting thresholds
    assert criteria.min_deflated_sharpe_ratio == Decimal("0.95")
    assert criteria.min_haircut_sharpe_ratio == Decimal("1.25")
    assert criteria.dsr_trial_count_basis == "TOTAL_ATTEMPTED_TRIALS"
    assert criteria.dsr_sharpe_variance_divisor == "EVALUATED_TRIALS_MINUS_ONE"
    assert criteria.sessions_per_year == 250
    assert criteria.kurtosis_convention == "RAW_NORMAL_THREE"
    assert criteria.haircut_variant == "BONFERRONI"
    assert criteria.min_total_trades == 100
    assert criteria.max_annual_turnover == Decimal("12.0")
    assert criteria.min_positive_walk_forward_fold_ratio == Decimal("0.80")

    # Risk & execution
    assert criteria.max_portfolio_drawdown == Decimal("0.25")
    assert criteria.max_volume_participation_cap == Decimal("0.03")
    assert criteria.prohibit_buy_at_upper_circuit is True
    assert criteria.prohibit_sell_at_lower_circuit is True

    # Market data and accounting invariants (Finding H-54, Finding N-32)
    assert criteria.min_binding_evaluation_start_date == datetime.date(2022, 1, 3)
    assert criteria.min_traded_eq_resolution_pct == Decimal("100.0")
    assert criteria.expected_sourced_window_calendar_fingerprint == "CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1"

    # Statutory taxes
    costs = criteria.statutory_costs
    assert costs.stt_delivery_rate == Decimal("0.0010")
    assert costs.stt_intraday_sell_rate == Decimal("0.00025")
    assert costs.sebi_turnover_charge_rate == Decimal("0.000001")
    assert costs.stamp_duty_delivery_buy_rate == Decimal("0.00015")
    assert costs.stamp_duty_intraday_buy_rate == Decimal("0.00003")
    assert costs.gst_rate == Decimal("0.18")
    assert costs.brokerage_per_order_inr == Decimal("20.00")
    assert "ipft" in costs.gst_taxable_base_components


def test_effective_dated_nse_fee_schedule_resolution():
    """
    Verify resolution of official NSE circulars across historical dates:
    - Pre-April 2023: NSE/FA/46730 (Turnover 0.0000345, IPFT 0.000000001 = ₹0.01/cr)
    - April 2023 to March 2024: NSE/FA/56129 (Turnover 0.0000325, IPFT 0.000001 = ₹10/cr)
    - April 2024 to Sept 2024: NSE/FA/61137 (Turnover 0.0000322, IPFT 0.000001 = ₹10/cr)
    - Oct 2024 to Feb 2026: NSE/FA/64323 / SEBI uniform (Turnover 0.0000297, IPFT 0.000001 = ₹10/cr)
    - March 2026 onwards: NSE/FA/73061 (Turnover 0.000030699, IPFT 0.000000001 = ₹0.01/cr)
    """
    criteria = load_go_no_go_criteria()
    costs = criteria.statutory_costs

    # 1. 2022 Pre-April 2023
    p1 = costs.get_exchange_fee_for_date(datetime.date(2022, 6, 15))
    assert p1.circular_ref == "NSE/FA/46730"
    assert p1.exchange_turnover_rate == Decimal("0.0000345")
    assert p1.ipft_rate == Decimal("0.000000001")

    # Boundary check: 2023-03-31 vs 2023-04-01
    p1_end = costs.get_exchange_fee_for_date(datetime.date(2023, 3, 31))
    assert p1_end.circular_ref == "NSE/FA/46730"

    p2 = costs.get_exchange_fee_for_date(datetime.date(2023, 4, 1))
    assert p2.circular_ref == "NSE/FA/56129"
    assert p2.exchange_turnover_rate == Decimal("0.0000325")
    assert p2.ipft_rate == Decimal("0.000001")  # ₹10 per crore

    # 2. April 2024 transition
    p3 = costs.get_exchange_fee_for_date(datetime.date(2024, 4, 1))
    assert p3.circular_ref == "NSE/FA/61137"
    assert p3.exchange_turnover_rate == Decimal("0.0000322")

    # Boundary check: 2024-09-30 vs 2024-10-01 (SEBI uniform flat rate)
    p3_end = costs.get_exchange_fee_for_date(datetime.date(2024, 9, 30))
    assert p3_end.circular_ref == "NSE/FA/61137"

    p4 = costs.get_exchange_fee_for_date(datetime.date(2024, 10, 1))
    assert p4.circular_ref == "NSE/FA/64323"
    assert p4.exchange_turnover_rate == Decimal("0.0000297")
    assert p4.ipft_rate == Decimal("0.000001")

    # 3. 2026 revision
    p5 = costs.get_exchange_fee_for_date(datetime.date(2026, 3, 1))
    assert p5.circular_ref == "NSE/FA/73061"
    assert p5.exchange_turnover_rate == Decimal("0.000030699")
    assert p5.ipft_rate == Decimal("0.000000001")


def test_criteria_loader_rejections(tmp_path: Path):
    """Verify that criteria loader fails closed on missing files or invalid types."""
    with pytest.raises(FileNotFoundError):
        load_go_no_go_criteria(Path("non_existent_criteria.yaml"))

    # Test invalid methodology constants
    valid_yaml = Path("configs/go_no_go_criteria.yaml").read_text(encoding="utf-8")

    # Invalid sessions_per_year (boolean or non-positive)
    bad_yaml = valid_yaml.replace("sessions_per_year: 250", "sessions_per_year: true")
    bad_file = tmp_path / "bad1.yaml"
    bad_file.write_text(bad_yaml, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="sessions_per_year"):
        load_go_no_go_criteria(bad_file)

    # Invalid kurtosis_convention
    bad_yaml2 = valid_yaml.replace("kurtosis_convention: \"RAW_NORMAL_THREE\"", "kurtosis_convention: \"UNKNOWN\"")
    bad_file2 = tmp_path / "bad2.yaml"
    bad_file2.write_text(bad_yaml2, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="kurtosis_convention"):
        load_go_no_go_criteria(bad_file2)

    # Invalid haircut_variant
    bad_yaml3 = valid_yaml.replace("haircut_variant: \"BONFERRONI\"", "haircut_variant: \"INVALID_VARIANT\"")
    bad_file3 = tmp_path / "bad3.yaml"
    bad_file3.write_text(bad_yaml3, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="haircut_variant"):
        load_go_no_go_criteria(bad_file3)

    # D-4: TOTAL_TRIALS_MINUS_ONE rejected by loader (EVALUATED_TRIALS_MINUS_ONE is pinned authority)
    bad_yaml4 = valid_yaml.replace("dsr_sharpe_variance_divisor: \"EVALUATED_TRIALS_MINUS_ONE\"", "dsr_sharpe_variance_divisor: \"TOTAL_TRIALS_MINUS_ONE\"")
    bad_file4 = tmp_path / "bad4.yaml"
    bad_file4.write_text(bad_yaml4, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="dsr_sharpe_variance_divisor"):
        load_go_no_go_criteria(bad_file4)



def test_criteria_calendar_fingerprint_pin_present(tmp_path: Path):
    """H-64: expected_calendar_fingerprint must be present and must be a CAL-FPR-V1-... string (Finding H-64)."""
    criteria = load_go_no_go_criteria()
    assert criteria.expected_calendar_fingerprint.startswith("CAL-FPR-V1-"), (
        "expected_calendar_fingerprint must carry the CAL-FPR-V1- prefix (Finding H-64)"
    )
    assert len(criteria.expected_calendar_fingerprint) == len("CAL-FPR-V1-") + 64, (
        "expected_calendar_fingerprint must carry a full SHA-256 hex digest (Finding H-64)"
    )

    valid_yaml = Path("configs/go_no_go_criteria.yaml").read_text(encoding="utf-8")

    # Removing the fingerprint pin must fail closed (N-51)
    bad_yaml = valid_yaml.replace(
        "expected_calendar_fingerprint:",
        "# expected_calendar_fingerprint:",
    )
    bad_file = tmp_path / "no_fingerprint.yaml"
    bad_file.write_text(bad_yaml, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="expected_calendar_fingerprint"):
        load_go_no_go_criteria(bad_file)

    # An invalid prefix must also fail closed
    bad_yaml2 = valid_yaml.replace(
        'expected_calendar_fingerprint: "CAL-FPR-V1-',
        'expected_calendar_fingerprint: "WRONG-PREFIX-',
    )
    bad_file2 = tmp_path / "bad_prefix.yaml"
    bad_file2.write_text(bad_yaml2, encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="CAL-FPR-V1"):
        load_go_no_go_criteria(bad_file2)


def test_criteria_n51_missing_count_pins_fail_closed(tmp_path: Path):
    """N-51: Removing any mandatory calendar count pin from criteria.yaml must fail closed (Note N-51)."""
    import yaml

    valid_yaml = Path("configs/go_no_go_criteria.yaml").read_text(encoding="utf-8")
    base = yaml.safe_load(valid_yaml)

    mandatory_keys = (
        "expected_baseline_calendar_sessions",
        "expected_authoritative_calendar_sessions",
        "expected_total_calendar_sessions",
        "authorized_unarchived_special_sessions",
        "authorized_calendar_holiday_exclusions",
        "authorized_calendar_trading_inclusions",
        "expected_calendar_fingerprint",
        "expected_sourced_window_calendar_fingerprint",
    )

    for mandatory_key in mandatory_keys:
        import copy
        mutated = copy.deepcopy(base)
        del mutated["market_data_and_accounting_invariants"][mandatory_key]
        bad_file = tmp_path / f"missing_{mandatory_key}.yaml"
        bad_file.write_text(yaml.dump(mutated), encoding="utf-8")
        with pytest.raises(CriteriaValidationError, match=mandatory_key):
            load_go_no_go_criteria(bad_file)
