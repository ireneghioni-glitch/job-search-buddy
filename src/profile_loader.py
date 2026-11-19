# src/profile_loader.py
"""Load the candidate profile by concatenating the Markdown documents
stored in the profile subfolder, plus any extra files requested."""

from pathlib import Path

PROFILE_DOCS_DIR = "profile"


def load_profile(profile_dir: Path, extra_files=None) -> str:
    """Load and concatenate the profile Markdown files into one string.

    By default, loads every ``*.md`` file in ``<profile_dir>/profile/``,
    sorted by filename and skipping ``*.example.md`` templates. Extra files
    are appended afterwards.

    Args:
        profile_dir: Path to the profile folder (e.g. profiles/irene).
        extra_files: Optional list of extra filenames to append. Relative
            names are resolved inside the docs subfolder; absolute paths
            are used as-is.

    Returns:
        A single string with all documents, separated by blank lines.
    """
    docs_dir = profile_dir / PROFILE_DOCS_DIR
    parts = []

    # 1) Default documents: discover them instead of hardcoding a list.
    if docs_dir.is_dir():
        for path in sorted(docs_dir.glob("*.md")):
            if path.name.endswith(".example.md"):
                continue
            parts.append(f"### {path.name}\n\n{path.read_text(encoding='utf-8')}")

    # 2) Extra files (e.g. from --extra-files).
    for name in extra_files or []:
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = docs_dir / candidate
        if candidate.is_file():
            parts.append(f"### {name}\n\n{candidate.read_text(encoding='utf-8')}")
        else:
            print(f"[WARN] file not found: {candidate}")

    return "\n\n".join(parts)
