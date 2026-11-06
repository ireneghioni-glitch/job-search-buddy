# src/manual_adder.py
"""
manual_adder.py
===============
Allows manual addition of a job posting to the jobs/ folder.
Useful for sites that are too heavily protected for automatic scraping (e.g., StepStone).

It will attempt to fetch the text from the URL. If that fails (due to Cloudflare),
it will prompt you to paste the text manually.

Usage:
    python3 src/manual_adder.py
"""

import re
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT_DIR / "jobs"

def sanitize_filename(name: str, max_length: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = re.sub(r"\s+", " ", name).strip().replace(" ", "_")
    name = name.rstrip(". ")
    if len(name) > max_length:
        name = name[:max_length].rstrip("._- ")
    return name or "unknown"

def fetch_url_text(url: str) -> str:
    """Attempt to fetch and clean text from a URL."""
    print("[INFO] Trying to fetch text from URL...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, "html.parser")
        # Remove scripts and styles
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator="\n", strip=True)
        
        # Basic check to see if we got blocked
        if "Access Denied" in text or "Cloudflare" in text or "Attention Required" in text:
            print("[WARN] The page seems to be blocked by an anti-bot system.")
            return ""
            
        return text
    except Exception as e:
        print(f"[WARN] Could not fetch URL: {e}")
        return ""

def main():
    JOBS_DIR.mkdir(exist_ok=True)
    
    print("=== MANUAL JOB ADDER ===\n")
    
    url = input("URL dell'annuncio (obbligatorio): ").strip()
    if not url:
        print("[ERROR] URL is required.")
        return

    title = input("Titolo della posizione: ").strip()
    company = input("Nome dell'azienda: ").strip()
    location = input("Location (es. Brussels, Remote): ").strip()
    site_name = input("Sito di provenienza (es. stepstone, jobat): ").strip().lower()
    
    if not site_name:
        site_name = "manual"

    description = fetch_url_text(url)
    
    if not description or len(description) < 200:
        print("\n[NOTICE] Impossibile scaricare automaticamente il testo (blocco anti-bot o pagina troppo corta).")
        print("Copia e incolla la descrizione dell'annuncio qui sotto.")
        print("Quando hai finito, scrivi 'FINE' su una nuova riga e premi Invio:\n")
        
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "FINE":
                break
            lines.append(line)
        description = "\n".join(lines)

    if not description.strip():
        print("[ERROR] Descrizione vuota. Annullamento.")
        return

    # Assemble the standard format
    timestamp = datetime.now().strftime("%Y%m%d")
    full_text = (
        f"Title: {title}\n"
        f"Company: {company}\n"
        f"Location: {location}\n"
        f"URL: {url}\n"
        f"Posted: {timestamp}\n"
        f"Site: {site_name}\n"
        f"Search query: manual_addition\n"
        + "-" * 40 + "\n\n"
        + description
    )

    filename = f"{timestamp}_{sanitize_filename(company)}_{sanitize_filename(title)}.txt"
    filepath = JOBS_DIR / filename

    # Handle long filenames
    if len(str(filepath)) > 250:
        filename = f"{timestamp}_{sanitize_filename(company)[:30]}_{sanitize_filename(title)[:30]}.txt"
        filepath = JOBS_DIR / filename

    if filepath.exists():
        print(f"\n[WARN] File already exists: {filename}")
        overwrite = input("Vuoi sovrascriverlo? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Annullamento.")
            return

    filepath.write_text(full_text, encoding="utf-8")
    print(f"\n[SUCCESS] Annuncio salvato in: {filepath.name}")
    print("Ora puoi lanciare l'analisi con:")
    print(f"python3 src/analyze_all.py --filter \"{sanitize_filename(company)[:10]}\" --extra-files 02_experiences.md 06_cv_master.md")

if __name__ == "__main__":
    main()