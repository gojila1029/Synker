"""Token storage: tested against an injected in-memory fake, never the real
OS keyring (no live keychain in CI/this environment)."""
import pytest

from synker_bridge.token_store import (
    StoredSession,
    TokenStoreError,
    check_backend_available,
    clear_session,
    load_session,
    mask_token,
    save_session,
)


class _FakeKeyring:
    """In-memory stand-in satisfying the KeyringBackend protocol."""

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service_name, username):
        return self._store.get((service_name, username))

    def set_password(self, service_name, username, password):
        self._store[(service_name, username)] = password

    def delete_password(self, service_name, username):
        self._store.pop((service_name, username), None)


class _BrokenKeyring:
    def get_password(self, service_name, username):
        raise RuntimeError("no secret service running")

    def set_password(self, service_name, username, password):
        raise RuntimeError("no secret service running")

    def delete_password(self, service_name, username):
        raise RuntimeError("no secret service running")


def test_save_and_load_round_trip():
    backend = _FakeKeyring()
    session = StoredSession(access_token="at", refresh_token="rt", expires_at=123.0)

    save_session(backend, "staging", "user@example.com", session)
    loaded = load_session(backend, "staging", "user@example.com")

    assert loaded == session


def test_load_returns_none_when_absent():
    backend = _FakeKeyring()
    assert load_session(backend, "staging", "nobody@example.com") is None


def test_staging_and_production_are_isolated():
    backend = _FakeKeyring()
    save_session(backend, "staging", "user@example.com",
                 StoredSession(access_token="staging-at", refresh_token="staging-rt"))
    save_session(backend, "production", "user@example.com",
                 StoredSession(access_token="prod-at", refresh_token="prod-rt"))

    assert load_session(backend, "staging", "user@example.com").access_token == "staging-at"
    assert load_session(backend, "production", "user@example.com").access_token == "prod-at"


def test_clear_session_removes_entry():
    backend = _FakeKeyring()
    save_session(backend, "staging", "user@example.com",
                 StoredSession(access_token="at", refresh_token="rt"))

    clear_session(backend, "staging", "user@example.com")

    assert load_session(backend, "staging", "user@example.com") is None


def test_clear_session_is_idempotent_when_nothing_stored():
    backend = _FakeKeyring()
    clear_session(backend, "staging", "user@example.com")  # must not raise


def test_check_backend_available_passes_for_working_backend():
    check_backend_available(_FakeKeyring())  # must not raise


def test_check_backend_available_raises_actionable_error_when_broken():
    with pytest.raises(TokenStoreError, match="unavailable"):
        check_backend_available(_BrokenKeyring())


def test_save_session_raises_token_store_error_on_backend_failure():
    with pytest.raises(TokenStoreError):
        save_session(_BrokenKeyring(), "staging", "user@example.com",
                     StoredSession(access_token="at", refresh_token="rt"))


def test_is_expired_true_when_past():
    session = StoredSession(access_token="at", refresh_token="rt", expires_at=100.0)
    assert session.is_expired(now=200.0) is True


def test_is_expired_false_when_future():
    session = StoredSession(access_token="at", refresh_token="rt", expires_at=200.0)
    assert session.is_expired(now=100.0) is False


def test_is_expired_false_when_unknown():
    session = StoredSession(access_token="at", refresh_token="rt", expires_at=None)
    assert session.is_expired(now=999999.0) is False


def test_mask_token_never_reveals_full_value():
    masked = mask_token("sb-access-token-abcdefghijklmnop")
    assert "abcdefghijklmnop" not in masked
    assert masked.startswith("sb-acc")
    assert masked.endswith("mnop")


def test_mask_token_handles_short_values():
    assert mask_token("short") == "*****"
