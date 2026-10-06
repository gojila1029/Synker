"""CLI wiring: each command function is called directly (not via subprocess)
with its dependencies monkeypatched, so these run without a display, a
keyring daemon, or network access. A real subprocess invocation of --help
(this package's actual installed entry point) is verified separately, not
in this file, per Stage 6 item 7 ("execute the CLI from the same environment
a real user would run it")."""
import argparse

import pytest

from synker_bridge import api_client, auth, cli
from synker_bridge.config import BridgeConfig
from synker_bridge.sync import SyncOutcome


class _FakeKeyring:
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service_name, username):
        return self._store.get((service_name, username))

    def set_password(self, service_name, username, password):
        self._store[(service_name, username)] = password

    def delete_password(self, service_name, username):
        self._store.pop((service_name, username), None)


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def test_help_lists_implemented_commands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    output = capsys.readouterr().out
    for command in ("pick-folder", "login", "logout", "status", "sync"):
        assert command in output


def test_pick_folder_rejects_invalid_path(capsys):
    args = _ns(path="/definitely/does/not/exist")
    exit_code = cli.cmd_pick_folder(args)
    assert exit_code == 1
    assert "Invalid folder" in capsys.readouterr().err


def test_pick_folder_accepts_valid_path_and_saves_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "save_config", lambda cfg: setattr(cli, "_saved_cfg", cfg))
    args = _ns(path=str(tmp_path))
    exit_code = cli.cmd_pick_folder(args)
    assert exit_code == 0
    assert str(tmp_path.resolve()) in capsys.readouterr().out
    assert cli._saved_cfg.vault_path == str(tmp_path.resolve())


def test_login_success_stores_session(monkeypatch, capsys):
    fake_keyring = _FakeKeyring()
    monkeypatch.setenv("SYNKER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SYNKER_SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    async def fake_login(supabase_url, anon_key, email, password):
        return auth.Session(access_token="at-secret-value", refresh_token="rt-secret-value")

    monkeypatch.setattr(cli.auth, "login", fake_login)

    args = _ns(email="user@example.com", password="hunter2")
    exit_code = cli.cmd_login(args)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "hunter2" not in output
    assert "at-secret-value" not in output  # full token never printed
    stored = fake_keyring.get_password("synker-bridge:staging", "user@example.com")
    assert stored is not None
    assert "at-secret-value" in stored  # the *store* holds it; only display is masked


def test_login_failure_returns_nonzero_and_does_not_leak_password(monkeypatch, capsys):
    monkeypatch.setenv("SYNKER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SYNKER_SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(cli, "_keyring_backend", lambda: _FakeKeyring())

    async def failing_login(*a, **kw):
        raise auth.AuthError("Request failed (400): invalid credentials")

    monkeypatch.setattr(cli.auth, "login", failing_login)

    args = _ns(email="user@example.com", password="hunter2")
    exit_code = cli.cmd_login(args)

    assert exit_code == 1
    assert "hunter2" not in capsys.readouterr().err


def test_login_requires_env_config(monkeypatch, capsys):
    monkeypatch.delenv("SYNKER_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SYNKER_SUPABASE_ANON_KEY", raising=False)
    args = _ns(email="user@example.com", password="x")
    assert cli.cmd_login(args) == 1


def test_sync_refuses_when_not_authenticated(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: BridgeConfig(str(tmp_path), "staging"))
    monkeypatch.setattr(cli, "_keyring_backend", lambda: _FakeKeyring())  # empty — no session

    args = _ns(email="user@example.com")
    exit_code = cli.cmd_sync(args)

    assert exit_code == 1
    assert "Not authenticated" in capsys.readouterr().err


def test_sync_refuses_when_no_vault_configured(monkeypatch, capsys):
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: None)

    args = _ns(email="user@example.com")
    exit_code = cli.cmd_sync(args)

    assert exit_code == 1
    assert "pick-folder" in capsys.readouterr().err


def test_sync_returns_nonzero_on_api_failure(monkeypatch, tmp_path, capsys):
    fake_keyring = _FakeKeyring()
    fake_keyring.set_password(
        "synker-bridge:staging", "user@example.com",
        '{"access_token": "at", "refresh_token": "rt", "expires_at": null}',
    )
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: BridgeConfig(str(tmp_path), "staging"))
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    async def failing_fetch(*a, **kw):
        raise api_client.ApiError("pending-sync failed (500): boom")

    monkeypatch.setattr(cli.api_client, "fetch_pending", failing_fetch)

    args = _ns(email="user@example.com")
    exit_code = cli.cmd_sync(args)

    assert exit_code == 1
    assert "Sync failed" in capsys.readouterr().err


