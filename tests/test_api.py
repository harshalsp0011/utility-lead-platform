"""
Integration tests for FastAPI routes using FastAPI's TestClient.

Purpose:
    Full route-level integration testing for all API route modules
    (leads, emails, pipeline, triggers, reports). All external dependencies
    (database, pipeline_monitor, report_generator, orchestrator) are replaced
    with mocks so tests run offline without a real PostgreSQL instance.

Dependencies:
    - pytest: Test runner and assertion library
    - fastapi.testclient.TestClient: Synchronous ASGI test client
    - unittest.mock: MagicMock, patch for test doubles
    - api.main: FastAPI app instance
    - api.dependencies: get_db dependency (overridden per test class)

Usage:
    Run all tests:       pytest tests/test_api.py -v
    Run single class:    pytest tests/test_api.py::TestLeadRoutes -v
    Run single test:     pytest tests/test_api.py::TestLeadRoutes::test_get_leads_returns_list -v
    With coverage:       pytest tests/test_api.py --cov=api --cov-report=html

Notes:
    - DEPLOY_ENV defaults to 'local' so the X-API-Key check is bypassed for all tests.
    - DB sessions are replaced via app.dependency_overrides[get_db] in setup_method.
    - pipeline_monitor, report_generator, and orchestrator calls are patched per test.
    - Background task wrappers in trigger routes are patched to prevent real DB connections.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db
from api.main import app

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

_COMPANY_ID = "12345678-1234-5678-1234-123456789012"
_SCORE_ID   = "22345678-1234-5678-1234-123456789012"
_CONTACT_ID = "32345678-1234-5678-1234-123456789012"
_DRAFT_ID   = "42345678-1234-5678-1234-123456789012"
_NOW        = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _lead_row(
    company_id: str = _COMPANY_ID,
    industry: str = "healthcare",
    tier: str = "medium",
) -> dict:
    """Return a minimal dict that matches the companies+lead_scores JOIN output."""
    return {
        "company_id": company_id,
        "company_name": "Metro General Hospital",
        "industry": industry,
        "state": "NY",
        "site_count": 4,
        "employee_count": 1200,
        "estimated_total_spend": 2_400_000.0,
        "savings_low": 240_000.0,
        "savings_mid": 324_000.0,
        "savings_high": 408_000.0,
        "score": 74.0 if tier == "high" else 55.0,
        "tier": tier,
        "score_reason": "High recovery potential",
        "approved_human": False,
        "approved_by": None,
        "approved_at": None,
        "status": "scored",
        "contact_found": True,
        "date_scored": _NOW,
    }


def _draft_row(
    draft_id: str = _DRAFT_ID,
    company_id: str = _COMPANY_ID,
    approved: bool = False,
) -> dict:
    """Return a minimal dict that matches the email_drafts JOIN output."""
    return {
        "id": draft_id,
        "company_id": company_id,
        "company_name": "Metro General Hospital",
        "contact_id": _CONTACT_ID,
        "contact_name": "Jane Doe",
        "contact_title": "CFO",
        "contact_email": "jdoe@metrogeneral.org",
        "subject_line": "Energy savings opportunity for Metro General Hospital",
        "body": "Dear Jane, we can help reduce your utility costs...",
        "savings_estimate": "$324k",
        "template_used": "email_healthcare.txt",
        "created_at": _NOW,
        "approved_human": approved,
        "approved_by": "Test Manager" if approved else None,
        "approved_at": _NOW if approved else None,
        "edited_human": False,
    }


def _make_result(
    first=None,
    all_rows=None,
    fetchone_value=None,
) -> MagicMock:
    """Build a mock SQLAlchemy execute result supporting all common query patterns."""
    r = MagicMock()
    r.mappings.return_value.first.return_value = first
    r.mappings.return_value.all.return_value = all_rows or []
    r.all.return_value = all_rows or []
    r.first.return_value = first
    r.fetchone.return_value = fetchone_value
    return r


def _mock_db() -> MagicMock:
    """Create a fresh mock SQLAlchemy Session with a safe default result."""
    db = MagicMock()
    db.execute.return_value = _make_result()
    return db


# ---------------------------------------------------------------------------
# TestLeadRoutes
# ---------------------------------------------------------------------------


class TestLeadRoutes:
    """Integration tests for GET/PATCH /leads routes."""

    def setup_method(self):
        """Override get_db with a fresh mock before each test."""
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        """Restore dependencies after each test."""
        app.dependency_overrides.clear()

    def test_get_leads_returns_list(self):
        """
        GET /leads returns 200 with a 'leads' array and 'total_count' integer.

        Expected: status 200
        Verify:
            - response.json() has key 'leads' → list
            - response.json() has key 'total_count' → int
        """
        self.db.execute.return_value = _make_result(
            first={"total_count": 0, "high_count": 0, "medium_count": 0, "low_count": 0},
            all_rows=[],
        )

        response = self.client.get("/leads")

        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert "total_count" in data
        assert isinstance(data["leads"], list)
        assert isinstance(data["total_count"], int)

    def test_get_leads_filter_by_industry(self):
        """
        GET /leads?industry=healthcare returns 200 with only healthcare leads.

        Expected: status 200
        Verify: every lead in the response has industry = 'healthcare'
        """
        row = _lead_row(industry="healthcare", tier="medium")
        self.db.execute.return_value = _make_result(
            first={"total_count": 1, "high_count": 0, "medium_count": 1, "low_count": 0},
            all_rows=[row],
        )

        response = self.client.get("/leads?industry=healthcare")

        assert response.status_code == 200
        data = response.json()
        assert len(data["leads"]) == 1
        for lead in data["leads"]:
            assert lead["industry"] == "healthcare"

    def test_get_leads_filter_by_tier(self):
        """
        GET /leads?tier=high returns 200 with only high-tier leads.

        Expected: status 200
        Verify: every lead in the response has tier = 'high'
        """
        row = _lead_row(tier="high")
        self.db.execute.return_value = _make_result(
            first={"total_count": 1, "high_count": 1, "medium_count": 0, "low_count": 0},
            all_rows=[row],
        )

        response = self.client.get("/leads?tier=high")

        assert response.status_code == 200
        data = response.json()
        assert len(data["leads"]) == 1
        for lead in data["leads"]:
            assert lead["tier"] == "high"

    def test_get_lead_by_id_found(self):
        """
        GET /leads/{company_id} returns 200 with matching company_id.

        Setup: mock DB returns a lead row for the given company_id
        Expected: status 200
        Verify: response body company_id matches requested id
        """
        row = _lead_row(company_id=_COMPANY_ID)
        self.db.execute.return_value = _make_result(first=row)

        response = self.client.get(f"/leads/{_COMPANY_ID}")

        assert response.status_code == 200
        assert response.json()["company_id"] == _COMPANY_ID

    def test_get_lead_by_id_not_found(self):
        """
        GET /leads/{nonexistent-id} returns 404 when no matching company exists.

        Expected: status 404
        """
        self.db.execute.return_value = _make_result(first=None)

        response = self.client.get("/leads/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_approve_lead(self):
        """
        PATCH /leads/{id}/approve returns 200 and updates lead_scores.approved_human=true.

        Setup: mock DB returns a score_row for the lead
        Body:  { approved_by: 'Test Manager' }
        Expected: status 200
        Verify:
            - response has success=true
            - lead_scores approved_human SQL was executed
            - db.commit() was called
        """
        # First execute: SELECT id FROM lead_scores (existence check)
        # Next two: UPDATE lead_scores, UPDATE companies
        self.db.execute.side_effect = [
            _make_result(first={"id": _SCORE_ID}),
            _make_result(),
            _make_result(),
        ]

        response = self.client.patch(
            f"/leads/{_COMPANY_ID}/approve",
            json={"approved_by": "Test Manager"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify DB interactions
        assert self.db.execute.call_count >= 3
        self.db.commit.assert_called_once()
        all_sql = " ".join(str(c) for c in self.db.execute.call_args_list)
        assert "approved_human" in all_sql

    def test_reject_lead(self):
        """
        PATCH /leads/{id}/reject returns 200 and archives the company in DB.

        Setup: mock DB accepts updates without error
        Body:  { rejected_by: 'Test Manager', rejection_reason: 'Too small' }
        Expected: status 200
        Verify:
            - response has success=true
            - companies.status = 'archived' SQL was executed
            - db.commit() was called
        """
        self.db.execute.return_value = _make_result()

        response = self.client.patch(
            f"/leads/{_COMPANY_ID}/reject",
            json={"rejected_by": "Test Manager", "rejection_reason": "Too small"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify 'archived' status appeared in one of the executed SQL statements
        all_sql = " ".join(str(c) for c in self.db.execute.call_args_list)
        assert "archived" in all_sql
        self.db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# TestEmailRoutes
# ---------------------------------------------------------------------------


class TestEmailRoutes:
    """Integration tests for GET/PATCH /emails routes."""

    def setup_method(self):
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_get_pending_emails(self):
        """
        GET /emails/pending returns 200 with all drafts having approved_human=false.

        Expected: status 200
        Verify: every draft in the response has approved_human = false
        """
        draft = _draft_row(approved=False)
        # First execute: SELECT pending drafts
        # Second execute: _count_drafts aggregation query
        self.db.execute.side_effect = [
            _make_result(all_rows=[draft]),
            _make_result(
                first={
                    "total_count": 1,
                    "pending_approval": 1,
                    "approved_count": 0,
                    "sent_count": 0,
                }
            ),
        ]

        response = self.client.get("/emails/pending")

        assert response.status_code == 200
        data = response.json()
        assert "drafts" in data
        for d in data["drafts"]:
            assert d["approved_human"] is False

    def test_approve_email(self):
        """
        PATCH /emails/{id}/approve returns 200 and sets email_drafts.approved_human=true.

        Setup: mock DB returns the draft row on UPDATE ... RETURNING id
        Body:  { approved_by: 'Test Manager' }
        Expected: status 200
        Verify:
            - response has success=true
            - SQL contained 'approved_human' update
            - db.commit() was called
        """
        # UPDATE ... RETURNING id → fetchone returns a row tuple
        self.db.execute.return_value = _make_result(fetchone_value=(_DRAFT_ID,))

        response = self.client.patch(
            f"/emails/{_DRAFT_ID}/approve",
            json={"approved_by": "Test Manager"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        all_sql = " ".join(str(c) for c in self.db.execute.call_args_list)
        assert "approved_human" in all_sql
        self.db.commit.assert_called_once()

    def test_edit_email(self):
        """
        PATCH /emails/{id}/edit returns 200 and updates subject_line and edited_human.

        Setup: mock DB returns the draft row on UPDATE ... RETURNING id
        Body:  { edited_by, new_subject_line, new_body }
        Expected: status 200
        Verify:
            - response has success=true
            - SQL contained 'subject_line' and 'edited_human' columns
            - db.commit() was called
        """
        self.db.execute.return_value = _make_result(fetchone_value=(_DRAFT_ID,))

        response = self.client.patch(
            f"/emails/{_DRAFT_ID}/edit",
            json={
                "edited_by": "Test Manager",
                "new_subject_line": "New subject here",
                "new_body": "New body text here",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        all_sql = " ".join(str(c) for c in self.db.execute.call_args_list)
        assert "subject_line" in all_sql
        assert "edited_human" in all_sql
        self.db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# TestPipelineRoutes
# ---------------------------------------------------------------------------


class TestPipelineRoutes:
    """Integration tests for GET /pipeline/status and /pipeline/health routes."""

    def setup_method(self):
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("agents.orchestrator.pipeline_monitor.get_pipeline_counts")
    @patch("agents.orchestrator.pipeline_monitor.get_pipeline_value")
    def test_pipeline_status_returns_all_stages(self, mock_value, mock_counts):
        """
        GET /pipeline/status returns 200 with all pipeline stage keys present.

        Expected: status 200
        Verify: response contains keys:
            new, enriched, scored, approved, contacted, replied,
            meeting_booked, won, lost, no_response, archived
        """
        mock_counts.return_value = {
            "new": 10, "enriched": 8, "scored": 6, "approved": 4,
            "contacted": 3, "replied": 2, "meeting_booked": 1, "won": 0,
            "lost": 1, "no_response": 2, "archived": 3,
        }
        mock_value.return_value = {
            "total_savings_mid": 500_000.0,
            "total_tb_revenue_est": 120_000.0,
        }

        response = self.client.get("/pipeline/status")

        assert response.status_code == 200
        data = response.json()
        required_stages = (
            "new", "enriched", "scored", "approved", "contacted",
            "replied", "meeting_booked", "won", "lost", "no_response", "archived",
        )
        for stage in required_stages:
            assert stage in data, f"Stage '{stage}' missing from /pipeline/status response"

    @patch("agents.orchestrator.pipeline_monitor.check_agent_health")
    def test_pipeline_health_returns_services(self, mock_health):
        """
        GET /pipeline/health returns 200 with all service health keys.

        Expected: status 200
        Verify: response contains keys:
            postgres, ollama, api, airflow, sendgrid, tavily, slack
        """
        _ok = {"status": "ok", "message": "connected"}
        mock_health.return_value = {
            "postgres": _ok,
            "ollama":   _ok,
            "api":      {"status": "ok", "message": "running"},
            "airflow":  {"status": "ok", "message": "running"},
            "sendgrid": {"status": "ok", "message": "configured"},
            "tavily":   {"status": "ok", "message": "configured"},
            "slack":    {"status": "ok", "message": "configured"},
        }

        response = self.client.get("/pipeline/health")

        assert response.status_code == 200
        data = response.json()
        required_services = ("postgres", "ollama", "api", "airflow", "sendgrid", "tavily", "slack")
        for service in required_services:
            assert service in data, f"Service '{service}' missing from /pipeline/health response"


# ---------------------------------------------------------------------------
# TestTriggerRoutes
# ---------------------------------------------------------------------------


class TestTriggerRoutes:
    """Integration tests for POST /trigger/* routes."""

    def setup_method(self):
        # Provide a mock DB for any route that might call get_db
        app.dependency_overrides[get_db] = lambda: _mock_db()
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("api.routes.triggers._wrap")
    def test_trigger_scout_returns_immediately(self, mock_wrap):
        """
        POST /trigger/scout returns 200 immediately before the pipeline completes.

        Body: { industry, location, count, run_mode }
        Expected: status 200
        Verify:
            - response has trigger_id (valid UUID)
            - response has status = 'started'
            - response is received before background pipeline completes
              (confirmed by patching the background task wrapper _wrap)
        """
        response = self.client.post(
            "/trigger/scout",
            json={
                "industry": "healthcare",
                "location": "Buffalo, NY",
                "count": 5,
                "run_mode": "scout_only",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "trigger_id" in data
        assert data["status"] == "started"
        # Validate trigger_id is a well-formed UUID
        parsed = uuid.UUID(data["trigger_id"])
        assert str(parsed) == data["trigger_id"]

    def test_trigger_invalid_industry(self):
        """
        POST /trigger/full with an unrecognised industry returns 422 (validation error).

        Body:     { industry: 'invalid_industry', location, count, run_mode }
        Expected: status 422
        """
        response = self.client.post(
            "/trigger/full",
            json={
                "industry": "invalid_industry",
                "location": "Buffalo, NY",
                "count": 10,
                "run_mode": "full",
            },
        )

        assert response.status_code == 422

    def test_trigger_count_too_high(self):
        """
        POST /trigger/scout with count=999 (exceeds max 100) returns 422.

        Body:     { count: 999 }
        Expected: status 422
        """
        response = self.client.post(
            "/trigger/scout",
            json={
                "industry": "healthcare",
                "location": "Buffalo, NY",
                "count": 999,
                "run_mode": "scout_only",
            },
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestReportRoutes
# ---------------------------------------------------------------------------


class TestReportRoutes:
    """Integration tests for GET /health, /reports/weekly, and /reports/funnel."""

    def setup_method(self):
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_health_endpoint(self):
        """
        GET /health returns 200 with platform identity and timestamp.

        Expected: status 200
        Verify:
            - status = 'ok'
            - service = 'Utility Lead Intelligence Platform'
            - version = '1.0.0'
            - timestamp is not None
        """
        response = self.client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "Utility Lead Intelligence Platform"
        assert data["version"] == "1.0.0"
        assert data["timestamp"] is not None

    @patch("agents.orchestrator.report_generator.generate_weekly_report")
    def test_weekly_report_custom_date_range(self, mock_report):
        """
        GET /reports/weekly?start_date=2026-02-01&end_date=2026-02-28 returns 200
        with period_start and period_end matching the requested range.

        Expected: status 200
        Verify:
            - period_start = '2026-02-01'
            - period_end   = '2026-02-28'
        """
        mock_report.return_value = {
            "companies_found": {"total": 5, "by_industry": {}, "by_state": {}},
            "leads_by_tier": {"high": 2, "medium": 2, "low": 1},
            "emails": {
                "total_sent": 3, "first_emails": 3, "followups": 0,
                "open_rate_pct": 60.0, "click_rate_pct": 20.0,
            },
            "replies": {
                "total_replies": 1, "positive": 1, "neutral": 0,
                "negative": 0, "reply_rate_pct": 33.3,
            },
            "pipeline_value": {
                "total_savings_mid": 200_000.0,
                "total_tb_revenue_est": 48_000.0,
            },
        }
        # outcome counts query (meetings_booked, deals_won, deals_lost)
        self.db.execute.return_value = _make_result(
            first={"meetings_booked": 0, "deals_won": 0, "deals_lost": 0}
        )

        response = self.client.get(
            "/reports/weekly?start_date=2026-02-01&end_date=2026-02-28"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_start"] == "2026-02-01"
        assert data["period_end"] == "2026-02-28"

    @patch("agents.orchestrator.pipeline_monitor.get_pipeline_counts")
    def test_funnel_report_has_all_stages(self, mock_counts):
        """
        GET /reports/funnel returns 200 with all pipeline funnel stages and required keys.

        Expected: status 200
        Verify: response contains all funnel stages:
            new (found), scored (high-value leads), contacted,
            replied, meeting_booked (meeting)
        Verify: each stage item has 'count' and 'drop_off_from_prev_pct' keys
        """
        mock_counts.return_value = {
            "new": 50, "enriched": 40, "scored": 30, "approved": 20,
            "contacted": 15, "replied": 8, "meeting_booked": 3, "won": 1,
            "lost": 2, "no_response": 5, "archived": 3,
        }

        response = self.client.get("/reports/funnel")

        assert response.status_code == 200
        data = response.json()
        assert "funnel" in data

        stage_names = {item["stage"] for item in data["funnel"]}
        # Map user-facing conceptual stage names → actual API stage keys
        assert "new" in stage_names            # "found"         — newly discovered leads
        assert "scored" in stage_names         # "scored_high"   — analyst-scored leads
        assert "contacted" in stage_names      # "contacted"     — outreach sent
        assert "replied" in stage_names        # "replied"       — replied to outreach
        assert "meeting_booked" in stage_names # "meeting"       — booked a meeting

        for item in data["funnel"]:
            assert "count" in item, f"Stage item missing 'count': {item}"
            assert "drop_off_from_prev_pct" in item, (
                f"Stage item missing 'drop_off_from_prev_pct': {item}"
            )


# ---------------------------------------------------------------------------
# TestApiEdgeCases
# ---------------------------------------------------------------------------


class TestApiEdgeCases:
    """Edge case and boundary condition tests across all API routes."""

    def setup_method(self):
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_get_leads_empty_database(self):
        """GET /leads from an empty DB returns 200 with empty leads list and total_count=0."""
        self.db.execute.return_value = _make_result(
            first={"total_count": 0, "high_count": 0, "medium_count": 0, "low_count": 0},
            all_rows=[],
        )

        response = self.client.get("/leads")

        assert response.status_code == 200
        data = response.json()
        assert data["leads"] == []
        assert data["total_count"] == 0

    def test_get_pending_emails_all_approved(self):
        """GET /emails/pending when all drafts are approved returns empty drafts list."""
        self.db.execute.side_effect = [
            _make_result(all_rows=[]),
            _make_result(
                first={"total_count": 5, "pending_approval": 0, "approved_count": 5, "sent_count": 3}
            ),
        ]

        response = self.client.get("/emails/pending")

        assert response.status_code == 200
        data = response.json()
        assert data["drafts"] == []
        assert data["pending_approval"] == 0

    def test_approve_lead_not_found(self):
        """PATCH /leads/{id}/approve when no score row exists returns 404."""
        # SELECT id FROM lead_scores returns nothing
        self.db.execute.return_value = _make_result(first=None)

        response = self.client.patch(
            f"/leads/{_COMPANY_ID}/approve",
            json={"approved_by": "Test Manager"},
        )

        assert response.status_code == 404

    def test_approve_email_not_found(self):
        """PATCH /emails/{id}/approve when draft does not exist returns 404."""
        # UPDATE ... RETURNING id → fetchone returns None (no rows matched)
        self.db.execute.return_value = _make_result(fetchone_value=None)

        response = self.client.patch(
            f"/emails/{_DRAFT_ID}/approve",
            json={"approved_by": "Test Manager"},
        )

        assert response.status_code == 404

    def test_edit_email_not_found(self):
        """PATCH /emails/{id}/edit when draft does not exist returns 404."""
        self.db.execute.return_value = _make_result(fetchone_value=None)

        response = self.client.patch(
            f"/emails/{_DRAFT_ID}/edit",
            json={"edited_by": "Test Manager", "new_subject_line": "New subject"},
        )

        assert response.status_code == 404

    def test_trigger_count_too_low(self):
        """POST /trigger/scout with count=2 (below minimum 5) returns 422."""
        response = self.client.post(
            "/trigger/scout",
            json={
                "industry": "retail",
                "location": "Buffalo, NY",
                "count": 2,
                "run_mode": "scout_only",
            },
        )

        assert response.status_code == 422

    def test_get_leads_invalid_uuid_format(self):
        """GET /leads/{id} with a non-UUID path parameter returns 422."""
        response = self.client.get("/leads/not-a-valid-uuid")

        assert response.status_code == 422

    @patch("agents.orchestrator.pipeline_monitor.get_pipeline_counts")
    @patch("agents.orchestrator.pipeline_monitor.get_pipeline_value")
    def test_pipeline_status_total_active_count(self, mock_value, mock_counts):
        """GET /pipeline/status total_active reflects only active (non-terminal) stages."""
        mock_counts.return_value = {
            "new": 5, "enriched": 4, "scored": 3, "approved": 2,
            "contacted": 1, "replied": 1, "meeting_booked": 0, "won": 0,
            "lost": 2, "no_response": 1, "archived": 1,
        }
        mock_value.return_value = {"total_savings_mid": 0.0}

        response = self.client.get("/pipeline/status")

        assert response.status_code == 200
        data = response.json()
        # Active statuses: new + enriched + scored + approved + contacted + replied = 16
        assert data["total_active"] == 16


# ---------------------------------------------------------------------------
# TestParametrizedApi
# ---------------------------------------------------------------------------


class TestParametrizedApi:
    """Parametrized route tests for common patterns."""

    def setup_method(self):
        self.db = _mock_db()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("industry", [
        "healthcare", "hospitality", "manufacturing", "retail", "public_sector",
    ])
    def test_valid_industry_filter(self, industry):
        """GET /leads?industry=<valid> returns 200 for every valid industry."""
        self.db.execute.return_value = _make_result(
            first={"total_count": 0, "high_count": 0, "medium_count": 0, "low_count": 0},
            all_rows=[],
        )

        response = self.client.get(f"/leads?industry={industry}")

        assert response.status_code == 200

    @pytest.mark.parametrize("trigger_body,expected_status", [
        (
            {"industry": "healthcare", "location": "Buffalo, NY", "count": 5, "run_mode": "scout_only"},
            200,
        ),
        (
            {"industry": "bad_industry", "location": "Buffalo, NY", "count": 5, "run_mode": "full"},
            422,
        ),
        (
            {"industry": "retail", "location": "Buffalo, NY", "count": 101, "run_mode": "scout_only"},
            422,
        ),
        (
            {"industry": "retail", "location": "Buffalo, NY", "count": 4, "run_mode": "scout_only"},
            422,
        ),
    ])
    @patch("api.routes.triggers._wrap")
    def test_trigger_validation_cases(self, mock_wrap, trigger_body, expected_status):
        """Parametrized test across valid and invalid trigger request bodies."""
        response = self.client.post("/trigger/scout", json=trigger_body)
        assert response.status_code == expected_status

    @pytest.mark.parametrize("tier", ["high", "medium", "low"])
    def test_valid_tier_filter(self, tier):
        """GET /leads?tier=<valid> returns 200 for every valid tier value."""
        row = _lead_row(tier=tier)
        self.db.execute.return_value = _make_result(
            first={"total_count": 1, "high_count": int(tier == "high"),
                   "medium_count": int(tier == "medium"), "low_count": int(tier == "low")},
            all_rows=[row],
        )

        response = self.client.get(f"/leads?tier={tier}")

        assert response.status_code == 200
        data = response.json()
        for lead in data["leads"]:
            assert lead["tier"] == tier
