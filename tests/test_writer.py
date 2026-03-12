"""
Unit tests for Writer Agent modules (template_engine, tone_validator).

Purpose:
    Comprehensive test coverage for writer agent email template processing,
    dynamic content injection, and email tone/quality validation.

Dependencies:
    - pytest: Test runner and assertion library
    - unittest.mock: Mock and patch for test doubles
    - agents.writer.template_engine: TemplateEngine class
    - agents.writer.tone_validator: ToneValidator class

Usage:
    Run all tests:     pytest tests/test_writer.py -v
    Run single class:  pytest tests/test_writer.py::TestTemplateEngine -v
    Run single test:   pytest tests/test_writer.py::TestTemplateEngine::test_fill_static_fields_basic -v
    With coverage:     pytest tests/test_writer.py --cov=agents.writer --cov-report=html

Test Coverage:
    - TemplateEngine: Template filling, context building, industry template lookup
    - ToneValidator: Spam word detection, length validation, CTA detection, caps validation
    - Edge Cases: Missing fields, partial fills, various email lengths
    - Validation Rules: Tone compliance, spam score, professionalism checks
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.writer.template_engine import TemplateEngine
from agents.writer.tone_validator import ToneValidator


class TestTemplateEngine:
    """Test suite for TemplateEngine module."""

    def setup_method(self):
        """Initialize TemplateEngine instance for each test."""
        self.engine = TemplateEngine()

    def test_fill_static_fields_basic(self):
        """
        Test basic template field substitution.

        Input:
            template = "Hello {{contact_first_name}} from {{company_name}}"
            context = {
                'contact_first_name': 'John',
                'company_name': 'Kaleida Health'
            }

        Expected Output:
            "Hello John from Kaleida Health"
        """
        template = "Hello {{contact_first_name}} from {{company_name}}"
        context = {
            'contact_first_name': 'John',
            'company_name': 'Kaleida Health'
        }
        result = self.engine.fill_static_fields(template, context)
        assert result == "Hello John from Kaleida Health"

    def test_fill_static_fields_partial(self):
        """
        Test template filling with missing context values.

        Input:
            template = "Hello {{contact_first_name}} at {{company_name}} in {{state}}"
            context = {
                'contact_first_name': 'John',
                'company_name': 'Kaleida Health'
            }

        Expected Output:
            "Hello John at Kaleida Health in {{state}}"

        Verification: Unfilled placeholder {{state}} remains as-is
        """
        template = "Hello {{contact_first_name}} at {{company_name}} in {{state}}"
        context = {
            'contact_first_name': 'John',
            'company_name': 'Kaleida Health'
        }
        result = self.engine.fill_static_fields(template, context)
        assert result == "Hello John at Kaleida Health in {{state}}"
        assert "{{state}}" in result  # Verify unfilled placeholder remains

    def test_fill_static_fields_empty_context(self):
        """Test template filling with empty context (no substitutions)."""
        template = "Hello {{contact_first_name}} from {{company_name}}"
        context = {}
        result = self.engine.fill_static_fields(template, context)
        assert result == template
        assert "{{contact_first_name}}" in result

    def test_fill_static_fields_multiline(self):
        """Test template filling across multiple lines."""
        template = """Dear {{contact_first_name}},

We identified {{site_count}} facilities at {{company_name}}.

