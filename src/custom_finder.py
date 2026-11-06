# src/custom_finder.py
"""
custom_finder.py
================
Custom scraper for job portals protected by Cloudflare (Jobat, StepStone).
Returns structured data (list of dicts) to be processed by the main orchestrator.
"""

import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

async def _scrape_url(url: str, site_name: str, query_name: str, debug: bool = False) -> str:
    """Helper to open a page with Playwright and return HTML."""
    async with async_playwright() as p:
        # Avviamo il browser
        browser = await p.chromium.launch(headless=True)
        
        # Creiamo un contesto finto (schermo grande, browser Mac, italiano/inglese)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # --- TENTATIVO DI ACCETTARE I COOKIE ---
            # Questi siti non mostrano i risultati finché non accetti i cookie
            cookie_selectors = [
                "button:has-text('Accept all')", 
                "button:has-text('Alles accepteren')",
                "button:has-text('Accepteren')",
                "button:has-text('Accept')",
                "button:has-text('Akkoord')"
            ]
            for selector in cookie_selectors:
                try:
                    # Se trova il bottone, ci clicca
                    await page.click(selector, timeout=2000)
                    await page.wait_for_timeout(2000) # Aspetta che il sito si ricarichi
                    break
                except:
                    pass
            
            # Aspetta un altro po' per far caricare i risultati in JavaScript
            await page.wait_for_timeout(3000)
            
            html = await page.content()
            
            if debug:
                safe_query = re.sub(r'[^a-zA-Z0-9]', '_', query_name)[:30]
                debug_file = ROOT_DIR / f"debug_{site_name.lower()}_{safe_query}.html"
                debug_file.write_text(html, encoding="utf-8")
                print(f"     [DEBUG] HTML saved to {debug_file.name}")
                
        except Exception as e:
            print(f"     [ERROR] {site_name} failed to load: {e}")
            html = ""
        await browser.close()
        return html

def _parse_jobat(html: str) -> list[dict]:
    """Parse Jobat HTML into a list of job dicts."""
    jobs = []
    if not html: return jobs
    soup = BeautifulSoup(html, "html.parser")
    
    # Cerchiamo i contenitori degli annunci. Jobat usa spesso tag <article> o <div> con classi "job-item"
    cards = soup.find_all("article", class_=re.compile("job|vacature|result", re.IGNORECASE))
    if not cards:
        cards = soup.find_all("div", class_=re.compile("job-item|job-card|vacature|result", re.IGNORECASE))
        
    for card in cards:
        try:
            # Trova il link
            link_tag = card.find("a", href=True)
            if not link_tag: continue
            
            url = link_tag["href"]
            if not url.startswith("http"):
                url = "https://www.jobat.be" + url
                
            # Titolo
            title_tag = card.find("h2") or card.find("h3") or link_tag
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
            
            # Azienda (spesso in uno span o div con classe "company")
            company_tag = card.find(class_=re.compile("company|bedrijf", re.IGNORECASE))
            company = company_tag.get_text(strip=True) if company_tag else "Unknown Company"
            
            # Location
            loc_tag = card.find(class_=re.compile("location|plaats|gemeente", re.IGNORECASE))
            location = loc_tag.get_text(strip=True) if loc_tag else "Belgium"
            
            desc = card.get_text(separator="\n", strip=True)
            
            jobs.append({
                "title": title, "company": company, "location": location,
                "url": url, "description": desc, "site": "jobat"
            })
        except Exception:
            continue
    return jobs

def _parse_stepstone(html: str) -> list[dict]:
    """Parse StepStone HTML into a list of job dicts."""
    jobs = []
    if not html: return jobs
    soup = BeautifulSoup(html, "html.parser")
    
    # StepStone solitamente usa <article> con data-at="job-item"
    cards = soup.find_all("article", attrs={"data-at": "job-item"})
    if not cards:
        cards = soup.find_all("article")
        
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag: continue
            
            url = link_tag["href"]
            if not url.startswith("http"):
                url = "https://www.stepstone.be" + url
                
            title_tag = card.find("h2") or link_tag
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
            
            company_tag = card.find(attrs={"data-at": "job-item-company-name"})
            company = company_tag.get_text(strip=True) if company_tag else "Unknown Company"
            
            location_tag = card.find(attrs={"data-at": "job-item-location"})
            location = location_tag.get_text(strip=True) if location_tag else "Belgium"
            
            desc = card.get_text(separator="\n", strip=True)
            
            jobs.append({
                "title": title, "company": company, "location": location,
                "url": url, "description": desc, "site": "stepstone"
            })
        except Exception:
            continue
    return jobs

def get_custom_jobs(query: str, location: str, site: str, debug: bool = False) -> list[dict]:
    """
    Synchronous wrapper to fetch jobs from custom sites.
    """
    q_enc = query.replace(' ', '+')
    l_enc = location.replace(' ', '+')
    
    if site == "jobat":
        # --- CORREZIONE URL ---
        # Jobat usa /nl/jobs/results invece di /nl/vacatures
        url = f"https://www.jobat.be/nl/jobs/results?q={q_enc}&l={l_enc}"
        html = asyncio.run(_scrape_url(url, "jobat", query, debug))
        return _parse_jobat(html)
    elif site == "stepstone":
        url = f"https://www.stepstone.be/en/jobs/{q_enc}/in-{l_enc}/?radius=30"
        html = asyncio.run(_scrape_url(url, "stepstone", query, debug))
        return _parse_stepstone(html)
    return []