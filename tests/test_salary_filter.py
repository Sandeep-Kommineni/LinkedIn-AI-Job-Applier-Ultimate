"""Tests for salary parsing and threshold filtering."""

import pytest

from src.utils.utils import check_salary_threshold, parse_salary_from_text


class TestParseSalaryFromText:
    # -- LPA formats --
    def test_single_lpa(self):
        result = parse_salary_from_text("Salary: 5 LPA")
        assert result["found"] is True
        assert result["min_annual_inr"] == 500000
        assert result["max_annual_inr"] == 500000

    def test_range_lpa(self):
        result = parse_salary_from_text("Compensation: 5-12 LPA")
        assert result["found"] is True
        assert result["min_annual_inr"] == 500000
        assert result["max_annual_inr"] == 1200000

    def test_decimal_lpa(self):
        result = parse_salary_from_text("CTC: 4.5 LPA")
        assert result["found"] is True
        assert result["min_annual_inr"] == 450000

    def test_lowercase_lpa(self):
        result = parse_salary_from_text("We offer 8 lpa")
        assert result["found"] is True
        assert result["min_annual_inr"] == 800000

    # -- Lakhs formats --
    def test_lakhs_per_annum(self):
        result = parse_salary_from_text("₹6 lakhs per annum")
        assert result["found"] is True
        assert result["min_annual_inr"] == 600000

    def test_lakh_singular(self):
        result = parse_salary_from_text("10 lakh per year")
        assert result["found"] is True
        assert result["min_annual_inr"] == 1000000

    def test_range_lakhs(self):
        result = parse_salary_from_text("5-8 lakhs per annum")
        assert result["found"] is True
        assert result["min_annual_inr"] == 500000
        assert result["max_annual_inr"] == 800000

    # -- Monthly INR --
    def test_inr_monthly(self):
        result = parse_salary_from_text("₹50,000 per month")
        assert result["found"] is True
        assert result["min_annual_inr"] == 600000

    def test_inr_monthly_k(self):
        result = parse_salary_from_text("₹100k per month")
        assert result["found"] is True
        assert result["min_annual_inr"] == 1200000

    # -- USD annual --
    def test_usd_annual(self):
        result = parse_salary_from_text("$60,000 per year")
        assert result["found"] is True
        assert result["min_annual_usd"] == 60000
        assert result["max_annual_usd"] == 60000

    def test_usd_range(self):
        result = parse_salary_from_text("$60k-$80k per year")
        assert result["found"] is True
        assert result["min_annual_usd"] == 60000
        assert result["max_annual_usd"] == 80000

    # -- USD monthly --
    def test_usd_monthly(self):
        result = parse_salary_from_text("$5,000 per month")
        assert result["found"] is True
        assert result["min_annual_usd"] == 60000

    # -- No salary found --
    def test_no_salary_mentioned(self):
        result = parse_salary_from_text("We are looking for a talented engineer.")
        assert result["found"] is False

    def test_empty_text(self):
        result = parse_salary_from_text("")
        assert result["found"] is False

    def test_none_text(self):
        result = parse_salary_from_text(None)
        assert result["found"] is False


class TestCheckSalaryThreshold:
    @pytest.fixture
    def enabled_config(self):
        return {
            "enabled": True,
            "min_annual_inr": 500000,
            "min_annual_usd": 14000,
        }

    @pytest.fixture
    def disabled_config(self):
        return {"enabled": False}

    def test_disabled_filter_allows_all(self, disabled_config):
        skip, reason = check_salary_threshold("3 LPA", disabled_config)
        assert skip is False
        assert reason == ""

    def test_no_salary_allows_job(self, enabled_config):
        skip, reason = check_salary_threshold(
            "Great opportunity for a ML engineer.", enabled_config
        )
        assert skip is False

    def test_low_lpa_skips_job(self, enabled_config):
        skip, reason = check_salary_threshold("CTC: 3 LPA", enabled_config)
        assert skip is True
        assert "below minimum threshold" in reason

    def test_acceptable_lpa_allows_job(self, enabled_config):
        skip, reason = check_salary_threshold("CTC: 8 LPA", enabled_config)
        assert skip is False

    def test_high_lpa_allows_job(self, enabled_config):
        skip, reason = check_salary_threshold("CTC: 20 LPA", enabled_config)
        assert skip is False

    def test_range_lpa_above_min_allows_job(self, enabled_config):
        skip, reason = check_salary_threshold("Salary: 5-12 LPA", enabled_config)
        assert skip is False

    def test_low_monthly_inr_skips(self, enabled_config):
        skip, reason = check_salary_threshold("₹30,000 per month", enabled_config)
        assert skip is True

    def test_acceptable_monthly_inr_allows(self, enabled_config):
        skip, reason = check_salary_threshold("₹50,000 per month", enabled_config)
        assert skip is False

    def test_low_usd_skips_job(self, enabled_config):
        skip, reason = check_salary_threshold("$10,000 per year", enabled_config)
        assert skip is True

    def test_acceptable_usd_allows_job(self, enabled_config):
        skip, reason = check_salary_threshold("$60,000 per year", enabled_config)
        assert skip is False