Best regards,
{{sender_name}}"""
        context = {
            'contact_first_name': 'Jane',
            'site_count': '8',
            'company_name': 'Kaleida Health',
            'sender_name': 'Troy Banks'
        }
        result = self.engine.fill_static_fields(template, context)
        assert "Jane" in result
        assert "8 facilities at Kaleida Health" in result
        assert "Troy Banks" in result

    def test_build_context_all_fields_present(self):
        """
        Test context builder with complete mock objects.

        Inputs: Mock company, features, score, contact, settings objects

        Expected Output: Dictionary containing all required keys:
            - contact_first_name
            - company_name
            - site_count
            - state
            - industry
            - savings_low_formatted
            - savings_high_formatted
            - savings_mid_formatted
            - tb_sender_name
            - tb_sender_title
            - tb_phone
            - unsubscribe_link

        Verification: No key is None or empty string
        """
        # Mock objects
        mock_company = Mock()
        mock_company.name = "Kaleida Health"
        mock_company.state = "NY"
        mock_company.website = "kaleida.org"

        mock_features = Mock()
        mock_features.site_count = 8
        mock_features.industry = "healthcare"

        mock_score = Mock()
        mock_score.savings_low_formatted = "$1.0M"
        mock_score.savings_mid_formatted = "$1.35M"
        mock_score.savings_high_formatted = "$1.7M"

        mock_contact = Mock()
        mock_contact.first_name = "John"
        mock_contact.email = "john@kaleida.org"

        mock_settings = Mock()
        mock_settings.TB_SENDER_NAME = "Troy Banks"
        mock_settings.TB_SENDER_TITLE = "VP of Growth"
        mock_settings.TB_PHONE = "(716) 555-0100"
        mock_settings.UNSUBSCRIBE_LINK = "https://www.troy-banks.io/unsubscribe"

        # Build context
        context = self.engine.build_context(
            company=mock_company,
            features=mock_features,
            score=mock_score,
            contact=mock_contact,
            settings=mock_settings
        )

        # Verify all required keys present and non-empty
        required_keys = [
            'contact_first_name',
            'company_name',
            'site_count',
            'state',
            'industry',
            'savings_low_formatted',
            'savings_high_formatted',
            'savings_mid_formatted',
            'tb_sender_name',
            'tb_sender_title',
            'tb_phone',
            'unsubscribe_link'
        ]

        for key in required_keys:
            assert key in context, f"Missing key: {key}"
            assert context[key] is not None, f"Key {key} is None"
            assert context[key] != "", f"Key {key} is empty string"

        # Verify correct values
        assert context['contact_first_name'] == "John"
        assert context['company_name'] == "Kaleida Health"
        assert context['site_count'] == 8
        assert context['state'] == "NY"
        assert context['industry'] == "healthcare"

    def test_get_template_for_industry_healthcare(self):
        """Test template lookup for healthcare industry."""
        template_path = self.engine.get_template_for_industry('healthcare')
        assert template_path.endswith('email_healthcare.txt')

    def test_get_template_for_industry_hospitality(self):
        """Test template lookup for hospitality industry."""
        template_path = self.engine.get_template_for_industry('hospitality')
        assert template_path.endswith('email_hospitality.txt')

    def test_get_template_for_industry_manufacturing(self):
        """Test template lookup for manufacturing industry."""
        template_path = self.engine.get_template_for_industry('manufacturing')
        assert template_path.endswith('email_manufacturing.txt')

    def test_get_template_for_industry_retail(self):
        """Test template lookup for retail industry."""
        template_path = self.engine.get_template_for_industry('retail')
        assert template_path.endswith('email_retail.txt')

    def test_get_template_for_industry_public_sector(self):
        """Test template lookup for public sector industry."""
        template_path = self.engine.get_template_for_industry('public_sector')
        assert template_path.endswith('email_public_sector.txt')

    def test_get_template_for_industry_all_industries(self):
        """Test template lookup for all supported industries."""
        industries_and_paths = {
            'healthcare': 'email_healthcare.txt',
            'hospitality': 'email_hospitality.txt',
            'manufacturing': 'email_manufacturing.txt',
            'retail': 'email_retail.txt',
            'public_sector': 'email_public_sector.txt',
        }

        for industry, expected_filename in industries_and_paths.items():
            template_path = self.engine.get_template_for_industry(industry)
            assert expected_filename in template_path, \
                f"Industry {industry} returned wrong template path: {template_path}"


class TestToneValidator:
    """Test suite for ToneValidator module."""

    def setup_method(self):
        """Initialize ToneValidator instance for each test."""
        self.validator = ToneValidator()

    def test_validate_tone_passing_email(self):
        """
        Test email that passes all tone validation checks.

        Input:
            subject = "Potential utility savings for Kaleida Health"
            body = Valid 150-word professional email with CTA

        Expected Output:
            - passed = True
            - issues = empty list
            - score = 10
        """
        subject = "Potential utility savings for Kaleida Health"
        body = """Hi John,

We recently identified that Kaleida Health operates eight facilities across Western New York with 
significant utility and telecom spending. Our analysis suggests there are substantial cost recovery 
opportunities available through audit and optimization.

Troy Banks specializes in helping healthcare organizations like yours identify and realize these savings. 
We've helped similar facilities recover between $1M-$2M annually.

Would you be open to a brief call next week to discuss the potential savings for Kaleida Health?

