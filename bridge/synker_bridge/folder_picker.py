"""Local vault folder selection and validation.

This REPLACES backend/app/api/routes/settings_route.py's old
_open_directory_dialog — that endpoint ran tkinter on the Railway container,
which has no display and can never show a dialog to the user. This module
runs the same tkinter dialog logic here instead, on the user's own machine,
where a display actually exists.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class VaultValidationError(Exception):
    """Raised when a chosen folder cannot be used as a vault root."""


@dataclass(frozen=True)
class VaultFolderInfo:
    path: Path
    has_obsidian: bool


def validate_vault_folder(path_str: str) -> VaultFolderInfo:
    """Verify the folder exists, is a directory, and is readable/writable.
    Detects an .obsidian subdirectory when present. Raises
    VaultValidationError with a clear message on any failed check."""
    if not path_str or not path_str.strip():
        raise VaultValidationError("No folder path given.")

    path = Path(path_str).expanduser().resolve()

    if not path.exists():
        raise VaultValidationError(f"Folder does not exist: {path}")
    if not path.is_dir():
        raise VaultValidationError(f"Not a folder: {path}")
    if not os.access(path, os.R_OK | os.W_OK):
        raise VaultValidationError(f"Folder is not readable/writable: {path}")

    return VaultFolderInfo(path=path, has_obsidian=(path / ".obsidian").is_dir())


def pick_folder_dialog() -> str:
    """Open a native OS folder picker. Returns "" if the user cancels or no
    display is available (e.g. running the bridge headless/over SSH)."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        path = filedialog.askdirectory(title="Select Obsidian Vault Folder")
        root.destroy()
        return path or ""
    except Exception:
        return ""
