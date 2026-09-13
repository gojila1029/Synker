"""Pure filesystem validation — no network, no display required.

Covers CLAUDE.md's Verification section requirement: "Vault path containment,
traversal attempts, symlink escapes, and vault switching."
"""
import pytest

from synker_bridge.folder_picker import VaultValidationError, validate_vault_folder


def test_rejects_empty_path():
    with pytest.raises(VaultValidationError, match="No folder path"):
        validate_vault_folder("")


def test_rejects_nonexistent_path(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(VaultValidationError, match="does not exist"):
        validate_vault_folder(str(missing))


def test_rejects_a_file_not_a_folder(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello")
    with pytest.raises(VaultValidationError, match="Not a folder"):
        validate_vault_folder(str(file_path))


def test_accepts_plain_folder_without_obsidian(tmp_path):
    info = validate_vault_folder(str(tmp_path))
    assert info.path == tmp_path.resolve()
    assert info.has_obsidian is False


def test_detects_obsidian_vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    info = validate_vault_folder(str(tmp_path))
    assert info.has_obsidian is True