Best regards,
Troy Banks
VP of Growth"""

        result = self.validator.validate_tone(subject=subject, body=body)

        assert result['passed'] is True
        assert isinstance(result['issues'], list)
        assert len(result['issues']) == 0
        assert result['score'] == 10

    def test_check_spam_words_found(self):
        """
        Test spam word detection when offensive words are present.

        Input: "This is a guaranteed free offer — act now"

        Expected Output: List containing: ["guaranteed", "free", "act now"]
        """
        text = "This is a guaranteed free offer — act now"
        spam_words = self.validator.check_spam_words(text)
        
        assert isinstance(spam_words, list)
        assert len(spam_words) > 0
        assert any("guaranteed" in word.lower() for word in spam_words)
        assert any("free" in word.lower() for word in spam_words)
        assert any("act now" in word.lower() for word in spam_words)

    def test_check_spam_words_clean(self):
        """
        Test spam word detection on clean text.

        Input: "We help organizations reduce utility costs"

        Expected Output: Empty list (no spam words)
        """
        text = "We help organizations reduce utility costs"
        spam_words = self.validator.check_spam_words(text)
        
        assert isinstance(spam_words, list)
        assert len(spam_words) == 0

    def test_check_length_too_long(self):
        """
        Test email body length validation when too long.

        Input: String with 300 words

        Expected Output: "Email too long: 300 words. Max 250."
        """
        # Generate 300-word body
        words = ["word"] * 300
        body = " ".join(words)
        
        error_msg = self.validator.check_length(body)
        
        assert error_msg is not None
        assert "too long" in error_msg.lower()
        assert "300" in error_msg
        assert "250" in error_msg

    def test_check_length_too_short(self):
        """
        Test email body length validation when too short.

        Input: String with 30 words

        Expected Output: "Email too short: 30 words. Min 50."
        """
        # Generate 30-word body
        words = ["word"] * 30
        body = " ".join(words)
        
        error_msg = self.validator.check_length(body)
        
        assert error_msg is not None
        assert "too short" in error_msg.lower()
        assert "30" in error_msg
        assert "50" in error_msg

    def test_check_length_valid(self):
        """
        Test email body length validation when length is acceptable.

        Input: String with 150 words

        Expected Output: None (no error)
        """
        # Generate 150-word body
        words = ["word"] * 150
        body = " ".join(words)
        
        error_msg = self.validator.check_length(body)
        
        assert error_msg is None

    def test_check_cta_present_found(self):
        """
        Test call-to-action detection when CTA is present.

        Input: "Would you be open to schedule a call?"

        Expected Output: None (CTA found, no error)
        """
        body = "Would you be open to schedule a call?"
        error_msg = self.validator.check_cta(body)
        
        assert error_msg is None

    def test_check_cta_missing(self):
        """
        Test call-to-action detection when CTA is missing.

        Input: "We are a great company with good services."

        Expected Output: "No call to action found in email body"
        """
        body = "We are a great company with good services."
        error_msg = self.validator.check_cta(body)
        
        assert error_msg is not None
        assert "no call to action" in error_msg.lower()

    def test_check_caps_too_many(self):
        """
        Test all-caps word detection when too many are present.

        Input: "FREE SAVINGS GUARANTEED TODAY AVAILABLE NOW URGENT"

        Expected Output: "Too many all-caps words: may trigger spam filters"
        """
        body = "FREE SAVINGS GUARANTEED TODAY AVAILABLE NOW URGENT"
        error_msg = self.validator.check_caps(body)
        
        assert error_msg is not None
        assert "too many all-caps" in error_msg.lower()
        assert "spam" in error_msg.lower()

    def test_check_caps_acceptable(self):
        """
        Test all-caps word detection when limited caps are present.

        Input: "Troy & Banks is based in NY and Buffalo"

        Expected Output: None (acceptable caps usage)
        """
        body = "Troy & Banks is based in NY and Buffalo"
        error_msg = self.validator.check_caps(body)
        
        assert error_msg is None

    def test_check_caps_proper_nouns(self):
        """Test that proper nouns in caps don't trigger spam flag."""
        body = "John Smith from ACME Corporation called today."
        error_msg = self.validator.check_caps(body)
        
        # Should not flag reasonable number of caps
        # (depends on implementation threshold)
        assert error_msg is None or "acceptable" in error_msg.lower()


class TestToneValidatorEdgeCases:
    """Edge case tests for tone validation."""

    def setup_method(self):
        """Initialize ToneValidator instance for each test."""
        self.validator = ToneValidator()

    def test_check_length_boundary_exactly_50(self):
        """Test length check at exact minimum boundary (50 words)."""
        body = " ".join(["word"] * 50)
        error_msg = self.validator.check_length(body)
        assert error_msg is None

    def test_check_length_boundary_exactly_250(self):
        """Test length check at exact maximum boundary (250 words)."""
        body = " ".join(["word"] * 250)
        error_msg = self.validator.check_length(body)
        assert error_msg is None

    def test_check_cta_variations(self):
        """Test CTA detection with various phrasing."""
        cta_variations = [
            "Would you be interested in learning more?",
            "Are you open to a conversation about this?",
            "Let me know if you'd like to discuss further.",
            "Can we schedule a brief call?",
            "I'd love to connect with you about this opportunity.",
        ]

        for cta_text in cta_variations:
            error_msg = self.validator.check_cta(cta_text)
            assert error_msg is None, f"Failed to detect CTA: {cta_text}"

    def test_spam_words_case_insensitive(self):
        """Test that spam word detection is case-insensitive."""
        variations = [
            "This is GUARANTEED to work",
            "guaranteed results",
            "Guaranteed SAVINGS",
            "GUARANTEED",
        ]

        for text in variations:
            spam_words = self.validator.check_spam_words(text)
            assert len(spam_words) > 0, f"Failed to detect spam word in: {text}"

    def test_validate_tone_multiple_issues(self):
        """Test tone validation that catches multiple issues."""
        subject = "FREE MONEY NOW!!!!"
        body = "This is great."  # Too short
        
        result = self.validator.validate_tone(subject=subject, body=body)
        
        assert result['passed'] is False
        assert len(result['issues']) > 0


