"""Intent parsing for search queries using Claude Haiku.

Parses natural language user messages into structured search parameters
for YouTube and website searches. Falls back gracefully on errors.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedIntent:
    """Result of parsing a user's search intent."""

    search_query: str
    limit: int
    confidence: float
    fallback_used: bool = False
    error: str | None = None


async def parse_youtube_intent(
    message: str,
    ai_settings: dict[str, Any],
    fallback_limit: int = 10,
) -> ParsedIntent:
    """Parse a user's natural language message into YouTube search parameters.

    Uses Claude Haiku to extract search query and desired result count.
    Falls back to the original message if parsing fails or confidence is low.

    Args:
        message: User's natural language input
        ai_settings: AI provider configuration from user_settings
        fallback_limit: Default limit if parsing fails

    Returns:
        ParsedIntent with search_query, limit, and confidence score
    """
    try:
        import anthropic
    except ImportError:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error="Anthropic library not installed",
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        encrypted_key = ai_settings.get("claudeKey", "")
        if isinstance(encrypted_key, str) and encrypted_key:
            from app.ai.client import _decrypt_field

            api_key = _decrypt_field(encrypted_key)

    if not api_key:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error="No Claude API key configured",
        )

    prompt = f"""Parse this user message into YouTube search parameters.

User message: {message}

Respond with a JSON object containing:
- "search_query": cleaned search query (string, preserve Korean if present)
- "limit": desired number of results (integer, 1-25, default 10)
- "confidence": how confidently you understood the intent (0.0-1.0)

Example: {{"search_query": "Python tutorials for beginners", "limit": 10, "confidence": 0.95}}

Respond with ONLY the JSON object, no markdown or explanation."""

    try:
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""
        parsed = json.loads(text.strip())

        search_query = parsed.get("search_query", message)
        limit = int(parsed.get("limit", fallback_limit))
        limit = max(1, min(25, limit))
        confidence = float(parsed.get("confidence", 0.6))

        # Validate search query is not empty
        if not search_query or not search_query.strip():
            return ParsedIntent(
                search_query=message,
                limit=fallback_limit,
                confidence=0.0,
                fallback_used=True,
                error="AI returned empty search query",
            )
        search_query = search_query.strip()

        # If confidence is too low, flag it but return the parsed result
        fallback_used = confidence < 0.6

        return ParsedIntent(
            search_query=search_query,
            limit=limit,
            confidence=confidence,
            fallback_used=fallback_used,
        )
    except Exception as exc:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error=str(exc),
        )


async def parse_website_intent(
    message: str,
    ai_settings: dict[str, Any],
    fallback_limit: int = 5,
) -> ParsedIntent:
    """Parse a user's natural language message into website search parameters.

    Uses Claude Haiku to extract search query and desired result count.
    Falls back to the original message if parsing fails or confidence is low.

    Args:
        message: User's natural language input
        ai_settings: AI provider configuration from user_settings
        fallback_limit: Default limit if parsing fails (default 5 for web)

    Returns:
        ParsedIntent with search_query, limit, and confidence score
    """
    try:
        import anthropic
    except ImportError:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error="Anthropic library not installed",
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        encrypted_key = ai_settings.get("claudeKey", "")
        if isinstance(encrypted_key, str) and encrypted_key:
            from app.ai.client import _decrypt_field

            api_key = _decrypt_field(encrypted_key)

    if not api_key:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error="No Claude API key configured",
        )

    prompt = f"""Parse this user message into website search parameters.

User message: {message}

Respond with a JSON object containing:
- "search_query": cleaned search query (string, preserve Korean if present)
- "limit": desired number of website results (integer, 1-10, default 5)
- "confidence": how confidently you understood the intent (0.0-1.0)

Example: {{"search_query": "best practices for React hooks", "limit": 5, "confidence": 0.92}}

Respond with ONLY the JSON object, no markdown or explanation."""

    try:
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""
        parsed = json.loads(text.strip())

        search_query = parsed.get("search_query", message)
        limit = int(parsed.get("limit", fallback_limit))
        limit = max(1, min(10, limit))
        confidence = float(parsed.get("confidence", 0.6))

        # Validate search query is not empty
        if not search_query or not search_query.strip():
            return ParsedIntent(
                search_query=message,
                limit=fallback_limit,
                confidence=0.0,
                fallback_used=True,
                error="AI returned empty search query",
            )
        search_query = search_query.strip()

        # If confidence is too low, flag it but return the parsed result
        fallback_used = confidence < 0.6

        return ParsedIntent(
            search_query=search_query,
            limit=limit,
            confidence=confidence,
            fallback_used=fallback_used,
        )
    except Exception as exc:
        return ParsedIntent(
            search_query=message,
            limit=fallback_limit,
            confidence=0.0,
            fallback_used=True,
            error=str(exc),
        )
