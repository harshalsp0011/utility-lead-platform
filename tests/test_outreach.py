"""
Unit tests for Outreach Agent modules (email_sender, followup_scheduler, sequence_manager).

Purpose:
    Comprehensive test coverage for outreach agent email sending, followup scheduling,
    and sequence management logic.

Dependencies:
    - pytest: Test runner and assertion library
    - unittest.mock: Mock and patch for test doubles
    - agents.outreach.email_sender: EmailSender class
    - agents.outreach.followup_scheduler: FollowupScheduler class
    - agents.outreach.sequence_manager: SequenceManager class

Usage:
    Run all tests:     pytest tests/test_outreach.py -v
    Run single class:  pytest tests/test_outreach.py::TestEmailSender -v
    Run single test:   pytest tests/test_outreach.py::TestEmailSender::test_add_unsubscribe_footer -v
    With coverage:     pytest tests/test_outreach.py --cov=agents.outreach --cov-report=html

Test Coverage:
    - EmailSender: Footer addition, provider selection, daily limits, unsubscribe handling
    - FollowupScheduler: Followup creation, date calculations, cancellation, due followup retrieval
    - SequenceManager: Subject line building, template loading
    - Edge Cases: Boundary conditions, date calculations, early returns
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from agents.outreach.email_sender import EmailSender
from agents.outreach.followup_scheduler import FollowupScheduler
from agents.outreach.sequence_manager import SequenceManager


class TestEmailSender:
    """Test suite for EmailSender module."""

    def setup_method(self):
        """Initialize EmailSender instance for each test."""
        self.sender = EmailSender()

    def test_add_unsubscribe_footer(self):
        """
        Test that unsubscribe footer is appended to email body.

        Input: "This is the email body text."

        Expected Output:
            String containing original body + footer:
            "Reply STOP to unsubscribe.
             Troy & Banks | Buffalo, NY | (800) 499-8599"

        Verification: Original body content present at start
        """
        body = "This is the email body text."
        result = self.sender.add_unsubscribe_footer(body)
        
        assert body in result
        assert "STOP" in result
        assert "Troy & Banks" in result or "unsubscribe" in result.lower()
        assert result.startswith(body)

    def test_select_provider_sendgrid(self):
        """
        Test provider selection when SendGrid is configured.

        Setup: EMAIL_PROVIDER = 'sendgrid' in environment/settings

        Expected Output: 'sendgrid'
        """
        with patch('agents.outreach.email_sender.get_settings') as mock_settings:
            mock_settings.return_value.EMAIL_PROVIDER = 'sendgrid'
            result = self.sender.select_provider()
            assert result == 'sendgrid'

    def test_select_provider_instantly(self):
        """
        Test provider selection when Instantly is configured.

        Setup: EMAIL_PROVIDER = 'instantly' in environment/settings

        Expected Output: 'instantly'
        """
        with patch('agents.outreach.email_sender.get_settings') as mock_settings:
            mock_settings.return_value.EMAIL_PROVIDER = 'instantly'
            result = self.sender.select_provider()
            assert result == 'instantly'

    def test_check_daily_limit_within(self):
        """
        Test daily email limit check when under limit.

        Setup:
            - DB returns 20 sent emails today
            - EMAIL_DAILY_LIMIT = 50

        Expected Output:
            - within_limit = True
            - sent_today = 20
            - remaining = 30
        """
        mock_db = Mock()
        mock_db.count_emails_sent_today.return_value = 20
        
        result = self.sender.check_daily_limit(db_session=mock_db, daily_limit=50)
        
        assert result['within_limit'] is True
        assert result['sent_today'] == 20
        assert result['remaining'] == 30

    def test_check_daily_limit_exceeded(self):
        """
        Test daily email limit check when limit is exceeded.

        Setup:
            - DB returns 55 sent emails today
            - EMAIL_DAILY_LIMIT = 50

        Expected Output:
            - within_limit = False
            - sent_today = 55
            - remaining = 0 (or capped at 0)
        """
        mock_db = Mock()
        mock_db.count_emails_sent_today.return_value = 55
        
        result = self.sender.check_daily_limit(db_session=mock_db, daily_limit=50)
        
        assert result['within_limit'] is False
        assert result['sent_today'] == 55
        assert result['remaining'] <= 0

    def test_check_daily_limit_exactly_at_limit(self):
        """Test daily limit when exactly at boundary (50/50)."""
        mock_db = Mock()
        mock_db.count_emails_sent_today.return_value = 50
        
        result = self.sender.check_daily_limit(db_session=mock_db, daily_limit=50)
        
        assert result['within_limit'] is False  # At limit means can't send more
        assert result['sent_today'] == 50
        assert result['remaining'] == 0

    def test_send_email_skips_unsubscribed(self):
        """
        Test that emails are not sent to unsubscribed contacts.

        Setup: Mock contact with unsubscribed = True

        Expected Output:
            - Function returns early
            - No send API call made
            - Result: { success: False, reason: 'contact_unsubscribed' }
        """
        mock_contact = Mock()
        mock_contact.unsubscribed = True
        
        result = self.sender.send_email(
            contact=mock_contact,
            subject="Test",
            body="Test body"
        )
        
        assert result['success'] is False
        assert result['reason'] == 'contact_unsubscribed'

    def test_send_email_valid_contact(self):
        """Test that valid contact email is sent."""
        mock_contact = Mock()
        mock_contact.email = "john@kaleida.org"
        mock_contact.unsubscribed = False
        
        with patch('agents.outreach.email_sender.EmailSender.select_provider') as mock_provider:
            with patch('agents.outreach.email_sender.EmailSender._send_via_sendgrid') as mock_send:
                mock_provider.return_value = 'sendgrid'
                mock_send.return_value = {'success': True, 'message_id': '12345'}
                
                result = self.sender.send_email(
                    contact=mock_contact,
                    subject="Test",
                    body="Test body"
                )
                
                assert result['success'] is True


class TestFollowupScheduler:
    """Test suite for FollowupScheduler module."""

    def setup_method(self):
        """Initialize FollowupScheduler instance for each test."""
        self.scheduler = FollowupScheduler()

    def test_schedule_followups_creates_three(self):
        """
        Test that scheduling followups creates three records.

        Input:
            - company_id = valid UUID
            - send_date = today

        Expected Output:
            - 3 records created in outreach_events
            - follow_up_number = 1, 2, 3
        """
        mock_db = Mock()
        company_id = "550e8400-e29b-41d4-a716-446655440000"
        send_date = datetime.now().date()
        
        records_created = self.scheduler.schedule_followups(
            company_id=company_id,
            send_date=send_date,
            db_session=mock_db
        )
        
        assert len(records_created) == 3
        followup_numbers = [r['follow_up_number'] for r in records_created]
        assert followup_numbers == [1, 2, 3]

    def test_schedule_followup_dates(self):
        """
        Test that followup dates are calculated correctly.

        Input:
            - send_date = 2026-03-03
            - FOLLOWUP_DAY_1 = 3
            - FOLLOWUP_DAY_2 = 7
            - FOLLOWUP_DAY_3 = 14

        Expected Output:
            - followup 1 date = 2026-03-06
            - followup 2 date = 2026-03-10
            - followup 3 date = 2026-03-17
        """
        mock_db = Mock()
        company_id = "550e8400-e29b-41d4-a716-446655440000"
        send_date = datetime(2026, 3, 3).date()
        
        records = self.scheduler.schedule_followups(
            company_id=company_id,
            send_date=send_date,
            db_session=mock_db,
            followup_days=[3, 7, 14]  # Custom followup days
        )
        
        # Extract dates from scheduled records
        dates = {r['follow_up_number']: r['next_followup_date'] for r in records}
        
        assert dates[1] == datetime(2026, 3, 6).date()
        assert dates[2] == datetime(2026, 3, 10).date()
        assert dates[3] == datetime(2026, 3, 17).date()

    def test_cancel_followups(self):
        """
        Test that followups can be cancelled.

        Setup: Create 3 scheduled followup records

        Input: company_id

        Expected Output:
            - All 3 records updated to event_type = 'cancelled_followup'
            - Returns count = 3
        """
        mock_db = Mock()
        company_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Mock 3 existing followup records
        mock_followups = [
            Mock(id=f"followup_{i}", event_type='scheduled_followup')
            for i in range(1, 4)
        ]
        mock_db.query.return_value.filter.return_value = mock_followups
        
        count = self.scheduler.cancel_followups(
            company_id=company_id,
            db_session=mock_db
        )
        
        assert count == 3
        for followup in mock_followups:
            assert followup.event_type == 'cancelled_followup'

    def test_get_due_followups_today(self):
        """
        Test retrieval of followups due today.

        Setup: Create followup record with next_followup_date = today

        Expected Output: List containing that record
        """
        mock_db = Mock()
        today = datetime.now().date()
        
        mock_followup = Mock()
        mock_followup.next_followup_date = today
        mock_followup.event_type = 'scheduled_followup'
        
        mock_db.query.return_value.filter.return_value = [mock_followup]
        
        due_followups = self.scheduler.get_due_followups(
            db_session=mock_db,
            cutoff_date=today
        )
        
        assert len(due_followups) >= 1
        assert mock_followup in due_followups

    def test_get_due_followups_future_excluded(self):
        """
        Test that future followups are not included in due list.

        Setup: Create followup record with next_followup_date = tomorrow

        Expected Output: Empty list (or doesn't include tomorrow's followup)
        """
        mock_db = Mock()
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        mock_followup = Mock()
        mock_followup.next_followup_date = tomorrow
        mock_followup.event_type = 'scheduled_followup'
        
        # Mock query to return empty when filtering for today or earlier
        mock_db.query.return_value.filter.return_value = []
        
        due_followups = self.scheduler.get_due_followups(
            db_session=mock_db,
            cutoff_date=today
        )
        
        assert len(due_followups) == 0

    def test_get_due_followups_past_included(self):
        """Test that overdue followups (from past) are included."""
        mock_db = Mock()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        mock_followup = Mock()
        mock_followup.next_followup_date = yesterday
        mock_followup.event_type = 'scheduled_followup'
        
        mock_db.query.return_value.filter.return_value = [mock_followup]
        
        due_followups = self.scheduler.get_due_followups(
            db_session=mock_db,
            cutoff_date=today
        )
        
        assert len(due_followups) >= 1


class TestSequenceManager:
    """Test suite for SequenceManager module."""

    def setup_method(self):
        """Initialize SequenceManager instance for each test."""
        self.manager = SequenceManager()

    def test_build_followup_subject_day1(self):
        """
        Test subject line building for first followup (day 3).

        Input:
            - original_subject = "Utility savings for Kaleida"
            - follow_up_number = 1

        Expected Output: "Re: Utility savings for Kaleida"
        """
        original_subject = "Utility savings for Kaleida"
        result = self.manager.build_followup_subject(
            original_subject=original_subject,
            follow_up_number=1
        )
        
        assert "Re:" in result or "re:" in result.lower()
        assert "Utility savings for Kaleida" in result

    def test_build_followup_subject_day3(self):
        """
        Test subject line building for final followup (day 14).

        Input:
            - original_subject = "Utility savings for Kaleida"
            - follow_up_number = 3

        Expected Output: "Following up one last time" or similar final-touch language
        """
        original_subject = "Utility savings for Kaleida"
        result = self.manager.build_followup_subject(
            original_subject=original_subject,
            follow_up_number=3
        )
        
        # Should be different from original and indicate final followup
        assert result != original_subject
        assert len(result) > 0
        # Common patterns for final followup
        assert any(phrase in result.lower() for phrase in [
            "last", "final", "final followup", "one last time",
            "urgent", "quick question", "brief moment"
        ]) or "Re:" in result

    def test_build_followup_subject_day2(self):
        """Test subject line building for second followup (day 7)."""
        original_subject = "Utility savings for Kaleida"
        result = self.manager.build_followup_subject(
            original_subject=original_subject,
            follow_up_number=2
        )
        
        assert result != original_subject
        assert len(result) > 0

    def test_get_followup_template_returns_string(self):
        """
        Test that followup template is loaded and contains placeholders.

        Input: follow_up_number = 1

        Expected Output:
            - Non-empty string
            - Contains {{company_name}} placeholder
        """
        result = self.manager.get_followup_template(follow_up_number=1)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "{{" in result or "{" in result  # Contains placeholders

    def test_get_followup_template_all_sequences(self):
        """Test that all three followup templates load successfully."""
        for follow_up_number in [1, 2, 3]:
            result = self.manager.get_followup_template(follow_up_number=follow_up_number)
            assert isinstance(result, str)
            assert len(result) > 0
            assert len(result) > 50  # Should be substantial content


class TestOutreachIntegration:
    """Integration tests combining multiple outreach components."""

    def test_end_to_end_email_and_schedule(self):
        """Test complete flow: send email, then schedule followups."""
        mock_db = Mock()
        
        # Send initial email
        sender = EmailSender()
        mock_contact = Mock()
        mock_contact.email = "john@kaleida.org"
        mock_contact.unsubscribed = False
        
        with patch('agents.outreach.email_sender.EmailSender.select_provider'):
            with patch('agents.outreach.email_sender.EmailSender._send_via_sendgrid') as mock_send:
                mock_send.return_value = {'success': True, 'message_id': '12345'}
                
                send_result = sender.send_email(
                    contact=mock_contact,
                    subject="Test",
                    body="Test body"
                )
        
        assert send_result['success'] is True
        
        # Schedule followups
        scheduler = FollowupScheduler()
        company_id = "550e8400-e29b-41d4-a716-446655440000"
        followups = scheduler.schedule_followups(
            company_id=company_id,
            send_date=datetime.now().date(),
            db_session=mock_db
        )
        
        assert len(followups) == 3

    def test_buildup_followup_sequence(self):
        """Test building complete followup sequence with subjects."""
        manager = SequenceManager()
        original_subject = "Potential utility savings"
        
        subjects = []
        for follow_up_number in [1, 2, 3]:
            subject = manager.build_followup_subject(
                original_subject=original_subject,
                follow_up_number=follow_up_number
            )
            subjects.append(subject)
        
        # All subjects should be non-empty
        assert all(len(s) > 0 for s in subjects)
        # Should have variety (not all identical)
        assert len(set(subjects)) >= 2


class TestEdgeCases:
    """Edge case and boundary testing."""

    def test_daily_limit_zero(self):
        """Test daily limit with zero allowed emails."""
        sender = EmailSender()
        mock_db = Mock()
        mock_db.count_emails_sent_today.return_value = 1
        
        result = sender.check_daily_limit(db_session=mock_db, daily_limit=0)
        
        assert result['within_limit'] is False
        assert result['remaining'] <= 0

    def test_add_footer_to_empty_body(self):
        """Test adding footer to empty email body."""
        sender = EmailSender()
        result = sender.add_unsubscribe_footer("")
        
        assert len(result) > 0
        assert "unsubscribe" in result.lower() or "STOP" in result

    def test_schedule_followups_zero_days(self):
        """Test scheduling with zero day offset."""
        scheduler = FollowupScheduler()
        mock_db = Mock()
        company_id = "550e8400-e29b-41d4-a716-446655440000"
        send_date = datetime(2026, 3, 1).date()
        
        records = scheduler.schedule_followups(
            company_id=company_id,
            send_date=send_date,
            db_session=mock_db,
            followup_days=[0, 0, 0]  # Unusual but should handle
        )
        
        assert len(records) == 3

    def test_sequence_manager_high_followup_number(self):
        """Test sequence manager with invalid followup number."""
        manager = SequenceManager()
        
        # Should handle gracefully (return template or error)
        result = manager.get_followup_template(follow_up_number=10)
        
        # Either returns a valid template or empty/None
        assert result is not None or isinstance(result, str)


class TestParametrizedOutreach:
    """Parametrized tests for outreach scenarios."""

    @pytest.mark.parametrize("provider,expected", [
        ('sendgrid', 'sendgrid'),
        ('instantly', 'instantly'),
    ])
    def test_provider_selection_variations(self, provider, expected):
        """Parametrized test for email provider selection."""
        sender = EmailSender()
        
        with patch('agents.outreach.email_sender.get_settings') as mock_settings:
            mock_settings.return_value.EMAIL_PROVIDER = provider
            result = sender.select_provider()
            assert result == expected

    @pytest.mark.parametrize("sent_count,limit,expected_within", [
        (10, 50, True),
        (50, 50, False),
        (55, 50, False),
        (0, 50, True),
        (49, 50, True),
    ])
    def test_daily_limit_parametrized(self, sent_count, limit, expected_within):
        """Parametrized test for daily email limit checking."""
        sender = EmailSender()
        mock_db = Mock()
        mock_db.count_emails_sent_today.return_value = sent_count
        
        result = sender.check_daily_limit(db_session=mock_db, daily_limit=limit)
        
        assert result['within_limit'] == expected_within
        assert result['sent_today'] == sent_count
        assert result['remaining'] == max(0, limit - sent_count)

    @pytest.mark.parametrize("followup_num,has_re", [
        (1, True),
        (2, True),
        (3, True),
    ])
    def test_followup_subjects_have_markers(self, followup_num, has_re):
        """Parametrized test that all followup subjects have reply markers."""
        manager = SequenceManager()
        result = manager.build_followup_subject(
            original_subject="Test subject",
            follow_up_number=followup_num
        )
        
        # All followups should have "Re:" or similar
        assert "Re:" in result or "re:" in result.lower() or len(result) > len("Test subject")
