# Test Suite

Unit tests for the Utility Lead Platform agents and services.

## Directory Structure

```
tests/
├── test_scout.py           # Scout agent tests (company extraction, web crawling)
├── test_analyst.py         # Analyst agent tests (spend, savings, scoring calculations)
├── test_writer.py          # Writer agent tests (template engine, tone validation)
├── test_outreach.py        # Outreach agent tests (email sending, followups, sequences)
├── test_tracker.py         # Tracker agent tests (webhook parsing, reply classification, status updates)
├── test_api.py             # API integration tests (leads, emails, pipeline, triggers, reports)
└── README.md               # This file
```

## Test Suite Overview

### test_writer.py

**Purpose**: Unit tests for Writer agent modules (email template processing and tone validation)

**Test Classes**:

1. **TestTemplateEngine** (11 tests + 1 integration)
   - `test_fill_static_fields_basic`: Basic {{variable}} substitution (Hello {{name}} → Hello John)
   - `test_fill_static_fields_partial`: Template with missing context (unfilled placeholders preserved)
   - `test_fill_static_fields_empty_context`: No substitutions with empty context
   - `test_fill_static_fields_multiline`: Multi-line template filling across sections
   - `test_build_context_all_fields_present`: Full context dict with 12 required keys (contact name, company, savings, sender info, etc.)
   - `test_get_template_for_industry_healthcare`: Templates/email_healthcare.txt lookup
   - `test_get_template_for_industry_hospitality`: Templates/email_hospitality.txt lookup
   - `test_get_template_for_industry_manufacturing`: Templates/email_manufacturing.txt lookup
   - `test_get_template_for_industry_retail`: Templates/email_retail.txt lookup
   - `test_get_template_for_industry_public_sector`: Templates/email_public_sector.txt lookup
   - `test_get_template_for_industry_all_industries`: Parametrized test across all 5 industries

2. **TestToneValidator** (10 core tests)
   - `test_validate_tone_passing_email`: Full validation passes (score=10, passed=True, no issues)
   - `test_check_spam_words_found`: Detects ["guaranteed", "free", "act now"] in text
   - `test_check_spam_words_clean`: No spam words detected in professional text
   - `test_check_length_too_long`: 300-word email rejected (max 250)
   - `test_check_length_too_short`: 30-word email rejected (min 50)
   - `test_check_length_valid`: 150-word email passes length check
   - `test_check_cta_present_found`: Detects "Would you be open to schedule a call?"
   - `test_check_cta_missing`: Flags email without call-to-action
   - `test_check_caps_too_many`: Detects excessive all-caps words (FREE, GUARANTEED, etc.)
   - `test_check_caps_acceptable`: Allows reasonable caps (NY, ACME Corp, proper nouns)

3. **TestToneValidatorEdgeCases** (5 edge case tests)
   - Exact boundary tests (50 words min, 250 words max)
   - CTA detection variations (multiple phrasing styles)
   - Case-insensitive spam word detection
   - Multiple validation issues caught together

4. **TestTemplateEngineIntegration** (1 integration test)
   - End-to-end flow: build context → get template → fill template

5. **Parametrized Test Suites** (3 parametrized)
   - `TestParametrizedValidation.test_length_validation_comprehensive`: 6 word count variations (30, 50, 100, 150, 250, 300)
   - `TestParametrizedValidation.test_template_lookup_all_industries`: All 5 industries
   - `TestParametrizedValidation.test_cta_detection_variations`: 6 CTA phrase variations

**Total**: 35+ test cases

### test_analyst.py

**Purpose**: Unit tests for Analyst agent modules (spend calculations, savings estimates, lead scoring)

**Test Classes**:

1. **TestSpendCalculator** (5 tests)
   - `test_calculate_utility_spend_healthcare`: 8 sites × 150k × 25x multiplier × 0.19 NY rate = $5.7M
   - `test_calculate_telecom_spend`: Telecom spend based on employee count (5000 × 1200 = $6M)
   - `test_calculate_total_spend`: Total spend aggregation (utility + telecom)
   - `test_get_electricity_rate_ny`: State-specific electricity rate ($0.19 for NY)
   - `test_get_electricity_rate_default`: Fallback to default rate ($0.12 for unknown state)

