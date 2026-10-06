"""Persistent session storage using the OS's secure credential store.

Never falls back to a plaintext file. If the keyring backend can't actually
be used (no OS keychain daemon, headless Linux with no secret service, etc.)
this fails loudly with an actionable message instead of silently writing
tokens to disk — per CLAUDE.md's "Keep credentials... secure" invariant.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Protocol


class TokenStoreError(Exception):
    """Raised when the secure credential store is unavailable or fails."""


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...
    def set_password(self, service_name: str, username: str, password: str) -> None: ...
    def delete_password(self, service_name: str, username: str) -> None: ...


@dataclass(frozen=True)
class StoredSession:
    access_token: str
    refresh_token: str
    expires_at: float | None = None  # unix timestamp; None if unknown

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at


def mask_token(token: str) -> str:
    """Never display a complete token."""
    if len(token) <= 10:
        return "*" * len(token)
    return f"{token[:6]}…{token[-4:]}"


def _service_name(environment: str) -> str:
    return f"synker-bridge:{environment}"


def check_backend_available(backend: KeyringBackend) -> None:
    """Round-trip a throwaway value to confirm the backend actually works —
    a successful `import keyring` does not mean a usable backend is
    configured (e.g. Linux with no Secret Service / no keyring daemon)."""
    probe_service = "synker-bridge:_probe"
    try:
        backend.set_password(probe_service, "_probe", "_probe")
        ok = backend.get_password(probe_service, "_probe") == "_probe"
        backend.delete_password(probe_service, "_probe")
    except Exception as exc:
        raise TokenStoreError(
            f"Secure credential store is unavailable ({exc}). Synker Bridge will "
            "not store tokens in plaintext. Install/configure an OS keyring "
            "backend (see the `keyring` package's supported backends) and retry."
        ) from exc
    if not ok:
        raise TokenStoreError("Secure credential store did not return the expected value.")


def save_session(
    backend: KeyringBackend, environment: str, email: str, session: StoredSession
) -> None:
    try:
        backend.set_password(_service_name(environment), email, json.dumps(asdict(session)))
    except Exception as exc:
        raise TokenStoreError(f"Could not save session: {exc}") from exc


def load_session(backend: KeyringBackend, environment: str, email: str) -> StoredSession | None:
    try:
        raw = backend.get_password(_service_name(environment), email)
    except Exception as exc:
        raise TokenStoreError(f"Could not read session: {exc}") from exc
    if not raw:
        return None
    try:
        return StoredSession(**json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return None


def clear_session(backend: KeyringBackend, environment: str, email: str) -> None:
    try:
        backend.delete_password(_service_name(environment), email)
    except Exception:
        pass  # logout is idempotent — already-absent is not an error
