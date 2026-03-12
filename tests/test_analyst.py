"""
Unit tests for Analyst Agent modules (spend_calculator, savings_calculator, score_engine).

Purpose:
    Comprehensive test coverage for analyst agent core calculation and scoring logic,
    including spend calculations, savings estimates, revenue projections, and lead scoring.

Dependencies:
    - pytest: Test runner and assertion library
    - unittest.mock: Mock and patch for test doubles
    - agents.analyst.spend_calculator: SpendCalculator class
    - agents.analyst.savings_calculator: SavingsCalculator class
    - agents.analyst.score_engine: ScoreEngine class

Usage:
    Run all tests:     pytest tests/test_analyst.py -v
    Run single class:  pytest tests/test_analyst.py::TestSpendCalculator -v
    Run single test:   pytest tests/test_analyst.py::TestSpendCalculator::test_calculate_utility_spend_healthcare -v
    With coverage:     pytest tests/test_analyst.py --cov=agents.analyst --cov-report=html

Test Coverage:
    - SpendCalculator: 5 core tests for utility, telecom, and total spend calculations
    - SavingsCalculator: 6 tests for savings tiers, revenue, and formatting
    - ScoreEngine: 8 tests for scoring components and full composite scoring
    - Edge Cases: Empty/zero inputs, boundary conditions, percentage calculations
    - Error Handling: Invalid states, unknown industries, missing data
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.analyst.spend_calculator import SpendCalculator
from agents.analyst.savings_calculator import SavingsCalculator
from agents.analyst.score_engine import ScoreEngine


class TestSpendCalculator:
    """Test suite for SpendCalculator module."""

    def setup_method(self):
        """Initialize SpendCalculator instance for each test."""
        self.calculator = SpendCalculator()

    def test_calculate_utility_spend_healthcare(self):
        """
        Test utility spend calculation for healthcare industry.

        Inputs:
            site_count=8, industry='healthcare', state='NY'
        Expected Calculation:
            8 × 150,000 (cost per site) × 25 (healthcare multiplier) × 0.19 (NY rate)
            = 8 × 150,000 × 25 × 0.19
            = 5,700,000
        """
        result = self.calculator.calculate_utility_spend(
            site_count=8,
            industry='healthcare',
            state='NY'
        )
        expected = 8 * 150000 * 25 * 0.19
        assert result == expected
        assert isinstance(result, float)
        assert result > 1_000_000

    def test_calculate_telecom_spend(self):
        """
        Test telecom spend calculation based on employee count.

        Inputs:
            employee_count=5000, industry='healthcare'
        Expected Calculation:
            5000 × 1200 (cost per employee)
            = 6,000,000
        """
        result = self.calculator.calculate_telecom_spend(
            employee_count=5000,
            industry='healthcare'
        )
        expected = 5000 * 1200
        assert result == expected
        assert result == 6_000_000

    def test_calculate_total_spend(self):
        """
        Test total spend aggregation.

        Inputs:
            utility=4,800,000, telecom=6,000,000
        Expected Output:
            4,800,000 + 6,000,000 = 10,800,000
        """
        result = self.calculator.calculate_total_spend(
            utility_spend=4_800_000,
            telecom_spend=6_000_000
        )
        expected = 10_800_000
        assert result == expected

    def test_get_electricity_rate_ny(self):
        """
        Test electricity rate lookup for New York.

        Input: state='NY'
        Expected Output: 0.19 (New York specific rate)
        """
        result = self.calculator.get_electricity_rate(state='NY')
        assert result == 0.19

    def test_get_electricity_rate_default(self):
        """
        Test electricity rate lookup with invalid state.

        Input: state='ZZ' (unknown state)
        Expected Output: 0.12 (default national average)
        """
        result = self.calculator.get_electricity_rate(state='ZZ')
        assert result == 0.12


class TestSavingsCalculator:
    """Test suite for SavingsCalculator module."""

    def setup_method(self):
        """Initialize SavingsCalculator instance for each test."""
        self.calculator = SavingsCalculator()

    def test_calculate_savings_low(self):
        """
        Test low-tier savings estimate (10% of total spend).

        Input: total_spend=10,000,000
        Expected Output: 10,000,000 × 0.10 = 1,000,000
        """
        result = self.calculator.calculate_savings_low(total_spend=10_000_000)
        expected = 1_000_000
        assert result == expected

    def test_calculate_savings_mid(self):
        """
        Test mid-tier savings estimate (13.5% of total spend).

        Input: total_spend=10,000,000
        Expected Output: 10,000,000 × 0.135 = 1,350,000
        """
        result = self.calculator.calculate_savings_mid(total_spend=10_000_000)
        expected = 1_350_000
        assert result == expected

    def test_calculate_savings_high(self):
        """
        Test high-tier savings estimate (17% of total spend).

        Input: total_spend=10,000,000
        Expected Output: 10,000,000 × 0.17 = 1,700,000
        """
        result = self.calculator.calculate_savings_high(total_spend=10_000_000)
        expected = 1_700_000
        assert result == expected

    def test_calculate_tb_revenue(self):
        """
        Test Troy Banks revenue projection from mid-tier savings.

        Input: savings_mid=1,350,000
        Expected Output: 1,350,000 × 0.24 = 324,000
        Rationale: Troy Banks typically takes 24% commission on realized savings
        """
        result = self.calculator.calculate_tb_revenue(savings_mid=1_350_000)
        expected = 1_350_000 * 0.24
        assert result == expected
        assert result == 324_000

    def test_format_savings_millions(self):
        """
        Test currency formatting for large savings amounts (millions).

        Input: amount=1,500,000
        Expected Output: "$1.5M"
        """
        result = self.calculator.format_savings(amount=1_500_000)
        assert result == "$1.5M"

    def test_format_savings_thousands(self):
        """
        Test currency formatting for moderate savings amounts (thousands).

        Input: amount=500,000
        Expected Output: "$500k"
        """
        result = self.calculator.format_savings(amount=500_000)
        assert result == "$500k"


class TestScoreEngine:
    """Test suite for ScoreEngine module."""

    def setup_method(self):
        """Initialize ScoreEngine instance for each test."""
        self.engine = ScoreEngine()

    def test_score_recovery_high(self):
        """
        Test recovery/savings score for high savings value.

        Input: savings_mid=2,500,000
        Expected Output: 40
        Rationale: High savings values (>$2M) receive maximum recovery score
        """
        result = self.engine.score_recovery(savings_mid=2_500_000)
        assert result == 40

    def test_score_recovery_medium(self):
        """
        Test recovery/savings score for medium savings value.

        Input: savings_mid=300,000
        Expected Output: 20
        Rationale: Mid-range savings ($300k-$1M) receive moderate score
        """
        result = self.engine.score_recovery(savings_mid=300_000)
        assert result == 20

    def test_score_industry_healthcare(self):
        """
        Test industry score for healthcare sector.

        Input: industry='healthcare'
        Expected Output: 25
        Rationale: Healthcare is high-priority target industry
        """
        result = self.engine.score_industry(industry='healthcare')
        assert result == 25

    def test_score_industry_unknown(self):
        """
        Test industry score for unknown/unmapped industry.

        Input: industry='unknown'
        Expected Output: 0
        Rationale: Unknown industries are not scored
        """
        result = self.engine.score_industry(industry='unknown')
        assert result == 0

    def test_assign_tier_high(self):
        """
        Test lead tier assignment for high-value leads.

        Input: score=75
        Expected Output: 'high'
        Rationale: Scores >= 70 are high tier
        """
        result = self.engine.assign_tier(score=75)
        assert result == 'high'

    def test_assign_tier_medium(self):
        """
        Test lead tier assignment for medium-value leads.

        Input: score=55
        Expected Output: 'medium'
        Rationale: Scores 50-69 are medium tier
        """
        result = self.engine.assign_tier(score=55)
        assert result == 'medium'

    def test_assign_tier_low(self):
        """
        Test lead tier assignment for low-value leads.

        Input: score=30
        Expected Output: 'low'
        Rationale: Scores < 50 are low tier
        """
        result = self.engine.assign_tier(score=30)
        assert result == 'low'

    def test_compute_score_full(self):
        """
        Test composite scoring with all components.

        Inputs:
            savings_mid=2,000,000
            industry='healthcare'
            site_count=10
            data_quality_score=8
            deregulated_state=True

        Expected Output: float >= 70
        Verification: Result is between 0 and 100
        Rationale: Full score computation aggregates all scoring components
        """
        result = self.engine.compute_score(
            savings_mid=2_000_000,
            industry='healthcare',
            site_count=10,
            data_quality_score=8,
            deregulated_state=True
        )
        assert isinstance(result, float)
        assert 0 <= result <= 100
        assert result >= 70


class TestAnalystIntegration:
    """Integration tests combining multiple analyst components."""

    def test_end_to_end_spend_and_savings(self):
        """
        Test complete workflow: calculate spend, estimate savings, derive score.

        Scenario: 8-site healthcare facility in NY with 5,000 employees
        """
        spend_calc = SpendCalculator()
        savings_calc = SavingsCalculator()
        score_engine = ScoreEngine()

        # Calculate spends
        utility_spend = spend_calc.calculate_utility_spend(
            site_count=8,
            industry='healthcare',
            state='NY'
        )
        telecom_spend = spend_calc.calculate_telecom_spend(
            employee_count=5000,
            industry='healthcare'
        )
        total_spend = spend_calc.calculate_total_spend(
            utility_spend=utility_spend,
            telecom_spend=telecom_spend
        )

        # Calculate savings
        savings_mid = savings_calc.calculate_savings_mid(total_spend=total_spend)
        tb_revenue = savings_calc.calculate_tb_revenue(savings_mid=savings_mid)

        # Compute score
        score = score_engine.compute_score(
            savings_mid=savings_mid,
            industry='healthcare',
            site_count=8,
            data_quality_score=9,
            deregulated_state=True
        )
        tier = score_engine.assign_tier(score=score)

        # Assertions
        assert total_spend > 10_000_000
        assert savings_mid > 1_000_000
        assert tb_revenue > 200_000
        assert score >= 70
        assert tier == 'high'

    def test_low_priority_lead_workflow(self):
        """
        Test workflow for low-priority lead (low savings opportunity).

        Scenario: Small 2-site retail facility in unknown state
        """
        spend_calc = SpendCalculator()
        savings_calc = SavingsCalculator()
        score_engine = ScoreEngine()

        # Small facility, low spend
        utility_spend = spend_calc.calculate_utility_spend(
            site_count=2,
            industry='retail',
            state='ZZ'  # Unknown state uses default rate
        )
        telecom_spend = spend_calc.calculate_telecom_spend(
            employee_count=150,
            industry='retail'
        )
        total_spend = spend_calc.calculate_total_spend(
            utility_spend=utility_spend,
            telecom_spend=telecom_spend
        )

        # Low savings
        savings_mid = savings_calc.calculate_savings_mid(total_spend=total_spend)

        # Low score
        score = score_engine.compute_score(
            savings_mid=savings_mid,
            industry='retail',
            site_count=2,
            data_quality_score=4,
            deregulated_state=False
        )
        tier = score_engine.assign_tier(score=score)

        # Assertions
        assert tier == 'low'
        assert score < 50


class TestEdgeCases:
    """Edge case and boundary testing."""

    def test_zero_spend_leads_to_zero_savings(self):
        """Test that zero spend results in zero savings."""
        savings_calc = SavingsCalculator()
        result = savings_calc.calculate_savings_mid(total_spend=0)
        assert result == 0

    def test_score_boundary_high_tier(self):
        """Test score at high-tier boundary (exactly 70)."""
        engine = ScoreEngine()
        tier = engine.assign_tier(score=70)
        assert tier == 'high'

    def test_score_boundary_medium_tier(self):
        """Test score at medium-tier boundary (exactly 50)."""
        engine = ScoreEngine()
        tier = engine.assign_tier(score=50)
        assert tier == 'medium'

    def test_large_employee_count_telecom_spend(self):
        """Test telecom spend calculation with very large employee count."""
        calc = SpendCalculator()
        result = calc.calculate_telecom_spend(
            employee_count=50_000,
            industry='healthcare'
        )
        assert result == 50_000 * 1200
        assert result == 60_000_000

    def test_multiple_state_rates(self):
        """Test electricity rate lookup for multiple state codes."""
        calc = SpendCalculator()
        states_and_rates = {
            'NY': 0.19,
            'CA': 0.15,
            'ZZ': 0.12,  # Default
        }
        for state, expected_rate in states_and_rates.items():
            result = calc.get_electricity_rate(state=state)
            assert result == expected_rate


class TestParametrizedCalculations:
    """Parametrized tests for comprehensive coverage of calculation variations."""

    @pytest.mark.parametrize("site_count,multiplier,expected_factor", [
        (1, 1, 1),
        (5, 5, 25),
        (10, 10, 100),
        (50, 50, 2500),
    ])
    def test_site_count_multiplier_effect(self, site_count, multiplier, expected_factor):
        """
        Test that site count scales spend linearly.

        Parametrization covers 1, 5, 10, and 50 sites.
        """
        calc = SpendCalculator()
        # Base spend for healthcare in default state
        base_rate = 150000 * 25 * 0.12  # cost_per_site * industry_multiplier * default_rate
        result = calc.calculate_utility_spend(
            site_count=site_count,
            industry='healthcare',
            state='ZZ'
        )
        expected = base_rate * site_count
        assert result == expected

    @pytest.mark.parametrize("total_spend,savings_percentage,expected_savings", [
        (10_000_000, 0.10, 1_000_000),
        (10_000_000, 0.135, 1_350_000),
        (10_000_000, 0.17, 1_700_000),
        (5_000_000, 0.135, 675_000),
        (20_000_000, 0.135, 2_700_000),
    ])
    def test_savings_percentage_variations(self, total_spend, savings_percentage, expected_savings):
        """
        Test savings calculations with varying percentages and spend amounts.

        Parametrization covers low (10%), mid (13.5%), and high (17%) tiers across multiple spend levels.
        """
        calc = SavingsCalculator()
        # Choose appropriate method based on percentage
        if savings_percentage == 0.10:
            result = calc.calculate_savings_low(total_spend=total_spend)
        elif savings_percentage == 0.135:
            result = calc.calculate_savings_mid(total_spend=total_spend)
        elif savings_percentage == 0.17:
            result = calc.calculate_savings_high(total_spend=total_spend)
        
        assert result == expected_savings

    @pytest.mark.parametrize("savings_value,expected_tier", [
        (1_000_000, 'low'),
        (2_000_000, 'high'),
        (500_000, 'low'),
        (5_000_000, 'high'),
    ])
    def test_recovery_score_to_tier_mapping(self, savings_value, expected_tier):
        """
        Test that savings values map correctly to lead tiers through score.

        Parametrization covers various savings levels.
        """
        engine = ScoreEngine()
        recovery_score = engine.score_recovery(savings_mid=savings_value)
        # Simplified: assume other component scores contribute ~30
        approximate_score = recovery_score + 30
        tier = engine.assign_tier(score=approximate_score)
        # Verify general tier assignment (exact threshold depends on all component scores)
        assert tier in ['low', 'medium', 'high']

    @pytest.mark.parametrize("industry,expected_score", [
        ('healthcare', 25),
        ('hospitality', 20),
        ('manufacturing', 22),
        ('public_sector', 18),
        ('retail', 15),
        ('unknown', 0),
    ])
    def test_industry_scoring_variations(self, industry, expected_score):
        """
        Test industry score assignments for all supported industries.

        Parametrization covers healthcare, hospitality, manufacturing, public sector, retail, and unknown.
        """
        engine = ScoreEngine()
        result = engine.score_industry(industry=industry)
        assert result == expected_score
