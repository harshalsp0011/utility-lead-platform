from __future__ import annotations

"""API Lab routes — live test endpoints for every external provider.

Each endpoint calls the underlying agent client function directly and returns
a unified ApiLabResult envelope with timing, success, data, and storage info.
These are developer/operator tools; they do NOT log to OutreachEvents and most
do NOT write to the database (the enrichment waterfall is the exception).
"""

import logging
import time
from typing import Any

import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_db, verify_api_key
from api.models.api_lab import (
    ApiLabResult,
    ApolloEnrichRequest,
    ApolloSearchRequest,
    EnrichmentWaterfallRequest,
    GoogleMapsRequest,
    HunterRequest,
    InstantlyTestRequest,
    ProspeoRequest,
    ScraperDirectoryRequest,
    SendGridTestRequest,
    SerperEmailRequest,
    SnovRequest,
    TavilyNewsRequest,
    TavilySearchRequest,
    YelpRequest,
    ZeroBounceGuessFormatRequest,
    ZeroBounceValidateRequest,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------

def _timed_call(fn, *args, **kwargs) -> tuple[Any, int, str | None]:
    t0 = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        return result, int((time.monotonic() - t0) * 1000), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("API Lab call failed: %s", exc)
        return None, int((time.monotonic() - t0) * 1000), str(exc)


def _empty_hint(provider_env_var: str) -> str:
    return f"Returned empty — check that {provider_env_var} is set in .env"


# ---------------------------------------------------------------------------
# Search & Discovery
# ---------------------------------------------------------------------------

@router.post("/tavily/search", response_model=ApiLabResult)
def lab_tavily_search(req: TavilySearchRequest) -> ApiLabResult:
    from agents.scout.search_client import search_directory_sources

    data, ms, err = _timed_call(
        search_directory_sources, req.industry, req.location, None
    )
    if err is None and not data:
        err = _empty_hint("TAVILY_API_KEY")
    return ApiLabResult(
        provider="tavily_search",
        endpoint="/api-lab/tavily/search",
        duration_ms=ms,
        stored_in="directory_sources table (requires db_session — not stored from API Lab)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/tavily/news", response_model=ApiLabResult)
def lab_tavily_news(req: TavilyNewsRequest) -> ApiLabResult:
    from agents.scout.news_scout_client import find_companies_in_news

    data, ms, err = _timed_call(
        find_companies_in_news, req.industry, req.location, req.max_results
    )
    if err is None and not data:
        err = _empty_hint("TAVILY_API_KEY")
    return ApiLabResult(
        provider="tavily_news",
        endpoint="/api-lab/tavily/news",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/google-maps/search", response_model=ApiLabResult)
def lab_google_maps(req: GoogleMapsRequest) -> ApiLabResult:
    from agents.scout.google_maps_client import search_companies

    data, ms, err = _timed_call(
        search_companies, req.industry, req.location, req.limit
    )
    if err is None and not data:
        err = _empty_hint("GOOGLE_MAPS_API_KEY")
    return ApiLabResult(
        provider="google_maps",
        endpoint="/api-lab/google-maps/search",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/yelp/search", response_model=ApiLabResult)
def lab_yelp(req: YelpRequest) -> ApiLabResult:
    from agents.scout.yelp_client import search_companies

    data, ms, err = _timed_call(
        search_companies, req.industry, req.location, req.limit
    )
    if err is None and not data:
        err = _empty_hint("YELP_API_KEY")
    return ApiLabResult(
        provider="yelp",
        endpoint="/api-lab/yelp/search",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


# ---------------------------------------------------------------------------
# Contact Enrichment & Email Finding — individual (read-only, no DB writes)
# ---------------------------------------------------------------------------

@router.post("/hunter/search", response_model=ApiLabResult)
def lab_hunter(req: HunterRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_via_hunter

    data, ms, err = _timed_call(find_via_hunter, req.domain)
    if err is None and not data:
        err = _empty_hint("HUNTER_API_KEY")
    return ApiLabResult(
        provider="hunter",
        endpoint="/api-lab/hunter/search",
        duration_ms=ms,
        stored_in="not stored (individual call — use /enrichment/waterfall to persist)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/apollo/enrich", response_model=ApiLabResult)
def lab_apollo_enrich(req: ApolloEnrichRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import enrich_company_data

    data, ms, err = _timed_call(enrich_company_data, req.domain)
    if err is None and not data:
        err = _empty_hint("APOLLO_API_KEY")
    return ApiLabResult(
        provider="apollo_enrich",
        endpoint="/api-lab/apollo/enrich",
        duration_ms=ms,
        stored_in="not stored (individual call)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/apollo/search", response_model=ApiLabResult)
def lab_apollo_search(req: ApolloSearchRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_via_apollo

    data, ms, err = _timed_call(find_via_apollo, req.company_name, req.domain)
    if err is None and not data:
        err = _empty_hint("APOLLO_API_KEY")
    return ApiLabResult(
        provider="apollo_search",
        endpoint="/api-lab/apollo/search",
        duration_ms=ms,
        stored_in="not stored (individual call — use /enrichment/waterfall to persist)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/snov/search", response_model=ApiLabResult)
def lab_snov(req: SnovRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_via_snov

    data, ms, err = _timed_call(find_via_snov, req.company_name, req.domain)
    if err is None and not data:
        err = _empty_hint("SNOV_CLIENT_ID / SNOV_CLIENT_SECRET")
    return ApiLabResult(
        provider="snov",
        endpoint="/api-lab/snov/search",
        duration_ms=ms,
        stored_in="not stored (individual call — use /enrichment/waterfall to persist)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/prospeo/search", response_model=ApiLabResult)
def lab_prospeo(req: ProspeoRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_via_prospeo

    data, ms, err = _timed_call(find_via_prospeo, req.company_name, req.domain)
    if err is None and not data:
        err = _empty_hint("PROSPEO_API_KEY")
    return ApiLabResult(
        provider="prospeo",
        endpoint="/api-lab/prospeo/search",
        duration_ms=ms,
        stored_in="not stored (individual call — use /enrichment/waterfall to persist)",
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/zerobounce/validate", response_model=ApiLabResult)
def lab_zerobounce_validate(req: ZeroBounceValidateRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import verify_email_zerobounce

    data, ms, err = _timed_call(verify_email_zerobounce, req.email)
    if err is None and data is None:
        err = _empty_hint("ZEROBOUNCE_API_KEY")
    return ApiLabResult(
        provider="zerobounce_validate",
        endpoint="/api-lab/zerobounce/validate",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/zerobounce/guessformat", response_model=ApiLabResult)
def lab_zerobounce_guessformat(req: ZeroBounceGuessFormatRequest) -> ApiLabResult:
    """Inline call to ZeroBounce guessformat — no standalone fn in enrichment_client."""
    settings = get_settings()
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "https://api.zerobounce.net/v2/guessformat",
            params={"api_key": settings.ZEROBOUNCE_API_KEY, "domain": req.domain},
            timeout=15,
        )
        ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        data = resp.json()
        err = None if data else _empty_hint("ZEROBOUNCE_API_KEY")
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        data = None
        err = str(exc)

    return ApiLabResult(
        provider="zerobounce_guessformat",
        endpoint="/api-lab/zerobounce/guessformat",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.post("/serper/search", response_model=ApiLabResult)
def lab_serper_email(req: SerperEmailRequest) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_via_serper_email

    data, ms, err = _timed_call(find_via_serper_email, req.company_name, req.domain)
    if err is None and not data:
        err = _empty_hint("SERPER_API_KEY / SERPAPI_API_KEY")
    return ApiLabResult(
        provider="serper_email",
        endpoint="/api-lab/serper/search",
        duration_ms=ms,
        stored_in="not stored (individual call — use /enrichment/waterfall to persist)",
        success=err is None,
        data=data,
        error=err,
    )


# ---------------------------------------------------------------------------
# Contact Enrichment — combined waterfall (writes to contacts table)
# ---------------------------------------------------------------------------

@router.post("/enrichment/waterfall", response_model=ApiLabResult)
def lab_enrichment_waterfall(
    req: EnrichmentWaterfallRequest,
    db: Session = Depends(get_db),
) -> ApiLabResult:
    from agents.analyst.enrichment_client import find_contacts

    data, ms, err = _timed_call(find_contacts, req.company_name, req.domain, db)
    stored = "contacts table"
    if err is None and not data:
        err = (
            "Returned empty — company may not exist in the companies table "
            "(0 contacts saved), or no contact providers returned results."
        )
        stored = "contacts table (0 records saved)"
    return ApiLabResult(
        provider="enrichment_waterfall",
        endpoint="/api-lab/enrichment/waterfall",
        duration_ms=ms,
        stored_in=stored,
        success=err is None,
        data=data,
        error=err,
    )


# ---------------------------------------------------------------------------
# Email Delivery (live sends — confirmation required on frontend)
# ---------------------------------------------------------------------------

@router.post("/sendgrid/test", response_model=ApiLabResult)
def lab_sendgrid(req: SendGridTestRequest) -> ApiLabResult:
    from agents.outreach.email_sender import send_via_sendgrid

    settings = get_settings()
    data, ms, err = _timed_call(
        send_via_sendgrid,
        req.to_email,
        req.to_name,
        req.subject,
        req.body,
        settings.SENDGRID_FROM_EMAIL,
    )
    return ApiLabResult(
        provider="sendgrid",
        endpoint="/api-lab/sendgrid/test",
        duration_ms=ms,
        stored_in="not stored (test send — no OutreachEvent logged)",
        success=err is None and (data or {}).get("success", False),
        data=data,
        error=err or (None if (data or {}).get("success") else (data or {}).get("message_id")),
    )


@router.post("/instantly/test", response_model=ApiLabResult)
def lab_instantly(req: InstantlyTestRequest) -> ApiLabResult:
    from agents.outreach.email_sender import send_via_instantly

    data, ms, err = _timed_call(
        send_via_instantly,
        req.to_email,
        req.to_name,
        req.subject,
        req.body,
    )
    return ApiLabResult(
        provider="instantly",
        endpoint="/api-lab/instantly/test",
        duration_ms=ms,
        stored_in="not stored (test send — no OutreachEvent logged)",
        success=err is None and (data or {}).get("success", False),
        data=data,
        error=err or (None if (data or {}).get("success") else (data or {}).get("message_id")),
    )


# ---------------------------------------------------------------------------
# Web Scraping & Proxies
# ---------------------------------------------------------------------------

@router.post("/scraper/directory", response_model=ApiLabResult)
def lab_scraper_directory(req: ScraperDirectoryRequest) -> ApiLabResult:
    from agents.scout.directory_scraper import scrape_directory

    data, ms, err = _timed_call(scrape_directory, req.directory_url)
    if err is None and not data:
        err = "Returned empty — URL may have no recognisable listing elements or is blocked."
    return ApiLabResult(
        provider="scraper_directory",
        endpoint="/api-lab/scraper/directory",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


# ---------------------------------------------------------------------------
# Credit / limit checks  (GET — no body required)
# ---------------------------------------------------------------------------

@router.get("/credits/hunter", response_model=ApiLabResult)
def credits_hunter() -> ApiLabResult:
    """Check Hunter.io account: remaining domain-search credits."""
    settings = get_settings()
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/account",
            params={"api_key": settings.HUNTER_API_KEY},
            timeout=10,
        )
        ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        payload = resp.json().get("data", {})
        searches = payload.get("requests", {}).get("searches", {})
        data = {
            "plan": payload.get("plan_name"),
            "searches_used": searches.get("used"),
            "searches_available": searches.get("available"),
            "reset_date": payload.get("reset_date"),
        }
        err = None
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        data = None
        err = str(exc)
    return ApiLabResult(
        provider="hunter_credits",
        endpoint="/api-lab/credits/hunter",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.get("/credits/zerobounce", response_model=ApiLabResult)
def credits_zerobounce() -> ApiLabResult:
    """Check ZeroBounce remaining email-validation credits."""
    settings = get_settings()
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "https://api.zerobounce.net/v2/getcredits",
            params={"api_key": settings.ZEROBOUNCE_API_KEY},
            timeout=10,
        )
        ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        payload = resp.json()
        data = {"credits": payload.get("Credits")}
        err = None
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        data = None
        err = str(exc)
    return ApiLabResult(
        provider="zerobounce_credits",
        endpoint="/api-lab/credits/zerobounce",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.get("/credits/snov", response_model=ApiLabResult)
def credits_snov() -> ApiLabResult:
    """Check Snov.io remaining email-finder credits (requires OAuth token)."""
    settings = get_settings()
    t0 = time.monotonic()
    try:
        # Step 1 — get OAuth access token
        token_resp = requests.post(
            "https://api.snov.io/v1/oauth/access_token",
            json={
                "grant_type": "client_credentials",
                "client_id": settings.SNOV_CLIENT_ID,
                "client_secret": settings.SNOV_CLIENT_SECRET,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token", "")

        # Step 2 — get balance
        bal_resp = requests.post(
            "https://api.snov.io/v1/get-balance",
            json={"access_token": access_token},
            timeout=10,
        )
        ms = int((time.monotonic() - t0) * 1000)
        bal_resp.raise_for_status()
        data = bal_resp.json()
        err = None
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        data = None
        err = str(exc)
    return ApiLabResult(
        provider="snov_credits",
        endpoint="/api-lab/credits/snov",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )


@router.get("/credits/scraperapi", response_model=ApiLabResult)
def credits_scraperapi() -> ApiLabResult:
    """Check ScraperAPI account usage: requests used vs limit."""
    settings = get_settings()
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "http://api.scraperapi.com/account",
            params={"api_key": settings.SCRAPERAPI_KEY},
            timeout=10,
        )
        ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        payload = resp.json()
        data = {
            "requests_used": payload.get("requestCount"),
            "request_limit": payload.get("requestLimit"),
            "concurrency_limit": payload.get("concurrencyLimit"),
        }
        err = None
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        data = None
        err = str(exc)
    return ApiLabResult(
        provider="scraperapi_credits",
        endpoint="/api-lab/credits/scraperapi",
        duration_ms=ms,
        stored_in=None,
        success=err is None,
        data=data,
        error=err,
    )