2. **TestSavingsCalculator** (6 tests)
   - `test_calculate_savings_low`: Low-tier savings (10% of spend)
   - `test_calculate_savings_mid`: Mid-tier savings (13.5% of spend)
   - `test_calculate_savings_high`: High-tier savings (17% of spend)
   - `test_calculate_tb_revenue`: Troy Banks revenue projection (24% of mid savings)
   - `test_format_savings_millions`: Large amounts formatted as "$1.5M"
   - `test_format_savings_thousands`: Moderate amounts formatted as "$500k"

3. **TestScoreEngine** (8 tests)
   - `test_score_recovery_high`: High savings (>$2M) receives max recovery score
   - `test_score_recovery_medium`: Mid-range savings ($300k-$1M) receives moderate score
   - `test_score_industry_healthcare`: Healthcare industry high-priority score
   - `test_score_industry_unknown`: Unknown industry receives zero score
   - `test_assign_tier_high`: Score ≥70 assigned as 'high' tier
   - `test_assign_tier_medium`: Score 50-69 assigned as 'medium' tier
   - `test_assign_tier_low`: Score <50 assigned as 'low' tier
   - `test_compute_score_full`: Full composite scoring with 5 parameters returns 0-100 float

4. **TestAnalystIntegration** (2 integration tests)
   - `test_end_to_end_spend_and_savings`: Full workflow for 8-site healthcare facility (NY, 5k employees)
   - `test_low_priority_lead_workflow`: Full workflow for small 2-site retail facility

5. **TestEdgeCases** (5 edge case tests)
   - Zero spend leads to zero savings
   - Score boundary conditions (exactly 70, exactly 50)
   - Large employee count calculations
   - Multiple state rate lookups

6. **TestParametrizedCalculations** (4 parametrized test suites)
   - Site count multiplier effect (1, 5, 10, 50 sites)
   - Savings percentage variations (10%, 13.5%, 17% across multiple spend levels)
   - Recovery score to tier mapping (multiple savings values)
   - Industry scoring variations (healthcare, hospitality, manufacturing, etc.)

**Total**: 30+ test cases

### test_scout.py

**Purpose**: Unit tests for Scout agent modules (company discovery and qualification)

**Test Classes**:

1. **TestCompanyExtractor** (7 tests)
   - `test_classify_industry_healthcare`: Healthcare classification
   - `test_classify_industry_hospitality`: Hospitality classification
   - `test_classify_industry_unknown`: Unknown/unmapped industry handling
   - `test_extract_domain_full_url`: Domain extraction with www prefix
   - `test_extract_domain_no_www`: Domain extraction without www
   - `test_normalize_state_full_name`: State name to abbreviation
   - `test_normalize_state_already_code`: Already-abbreviated state handling
   - `test_normalize_state_lowercase`: Lowercase state normalization

2. **TestWebsiteCrawler** (5 tests)
   - `test_extract_location_count_hospitals`: Multi-location mentions (hospitals)
   - `test_extract_location_count_stores`: Store location count extraction
   - `test_extract_location_count_none_found`: Default count when not found
   - `test_extract_employee_signals_found`: Employee count extraction
   - `test_extract_employee_signals_not_found`: Handling missing signals

3. **TestScoutIntegration** (1 integration test)
   - `test_company_extractor_and_crawler_together`: End-to-end component integration

4. **TestEdgeCases** (4 edge case tests)
   - Domain extraction with paths and parameters
   - Invalid state handling
   - Multiple numbers in location text
   - Various employee count number formats

5. **TestErrorHandling** (6 robustness tests)
   - Empty string handling across all methods
   - Malformed URL handling

6. **TestStateNormalization** (1 parametrized test covering 10 cases)
   - Multiple state name and code combinations

7. **TestIndustryClassification** (1 parametrized test covering 9 cases)
   - Multiple industry name mappings

**Total**: 35+ test cases

### test_outreach.py

**Purpose**: Unit tests for Outreach agent modules (email sending, followup scheduling, sequence management)

**Test Classes**:

1. **TestEmailSender** (7 tests)
   - `test_add_unsubscribe_footer`: Appends unsubscribe text to email body
   - `test_select_provider_sendgrid`: Provider selection returns 'sendgrid'
   - `test_select_provider_instantly`: Provider selection returns 'instantly'
   - `test_check_daily_limit_within`: 20/50 emails sent, within_limit=True, remaining=30
   - `test_check_daily_limit_exceeded`: 55/50 emails sent, within_limit=False, remaining=0
   - `test_check_daily_limit_exactly_at_limit`: 50/50 emails, cannot send more
   - `test_send_email_skips_unsubscribed`: Unsubscribed contacts return success=False

