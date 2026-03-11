from __future__ import annotations

"""Pydantic models for reporting API response payloads.

Purpose:
- Defines schemas for weekly summary reports and top-lead ranking responses.

Dependencies:
- `pydantic` v2 for model validation and serialization.

Usage:
- Import the class you need in a route handler:
      from api.models.report import WeeklyReportResponse, TopLeadsResponse
"""

from datetime import date, datetime
from typing import Any, Dict, List
from uuid import UUID

from pydantic import BaseModel


class WeeklyReportResponse(BaseModel):
    """Full weekly report aggregating sourcing, scoring, outreach, and revenue."""

    period_start: date
    period_end: date

    # Sourcing
    companies_found: int
    companies_by_industry: Dict[str, Any]
    companies_by_state: Dict[str, Any]

    # Scoring
    leads_high: int
    leads_medium: int
    leads_low: int

    # Outreach
    emails_sent: int
    first_emails_sent: int
    followups_sent: int
    open_rate_pct: float
    click_rate_pct: float

    # Replies
    replies_total: int
    replies_positive: int
    replies_neutral: int
    replies_negative: int
    reply_rate_pct: float

    # Outcomes
    meetings_booked: int
    deals_won: int
    deals_lost: int

    # Pipeline value
    pipeline_value_mid: float
    pipeline_value_formatted: str
    troy_banks_revenue_estimate: float

    generated_at: datetime


class TopLeadItem(BaseModel):
    """Single lead entry in the top-leads ranking."""

    company_id: UUID
    company_name: str
    industry: str
    state: str
    score: float
    tier: str
    savings_formatted: str
    status: str
    contact_found: bool

    model_config = {"from_attributes": True}


class TopLeadsResponse(BaseModel):
    """Ranked list of top leads."""

    leads: List[TopLeadItem]
    total_count: int
