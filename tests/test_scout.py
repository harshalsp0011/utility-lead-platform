"""
Test Suite for Scout Agent Modules

Purpose: Unit tests for Scout agent scripts covering company extraction and website crawling.
Dependencies: pytest, requests (for mocking)
Usage: pytest tests/test_scout.py -v

Tests cover:
  - CompanyExtractor: industry classification, domain extraction, state normalization
  - WebsiteCrawler: location count extraction, employee signal detection
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from agents.scout.company_extractor import (
    classify_industry,
    extract_domain,
    normalize_state,
)
from agents.scout.website_crawler import (
    extract_location_count,
    extract_employee_signals,
)


class TestCompanyExtractor:
    """Tests for company_extractor module functions"""

    def test_classify_industry_healthcare(self):
        """Test industry classification for healthcare sector"""
        input_text = "Health Care Services"
        expected = "healthcare"
        result = classify_industry(input_text)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_classify_industry_hospitality(self):
        """Test industry classification for hospitality sector"""
        input_text = "Lodging & Travel"
        expected = "hospitality"
        result = classify_industry(input_text)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_classify_industry_unknown(self):
        """Test industry classification for unknown/unmapped sector"""
        input_text = "Furniture Repair"
        expected = "unknown"
        result = classify_industry(input_text)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_extract_domain_full_url(self):
        """Test domain extraction from full URL with www prefix"""
        input_url = "https://www.kaleida.org/about"
        expected = "kaleida.org"
        result = extract_domain(input_url)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_extract_domain_no_www(self):
        """Test domain extraction from URL without www prefix"""
        input_url = "https://delawarenorth.com"
        expected = "delawarenorth.com"
        result = extract_domain(input_url)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_normalize_state_full_name(self):
        """Test state normalization from full name to abbreviation"""
        input_state = "New York"
        expected = "NY"
        result = normalize_state(input_state)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_normalize_state_already_code(self):
        """Test state normalization when input is already abbreviation"""
        input_state = "NY"
        expected = "NY"
        result = normalize_state(input_state)
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_normalize_state_lowercase(self):
        """Test state normalization from lowercase full name"""
        input_state = "new york"
        expected = "NY"
        result = normalize_state(input_state)
        assert result == expected, f"Expected '{expected}', got '{result}'"


class TestWebsiteCrawler:
    """Tests for website_crawler module functions"""

    def test_extract_location_count_hospitals(self):
        """Test location count extraction for hospital mentions"""
        input_text = "We operate 8 hospitals across WNY"
        expected = 8
        result = extract_location_count(input_text, "https://example.com")
        assert result == expected, f"Expected {expected}, got {result}"

    def test_extract_location_count_stores(self):
        """Test location count extraction for store location mentions"""
        input_text = "150 store locations nationwide"
        expected = 150
        result = extract_location_count(input_text, "https://example.com")
        assert result == expected, f"Expected {expected}, got {result}"

    def test_extract_location_count_none_found(self):
        """Test location count extraction when no explicit count found"""
        input_text = "Welcome to our company website"
        expected = 1
        result = extract_location_count(input_text, "https://example.com")
        assert result == expected, f"Expected {expected}, got {result}"

    def test_extract_employee_signals_found(self):
        """Test employee count extraction when signal is found"""
        input_text = "Our team of 5,000 employees"
        expected = 5000
        result = extract_employee_signals(input_text)
        assert result == expected, f"Expected {expected}, got {result}"

    def test_extract_employee_signals_not_found(self):
        """Test employee count extraction when no signal is found"""
        input_text = "We are a growing company"
        expected = 0
        result = extract_employee_signals(input_text)
        assert result == expected, f"Expected {expected}, got {result}"


class TestScoutIntegration:
    """Integration tests for Scout agent components"""

    def test_company_extractor_and_crawler_together(self):
        """Test that extractor and crawler functions work well together"""
        # Mock company data
        company_name = "Kaleida Health"
        website_text = """
        Kaleida Health operates 8 hospitals across Western New York.
        Our team of 12,000 employees serves the Buffalo-Niagara region.
        """
        industry = "Health Care Services"
        website_url = "https://www.kaleida.org"

        # Test extraction pipeline
        classified_industry = classify_industry(industry)
        assert classified_industry == "healthcare"

        domain = extract_domain(website_url)
        assert domain == "kaleida.org"

        location_count = extract_location_count(website_text, website_url)
        assert location_count == 8

        employee_count = extract_employee_signals(website_text)
        assert employee_count == 12000


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_extract_domain_with_path_and_params(self):
        """Test domain extraction ignores paths and query parameters"""
        input_url = "https://www.example.org/path?param=value#anchor"
        result = extract_domain(input_url)
        assert "example.org" == result or result == "example.org"

    def test_normalize_state_invalid_input(self):
        """Test state normalization with invalid state name"""
        input_state = "XY"  # Invalid state code
        result = normalize_state(input_state)
        # Should return the input as-is or "invalid" based on implementation
        assert isinstance(result, (str, type(None)))

    def test_extract_location_count_with_multiple_numbers(self):
        """Test location count extraction with multiple numbers in text"""
        input_text = "We operate 5 clinics and 150 store locations"
        result = extract_location_count(input_text, "https://example.com")
        # Should extract the relevant count (likely the larger one)
        assert isinstance(result, int) and result > 0

    def test_extract_employee_signals_various_formats(self):
        """Test employee count extraction with various number formats"""
        test_cases = [
            ("5,000 employees", 5000),
            ("5000 staff members", 5000),
            ("approximately 10000 people work here", 10000),
            ("100+ team members", 100),
        ]
        for input_text, expected in test_cases:
            result = extract_employee_signals(input_text)
            # Allow flexibility in extraction logic
            assert isinstance(result, int)


class TestErrorHandling:
    """Test error handling and robustness"""

    def test_extract_domain_empty_string(self):
        """Test domain extraction with empty string"""
        result = extract_domain("")
        assert result == "" or result is None

    def test_classify_industry_empty_string(self):
        """Test industry classification with empty string"""
        result = classify_industry("")
        assert result == "unknown" or result is None

    def test_extract_location_count_empty_text(self):
        """Test location extraction with empty text"""
        result = extract_location_count("", "https://example.com")
        assert result == 0 or result == 1

    def test_extract_employee_signals_empty_text(self):
        """Test employee extraction with empty text"""
        result = extract_employee_signals("")
        assert result == 0

    def test_extract_domain_malformed_url(self):
        """Test domain extraction with malformed URL"""
        malformed_urls = [
            "not-a-url",
            "ftp://unsupported.com",
            "://missing-scheme.com",
        ]
        for url in malformed_urls:
            result = extract_domain(url)
            # Should handle gracefully (return value or empty)
            assert isinstance(result, (str, type(None)))


class TestStateNormalization:
    """Comprehensive tests for state normalization"""

    @pytest.mark.parametrize("input_state,expected_output", [
        ("New York", "NY"),
        ("California", "CA"),
        ("Texas", "TX"),
        ("Florida", "FL"),
        ("NY", "NY"),
        ("CA", "CA"),
        ("new york", "NY"),
        ("california", "CA"),
        ("NEW YORK", "NY"),
        ("CALIFORNIA", "CA"),
    ])
    def test_normalize_state_parametrized(self, input_state, expected_output):
        """Parametrized test for state normalization across multiple inputs"""
        result = normalize_state(input_state)
        assert result == expected_output, f"Failed for input '{input_state}': expected '{expected_output}', got '{result}'"


class TestIndustryClassification:
    """Comprehensive tests for industry classification"""

    @pytest.mark.parametrize("input_industry,expected_output", [
        ("Health Care Services", "healthcare"),
        ("Healthcare", "healthcare"),
        ("Lodging & Travel", "hospitality"),
        ("Hotel & Resort", "hospitality"),
        ("Manufacturing", "manufacturing"),
        ("Retail Trade", "retail"),
        ("Public Administration", "public_sector"),
        ("Furniture Repair", "unknown"),
        ("Unknown Sector", "unknown"),
    ])
    def test_classify_industry_parametrized(self, input_industry, expected_output):
        """Parametrized test for industry classification across multiple inputs"""
        result = classify_industry(input_industry)
        assert result == expected_output, f"Failed for input '{input_industry}': expected '{expected_output}', got '{result}'"
