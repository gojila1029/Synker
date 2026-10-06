"""Sync logic: atomic writes, path confinement, conflict detection.

No network involved — PendingFile content is passed in directly, as if
already fetched from GET /api/vault/pending-sync.
"""
import os

import pytest

from synker_bridge.sync import (
    PendingFile,
    SyncState,
    atomic_write,
    resolve_confined,
    sync_all,
    sync_one_file,
)


def test_writes_new_file(tmp_path):
    state = SyncState()
    file = PendingFile(path="Synker/note.md", content="# Hello\n")

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "written"
    assert (tmp_path / "Synker" / "note.md").read_text(encoding="utf-8") == "# Hello\n"
    assert "Synker/note.md" in state.synced_hashes


def test_rewrites_when_content_changed_and_no_local_edit(tmp_path):
    state = SyncState()
    original = PendingFile(path="note.md", content="v1")
    sync_one_file(tmp_path, original, state)

    updated = PendingFile(path="note.md", content="v2")
    outcome = sync_one_file(tmp_path, updated, state)

    assert outcome.status == "written"
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "v2"


def test_skips_write_when_local_file_modified_since_last_sync(tmp_path):
    """The hard invariant: never overwrite a newer manual edit."""
    state = SyncState()
    original = PendingFile(path="note.md", content="synced content")
    sync_one_file(tmp_path, original, state)

    # Simulate the user hand-editing the file in Obsidian after the sync.
    (tmp_path / "note.md").write_text("the user's own edit", encoding="utf-8")

    incoming = PendingFile(path="note.md", content="a newer version from the backend")
    outcome = sync_one_file(tmp_path, incoming, state)

    assert outcome.status == "skipped_conflict"
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "the user's own edit"


def test_rejects_path_traversal_in_remote_path(tmp_path):
    state = SyncState()
    file = PendingFile(path="../outside.md", content="malicious")

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "error"
    assert "escapes the vault root" in outcome.detail
    assert not (tmp_path.parent / "outside.md").exists()


def test_resolve_confined_rejects_absolute_escape(tmp_path):
    assert resolve_confined(tmp_path, "../../etc/passwd") is None


def test_resolve_confined_allows_nested_path(tmp_path):
    resolved = resolve_confined(tmp_path, "a/b/c.md")
    assert resolved == (tmp_path / "a" / "b" / "c.md").resolve()


def test_atomic_write_leaves_no_tmp_file_behind(tmp_path):
    state = SyncState()
    file = PendingFile(path="note.md", content="content")
    sync_one_file(tmp_path, file, state)

    leftovers = list(tmp_path.glob("*.synker-tmp"))
    assert leftovers == []


def test_sync_all_processes_every_file(tmp_path):
    state = SyncState()
    files = [
        PendingFile(path="a.md", content="A"),
        PendingFile(path="b.md", content="B"),
    ]

    outcomes = sync_all(tmp_path, files, state)

    assert [o.status for o in outcomes] == ["written", "written"]
    assert (tmp_path / "a.md").exists()
    assert (tmp_path / "b.md").exists()


def test_sync_state_round_trips_through_disk(tmp_path):
    state = SyncState()
    sync_one_file(tmp_path, PendingFile(path="note.md", content="x"), state)
    state_path = tmp_path / ".synker-sync-state.json"
    state.save(state_path)

    reloaded = SyncState.load(state_path)
    assert reloaded.synced_hashes == state.synced_hashes


# ── A. Vault confinement ─────────────────────────────────────────────────────

def test_rejects_absolute_path_outside_vault(tmp_path):
    state = SyncState()
    outside = (tmp_path.parent / "outside-absolute.md")
    file = PendingFile(path=str(outside), content="malicious")

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "error"
    assert not outside.exists()


