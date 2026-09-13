"""CLI entry point: `synker-bridge pick-folder|login|logout|status|sync`.

Wiring only — the real logic lives in auth.py / folder_picker.py / sync.py /
token_store.py / api_client.py so each piece is independently testable
without a terminal, a display, or a live network. Command functions take an
explicit argparse.Namespace and return an exit code so tests can call them
directly instead of going through argv/sys.exit.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from synker_bridge import api_client, auth
from synker_bridge.config import BridgeConfig, load_config, save_config
from synker_bridge.folder_picker import (
    VaultValidationError,
    pick_folder_dialog,
    validate_vault_folder,
)
from synker_bridge.sync import SyncOutcome, SyncState, sync_all
from synker_bridge.token_store import (
    KeyringBackend,
    StoredSession,
    TokenStoreError,
    check_backend_available,
    clear_session,
    load_session,
    mask_token,
    save_session,
)


class NotAuthenticatedError(Exception):
    """Raised by _ensure_valid_session when no usable session exists."""


def _environment() -> str:
    return os.environ.get("SYNKER_ENV", "staging")


def _keyring_backend() -> KeyringBackend:
    import keyring

    return keyring


def _require_env(name: str) -> str | None:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        return None
    return value


def cmd_pick_folder(args: argparse.Namespace) -> int:
    chosen = args.path or pick_folder_dialog()
    if not chosen:
        print("No folder selected.", file=sys.stderr)
        return 1
    try:
        info = validate_vault_folder(chosen)
    except VaultValidationError as exc:
        print(f"Invalid folder: {exc}", file=sys.stderr)
        return 1
    print(str(info.path))
    if not info.has_obsidian:
        print(
            "Note: no .obsidian folder found here — this may not be an Obsidian vault.",
            file=sys.stderr,
        )
    save_config(BridgeConfig(vault_path=str(info.path), environment=_environment()))
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    environment = _environment()
    supabase_url = _require_env("SYNKER_SUPABASE_URL")
    anon_key = _require_env("SYNKER_SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        return 1

    password = args.password or getpass.getpass("Password: ")

    backend = _keyring_backend()
    try:
        check_backend_available(backend)
    except TokenStoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        session = asyncio.run(auth.login(supabase_url, anon_key, args.email, password))
    except auth.AuthError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    save_session(
        backend, environment, args.email,
        StoredSession(session.access_token, session.refresh_token, session.expires_at),
    )
    print(f"Logged in as {args.email} ({environment}). "
          f"Access token: {mask_token(session.access_token)}")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    environment = _environment()
    clear_session(_keyring_backend(), environment, args.email)
    print(f"Logged out {args.email} ({environment}).")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    environment = _environment()
    stored = load_session(_keyring_backend(), environment, args.email)
    if stored is None:
        print(f"Not logged in ({environment}).")
        return 1
    state = "expired" if stored.is_expired() else "valid"
    print(f"Logged in as {args.email} ({environment}). "
          f"Access token: {mask_token(stored.access_token)} [{state}]")
    return 0


async def _ensure_valid_session(
    backend: KeyringBackend, environment: str, email: str, supabase_url: str, anon_key: str
) -> StoredSession:
    stored = load_session(backend, environment, email)
    if stored is None:
        raise NotAuthenticatedError("no stored session")
    if not stored.is_expired():
        return stored
    try:
        refreshed = await auth.refresh(supabase_url, anon_key, stored.refresh_token)
    except auth.AuthError as exc:
        raise NotAuthenticatedError("refresh failed") from exc
    new_session = StoredSession(
        refreshed.access_token, refreshed.refresh_token, refreshed.expires_at
    )
    save_session(backend, environment, email, new_session)
    return new_session


async def _run_sync(
    email: str, environment: str, api_base: str, supabase_url: str, anon_key: str, vault_root: Path
) -> tuple[list[SyncOutcome], bool]:
    backend = _keyring_backend()
    session = await _ensure_valid_session(backend, environment, email, supabase_url, anon_key)

    state_path = vault_root / ".synker-sync-state.json"
    state = SyncState.load(state_path)

    pending = await api_client.fetch_pending(
        api_base, session.access_token, updated_since=state.last_synced
    )
    outcomes = sync_all(vault_root, pending, state)

    seen_timestamps = [f.last_modified for f in pending if f.last_modified]
    if seen_timestamps:
        state.last_synced = max(seen_timestamps)
    state.save(state_path)

    had_error = any(o.status == "error" for o in outcomes)
    for outcome in outcomes:
        try:
            await api_client.report_sync_result(api_base, session.access_token, outcome)
        except api_client.ApiError:
            had_error = True

    return outcomes, had_error


def cmd_sync(args: argparse.Namespace) -> int:
    environment = _environment()
    api_base = _require_env("SYNKER_API_BASE")
    if not api_base:
        return 1
    supabase_url = os.environ.get("SYNKER_SUPABASE_URL", "")
    anon_key = os.environ.get("SYNKER_SUPABASE_ANON_KEY", "")

    config = load_config()
    if config is None:
        print("No vault folder configured. Run `synker-bridge pick-folder` first.",
              file=sys.stderr)
        return 1

    try:
        outcomes, had_error = asyncio.run(
            _run_sync(args.email, environment, api_base, supabase_url, anon_key,
                      Path(config.vault_path))
        )
    except NotAuthenticatedError:
        print("Not authenticated. Run `synker-bridge login <email>` first.", file=sys.stderr)
        return 1
    except api_client.ApiError as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1

    written = sum(1 for o in outcomes if o.status == "written")
    conflicts = sum(1 for o in outcomes if o.status == "skipped_conflict")
    errors = sum(1 for o in outcomes if o.status == "error")
    print(f"Sync complete: {written} written, {conflicts} conflicts skipped, {errors} errors.")
    return 1 if had_error else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synker-bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    pick = sub.add_parser("pick-folder", help="Open a local folder picker and validate the choice")
    pick.add_argument("--path", default=None, help="Skip the dialog, validate this path directly")

    login_p = sub.add_parser("login", help="Log in with your Synker (Supabase) account")
    login_p.add_argument("email")
    login_p.add_argument(
        "--password", default=None, help="Skip the interactive prompt (testing only)"
    )

    logout_p = sub.add_parser("logout", help="Remove the stored session for an account")
    logout_p.add_argument("email")

    status_p = sub.add_parser("status", help="Show whether an account has a stored session")
    status_p.add_argument("email")

    sync_p = sub.add_parser("sync", help="Pull pending notes and write them into the vault")
    sync_p.add_argument("email")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "pick-folder": cmd_pick_folder,
        "login": cmd_login,
        "logout": cmd_logout,
        "status": cmd_status,
        "sync": cmd_sync,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
