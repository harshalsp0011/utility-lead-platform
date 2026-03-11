from __future__ import annotations

"""Template loading and rendering helpers for outreach emails."""

from pathlib import Path
from typing import Any

from agents.analyst import savings_calculator

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates"

_INDUSTRY_TEMPLATE_MAP = {
    "healthcare": "email_healthcare.txt",
    "hospitality": "email_hospitality.txt",
    "manufacturing": "email_manufacturing.txt",
    "retail": "email_retail.txt",
    "public_sector": "email_public_sector.txt",
}

_FOLLOWUP_TEMPLATE_MAP = {
    1: "followup_day3.txt",
    2: "followup_day7.txt",
    3: "followup_day14.txt",
}


def load_template(industry: str) -> str:
    """Load a primary email template for the given industry bucket."""
    template_path = Path(get_template_for_industry(industry))
    return template_path.read_text(encoding="utf-8")


def load_followup_template(follow_up_number: int) -> str:
    """Load a follow-up email template by sequence number (1-3)."""
    file_name = _FOLLOWUP_TEMPLATE_MAP.get(int(follow_up_number))
    if file_name is None:
        raise ValueError("follow_up_number must be 1, 2, or 3")

    template_path = _TEMPLATES_DIR / file_name
    return template_path.read_text(encoding="utf-8")


def fill_static_fields(template_string: str, context_dict: dict[str, Any]) -> str:
    """Replace known placeholders while leaving unknown placeholders unchanged."""
    rendered = template_string
    for key, value in context_dict.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", "" if value is None else str(value))
    return rendered


def build_context(
    company: Any,
    features: Any,
    score: Any,
    contact: Any,
    settings: Any,
) -> dict[str, Any]:
    """Build one context dictionary with all template placeholders."""
    savings_low = _as_float(_read_field(features, "savings_low"))
    savings_mid = _as_float(_read_field(features, "savings_mid"))
    savings_high = _as_float(_read_field(features, "savings_high"))

    savings_range = savings_calculator.format_savings_for_display(
        savings_low=savings_low,
        savings_high=savings_high,
    )

    contact_first_name = _extract_first_name(
        _read_field(contact, "first_name") or _read_field(contact, "full_name")
    )

    company_name = _as_string(_read_field(company, "name"))
    site_count = _as_int(_read_field(features, "estimated_site_count") or _read_field(company, "site_count"))
    state = _as_string(_read_field(company, "state"))

    subject_line = (
        f"Potential utility recovery opportunities for {company_name}"
        if company_name
        else "Potential utility recovery opportunities"
    )

    unsubscribe_link = _as_string(getattr(settings, "UNSUBSCRIBE_LINK", ""))
    if not unsubscribe_link:
        unsubscribe_link = "https://www.troyandbanks.com/unsubscribe"

    return {
        "subject_line": subject_line,
        "contact_first_name": contact_first_name or "there",
        "company_name": company_name,
        "site_count": site_count,
        "state": state,
        "savings_low_formatted": _format_currency_full(savings_low),
        "savings_mid_formatted": _format_currency_full(savings_mid),
        "savings_high_formatted": _format_currency_full(savings_high),
        "savings_range_formatted": savings_range,
        "tier": _as_string(_read_field(score, "tier")),
        "score": _as_float(_read_field(score, "score")),
        "tb_sender_name": _as_string(getattr(settings, "TB_SENDER_NAME", "")),
        "tb_sender_title": _as_string(getattr(settings, "TB_SENDER_TITLE", "")),
        "tb_phone": _as_string(getattr(settings, "TB_PHONE", "")),
        "unsubscribe_link": unsubscribe_link,
    }


def get_template_for_industry(industry: str) -> str:
    """Return the full file path for an industry's primary email template."""
    normalized = (industry or "").strip().lower()
    file_name = _INDUSTRY_TEMPLATE_MAP.get(normalized, "email_healthcare.txt")
    return str(_TEMPLATES_DIR / file_name)


def _read_field(record: Any, key: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_first_name(value: Any) -> str:
    text_value = _as_string(value)
    if not text_value:
        return ""
    return text_value.split()[0]


def _format_currency_full(value: float) -> str:
    return f"${value:,.0f}"