2. **TestFollowupScheduler** (6 tests)
   - `test_schedule_followups_creates_three`: Scheduling creates 3 followup records (1, 2, 3)
   - `test_schedule_followup_dates`: Date calculations correct (+3, +7, +14 days from send_date)
   - `test_cancel_followups`: All 3 followups marked as cancelled_followup
   - `test_get_due_followups_today`: Returns followups with next_followup_date = today
   - `test_get_due_followups_future_excluded`: Tomorrow's followup not included in due list
   - `test_get_due_followups_past_included`: Overdue followups (from past) included in list

3. **TestSequenceManager** (4 tests)
   - `test_build_followup_subject_day1`: Prefixes original subject with "Re:"
   - `test_build_followup_subject_day3`: Final followup has distinct language
   - `test_build_followup_subject_day2`: Second followup varies from original/first
   - `test_get_followup_template_returns_string`: Loads template with {{placeholder}} syntax

4. **TestOutreachIntegration** (2 integration tests)
   - `test_end_to_end_email_and_schedule`: Send email, then schedule 3 followups
   - `test_buildup_followup_sequence`: Build complete subjects for all 3 followups

5. **TestEdgeCases** (4 edge case tests)
   - Zero daily email limit
   - Add footer to empty body
   - Schedule followups with zero day offsets
   - Handle invalid followup numbers

6. **TestParametrizedOutreach** (3 parametrized test suites)
   - Provider selection (sendgrid, instantly)
   - Daily limit boundaries (0, 10, 49, 50, 55 emails)
   - Followup subject markers (all followups have "Re:" or variation)

**Total**: 40+ test cases

### test_tracker.py

**Purpose**: Unit tests for Tracker agent modules (webhook event parsing, reply classification, and lead/contact status management)

**Test Classes**:

1. **TestWebhookListener** (8 tests)
   - `test_parse_sendgrid_event_open`: `{"event": "open"}` → `{event_type: "opened", email, message_id}`
   - `test_parse_sendgrid_event_reply`: `{"event": "inbound"}` → `{event_type: "replied", reply_content}`
   - `test_parse_sendgrid_event_bounce`: `{"event": "bounce"}` → `{event_type: "bounced"}`
   - `test_parse_multiple_events`: Array of 3 event types → list of 3 normalized dicts
   - `test_extract_reply_strips_quoted`: Reply with `> quoted lines` → cleaned reply text only
   - `test_parse_empty_payload`: Empty array `[]` → returns empty list
   - `test_parse_invalid_json`: Non-JSON string → returns empty list
   - `test_event_type_mapping_unsubscribe`: `"unsubscribe"` → `"unsubscribed"`

2. **TestReplyClassifier** (10 tests)
   - `test_classify_positive_meeting_request`: "can we schedule a call" → `{sentiment: "positive", intent: "wants_meeting"}`
   - `test_classify_positive_info_request`: "send me more information" → `{sentiment: "positive", intent: "wants_info"}`
   - `test_classify_negative_not_interested`: "remove me from your list" → `{sentiment: "negative", intent: "unsubscribe"}`
   - `test_classify_negative_has_provider`: "happy with current energy provider" → `{sentiment: "negative", intent: "not_interested"}`
   - `test_rule_based_classify_fallback`: LLM connector mocked to None, fallback to keyword rules
   - `test_should_alert_positive`: `(positive, wants_meeting)` → True
   - `test_should_alert_negative`: `(negative, not_interested)` → False
   - `test_should_alert_unsubscribe`: `(negative, unsubscribe)` → False
   - `test_classify_returns_required_fields`: Result always has sentiment/intent/confidence keys
   - `test_rule_based_classify_direct`: Direct rule-based classification without LLM

3. **TestStatusUpdater** (5 tests)
   - `test_update_lead_status_valid`: `new_status="contacted"` → True, companies table updated
   - `test_update_lead_status_invalid`: `new_status="invalid_status"` → raises `ValueError`
   - `test_mark_replied_cancels_followups`: Reply → status='replied', `cancel_followups` called, outreach_event created
   - `test_mark_unsubscribed_flags_contact`: `contact_id` → `contacts.unsubscribed=True`, followups cancelled
   - `test_mark_bounced_invalidates_contact`: `contact_id` → `contacts.verified=False`, bounced event inserted (2+ DB calls)