class TestTemplateEngineIntegration:
    """Integration tests for template engine."""

    def setup_method(self):
        """Initialize TemplateEngine instance for each test."""
        self.engine = TemplateEngine()

    def test_end_to_end_template_fill(self):
        """Test complete flow: build context, get template, fill template."""
        # Build mock objects
        mock_company = Mock()
        mock_company.name = "Kaleida Health"
        mock_company.state = "NY"
        mock_company.website = "kaleida.org"

        mock_features = Mock()
        mock_features.site_count = 8
        mock_features.industry = "healthcare"

        mock_score = Mock()
        mock_score.savings_low_formatted = "$1.0M"
        mock_score.savings_mid_formatted = "$1.35M"
        mock_score.savings_high_formatted = "$1.7M"

        mock_contact = Mock()
        mock_contact.first_name = "John"
        mock_contact.email = "john@kaleida.org"

        mock_settings = Mock()
        mock_settings.TB_SENDER_NAME = "Troy Banks"
        mock_settings.TB_SENDER_TITLE = "VP of Growth"
        mock_settings.TB_PHONE = "(716) 555-0100"
        mock_settings.UNSUBSCRIBE_LINK = "https://www.troy-banks.io/unsubscribe"

        # Build context
        context = self.engine.build_context(
            company=mock_company,
            features=mock_features,
            score=mock_score,
            contact=mock_contact,
            settings=mock_settings
        )

        # Get template
        template_path = self.engine.get_template_for_industry('healthcare')
        assert 'email_healthcare.txt' in template_path

        # Simulate template fill
        test_template = "Hello {{contact_first_name}} at {{company_name}}"
        filled = self.engine.fill_static_fields(test_template, context)
        assert "John" in filled
        assert "Kaleida Health" in filled


class TestParametrizedValidation:
    """Parametrized tests for various validation scenarios."""

    @pytest.mark.parametrize("word_count,should_pass", [
        (30, False),    # Too short
        (50, True),     # Minimum boundary
        (100, True),    # Normal
        (150, True),    # Normal
        (250, True),    # Maximum boundary
        (300, False),   # Too long
    ])
    def test_length_validation_comprehensive(self, word_count, should_pass):
        """
        Parametrized test for email length validation across all boundaries.
        """
        validator = ToneValidator()
        body = " ".join(["word"] * word_count)
        error_msg = validator.check_length(body)
        
        if should_pass:
            assert error_msg is None, f"Word count {word_count} should pass"
        else:
            assert error_msg is not None, f"Word count {word_count} should fail"

    @pytest.mark.parametrize("industry,filename", [
        ('healthcare', 'email_healthcare.txt'),
        ('hospitality', 'email_hospitality.txt'),
        ('manufacturing', 'email_manufacturing.txt'),
        ('retail', 'email_retail.txt'),
        ('public_sector', 'email_public_sector.txt'),
    ])
    def test_template_lookup_all_industries(self, industry, filename):
        """Parametrized test for template lookup across all industries."""
        engine = TemplateEngine()
        template_path = engine.get_template_for_industry(industry)
        assert filename in template_path, \
            f"Expected {filename} for {industry}, got {template_path}"

    @pytest.mark.parametrize("test_phrase,should_detect_cta", [
        ("Would you be open to a call?", True),
        ("Let's schedule a meeting", True),
        ("Can we discuss this?", True),
        ("We are a great company", False),
        ("Our services are excellent", False),
        ("Here's our pricing information", False),
    ])
    def test_cta_detection_variations(self, test_phrase, should_detect_cta):
        """Parametrized test for CTA detection with various phrases."""
        validator = ToneValidator()
        error_msg = validator.check_cta(test_phrase)
        
        if should_detect_cta:
            assert error_msg is None, f"Should detect CTA in: {test_phrase}"
        else:
            assert error_msg is not None, f"Should not detect CTA in: {test_phrase}"