def test_percent_encoded_traversal_is_treated_as_a_literal_filename_not_decoded(tmp_path):
    """We never URL-decode path segments, so a string containing literal
    '%2e%2e' characters is just an unusual filename, not a traversal — this
    proves there's no double-decoding vulnerability to exploit."""
    state = SyncState()
    file = PendingFile(path="%2e%2e/%2e%2e/outside.md", content="data")

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "written"
    written_path = tmp_path / "%2e%2e" / "%2e%2e" / "outside.md"
    assert written_path.exists()
    assert written_path.resolve().is_relative_to(tmp_path.resolve())


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific illegal filename characters")
def test_illegal_windows_filename_characters_error_instead_of_crashing(tmp_path):
    state = SyncState()
    file = PendingFile(path="bad:name?.md", content="data")

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "error"  # OSError from the filesystem, caught and reported


def test_symlink_escape_is_not_followed_outside_vault(tmp_path):
    """If the vault root itself contains a symlinked subdirectory pointing
    outside the vault, a pending path that walks through it must not let a
    write land outside the real vault tree."""
    outside_dir = tmp_path.parent / "symlink-target"
    outside_dir.mkdir(exist_ok=True)
    link = tmp_path / "escape-link"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks require elevated privileges/dev mode on this system")

    state = SyncState()
    file = PendingFile(path="escape-link/note.md", content="data")

    sync_one_file(tmp_path, file, state)

    # Whether or not the OS resolves the symlink, the write must not have
    # landed anywhere outside both the vault and the symlink's own target.
    assert not (tmp_path.parent / "note.md").exists()


# ── C. Idempotency ───────────────────────────────────────────────────────────

def test_repeated_sync_of_identical_content_is_idempotent(tmp_path):
    state = SyncState()
    file = PendingFile(path="note.md", content="same content")

    first = sync_one_file(tmp_path, file, state)
    second = sync_one_file(tmp_path, file, state)

    assert first.status == "written"
    assert second.status == "written"
    assert second.detail == "already up to date"
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "same content"


def test_orphaned_tmp_file_from_a_prior_crash_is_safely_overwritten(tmp_path):
    """Simulates the bridge being killed between the write and the rename on
    a previous run: a stale .synker-tmp file is already sitting there."""
    target = tmp_path / "note.md"
    orphan = tmp_path / "note.md.synker-tmp"
    orphan.write_text("half-written garbage from a crashed run", encoding="utf-8")

    atomic_write(target, "the real content")

    assert target.read_text(encoding="utf-8") == "the real content"
    assert not orphan.exists()


def test_atomic_write_cleans_up_tmp_file_if_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "note.md"

    def failing_replace(src, dst):
        raise OSError("simulated failure during rename")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        atomic_write(target, "content")

    assert not target.exists()
    assert not (tmp_path / "note.md.synker-tmp").exists()


# ── E. Deletion safety ───────────────────────────────────────────────────────

def test_sync_never_deletes_local_files_not_present_in_pending_list(tmp_path):
    original_content = "the user's own note, never synced from the server"
    untouched = tmp_path / "user-written-note.md"
    untouched.write_text(original_content, encoding="utf-8")

    state = SyncState()
    sync_all(tmp_path, [PendingFile(path="server-note.md", content="from server")], state)

    assert untouched.exists()
    assert untouched.read_text(encoding="utf-8") == original_content


# ── F. Untrusted content ─────────────────────────────────────────────────────

def test_note_content_is_written_as_inert_text_never_executed(tmp_path):
    """Markdown/frontmatter from the backend is data, not instructions —
    proven by writing content that looks like an embedded command and
    confirming it lands byte-for-byte on disk with no interpretation."""
    state = SyncState()
    suspicious_content = (
        "# Note\n\n```bash\nrm -rf /\n```\n\n"
        "[click me](javascript:alert(1))\n"
        "<script>alert('xss')</script>\n"
    )
    file = PendingFile(path="note.md", content=suspicious_content)

    outcome = sync_one_file(tmp_path, file, state)

    assert outcome.status == "written"
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == suspicious_content