4. **TestTrackerIntegration** (2 integration tests)
   - `test_webhook_to_classifier_pipeline`: Parse reply webhook → classify reply content
   - `test_classify_and_alert_routing`: Classify positive reply → should_alert=True; negative → should_alert=False

5. **TestEdgeCases** (5 edge case tests)
   - Empty reply classification
   - Large (100-sentence) reply classification
   - Unknown SendGrid event type passed through unchanged
   - Status update for non-existent company returns False
   - Reply strip preserves actual reply text, removes `>` quoted lines

6. **TestParametrizedTracker** (3 parametrized test suites)
   - `test_event_type_normalization`: All 5 SendGrid event mappings (open, click, bounce, unsubscribe, inbound)
   - `test_rule_based_classification_variations`: 4 reply text / sentiment / intent combinations
   - `test_should_alert_variations`: 5 sentiment/intent combinations
   - `test_valid_status_values`: 8 status values (5 valid + 3 invalid)

**Total**: 30+ test cases

## Running Tests

### test_api.py

**Purpose**: Integration tests for all FastAPI routes using `TestClient`. All database calls are replaced with mock sessions; `pipeline_monitor`, `report_generator`, and orchestrator functions are patched per test.

**Test Classes**:

1. **TestLeadRoutes** (7 tests)
   - `test_get_leads_returns_list`: `GET /leads` → 200, response has `leads` array and `total_count` integer
   - `test_get_leads_filter_by_industry`: `GET /leads?industry=healthcare` → all returned leads have `industry='healthcare'`
   - `test_get_leads_filter_by_tier`: `GET /leads?tier=high` → all returned leads have `tier='high'`
   - `test_get_lead_by_id_found`: `GET /leads/{id}` → 200, response `company_id` matches requested id
   - `test_get_lead_by_id_not_found`: `GET /leads/00000000-...` → 404 when no company exists
   - `test_approve_lead`: `PATCH /leads/{id}/approve` → 200, `lead_scores.approved_human=true` SQL executed
   - `test_reject_lead`: `PATCH /leads/{id}/reject` → 200, `companies.status='archived'` SQL executed

2. **TestEmailRoutes** (3 tests)
   - `test_get_pending_emails`: `GET /emails/pending` → 200, all drafts have `approved_human=false`
   - `test_approve_email`: `PATCH /emails/{id}/approve` → 200, `approved_human` SQL executed and committed
   - `test_edit_email`: `PATCH /emails/{id}/edit` → 200, `subject_line` and `edited_human` SQL executed

3. **TestPipelineRoutes** (2 tests)
   - `test_pipeline_status_returns_all_stages`: `GET /pipeline/status` → 200, all 11 stage keys present (`new`…`archived`)
   - `test_pipeline_health_returns_services`: `GET /pipeline/health` → 200, all 7 service keys present (postgres…slack)

4. **TestTriggerRoutes** (3 tests)
   - `test_trigger_scout_returns_immediately`: `POST /trigger/scout` → 200, response has `trigger_id` UUID and `status='started'`
   - `test_trigger_invalid_industry`: `POST /trigger/full {industry: invalid_industry}` → 422
   - `test_trigger_count_too_high`: `POST /trigger/scout {count: 999}` → 422

5. **TestReportRoutes** (3 tests)
   - `test_health_endpoint`: `GET /health` → 200, `status='ok'`, `service`, `version='1.0.0'`, `timestamp` present
   - `test_weekly_report_custom_date_range`: `GET /reports/weekly?start_date=2026-02-01&end_date=2026-02-28` → `period_start/end` match
   - `test_funnel_report_has_all_stages`: `GET /reports/funnel` → funnel contains `new`, `scored`, `contacted`, `replied`, `meeting_booked`; each item has `count` and `drop_off_from_prev_pct`

6. **TestApiEdgeCases** (7 edge case tests)
   - Empty DB scenarios, 404 on missing resources, invalid UUID path params, trigger count below minimum

7. **TestParametrizedApi** (3 parametrized test suites)
   - `test_valid_industry_filter`: All 5 valid industries return 200
   - `test_trigger_validation_cases`: 4 request body variations (valid, bad industry, count too high, count too low)
   - `test_valid_tier_filter`: All 3 valid tier values return 200 with correctly filtered leads

**Total**: 35+ test cases

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-cov

