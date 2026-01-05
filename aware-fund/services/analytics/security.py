"""
AWARE Analytics - Security Utilities

Provides sanitization functions for safe SQL query construction.
Used across all analytics modules to prevent SQL injection.
"""

import re
import logging

logger = logging.getLogger(__name__)


def sanitize_identifier(value: str, max_length: int = 100) -> str:
    """
    Sanitize a string identifier (username, market_slug, etc.) for safe SQL usage.

    This function:
    1. Escapes single quotes by doubling them (SQL standard)
    2. Removes null bytes and control characters
    3. Limits length to prevent buffer attacks
    4. Strips leading/trailing whitespace

    Args:
        value: The string to sanitize
        max_length: Maximum allowed length (default 100)

    Returns:
        Sanitized string safe for SQL interpolation
    """
    if not value:
        return ''

    # Convert to string if needed
    value = str(value)

    # Remove null bytes and control characters (except printable)
    sanitized = ''.join(c for c in value if c.isprintable() and c not in '\x00\n\r')

    # Escape single quotes (SQL standard escaping)
    sanitized = sanitized.replace("'", "''")

    # Strip whitespace
    sanitized = sanitized.strip()

    # Limit length
    return sanitized[:max_length]


def sanitize_market_slug(value: str) -> str:
    """
    Sanitize a market slug for SQL queries.

    Market slugs should only contain alphanumeric characters, hyphens, and underscores.
    """
    if not value:
        return ''

    # First apply general sanitization
    sanitized = sanitize_identifier(value, max_length=200)

    # Market slugs should be URL-safe characters
    # Allow: a-z, A-Z, 0-9, -, _, .
    sanitized = re.sub(r"[^a-zA-Z0-9\-_.]", '', sanitized)

    return sanitized


def sanitize_username(value: str) -> str:
    """
    Sanitize a username for SQL queries.

    Polymarket usernames are relatively permissive but shouldn't contain SQL special chars.
    """
    if not value:
        return ''

    # Apply general sanitization with reasonable username length
    return sanitize_identifier(value, max_length=50)


def validate_positive_int(value: int, max_value: int = 10000) -> int:
    """
    Validate and constrain a positive integer parameter.

    Args:
        value: The integer to validate
        max_value: Maximum allowed value

    Returns:
        Validated integer clamped to valid range
    """
    try:
        val = int(value)
        return max(0, min(val, max_value))
    except (TypeError, ValueError):
        return 0


def validate_days_param(days: int) -> int:
    """
    Validate a 'days' parameter for lookback queries.

    Args:
        days: Number of days

    Returns:
        Validated days value (1-365)
    """
    return max(1, min(int(days), 365))


# Strategy type whitelist for validation
VALID_STRATEGY_TYPES = frozenset({
    'UNKNOWN',
    'ARBITRAGEUR',
    'MARKET_MAKER',
    'DIRECTIONAL_FUNDAMENTAL',
    'DIRECTIONAL_MOMENTUM',
    'EVENT_DRIVEN',
    'SCALPER',
    'HYBRID',
    'SWING_TRADER',
})


def validate_strategy_type(value: str) -> str:
    """
    Validate a strategy type against the whitelist.

    Args:
        value: Strategy type string

    Returns:
        Validated strategy type or 'UNKNOWN' if invalid
    """
    if not value:
        return 'UNKNOWN'

    upper_value = str(value).upper().strip()

    if upper_value in VALID_STRATEGY_TYPES:
        return upper_value

    return 'UNKNOWN'
