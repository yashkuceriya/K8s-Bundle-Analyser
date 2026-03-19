"""Shared guardrails for AI-powered analyzers."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Prompt injection / off-topic patterns
INJECTION_PATTERNS = re.compile(
    r"(ignore (previous|above|all) (instructions|prompts|rules)|"
    r"you are now|act as|pretend (to be|you)|"
    r"new persona|change your (role|personality|identity)|"
    r"forget (your|all) (instructions|rules)|"
    r"disregard (your|all|previous)|"
    r"system prompt|reveal your prompt)",
    re.IGNORECASE,
)

# Explicit/inappropriate language
EXPLICIT_PATTERNS = re.compile(
    r"\b(fuck(?:ing|ed|er|s)?|shit|damn|ass(?:hole)?|bitch|dick|cunt|bastard|"
    r"crap|hell|bloody|wtf|stfu|lmao|porn|nsfw|nude|sex(?:ual)?|"
    r"kill yourself|kys)\b",
    re.IGNORECASE,
)

# Allowed values for AI output validation
ALLOWED_SEVERITIES = {"critical", "warning", "info"}
ALLOWED_CATEGORIES = {
    "pod-health", "networking", "storage",
    "configuration", "security", "resource-usage",
}

MAX_FIELD_LENGTH = 2000

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_text(text: str) -> str:
    """Remove lines that match injection patterns from input text and log warnings."""
    lines = text.split("\n")
    clean: list[str] = []
    for line in lines:
        if INJECTION_PATTERNS.search(line):
            logger.warning("Guardrail: stripped suspicious line from input: %s", line[:120])
            continue
        clean.append(line)
    return "\n".join(clean)


def strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return _HTML_TAG_RE.sub("", text)


def validate_severity(value: str) -> str:
    """Return a valid severity or default to 'info'."""
    if value.lower() in ALLOWED_SEVERITIES:
        return value.lower()
    return "info"


def validate_category(value: str) -> str:
    """Return a valid category or default to 'configuration'."""
    if value.lower() in ALLOWED_CATEGORIES:
        return value.lower()
    return "configuration"


def truncate(text: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """Truncate text to max_length."""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text
