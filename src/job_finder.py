# src/job_finder.py
"""
job_finder.py
=============
Main orchestrator. Reads searches.txt, scrapes JobSpy sites (Indeed, Glassdoor, Google),
applies filters and saves results to the jobs/ directory.

Note: Sites like Jobat and StepStone are excluded because they use heavy anti-bot 
protection (Cloudflare). For those, use `src/manual_adder.py`.
"""

import argparse
import re
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
from jobspy import scrape_jobs

ROOT_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT_DIR / "jobs"
SEARCHES_FILE = ROOT_DIR / "searches.txt"

NOISE_TITLE_KEYWORDS = [
    "forklift", "driver", "die cutter", "stitcher", "shipping",
    "receiving", "press operator", "apprentice", "warehouse",
    "clinical account", "faculty", "professor", "postdoc",
]

ACCEPTED_LOCATIONS = [
    "belgium", "belgië", "belgique", "belgien",
    "brussels", "bruxelles", "brussel", "etterbeek", "ixelles", "elsene",
    "schaerbeek", "schaarbeek", "woluwe", "anderlecht", "molenbeek",
    "zaventem", "diegem", "vilvoorde", "machelen",
    "leuven", "louvain", "mechelen", "malines",
    "antwerp", "antwerpen", "anvers",
    "ghent", "gent", "gand",
    "namur", "namen",
    "louvain-la-neuve", "lln",
    "wavre", "waterloo", "braine-l'alleud", "nivelles",
    "wallonia", "wallonie", "flanders", "vlaanderen",
    "remote",
]

REJECTED_LOCATIONS = [
    "united states", "usa", "u.s.", " wisconsin", " wisconsin,",
    " milwaukee", " chicago", " california", " new york", " texas",
    " florida", " boston", " seattle", " austin", " denver",
    ", ca", ", ny", ", tx", ", wa", ", il", ", ma", ", fl",
]

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
    t = title.lower()
    return any(kw in t for kw in NOISE_TITLE_KEYWORDS)

def is_wrong_location(location: str) -> bool:
    if not location:
        return False
    loc = location.lower()
    if any(r in loc for r in REJECTED_LOCATIONS):
        return True
    if not any(a in loc for a in ACCEPTED_LOCATIONS):
        return True
    return False

def is_wrong_remote(location: str) -> bool:
    if not location:
        return False
    loc = location.lower()
    if "remote" not in loc:
        return False
    eu_markers = ["europe", " eu", "eu,", "eu ", "emea", "anywhere in europe"]
    if any(m in loc for m in eu_markers):
        return False
    if any(m in loc for m in NON_EU_REMOTE_MARKERS):
        return True
    return False

def sanitize_filename(name: str, max_length: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = re.sub(r"\s+", " ", name).strip().replace(" ", "_")
    name = name.rstrip(". ")
    if len(name) > max_length:
        name = name[:max_length].rstrip("._- ")
    return name or "unknown"

def process_and_save_jobs(jobs_list: list[dict], query: str):
    """Applies filters and saves unique jobs to disk."""
    JOBS_DIR.mkdir(exist_ok=True)
    REJECTED_DIR = JOBS_DIR / "rejected"

    def save_to_rejected(text, filename, reason):
        folder = REJECTED_DIR / reason
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_text(text, encoding="utf-8")

    saved, skipped, failed = 0, 0, 0

    for job in jobs_list:
        title = str(job.get("title", "Unknown"))
        company = str(job.get("company", "Unknown"))
        location = str(job.get("location", ""))
        url = str(job.get("url", ""))
        description = str(job.get("description", "No description available."))
        site = str(job.get("site", "unknown"))
        posted = str(job.get("date_posted", datetime.now().strftime("%Y-%m-%d")))

        full_text = (
            f"Title: {title}\n"
            f"Company: {company}\n"
            f"Location: {location}\n"
            f"URL: {url}\n"
            f"Posted: {posted}\n"
            f"Site: {site}\n"
            f"Search query: {query}\n"
            + "-" * 40 + "\n\n"
            + description
        )

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}_{sanitize_filename(company)}_{sanitize_filename(title)}.txt"
        filepath = JOBS_DIR / filename

        if len(str(filepath)) > 250:
            filename = f"{timestamp}_{sanitize_filename(company)[:30]}_{sanitize_filename(title)[:30]}.txt"
            filepath = JOBS_DIR / filename

        if filepath.exists():
            save_to_rejected(full_text, filename, "duplicate")
            skipped += 1
            continue

        try:
            if is_wrong_location(location):
                save_to_rejected(full_text, filename, "wrong_location")
                skipped += 1
                continue
            if is_wrong_remote(location):
                save_to_rejected(full_text, filename, "wrong_remote")
                skipped += 1
                continue
            if is_obvious_noise(title):
                save_to_rejected(full_text, filename, "noise")
                skipped += 1
                continue

            filepath.write_text(full_text, encoding="utf-8")
            saved += 1
        except OSError as e:
            print(f"[WARN] could not save '{filename}': {e}")
            failed += 1

    return saved, skipped, failed

def parse_searches_file(path: Path) -> list:
    entries = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"): continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3: continue
        query, location, hours = parts
        try:
            entries.append({"query": query, "location": location, "hours_old": int(hours)})
        except ValueError:
            continue
    return entries

def main():
    parser = argparse.ArgumentParser(description="Master Job Scraper.")
    parser.add_argument("--sites", nargs="+", default=["indeed", "glassdoor"],
                        help="JobSpy sites to use (e.g., linkedin indeed glassdoor google)")
    parser.add_argument("--results", type=int, default=10, help="Results per JobSpy site")
    parser.add_argument("--query", help="Run a single ad-hoc query instead of the file.")
    parser.add_argument("--location", default="Brussels, Belgium", help="Location for ad-hoc query.")
    parser.add_argument("--hours", type=int, default=168, help="Max age in hours for ad-hoc query.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries to run")
    args = parser.parse_args()

    if args.query:
        entries = [{"query": args.query, "location": args.location, "hours_old": args.hours}]
    else:
        searches_path = Path(SEARCHES_FILE)
        if not searches_path.exists():
            print(f"[ERROR] {searches_path} not found.")
            return
        entries = parse_searches_file(searches_path)

    if args.limit:
        entries = entries[:args.limit]

    print(f"[INFO] Starting run for {len(entries)} queries.")
    print(f"[INFO] Sites: {', '.join(args.sites)}\n")

    for entry in entries:
        query = entry["query"]
        location = entry["location"]
        hours_old = entry["hours_old"]
        
        print(f"\n{'='*50}")
        print(f"QUERY: '{query}' in '{location}' (last {hours_old}h)")
        print(f"{'='*50}")

        all_jobs = []

        # Fetch from JobSpy (Indeed, Glassdoor)
        print(f"  -> Scraping JobSpy...")
        try:
            df = scrape_jobs(
                site_name=args.sites,
                search_term=query,
                location=location,
                results_wanted=args.results,
                hours_old=hours_old,
                fetch_description=True,
            )
            if df is not None and not df.empty:
                all_jobs.extend(df.to_dict("records"))
        except Exception as e:
            print(f"     [ERROR] JobSpy failed: {e}")

        # Filter and Save
        if all_jobs:
            saved, skipped, failed = process_and_save_jobs(all_jobs, query)
            print(f"[DONE] Saved: {saved} | Rejected/Skipped: {skipped} | Failed: {failed}")
        else:
            print("[INFO] No jobs found.")

        # Polite delay between queries
        time.sleep(5)

if __name__ == "__main__":
    main()