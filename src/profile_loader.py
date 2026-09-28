"""
profile_loader.py
=================
Loads the candidate profile from the profile/ folder.

This module concatenates the Markdown files that describe the candidate into
a single string, ready to be injected into a prompt for the local LLM.
"""

from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profile"

DEFAULT_FILES = [
    "01_profile.md"
]


def load_profile(files=None) -> str:
    """Load and concatenate profile files into a single string.

    Args:
        files: Optional list of filenames (relative to PROFILE_DIR) to load.
            If None or empty, DEFAULT_FILES is used.

    Returns:
        A single string containing all requested profile files, each prefixed
        with a "### <filename>" heading and separated by blank lines.
        Files that do not exist are skipped with a warning printed to stdout.
    """
    files = files or DEFAULT_FILES
    parts = []
    for name in files:
        path = PROFILE_DIR / name
        if not path.exists():
            print(f"[WARN] file not found: {path}")
            continue
        parts.append(f"### {name}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)