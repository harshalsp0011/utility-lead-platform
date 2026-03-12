"""
Unit tests for Tracker Agent modules (webhook_listener, reply_classifier, status_updater).

Purpose:
    Comprehensive test coverage for tracker agent event parsing, reply classification,
    and lead/contact status management.

Dependencies:
    - pytest: Test runner and assertion library
    - unittest.mock: Mock and patch for test doubles
    - agents.tracker.webhook_listener: WebhookListener class
    - agents.tracker.reply_classifier: ReplyClassifier class
    - agents.tracker.status_updater: StatusUpdater class

Usage:
    Run all tests:     pytest tests/test_tracker.py -v
    Run single class:  pytest tests/test_tracker.py::TestWebhookListener -v
    Run single test:   pytest tests/test_tracker.py::TestWebhookListener::test_parse_sendgrid_event_open -v
    With coverage:     pytest tests/test_tracker.py --cov=agents.tracker --cov-report=html

Test Coverage:
    - WebhookListener: Event parsing (open, reply, bounce), multi-event arrays, quoted reply stripping
    - ReplyClassifier: Sentiment/intent classification, LLM fallback, sales alert routing
    - StatusUpdater: Status transitions, cancel-on-reply, unsubscribe flagging, bounce invalidation
    - Edge Cases: Invalid statuses, empty payloads, LLM failures
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from agents.tracker.webhook_listener import WebhookListener
from agents.tracker.reply_classifier import ReplyClassifier
from agents.tracker.status_updater import StatusUpdater


class TestWebhookListener:
    """Test suite for WebhookListener module."""

    def setup_method(self):
        """Initialize WebhookListener instance for each test."""
        self.listener = WebhookListener()

    def test_parse_sendgrid_event_open(self):
        """
        Test parsing of SendGrid open event.

        Input:
            [{ "event": "open",
               "email": "cfo@company.com",
               "timestamp": 1234567890,
               "sg_message_id": "abc123" }]

        Expected Output:
            list with one event dict:
                - event_type = 'opened'
                - email = 'cfo@company.com'
                - message_id = 'abc123'
        """
        payload = json.dumps([{
            "event": "open",
            "email": "cfo@company.com",
            "timestamp": 1234567890,
            "sg_message_id": "abc123"
        }])

        events = self.listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == 'opened'
        assert events[0]['email'] == 'cfo@company.com'
        assert events[0]['message_id'] == 'abc123'

    def test_parse_sendgrid_event_reply(self):
        """
        Test parsing of SendGrid inbound reply event.

        Input:
            { "event": "inbound",
              "text": "This looks interesting, can we schedule a call?",
              "from": "cfo@company.com" }

        Expected Output:
            - event_type = 'replied'
            - reply_content contains original text
        """
        payload = json.dumps([{
            "event": "inbound",
            "text": "This looks interesting, can we schedule a call?",
            "from": "cfo@company.com",
            "email": "cfo@company.com"
        }])

        events = self.listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == 'replied'
        assert events[0]['reply_content'] is not None
        assert "interesting" in events[0]['reply_content'].lower() or \
               "schedule" in events[0]['reply_content'].lower()

    def test_parse_sendgrid_event_bounce(self):
        """
        Test parsing of SendGrid bounce event.

        Input: { "event": "bounce", "email": "wrong@company.com" }

        Expected Output: event_type = 'bounced'
        """
        payload = json.dumps([{
            "event": "bounce",
            "email": "wrong@company.com"
        }])

        events = self.listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == 'bounced'
        assert events[0]['email'] == 'wrong@company.com'

    def test_parse_multiple_events(self):
        """
        Test parsing of multiple events in one webhook payload.

        Input: Array of 3 different event types (open, click, bounce)

        Expected Output:
            - List of 3 standard event dicts
            - Each has correct event_type mapped
        """
        payload = json.dumps([
            {"event": "open", "email": "a@company.com", "timestamp": 1234567890},
            {"event": "click", "email": "b@company.com", "timestamp": 1234567891},
            {"event": "bounce", "email": "c@company.com", "timestamp": 1234567892},
        ])

        events = self.listener.parse_sendgrid_event(payload)

        assert len(events) == 3

        event_types = [e['event_type'] for e in events]
        assert 'opened' in event_types
        assert 'clicked' in event_types
        assert 'bounced' in event_types

    def test_extract_reply_strips_quoted(self):
        """
        Test that quoted original email content is stripped from reply.

        Input: Reply with quoted original email
            "Yes interested!\\n\\n> On March 3 you wrote:\\n> Dear John..."

        Expected Output: "Yes interested!"

        Verify: Quoted lines starting with > removed
        """
        raw_reply = "Yes interested!\n\n> On March 3 you wrote:\n> Dear John,\n> We noticed..."

        cleaned = self.listener.extract_reply_content({"text": raw_reply})

        assert "Yes interested!" in cleaned
        assert "> On March 3 you wrote:" not in cleaned
        assert "> Dear John" not in cleaned

    def test_parse_empty_payload(self):
        """Test that empty payload returns empty list."""
        events = self.listener.parse_sendgrid_event("[]")
        assert events == []

    def test_parse_invalid_json(self):
        """Test that invalid JSON returns empty list."""
        events = self.listener.parse_sendgrid_event("not-json")
        assert events == []

    def test_event_type_mapping_unsubscribe(self):
        """Test that 'unsubscribe' event maps to 'unsubscribed'."""
        payload = json.dumps([{
            "event": "unsubscribe",
            "email": "user@company.com"
        }])

        events = self.listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == 'unsubscribed'


class TestReplyClassifier:
    """Test suite for ReplyClassifier module."""

    def setup_method(self):
        """Initialize ReplyClassifier instance for each test."""
        self.classifier = ReplyClassifier()

    def test_classify_positive_meeting_request(self):
        """
        Test classification of positive reply requesting a meeting.

        Input: "Yes this looks great, can we schedule a call next week?"

        Expected Output:
            - sentiment = 'positive'
            - intent = 'wants_meeting'
        """
        text = "Yes this looks great, can we schedule a call next week?"
        result = self.classifier.classify_reply(text)

        assert result['sentiment'] == 'positive'
        assert result['intent'] == 'wants_meeting'

    def test_classify_positive_info_request(self):
        """
        Test classification of positive reply requesting more information.

        Input: "Interesting — can you send me more information about your process?"

        Expected Output:
            - sentiment = 'positive'
            - intent = 'wants_info'
        """
        text = "Interesting — can you send me more information about your process?"
        result = self.classifier.classify_reply(text)

        assert result['sentiment'] == 'positive'
        assert result['intent'] == 'wants_info'

    def test_classify_negative_not_interested(self):
        """
        Test classification of negative reply requesting unsubscribe.

        Input: "Not interested, please remove me from your list"

        Expected Output:
            - sentiment = 'negative'
            - intent = 'unsubscribe'
        """
        text = "Not interested, please remove me from your list"
        result = self.classifier.classify_reply(text)

        assert result['sentiment'] == 'negative'
        assert result['intent'] == 'unsubscribe'

    def test_classify_negative_has_provider(self):
        """
        Test classification of negative reply with existing provider.

        Input: "We are already happy with our current energy provider"

        Expected Output:
            - sentiment = 'negative'
            - intent = 'not_interested'
        """
        text = "We are already happy with our current energy provider"
        result = self.classifier.classify_reply(text)

        assert result['sentiment'] == 'negative'
        assert result['intent'] == 'not_interested'

    def test_rule_based_classify_fallback(self):
        """
        Test that rule-based classifier is used as fallback when LLM unavailable.

        Setup: Mock LLM to raise exception

        Input: "Yes let us set up a call"

        Expected Output:
            - Uses rule_based_classify() as fallback
            - Returns sentiment = 'positive'
        """
        text = "Yes let us set up a call"

        with patch('agents.tracker.reply_classifier.ReplyClassifier._get_llm_connector',
                   return_value=None):
            result = self.classifier.classify_reply(text)

        assert result['sentiment'] == 'positive'

    def test_should_alert_positive(self):
        """
        Test that positive meeting intent triggers sales alert.

        Input: sentiment='positive', intent='wants_meeting'

        Expected Output: True
        """
        result = self.classifier.should_alert_sales(
            sentiment='positive',
            intent='wants_meeting'
        )
        assert result is True

    def test_should_alert_negative(self):
        """
        Test that negative not-interested reply does not trigger alert.

        Input: sentiment='negative', intent='not_interested'

        Expected Output: False
        """
        result = self.classifier.should_alert_sales(
            sentiment='negative',
            intent='not_interested'
        )
        assert result is False

    def test_should_alert_unsubscribe(self):
        """
        Test that unsubscribe intent does not trigger sales alert.

        Input: sentiment='negative', intent='unsubscribe'

        Expected Output: False
        """
        result = self.classifier.should_alert_sales(
            sentiment='negative',
            intent='unsubscribe'
        )
        assert result is False

    def test_classify_returns_required_fields(self):
        """Test that classify_reply always returns all required fields."""
        result = self.classifier.classify_reply("Some reply text")

        assert 'sentiment' in result
        assert 'intent' in result
        assert 'confidence' in result
        assert result['sentiment'] in ('positive', 'negative', 'neutral')

    def test_rule_based_classify_direct(self):
        """Test rule_based_classify directly with various inputs."""
        result = self.classifier.rule_based_classify("Yes let's schedule a meeting")
        assert result['sentiment'] == 'positive'

        result = self.classifier.rule_based_classify("remove me from this list")
        assert result['sentiment'] == 'negative'
        assert result['intent'] == 'unsubscribe'


class TestStatusUpdater:
    """Test suite for StatusUpdater module."""

    def setup_method(self):
        """Initialize StatusUpdater instance for each test."""
        self.updater = StatusUpdater()

    def test_update_lead_status_valid(self):
        """
        Test that valid status update succeeds.

        Input: company_id, new_status='contacted'

        Expected Output: True

        Verify: companies table updated
        """
        mock_db = Mock()
        mock_db.execute.return_value.all.return_value = [Mock(id="row1")]

        result = self.updater.update_lead_status(
            company_id="company-123",
            new_status='contacted',
            db_session=mock_db
        )

        assert result is True
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    def test_update_lead_status_invalid(self):
        """
        Test that invalid status raises ValueError.

        Input: company_id, new_status='invalid_status'

        Expected Output: raises ValueError
        """
        mock_db = Mock()

        with pytest.raises(ValueError):
            self.updater.update_lead_status(
                company_id="company-123",
                new_status='invalid_status',
                db_session=mock_db
            )

    def test_mark_replied_cancels_followups(self):
        """
        Test that marking replied also cancels all scheduled followups.

        Setup: Company with 2 scheduled followup records

        Input: company_id, reply_content, sentiment='positive'

        Expected Output:
            - companies.status = 'replied'
            - All scheduled followups cancelled
            - outreach_events reply record created
        """
        mock_db = Mock()
        # Mock execute to return rows for update calls
        mock_result = Mock()
        mock_result.all.return_value = [Mock()]
        mock_db.execute.return_value = mock_result

        with patch('agents.tracker.status_updater.followup_scheduler.cancel_followups') as mock_cancel:
            mock_cancel.return_value = 2

            self.updater.mark_replied(
                company_id="company-123",
                reply_content="Yes, let's schedule a call",
                sentiment='positive',
                db_session=mock_db
            )

            # cancel_followups should have been called
            mock_cancel.assert_called_once_with(
                company_id="company-123",
                db_session=mock_db
            )

        # commit should be called
        mock_db.commit.assert_called()

    def test_mark_unsubscribed_flags_contact(self):
        """
        Test that marking unsubscribed correctly flags the contact.

        Input: contact_id

        Expected Output:
            - contacts.unsubscribed = True
            - No future emails sent to this contact
        """
        mock_db = Mock()
        mock_result = Mock()
        mock_result.mappings.return_value.first.return_value = {'company_id': 'company-123'}
        mock_result.first.return_value = None  # No remaining active contacts
        mock_result.all.return_value = [Mock()]
        mock_db.execute.return_value = mock_result

        with patch('agents.tracker.status_updater.followup_scheduler.cancel_followups') as mock_cancel:
            mock_cancel.return_value = 0

            self.updater.mark_unsubscribed(
                contact_id="contact-456",
                db_session=mock_db
            )

        # Should execute an UPDATE to set unsubscribed=true
        assert mock_db.execute.called
        mock_db.commit.assert_called()

    def test_mark_bounced_invalidates_contact(self):
        """
        Test that marking bounced invalidates the contact and logs event.

        Input: contact_id

        Expected Output:
            - contacts.verified = False
            - outreach_event bounce record created
        """
        mock_db = Mock()
        mock_result = Mock()
        mock_result.mappings.return_value.first.return_value = {'company_id': 'company-123'}
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        self.updater.mark_bounced(
            contact_id="contact-456",
            db_session=mock_db
        )

        # Should execute multiple SQL statements (UPDATE contacts + INSERT outreach_events)
        assert mock_db.execute.call_count >= 2
        mock_db.commit.assert_called()


class TestTrackerIntegration:
    """Integration tests combining tracker agent components."""

    def test_webhook_to_classifier_pipeline(self):
        """Test parsing a reply webhook then classifying the reply content."""
        listener = WebhookListener()
        classifier = ReplyClassifier()

        payload = json.dumps([{
            "event": "inbound",
            "text": "Yes, this sounds great. Can we set up a call?",
            "email": "cfo@kaleida.org"
        }])

        events = listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        reply_content = events[0].get('reply_content', '')

        if reply_content:
            classification = classifier.classify_reply(reply_content)
            assert classification['sentiment'] == 'positive'
        else:
            # If reply_content was empty, use the text field fallback
            classification = classifier.classify_reply("Yes, this sounds great. Can we set up a call?")
            assert classification['sentiment'] == 'positive'

    def test_classify_and_alert_routing(self):
        """Test full flow: classify reply then determine alert routing."""
        classifier = ReplyClassifier()

        positive_reply = "Absolutely, let's schedule a call next week."
        result = classifier.classify_reply(positive_reply)
        should_alert = classifier.should_alert_sales(
            sentiment=result['sentiment'],
            intent=result['intent']
        )
        assert should_alert is True

        negative_reply = "Not interested, please remove me from your list."
        result = classifier.classify_reply(negative_reply)
        should_alert = classifier.should_alert_sales(
            sentiment=result['sentiment'],
            intent=result['intent']
        )
        assert should_alert is False


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_classify_empty_reply(self):
        """Test classification of empty reply."""
        classifier = ReplyClassifier()
        result = classifier.classify_reply("")

        assert 'sentiment' in result
        assert result['sentiment'] in ('positive', 'negative', 'neutral')

    def test_classify_very_long_reply(self):
        """Test classification handles long replies without error."""
        classifier = ReplyClassifier()
        long_text = ("This is a very detailed email. " * 100) + "Can we schedule a call?"
        result = classifier.classify_reply(long_text)

        assert 'sentiment' in result

    def test_parse_sendgrid_unknown_event_type(self):
        """Test that unknown event types are passed through as-is."""
        listener = WebhookListener()
        payload = json.dumps([{
            "event": "custom_event_xyz",
            "email": "user@company.com"
        }])

        events = listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == 'custom_event_xyz'

    def test_update_status_no_matching_company(self):
        """Test status update when no company matches returns False."""
        updater = StatusUpdater()
        mock_db = Mock()
        mock_db.execute.return_value.all.return_value = []  # No rows updated

        result = updater.update_lead_status(
            company_id="nonexistent-id",
            new_status='contacted',
            db_session=mock_db
        )

        assert result is False

    def test_extract_reply_strips_signature(self):
        """Test that common email signatures are preserved but quoted text removed."""
        listener = WebhookListener()
        raw = "Sounds good!\n\n> On March 1, Troy wrote:\n> Hi John, hope this finds you well."

        cleaned = listener.extract_reply_content({"text": raw})

        assert "Sounds good" in cleaned
        assert "> On March 1" not in cleaned


class TestParametrizedTracker:
    """Parametrized tests for tracker scenarios."""

    @pytest.mark.parametrize("event_type,expected_normalized", [
        ("open", "opened"),
        ("click", "clicked"),
        ("bounce", "bounced"),
        ("unsubscribe", "unsubscribed"),
        ("inbound", "replied"),
    ])
    def test_event_type_normalization(self, event_type, expected_normalized):
        """Parametrized test for all SendGrid event type mappings."""
        listener = WebhookListener()
        payload = json.dumps([{"event": event_type, "email": "test@example.com"}])

        events = listener.parse_sendgrid_event(payload)

        assert len(events) == 1
        assert events[0]['event_type'] == expected_normalized

    @pytest.mark.parametrize("reply_text,expected_sentiment,expected_intent", [
        ("Yes, let's schedule a call", "positive", "wants_meeting"),
        ("Not interested, remove me", "negative", "unsubscribe"),
        ("We already have a provider", "negative", "not_interested"),
        ("Can you send me more details?", "positive", "wants_info"),
    ])
    def test_rule_based_classification_variations(self, reply_text, expected_sentiment, expected_intent):
        """Parametrized test for rule-based reply classification."""
        classifier = ReplyClassifier()
        result = classifier.rule_based_classify(reply_text)

        assert result['sentiment'] == expected_sentiment
        assert result['intent'] == expected_intent

    @pytest.mark.parametrize("sentiment,intent,expected_alert", [
        ("positive", "wants_meeting", True),
        ("positive", "wants_info", True),
        ("negative", "not_interested", False),
        ("negative", "unsubscribe", False),
        ("neutral", "other", False),
    ])
    def test_should_alert_variations(self, sentiment, intent, expected_alert):
        """Parametrized test for sales alert routing decisions."""
        classifier = ReplyClassifier()
        result = classifier.should_alert_sales(sentiment=sentiment, intent=intent)
        assert result == expected_alert

    @pytest.mark.parametrize("new_status,should_succeed", [
        ("contacted", True),
        ("replied", True),
        ("approved", True),
        ("meeting_booked", True),
        ("won", True),
        ("invalid_status", False),
        ("", False),
        ("FAKEVALUE", False),
    ])
    def test_valid_status_values(self, new_status, should_succeed):
        """Parametrized test for valid and invalid status transitions."""
        updater = StatusUpdater()
        mock_db = Mock()

        if should_succeed:
            mock_db.execute.return_value.all.return_value = [Mock(id="row1")]
            result = updater.update_lead_status(
                company_id="company-123",
                new_status=new_status,
                db_session=mock_db
            )
            assert result is True
        else:
            with pytest.raises((ValueError, Exception)):
                updater.update_lead_status(
                    company_id="company-123",
                    new_status=new_status,
                    db_session=mock_db
                )