def test_sync_writes_files_and_reports_success(monkeypatch, tmp_path, capsys):
    fake_keyring = _FakeKeyring()
    fake_keyring.set_password(
        "synker-bridge:staging", "user@example.com",
        '{"access_token": "at", "refresh_token": "rt", "expires_at": null}',
    )
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: BridgeConfig(str(tmp_path), "staging"))
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    async def fake_fetch(api_base, access_token, updated_since=None, http_client=None):
        from synker_bridge.sync import PendingFile
        return [PendingFile(path="note.md", content="# Hello")]

    reported: list[SyncOutcome] = []

    async def fake_report(api_base, access_token, outcome, http_client=None):
        reported.append(outcome)

    monkeypatch.setattr(cli.api_client, "fetch_pending", fake_fetch)
    monkeypatch.setattr(cli.api_client, "report_sync_result", fake_report)

    args = _ns(email="user@example.com")
    exit_code = cli.cmd_sync(args)

    assert exit_code == 0
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "# Hello"
    assert len(reported) == 1
    assert reported[0].status == "written"
    assert "1 written" in capsys.readouterr().out


def test_sync_persists_local_write_even_when_acknowledgement_fails(monkeypatch, tmp_path, capsys):
    """Offline scenario D: the backend is unreachable when we try to report
    the outcome, but the local write + state already happened and must not
    be lost — a later `sync` retry will just re-report the already-written
    file (idempotent), not lose or duplicate it."""
    fake_keyring = _FakeKeyring()
    fake_keyring.set_password(
        "synker-bridge:staging", "user@example.com",
        '{"access_token": "at", "refresh_token": "rt", "expires_at": null}',
    )
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: BridgeConfig(str(tmp_path), "staging"))
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    async def fake_fetch(api_base, access_token, updated_since=None, http_client=None):
        from synker_bridge.sync import PendingFile
        return [PendingFile(path="note.md", content="content")]

    async def failing_report(*a, **kw):
        raise api_client.ApiError("Could not reach the backend: connection refused")

    monkeypatch.setattr(cli.api_client, "fetch_pending", fake_fetch)
    monkeypatch.setattr(cli.api_client, "report_sync_result", failing_report)

    exit_code = cli.cmd_sync(_ns(email="user@example.com"))

    assert exit_code == 1  # signals "retry later", per spec item 5
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "content"
    assert (tmp_path / ".synker-sync-state.json").exists()


def test_sync_refuses_when_token_expired_and_refresh_fails(monkeypatch, tmp_path, capsys):
    import time
    fake_keyring = _FakeKeyring()
    fake_keyring.set_password(
        "synker-bridge:staging", "user@example.com",
        f'{{"access_token": "at", "refresh_token": "rt", "expires_at": {time.time() - 60}}}',
    )
    monkeypatch.setenv("SYNKER_API_BASE", "https://api.example.com")
    monkeypatch.setattr(cli, "load_config", lambda: BridgeConfig(str(tmp_path), "staging"))
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    async def failing_refresh(*a, **kw):
        raise auth.AuthError("refresh token revoked")

    monkeypatch.setattr(cli.auth, "refresh", failing_refresh)

    exit_code = cli.cmd_sync(_ns(email="user@example.com"))

    assert exit_code == 1
    assert "Not authenticated" in capsys.readouterr().err


def test_status_reports_not_logged_in(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_keyring_backend", lambda: _FakeKeyring())
    args = _ns(email="user@example.com")
    assert cli.cmd_status(args) == 1
    assert "Not logged in" in capsys.readouterr().out


def test_logout_clears_session(monkeypatch, capsys):
    fake_keyring = _FakeKeyring()
    fake_keyring.set_password(
        "synker-bridge:staging", "user@example.com",
        '{"access_token": "at", "refresh_token": "rt", "expires_at": null}',
    )
    monkeypatch.setattr(cli, "_keyring_backend", lambda: fake_keyring)

    exit_code = cli.cmd_logout(_ns(email="user@example.com"))

    assert exit_code == 0
    assert fake_keyring.get_password("synker-bridge:staging", "user@example.com") is None
