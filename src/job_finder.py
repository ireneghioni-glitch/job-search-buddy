# src/job_finder.py
"""
job_finder.py
=============
Job finder module using JobSpy.

Reads search queries from searches.txt, scrapes LinkedIn and Indeed,
and saves each job posting as a separate .txt file in jobs/.
"""

import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
from jobspy import scrape_jobs
import re

ROOT_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT_DIR / "jobs"
SEARCHES_FILE = ROOT_DIR / "searches.txt"
NOISE_TITLE_KEYWORDS = [
    "forklift", "driver", "die cutter", "stitcher", "shipping",
    "receiving", "press operator", "apprentice", "warehouse",
    "clinical account", "faculty", "professor", "postdoc",
]
# Acceptable location markers — a job must contain at least one of these
# to be saved. Case-insensitive substring match.
ACCEPTED_LOCATIONS = [
    "belgium", "belgië", "belgique", "belgien",
    "brussels", "bruxelles", "brussel",
    "antwerp", "antwerpen", "anvers",
    "ghent", "gent", "gand",
    "leuven", "louvain",
    "liège", "liege", "luik",
    "namur", "namen",
    "charleroi", "mons", "bergen",
    "wallonia", "wallonie", "flanders", "vlaanderen",
    "remote",
]

# Reject if any of these appear in the location — these are clearly not Belgium
REJECTED_LOCATIONS = [
    "united states", "usa", "u.s.", " wisconsin", " wisconsin,",
    " milwaukee", " chicago", " california", " new york", " texas",
    " florida", " boston", " seattle", " austin", " denver",
    ", ca", ", ny", ", tx", ", wa", ", il", ", ma", ", fl",
]

# Non-EU markers specifically for remote jobs
NON_EU_REMOTE_MARKERS = [
    "united states", "usa", "u.s.", " us,", ", us", "us -", "- us",
    "canada", "mexico", "brazil", "argentina", "chile", "colombia",
    "india", "pakistan", "bangladesh", "philippines", "indonesia",
    "singapore", "malaysia", "vietnam", "thailand", "china",
    "japan", "korea", "taiwan", "hong kong",
    "australia", "new zealand",
    "south africa", "nigeria", "kenya", "egypt", "morocco",
    "israel", "turkey", "uae", "saudi arabia", "qatar",
]

def is_obvious_noise(title: str) -> bool:
    """True if the title clearly doesn't match the candidate's target roles."""
    t = title.lower()
    return any(kw in t for kw in NOISE_TITLE_KEYWORDS)

def is_wrong_location(location: str) -> bool:
    """True if the job location is clearly outside the target geography."""
    if not location:
        return False  # don't filter if location is missing
    loc = location.lower()
    # Hard reject: matches a known non-Belgian location
    if any(r in loc for r in REJECTED_LOCATIONS):
        return True
    # Soft accept: must contain an accepted marker, otherwise reject
    if not any(a in loc for a in ACCEPTED_LOCATIONS):
        return True
    return False

def is_wrong_remote(location: str) -> bool:
    """
    For remote jobs, check if they specify a non-EU region.
    
    - 'Remote' alone: keep (LLM will evaluate)
    - 'Remote, Europe' / 'Remote, EU' / 'Remote, EMEA': keep
    - 'Remote, United States' / 'Remote - India': reject
    """
    if not location:
        return False
    loc = location.lower()
    if "remote" not in loc:
        return False  # not a remote job, other filters handle it
    
    # If it mentions any EU-ish marker, keep
    eu_markers = ["europe", " eu", "eu,", "eu ", "emea", "anywhere in europe"]
    if any(m in loc for m in eu_markers):
        return False
    
    # If it mentions a specific non-EU country, reject
    if any(m in loc for m in NON_EU_REMOTE_MARKERS):
        return True
    
    # Just "Remote" with no other info: keep
    return False

def sanitize_filename(name: str, max_length: int = 80) -> str:
    """
    Convert an arbitrary string into a safe Windows filename.

    Removes/replaces characters forbidden by Windows (< > : " / \\ | ? *),
    collapses whitespace, trims trailing dots/spaces, and truncates the
    result to a reasonable length.
    """
    # Replace forbidden characters with a dash
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    # Collapse any run of whitespace into a single space
    name = re.sub(r"\s+", " ", name).strip()
    # Replace spaces with underscores for readability in filenames
    name = name.replace(" ", "_")
    # Remove trailing dots and spaces (Windows forbids them)
    name = name.rstrip(". ")
    # Truncate to avoid MAX_PATH issues on long paths
    if len(name) > max_length:
        name = name[:max_length].rstrip("._- ")
    # Fallback if everything was stripped
    return name or "unknown"

