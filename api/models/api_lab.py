from __future__ import annotations

"""Pydantic models for the API Lab endpoints."""

from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared response envelope
# ---------------------------------------------------------------------------

class ApiLabResult(BaseModel):
    provider: str
    endpoint: str
    duration_ms: int
    stored_in: Optional[str] = None
    success: bool
    data: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Search & Discovery
# ---------------------------------------------------------------------------

class TavilySearchRequest(BaseModel):
    industry: str
    location: str


class TavilyNewsRequest(BaseModel):
    industry: str
    location: str
    max_results: int = 10


class GoogleMapsRequest(BaseModel):
    industry: str
    location: str
    limit: int = 20


class YelpRequest(BaseModel):
    industry: str
    location: str
    limit: int = 50


# ---------------------------------------------------------------------------
# Contact Enrichment & Email Finding
# ---------------------------------------------------------------------------

class HunterRequest(BaseModel):
    domain: str


class ApolloEnrichRequest(BaseModel):
    domain: str


class ApolloSearchRequest(BaseModel):
    company_name: str
    domain: str


class SnovRequest(BaseModel):
    company_name: str
    domain: str


class ProspeoRequest(BaseModel):
    company_name: str
    domain: str


class ZeroBounceValidateRequest(BaseModel):
    email: str


class ZeroBounceGuessFormatRequest(BaseModel):
    domain: str


class SerperEmailRequest(BaseModel):
    company_name: str
    domain: str


class EnrichmentWaterfallRequest(BaseModel):
    company_name: str
    domain: str


# ---------------------------------------------------------------------------
# Email Delivery
# ---------------------------------------------------------------------------

class SendGridTestRequest(BaseModel):
    to_email: str
    to_name: str
    subject: str
    body: str


class InstantlyTestRequest(BaseModel):
    to_email: str
    to_name: str
    subject: str
    body: str


# ---------------------------------------------------------------------------
# Web Scraping
# ---------------------------------------------------------------------------

class ScraperDirectoryRequest(BaseModel):
    directory_url: str
