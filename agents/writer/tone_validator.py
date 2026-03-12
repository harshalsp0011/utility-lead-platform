from __future__ import annotations

"""Tone and spam-safety checks for generated outreach emails."""

import re
from typing import Any

_SPAM_WORDS = [
    "free",
    "guaranteed",
    "no risk",
    "winner",
    "urgent",
    "act now",
    "limited time",
    "click here",
    "earn money",
    "make money",
    "congratulations",
    "you have been selected",
]

_CTA_KEYWORDS = [
    "call",
    "schedule",
    "meeting",
    "chat",
    "connect",
    "talk",
    "discuss",
    "available",
]


def validate_tone(email_subject: str, email_body: str) -> dict[str, Any]:
    """Run all tone checks and return pass/fail with issues and score."""
    issues: list[str] = []

    flagged_words = check_spam_words((email_body or "") + " " + (email_subject or ""))
    for word in flagged_words:
        issues.append(f"Spam-trigger word found: {word}")

    length_issue = check_length(email_body)
    if length_issue:
        issues.append(length_issue)

    cta_issue = check_cta_present(email_body)
    if cta_issue:
        issues.append(cta_issue)

    caps_issue = check_caps_usage(email_body)
    if caps_issue:
        issues.append(caps_issue)

    savings_issue = check_savings_claim(email_body)
    if savings_issue:
        issues.append(savings_issue)

    passed = len(issues) == 0
    score = max(0.0, 10.0 - (2.0 * len(issues)))

    return {
        "passed": passed,
        "issues": issues,
        "score": score,
    }


def check_spam_words(text: str) -> list[str]:
    """Return spam words/phrases that appear in text (case-insensitive)."""
    source = (text or "").lower()
    found: list[str] = []

    for word in _SPAM_WORDS:
        if word in source:
            found.append(word)

    return found


def check_length(email_body: str) -> str | None:
    """Validate body word count range (50 to 250 words)."""
    word_count = len(re.findall(r"\b\w+\b", email_body or ""))

    if word_count > 250:
        return f"Email too long: {word_count} words. Max 250."
    if word_count < 50:
        return f"Email too short: {word_count} words. Min 50."
    return None


def check_cta_present(email_body: str) -> str | None:
    """Ensure at least one call-to-action keyword is present."""
    body = (email_body or "").lower()
    if not any(keyword in body for keyword in _CTA_KEYWORDS):
        return "No call to action found in email body"
    return None


def check_caps_usage(text: str) -> str | None:
    """Flag excessive all-caps words that can increase spam risk."""
    all_caps_words = re.findall(r"\b[A-Z]{2,}\b", text or "")
    if len(all_caps_words) > 3:
        return "Too many all-caps words: may trigger spam filters"
    return None


def check_savings_claim(email_body: str) -> str | None:
    """Flag very large dollar claims that should be manually verified."""
    body = email_body or ""

    for match in re.finditer(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)([KMBkmb]?)", body):
        numeric_part = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").upper()

        try:
            amount = float(numeric_part)
        except ValueError:
            continue

        if suffix == "K":
            amount *= 1_000
        elif suffix == "M":
            amount *= 1_000_000
        elif suffix == "B":
            amount *= 1_000_000_000

        if amount > 50_000_000:
            return "Savings claim seems unrealistically high — verify"

    return None


class ToneValidator:
    """Class-based interface for tone validation (used by test suite)."""

    def validate_tone(self, subject: str = "", body: str = "") -> dict[str, Any]:
        """Run all tone checks and return pass/fail with issues and score."""
        return validate_tone(subject, body)

    def check_spam_words(self, text: str) -> list[str]:
        """Return spam words/phrases that appear in text (case-insensitive)."""
        return check_spam_words(text)

    def check_length(self, text: str) -> str | None:
        """Validate body word count range (50 to 250 words)."""
        return check_length(text)

    def check_cta(self, text: str) -> str | None:
        """Ensure at least one call-to-action keyword is present."""
        return check_cta_present(text)

    def check_caps(self, text: str) -> str | None:
        """Flag excessive all-caps words that can increase spam risk."""
        return check_caps_usage(text)
