# src/profile_loader.py
"""
profile_loader.py
=================
Load the candidate profile from the profile directory.

This module concatenates the Markdown files that describe the candidate into
a single string, ready to be injected into a prompt for the local LLM.
"""

from pathlib import Path

def load_profile(profile_dir: Path, files=None) -> str:
    """Load and concatenate profile files into a single string.

    Args:
        profile_dir: The path to the specific profile directory (e.g., profiles/irene).
        files: Optional list of filenames to load. If None, uses default files.

    Returns:
        A single string containing all requested profile files.
    """
    DEFAULT_FILES = [
        "01_profile.md",
    ]

    files = files or DEFAULT_FILES
    parts = []
    
    for name in files:
        path = profile_dir / name
        if not path.exists():
            print(f"[WARN] file not found: {path}")
            continue
        parts.append(f"### {name}\n\n{path.read_text(encoding='utf-8')}")
        
    return "\n\n".join(parts)