# Or from requirements.txt
pip install -r requirements.txt
```

### Run All Tests

```bash
# From project root
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=agents --cov-report=html
```

### Run Scout Tests Only

```bash
pytest tests/test_scout.py -v
```

### Run Analyst Tests Only

```bash
pytest tests/test_analyst.py -v
```

### Run Writer Tests Only

```bash
pytest tests/test_writer.py -v
```

### Run Outreach Tests Only

```bash
pytest tests/test_outreach.py -v
```

### Run Tracker Tests Only

```bash
pytest tests/test_tracker.py -v
```

### Run API Tests Only

```bash
pytest tests/test_api.py -v
```

### Run Specific Test Class

```bash
# Scout: CompanyExtractor tests
pytest tests/test_scout.py::TestCompanyExtractor -v

# Analyst: SpendCalculator tests
pytest tests/test_analyst.py::TestSpendCalculator -v

# Writer: TemplateEngine tests
pytest tests/test_writer.py::TestTemplateEngine -v

# Writer: ToneValidator tests
pytest tests/test_writer.py::TestToneValidator -v

# Outreach: EmailSender tests
pytest tests/test_outreach.py::TestEmailSender -v

# Outreach: FollowupScheduler tests
pytest tests/test_outreach.py::TestFollowupScheduler -v

# Tracker: WebhookListener tests
pytest tests/test_tracker.py::TestWebhookListener -v

# Tracker: ReplyClassifier tests
pytest tests/test_tracker.py::TestReplyClassifier -v

# Tracker: StatusUpdater tests
pytest tests/test_tracker.py::TestStatusUpdater -v
```

# API: LeadRoutes tests
pytest tests/test_api.py::TestLeadRoutes -v

# API: EmailRoutes tests
pytest tests/test_api.py::TestEmailRoutes -v

# API: PipelineRoutes tests
pytest tests/test_api.py::TestPipelineRoutes -v

# API: TriggerRoutes tests
pytest tests/test_api.py::TestTriggerRoutes -v

# API: ReportRoutes tests
pytest tests/test_api.py::TestReportRoutes -v
```

### Run Specific Test Method

```bash
# Scout example
pytest tests/test_scout.py::TestCompanyExtractor::test_classify_industry_healthcare -v

# Analyst example
pytest tests/test_analyst.py::TestSpendCalculator::test_calculate_utility_spend_healthcare -v

# Writer example: Template fill
pytest tests/test_writer.py::TestTemplateEngine::test_fill_static_fields_basic -v

# Writer example: Tone validation
pytest tests/test_writer.py::TestToneValidator::test_validate_tone_passing_email -v

# Outreach example: Email sender
pytest tests/test_outreach.py::TestEmailSender::test_add_unsubscribe_footer -v

# Outreach example: Followup scheduling
pytest tests/test_outreach.py::TestFollowupScheduler::test_schedule_followups_creates_three -v

# Tracker example: Webhook parsing
pytest tests/test_tracker.py::TestWebhookListener::test_parse_sendgrid_event_open -v

# Tracker example: Reply classification
pytest tests/test_tracker.py::TestReplyClassifier::test_classify_positive_meeting_request -v

# Tracker example: Status update
pytest tests/test_tracker.py::TestStatusUpdater::test_update_lead_status_valid -v

# API example: Get leads list
pytest tests/test_api.py::TestLeadRoutes::test_get_leads_returns_list -v

# API example: Approve lead
pytest tests/test_api.py::TestLeadRoutes::test_approve_lead -v

# API example: Health endpoint
pytest tests/test_api.py::TestReportRoutes::test_health_endpoint -v
```

### Run with Output

```bash
# Show print statements
pytest tests/test_scout.py -v -s

# Show test execution time
pytest tests/test_scout.py -v --durations=10
```

## Test Coverage

### Current Coverage (test_scout.py)

| Module | Classes | Methods | Test Cases | Coverage |
|--------|---------|---------|------------|----------|
| scout.company_extractor | CompanyExtractor | 3 | 15+ | TBD |
| scout.website_crawler | WebsiteCrawler | 2 | 20+ | TBD |

### Generate Coverage Report

```bash
# HTML coverage report
pytest tests/test_scout.py --cov=agents/scout --cov-report=html --cov-report=term

# View in browser
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
```

## Writing New Tests

### Test Structure Template

