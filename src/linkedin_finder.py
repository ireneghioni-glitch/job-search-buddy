# src/linkedin_finder.py
"""
linkedin_finder.py
==================
A Selenium-based scraper specifically for LinkedIn, using Brave.
Designed to be more 'human' than headless scrapers, with random delays,
scrolling, and fallback CSS selectors.
"""

import argparse
import random
import time
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

ROOT_DIR = Path(__file__).resolve().parent.parent

# --- BRAVE path on MAC ---
# Se Brave è installato diversamente, aggiorna questo percorso.
BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# --- CSS SELECTORS ON FALLBACK ---
# LinkedIn cambia spesso le classi. Questi sono i più comuni, ma potrebbero variare.
SELECTORS = {
    "job_card": [
        "li.jobs-search-results__list-item",
        "div.job-card-container",
        "li.scaffold-layout__list-item"
    ],
    "job_title": [
        "a.job-card-list__title",
        "h3.base-search-card__title",
        "a.job-card-container__link"
    ],
    "company": [
        "a.job-card-container__company-name",
        "h4.base-search-card__subtitle",
        "span.job-card-container__primary-description"
    ],
    "location": [
        "li.job-card-container__metadata-item",
        "span.job-search-card__location",
        "div.job-card-container__metadata-wrapper"
    ]
}

def human_delay(min_sec=2, max_sec=5):
    """Pausa casuale per simulare un utente umano."""
    time.sleep(random.uniform(min_sec, max_sec))

def human_scroll(driver):
    """Scrolla la pagina in modo casuale per far caricare i risultati."""
    scroll_amount = random.randint(300, 700)
    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
    time.sleep(random.uniform(1.5, 3.5))

def find_element_with_fallback(driver, selectors, parent=None):
    """Prova una lista di selettori CSS e restituisce il primo che trova."""
    for selector in selectors:
        try:
            if parent:
                return parent.find_element(By.CSS_SELECTOR, selector)
            else:
                return driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue
    return None

def save_job(job_data, jobs_dir: Path):
    """Salva un annuncio nel formato standard .txt."""
    title = job_data.get("title", "Unknown")
    company = job_data.get("company", "Unknown")
    location = job_data.get("location", "")
    url = job_data.get("url", "")
    description = job_data.get("description", "No description available.")
    site = "linkedin"
    posted = datetime.now().strftime("%Y-%m-%d")

    full_text = (
        f"Title: {title}\n"
        f"Company: {company}\n"
        f"Location: {location}\n"
        f"URL: {url}\n"
        f"Posted: {posted}\n"
        f"Site: {site}\n"
        f"Search query: linkedin_manual\n"
        + "-" * 40 + "\n\n"
        + description
    )

    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{timestamp}_{company}_{title}.txt".replace(" ", "_").replace("/", "-")
    filepath = jobs_dir / filename

    if filepath.exists():
        return False
    filepath.write_text(full_text, encoding="utf-8")
    return True

def main():
    parser = argparse.ArgumentParser(description="LinkedIn Scraper with Selenium + Brave.")
    parser.add_argument("--profile", default="irene", help="Nome del profilo (es. irene, giovanni)")
    parser.add_argument("--query", required=True, help="Search query (e.g., 'Data Scientist')")
    parser.add_argument("--location", default="Brussels, Belgium", help="Location")
    parser.add_argument("--max_jobs", type=int, default=10, help="Max number of jobs to scrape")
    args = parser.parse_args()

    profile_dir = ROOT_DIR / "profiles" / args.profile
    jobs_dir = profile_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # --- SETUP SELENIUM CON BRAVE ---
    options = Options()
    options.binary_location = BRAVE_PATH
    # Importante: NON usare headless! Deve essere visibile per sembrare umano.
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # --- GO TO LINKEDIN ---
        print("[INFO] Opening LinkedIn...")
        driver.get("https://www.linkedin.com/jobs/")
        human_delay(4, 7)

        # --- LOGIN (se richiesto) ---
        # Se non sei loggato, il sito potrebbe chiedere di farlo. Puoi farlo manualmente
        # nella finestra che si apre. Lo script aspetta che tu sia loggato.
        print("[INFO] If you are not logged in, please log in manually in the browser window.")
        print("[INFO] Waiting 15 seconds for login...")
        time.sleep(15)

        # --- BUILD SEARCH URL ---
        # Nota: l'URL di LinkedIn può cambiare, ma questo formato è abbastanza stabile.
        search_query = args.query.replace(" ", "%20")
        search_location = args.location.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&location={search_location}"
        
        print(f"[INFO] Navigating to search results: {url}")
        driver.get(url)
        human_delay(4, 7)

        # Scrolla per far caricare più risultati
        print("[INFO] Scrolling to load jobs...")
        for _ in range(3):
            human_scroll(driver)
            human_delay(2, 4)

        # --- EXTRACT RESULTS---
        print("[INFO] Extracting job cards...")
        job_cards = []
        for selector in SELECTORS["job_card"]:
            try:
                job_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if job_cards:
                    print(f"[INFO] Found {len(job_cards)} job cards using selector: {selector}")
                    break
            except:
                continue

        if not job_cards:
            print("[ERROR] Could not find any job cards. The page structure may have changed.")
            return

        saved_count = 0
        for i, card in enumerate(job_cards[:args.max_jobs]):
            try:
                print(f"  -> Processing job {i+1}/{min(len(job_cards), args.max_jobs)}...")
                human_delay(2, 5) # Pausa tra un annuncio e l'altro

                # Clicca sulla card per caricare i dettagli (a destra)
                card.click()
                human_delay(2, 4)

                # Estrai i dettagli dalla parte destra della pagina
                # (Questa parte è semplificata; potresti doverla adattare)
                title_el = find_element_with_fallback(driver, SELECTORS["job_title"])
                company_el = find_element_with_fallback(driver, SELECTORS["company"])
                location_el = find_element_with_fallback(driver, SELECTORS["location"])

                title = title_el.text if title_el else "Unknown"
                company = company_el.text if company_el else "Unknown"
                location = location_el.text if location_el else args.location

                # Per la descrizione, potresti dover cliccare "Show more" o estrarre da un contenitore specifico.
                # Qui usiamo un approccio generico.
                description = driver.find_element(By.TAG_NAME, "body").text[:2000] # Semplificato

                job_data = {
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": driver.current_url,
                    "description": description
                }

                if save_job(job_data, jobs_dir):
                    saved_count += 1
                    print(f"     [SAVED] {title} at {company}")
                else:
                    print(f"     [SKIP] Duplicate: {title}")

            except Exception as e:
                print(f"     [WARN] Failed to process job {i+1}: {e}")
                continue

        print(f"\n[DONE] Saved {saved_count} new jobs from LinkedIn.")

    finally:
        print("[INFO] Closing browser...")
        driver.quit()

if __name__ == "__main__":
    main()