def parse_searches_file(path: Path) -> list:
    """
    Parse a searches.txt file.

    Each non-comment, non-empty line must have the format:
        query | location | hours_old

    Returns:
        List of dicts with keys 'query', 'location', 'hours_old'.
    """
    entries = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            print(f"[WARN] skipping malformed line: {raw_line}")
            continue
        query, location, hours = parts
        try:
            hours_old = int(hours)
        except ValueError:
            print(f"[WARN] invalid hours_old in: {raw_line}")
            continue
        entries.append({"query": query, "location": location, "hours_old": hours_old})
    return entries


def search_and_save(query: str, location: str, hours_old: int,
                    site_names: list, results_wanted: int = 15):
    """
    Scrape jobs for a single query and save each as a .txt file.

    Args:
        query: Job title or keywords.
        location: Geographic location.
        hours_old: Only include jobs posted within this many hours.
        site_names: List of sites to scrape (e.g. ['linkedin', 'indeed']).
        results_wanted: Number of results to fetch per site.
    """
    print(f"\n[SEARCH] '{query}' in '{location}' (last {hours_old}h)")
    try:
        jobs_df = scrape_jobs(
            site_name=site_names,
            search_term=query,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            linkedin_fetch_description=True,
        )
    except Exception as e:
        print(f"[ERROR] scraping failed: {e}")
        return

    if jobs_df is None or jobs_df.empty:
        print("[INFO] no jobs found for this query.")
        return

    print(f"[INFO] found {len(jobs_df)} postings.")
    JOBS_DIR.mkdir(exist_ok=True)

    saved, skipped, failed = 0, 0, 0
    for _, row in jobs_df.iterrows():
        job_title = sanitize_filename(str(row.get("title", "unknown")))
        company = sanitize_filename(str(row.get("company", "unknown")))
        description = str(row.get("description", "No description available."))

        full_text = (
            f"Title: {row.get('title', 'N/A')}\n"
            f"Company: {row.get('company', 'N/A')}\n"
            f"Location: {row.get('location', 'N/A')}\n"
            f"URL: {row.get('job_url', 'N/A')}\n"
            f"Posted: {row.get('date_posted', 'N/A')}\n"
            f"Site: {row.get('site', 'N/A')}\n"
            f"Search query: {query}\n"
            + "-" * 40 + "\n\n"
            + description
        )

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}_{company}_{job_title}.txt"
        filepath = JOBS_DIR / filename

        # Guard against Windows MAX_PATH limit (~260 chars)
        if len(str(filepath)) > 250:
            filename = f"{timestamp}_{company[:30]}_{job_title[:30]}.txt"
            filepath = JOBS_DIR / filename

        if filepath.exists():
            skipped += 1
            continue

        try:
            if is_wrong_location(str(row.get("location", ""))):
                skipped += 1
                continue
            if is_wrong_remote(str(row.get("location", ""))):
                skipped += 1
                continue
            if is_obvious_noise(str(row.get("title", ""))):
                skipped += 1
                continue
            filepath.write_text(full_text, encoding="utf-8")
            saved += 1
        except OSError as e:
            print(f"[WARN] could not save '{filename}': {e}")
            failed += 1

    print(f"[DONE] saved {saved}, skipped {skipped}, failed {failed}.")


def main():
    """Parse CLI args and run all queries from searches.txt (or a single query)."""
    parser = argparse.ArgumentParser(description="Search jobs from searches.txt or a single query.")
    parser.add_argument("--file", default=str(SEARCHES_FILE),
                        help="Path to searches file (default: searches.txt in project root).")
    parser.add_argument("--query", help="Run a single ad-hoc query instead of the file.")
    parser.add_argument("--location", default="Brussels, Belgium",
                        help="Location for --query mode.")
    parser.add_argument("--hours", type=int, default=168,
                        help="Max age of postings in hours for --query mode.")
    parser.add_argument("--sites", nargs="+", default=["linkedin", "indeed"])
    parser.add_argument("--results", type=int, default=15,
                        help="Results per site (keep low to be respectful).")
    args = parser.parse_args()

    if args.query:
        search_and_save(args.query, args.location, args.hours,
                        args.sites, args.results)
        return

    searches_path = Path(args.file)
    if not searches_path.exists():
        print(f"[ERROR] searches file not found: {searches_path}")
        return

    entries = parse_searches_file(searches_path)
    print(f"[INFO] running {len(entries)} queries from {searches_path.name}")

    for entry in entries:
        search_and_save(
            query=entry["query"],
            location=entry["location"],
            hours_old=entry["hours_old"],
            site_names=args.sites,
            results_wanted=args.results,
        )


if __name__ == "__main__":
    main()