```python
import pytest
from agents.scout.company_extractor import CompanyExtractor

class TestMyFeature:
    """Tests for a specific feature"""
    
    def setup_method(self):
        """Run before each test"""
        self.extractor = CompanyExtractor()
    
    def teardown_method(self):
        """Run after each test"""
        pass
    
    def test_something_works(self):
        """Descriptive test name"""
        # Arrange
        input_data = "test_input"
        expected = "expected_output"
        
        # Act
        result = self.extractor.some_method(input_data)
        
        # Assert
        assert result == expected
    
    @pytest.mark.parametrize("input,expected", [
        ("case1", "result1"),
        ("case2", "result2"),
    ])
    def test_parametrized(self, input, expected):
        """Test with multiple input cases"""
        result = self.extractor.some_method(input)
        assert result == expected
```

### Naming Conventions

- Test files: `test_<module_name>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<specific_case>`
- Use descriptive names that explain what is being tested

### Best Practices

1. **One assertion per test** (or group related assertions)
2. **Clear setup/teardown** (use fixtures or setup_method)
3. **Parametrize repetitive tests** (avoid copy-paste)
4. **Test edge cases** (empty inputs, invalid data, boundaries)
5. **Test error handling** (exceptions, error cases)
6. **Use descriptive docstrings** (explain what and why)

## Mocking

For testing with external dependencies (APIs, databases), use `unittest.mock`:

```python
from unittest.mock import Mock, patch, MagicMock

class TestWithMocking:
    @patch('agents.scout.website_crawler.requests.get')
    def test_crawl_website(self, mock_get):
        """Test website crawling with mocked HTTP request"""
        # Arrange
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html>...</html>"
        
        # Act
        crawler = WebsiteCrawler()
        result = crawler.crawl("https://example.com")
        
        # Assert
        assert result is not None
        mock_get.assert_called_once()
```

## CI/CD Integration

### GitHub Actions (Recommended)

Create `.github/workflows/tests.yml`:

```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --cov=agents --cov-report=xml
      - uses: codecov/codecov-action@v2
```

### Local Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
pytest tests/ -v
if [ $? -ne 0 ]; then
  echo "Tests failed. Commit aborted."
  exit 1
fi
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'agents'`

**Solution**: Ensure tests are run from project root:
```bash
cd /path/to/utility-lead-platform
pytest tests/test_scout.py -v
```

### tests as a Package

If pytest can't find modules, create `tests/__init__.py`:
```bash
touch tests/__init__.py
```

### Fixture Issues

**Problem**: `fixture 'some_fixture' not found`

**Solution**: Use `setup_method()` or define fixtures in `conftest.py`:
```python
# tests/conftest.py
import pytest
from agents.scout.company_extractor import CompanyExtractor

@pytest.fixture
def company_extractor():
    """Fixture providing CompanyExtractor instance"""
    return CompanyExtractor()
```

Then use in tests:
```python
def test_something(company_extractor):
    result = company_extractor.classify_industry("Healthcare")
    assert result == "healthcare"
```

## Test Maintenance

### Updating Tests

When agent code changes:
1. Run tests to identify failures: `pytest tests/ -v`
2. Update test assertions to match new behavior
3. Add new tests for new features
4. Document changes in commit message

### Test Review Checklist

- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] Coverage meets baseline (aim for >80%): `pytest --cov`
- [ ] Edge cases covered (empty, null, invalid)
- [ ] Error cases tested (exceptions, failures)
- [ ] Test names are descriptive
- [ ] Docstrings explain test purpose
- [ ] No hardcoded paths or credentials in tests
- [ ] Parametrized tests used for multiple cases

## Future Test Suites

### test_analyst.py (Planned)

Tests for scoring and enrichment logic:
- Score calculation accuracy
- Tier classification (high/medium/low)
- Contact enrichment data quality
- Benchmark field mapping

### test_writer.py (Planned)

Tests for email generation:
- Template rendering with variables
- Tone validation (professional, friendly, urgent)
- Subject line generation
- Body content coherence

### test_tracker.py (Planned)

Tests for outreach tracking:
- Reply classification (positive, negative, neutral)
- Email open detection
- Followup scheduling logic
- Sequence completion marking

### test_api.py (Planned)

Tests for FastAPI endpoints:
- Endpoint response format validation
- Error handling (400, 401, 404, 500)
- Query parameter parsing
- Request body validation
- Authentication checks

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest Fixtures](https://docs.pytest.org/en/latest/fixture.html)
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py](https://coverage.readthedocs.io/)
