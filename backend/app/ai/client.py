import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class NoteResult:
    title: str
    content: str
    frontmatter: dict[str, str]
    citations: list[str] = field(default_factory=list)
    wiki_links: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    ai_action: str = "created"
    similarity_reasoning: str = ""
    error: Optional[str] = None


_NOTE_PROMPT = """\
You are a knowledge management assistant. Convert the source content below into a well-structured Obsidian Markdown note.

Source URL: {source_url}
Source type: {source_type}
Title hint: {title}
Existing note titles (for [[wiki links]]): {existing_titles}

Content:
{text}

Respond with a single JSON object (no markdown fences) containing exactly these keys:
  "title"               – concise, descriptive note title (string)
  "content"             – Markdown body with ## headings and bullet points (string, NO YAML frontmatter)
  "citations"           – list of citation strings each formatted as "Title – URL (date if known)"
  "wiki_links"          – list of exact titles from the existing note titles that are semantically related
  "quality_score"       – float 0.0–1.0: how complete and accurate the note is
  "ai_action"           – one of "created", "merged", or "updated"
  "similarity_reasoning" – one sentence on overlap with existing notes, or "No significant overlap found"

Do not fabricate information absent from the source.
"""


def _decrypt_field(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext

    key_str = os.getenv("SETTINGS_ENCRYPTION_KEY", "")
    if len(key_str) < 32:
        return ciphertext

    try:
        encrypted_bytes = base64.b64decode(ciphertext)
        if len(encrypted_bytes) < 12:
            return ciphertext

        nonce = encrypted_bytes[:12]
        ct = encrypted_bytes[12:]
        key = key_str.encode("utf-8")[:32]
        cipher = AESGCM(key)
        plaintext = cipher.decrypt(nonce, ct, None)
        return plaintext.decode("utf-8")
    except Exception:
        return ciphertext


def _get_claude_key(ai_settings: dict[str, object]) -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        return key
    encrypted = ai_settings.get("claudeKey", "")
    if isinstance(encrypted, str):
        return _decrypt_field(encrypted)
    return ""


def _get_openai_key(ai_settings: dict[str, object]) -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if key:
        return key
    encrypted = ai_settings.get("openaiKey", "")
    if isinstance(encrypted, str):
        return _decrypt_field(encrypted)
    return ""


def _parse_note_response(raw: str) -> dict[str, object]:
    clean = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    clean = re.sub(r"\n?```\s*$", "", clean)
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _build_frontmatter(title: str, source_url: str, source_type: str) -> dict[str, str]:
    return {
        "title": title,
        "source": source_url,
        "source_type": source_type,
        "created": datetime.now(timezone.utc).isoformat(),
        "tags": source_type,
    }


async def _generate_with_claude(
    title: str,
    text: str,
    source_url: str,
    source_type: str,
    api_key: str,
    existing_titles: list[str],
) -> NoteResult:
    try:
        import anthropic
    except ImportError:
        return NoteResult(
            title="",
            content="",
            frontmatter={},
            error="Note generation unavailable. Required AI library not installed.",
        )

    try:
        text_truncated = text[:30000]
        existing_str = ", ".join(existing_titles) if existing_titles else "None"
        prompt = _NOTE_PROMPT.format(
            source_url=source_url,
            source_type=source_type,
            title=title,
            existing_titles=existing_str,
            text=text_truncated,
        )

        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_dict = _parse_note_response(message.content[0].text)
        if not response_dict:
            return NoteResult(
                title=title,
                content="",
                frontmatter=_build_frontmatter(title, source_url, source_type),
                error="Note generation failed. Check Settings > AI Providers.",
            )

        note_title = response_dict.get("title", title)
        content = response_dict.get("content", "")
        citations = response_dict.get("citations", [])
        wiki_links = response_dict.get("wiki_links", [])
        quality_score = float(response_dict.get("quality_score", 0.5))
        ai_action = response_dict.get("ai_action", "created")
        similarity_reasoning = response_dict.get("similarity_reasoning", "")

        if not isinstance(citations, list):
            citations = []
        if not isinstance(wiki_links, list):
            wiki_links = []

        return NoteResult(
            title=note_title,
            content=content,
            frontmatter=_build_frontmatter(note_title, source_url, source_type),
            citations=citations,
            wiki_links=wiki_links,
            quality_score=quality_score,
            ai_action=ai_action,
            similarity_reasoning=similarity_reasoning,
        )
    except Exception as e:
        return NoteResult(
            title=title,
            content="",
            frontmatter=_build_frontmatter(title, source_url, source_type),
            error=str(e),
        )


async def _generate_with_openai(
    title: str,
    text: str,
    source_url: str,
    source_type: str,
    api_key: str,
    existing_titles: list[str],
) -> NoteResult:
    try:
        import openai
    except ImportError:
        return NoteResult(
            title="",
            content="",
            frontmatter={},
            error="Note generation unavailable. Required AI library not installed.",
        )

    try:
        text_truncated = text[:30000]
        existing_str = ", ".join(existing_titles) if existing_titles else "None"
        prompt = _NOTE_PROMPT.format(
            source_url=source_url,
            source_type=source_type,
            title=title,
            existing_titles=existing_str,
            text=text_truncated,
        )

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        client = openai.AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        response_dict = _parse_note_response(response.choices[0].message.content)
        if not response_dict:
            return NoteResult(
                title=title,
                content="",
                frontmatter=_build_frontmatter(title, source_url, source_type),
                error="Note generation failed. Check Settings > AI Providers.",
            )

        note_title = response_dict.get("title", title)
        content = response_dict.get("content", "")
        citations = response_dict.get("citations", [])
        wiki_links = response_dict.get("wiki_links", [])
        quality_score = float(response_dict.get("quality_score", 0.5))
        ai_action = response_dict.get("ai_action", "created")
        similarity_reasoning = response_dict.get("similarity_reasoning", "")

        if not isinstance(citations, list):
            citations = []
        if not isinstance(wiki_links, list):
            wiki_links = []

        return NoteResult(
            title=note_title,
            content=content,
            frontmatter=_build_frontmatter(note_title, source_url, source_type),
            citations=citations,
            wiki_links=wiki_links,
            quality_score=quality_score,
            ai_action=ai_action,
            similarity_reasoning=similarity_reasoning,
        )
    except Exception as e:
        return NoteResult(
            title=title,
            content="",
            frontmatter=_build_frontmatter(title, source_url, source_type),
            error=str(e),
        )


async def generate_note(
    title: str,
    text: str,
    source_url: str,
    source_type: str,
    ai_settings: dict[str, object],
    existing_note_titles: list[str] | None = None,
) -> NoteResult:
    if existing_note_titles is None:
        existing_note_titles = []

    fallback_order = ai_settings.get("fallbackOrder", ["claude", "openai"])
    if not isinstance(fallback_order, list):
        fallback_order = ["claude", "openai"]

    for provider in fallback_order:
        if provider == "claude":
            api_key = _get_claude_key(ai_settings)
            if api_key:
                result = await _generate_with_claude(
                    title, text, source_url, source_type, api_key, existing_note_titles
                )
                if result.error is None:
                    return result
        elif provider == "openai":
            api_key = _get_openai_key(ai_settings)
            if api_key:
                result = await _generate_with_openai(
                    title, text, source_url, source_type, api_key, existing_note_titles
                )
                if result.error is None:
                    return result

    return NoteResult(
        title=title,
        content="",
        frontmatter=_build_frontmatter(title, source_url, source_type),
        error="Note generation unavailable. No AI providers are configured.",
    )
