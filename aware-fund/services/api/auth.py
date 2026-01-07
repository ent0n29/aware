"""
AWARE API - Authentication Module

Simple API key authentication for the AWARE Fund API.
API keys are stored in the API_KEYS environment variable as a comma-separated list.

Usage:
    from auth import verify_api_key

    @app.get("/api/protected")
    async def protected_endpoint(api_key: str = Depends(verify_api_key)):
        return {"message": "Authenticated!"}

Environment Variables:
    API_KEYS - Comma-separated list of valid API keys
    API_AUTH_ENABLED - Set to "false" to disable auth (default: true)
"""

import os
from typing import Optional
from fastapi import Security, HTTPException, status, Request
from fastapi.security import APIKeyHeader

# API key header - standard X-API-Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_valid_api_keys() -> set[str]:
    """Get the set of valid API keys from environment."""
    keys_str = os.getenv("API_KEYS", "")
    if not keys_str:
        return set()
    return {key.strip() for key in keys_str.split(",") if key.strip()}


def is_auth_enabled() -> bool:
    """Check if API authentication is enabled."""
    return os.getenv("API_AUTH_ENABLED", "true").lower() != "false"


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Verify the API key from the X-API-Key header.

    Returns:
        The validated API key if successful

    Raises:
        HTTPException: 403 if key is invalid, 401 if key is missing
    """
    # Skip auth if disabled
    if not is_auth_enabled():
        return None

    # Get valid keys
    valid_keys = get_valid_api_keys()

    # If no keys configured, allow all (development mode)
    if not valid_keys:
        return None

    # Check if key was provided
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate key
    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key


async def optional_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Optional API key verification - doesn't require key but validates if present.
    Useful for endpoints that work for everyone but provide extra features for authenticated users.

    Returns:
        The validated API key if present and valid, None otherwise
    """
    if not api_key:
        return None

    valid_keys = get_valid_api_keys()
    if api_key in valid_keys:
        return api_key

    return None
