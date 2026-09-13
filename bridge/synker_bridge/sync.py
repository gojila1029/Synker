"""Pull-based sync: fetch pending vault files from the backend and write them
into the local vault folder without ever overwriting a newer manual edit.

Mirrors the path-confinement pattern already proven in
backend/app/worker/handlers.py's _graphify_sync_handler, and adds the two
things that handler can't do from inside a Railway container: an atomic
write, and conflict detection against a file the user edited by hand.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_confined(vault_root: Path, relative_path: str) -> Path | None:
    """Resolve relative_path against vault_root and verify the result is
    actually inside vault_root. Returns None on path traversal / escape."""
    candidate = (vault_root / relative_path).resolve()
    root = vault_root.resolve()
    if candidate != root and not str(candidate).startswith(str(root) + os.sep):
        return None
    return candidate


def atomic_write(path: Path, content: str) -> None:
    """Write via a temp file + os.replace so a crash mid-write never leaves a
    half-written file at the real path. A fixed tmp filename means a leftover
    orphan from a previous crash (e.g. the bridge process was killed between
    the write and the replace) is simply reused and overwritten on the next
    attempt, rather than accumulating stale .synker-tmp files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".synker-tmp")
    tmp_path.write_text(content, encoding="utf-8")
    try:
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class PendingFile:
    path: str
    content: str
    last_modified: str | None = None


@dataclass(frozen=True)
class SyncOutcome:
    path: str
    status: Literal["written", "skipped_conflict", "error"]
    detail: str = ""


@dataclass
class SyncState:
    """Local manifest of what the bridge last wrote, keyed by vault-relative
    path. synced_hashes tells "the user edited this file" apart from "we
    wrote this file last time and nothing has touched it since". last_synced
    is the updatedSince cursor for GET /api/vault/pending-sync, so a vault
    with more rows than the backend's per-response cap is still fully
    reachable across repeated syncs instead of only ever seeing the same
    oldest page."""

    synced_hashes: dict[str, str] = field(default_factory=dict)
    last_synced: str | None = None

    @classmethod
    def load(cls, state_path: Path) -> SyncState:
        if not state_path.exists():
            return cls()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls(
                synced_hashes=data.get("syncedHashes", {}),
                last_synced=data.get("lastSynced"),
            )
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"syncedHashes": self.synced_hashes, "lastSynced": self.last_synced}
        atomic_write(state_path, json.dumps(payload, indent=2))


def sync_one_file(vault_root: Path, file: PendingFile, state: SyncState) -> SyncOutcome:
    """Write one file if it's safe to do so. Never overwrites a local file
    whose content has diverged from what the bridge itself last wrote."""
    target = resolve_confined(vault_root, file.path)
    if target is None:
        return SyncOutcome(file.path, "error", "path escapes the vault root")

    incoming_hash = content_hash(file.content)
    last_synced_hash = state.synced_hashes.get(file.path)

    if target.exists():
        local_hash = content_hash(target.read_text(encoding="utf-8"))
        if local_hash == incoming_hash:
            return SyncOutcome(file.path, "written", "already up to date")
        if last_synced_hash is not None and local_hash != last_synced_hash:
            return SyncOutcome(
                file.path, "skipped_conflict",
                "local file was modified since the last sync — not overwritten",
            )

    try:
        atomic_write(target, file.content)
    except OSError as exc:
        return SyncOutcome(file.path, "error", str(exc))

    state.synced_hashes[file.path] = incoming_hash
    return SyncOutcome(file.path, "written", "")


def sync_all(
    vault_root: Path, files: list[PendingFile], state: SyncState
) -> list[SyncOutcome]:
    return [sync_one_file(vault_root, f, state) for f in files]
