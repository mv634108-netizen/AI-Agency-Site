"""
Unified scraper for 2GIS and Yandex Maps.

Collects: company name, phone, website, source.
Default query: "Грузоперевозки и аренда спецтехники".

Run:
  
  pip install selenium webdriver-manager openpyxl
  python scrape_leads_unified.py --source both

Output:
  - leads.csv  (delimiter: ';', UTF-8 with BOM for Excel)
  - leads.xlsx (if openpyxl is installed)
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_QUERY = "Грузоперевозки и аренда спецтехники"
OUTPUT_FILE = "leads.csv"
OUTPUT_XLSX_FILE = "leads.xlsx"


@dataclass
class CompanyLead:
    name: str
    phone: str
    website: str
    source: str


def build_driver(headless: bool) -> webdriver.Chrome:
    """Create Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")
    options.add_argument("--no-sandbox")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def first_text(root, selectors: List[str]) -> str:
    for selector in selectors:
        try:
            element = root.find_element(By.CSS_SELECTOR, selector)
            text = element.text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def first_href(root, selectors: List[str]) -> str:
    for selector in selectors:
        try:
            element = root.find_element(By.CSS_SELECTOR, selector)
            href = (element.get_attribute("href") or "").strip()
            if href:
                return href
        except NoSuchElementException:
            continue
    return ""


def extract_phone_from_tel_href(root) -> str:
    """Try to extract phone from tel: links."""
    try:
        links = root.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")
    except Exception:
        return ""
    for link in links:
        href = (link.get_attribute("href") or "").strip()
        if href.lower().startswith("tel:"):
            phone = href[4:].strip()
            if phone:
                return phone
    return ""


def extract_phone_from_text(root) -> str:
    """Fallback: detect Russian-like phone inside card text."""
    text = ""
    try:
        text = (root.text or "").strip()
    except Exception:
        return ""
    if not text:
        return ""
    match = re.search(r"(\+?\d[\d\-\s\(\)]{8,}\d)", text)
    return match.group(1).strip() if match else ""


def extract_phone_from_html(html: str) -> str:
    """
    Fallback parser for phone numbers from raw HTML.
    Useful when number is rendered in JSON/script data.
    """
    if not html:
        return ""

    patterns = [
        # JSON-like formats often used in embedded data
        r'"phone"\s*:\s*"\s*(\+?\d[\d\-\s\(\)]{8,}\d)\s*"',
        r'"formattedPhone"\s*:\s*"\s*(\+?\d[\d\-\s\(\)]{8,}\d)\s*"',
        r'"number"\s*:\s*"\s*(\+?\d[\d\-\s\(\)]{8,}\d)\s*"',
        # Generic Russian-style phone fallback
        r"(\+7[\d\-\s\(\)]{9,}\d)",
        r"(8[\d\-\s\(\)]{9,}\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1).strip()
    return ""


def resolve_phone(root, selectors: List[str]) -> str:
    """Get phone from selector text, tel href, or regex fallback."""
    phone = first_text(root, selectors)
    if phone:
        return phone
    phone = extract_phone_from_tel_href(root)
    if phone:
        return phone
    return extract_phone_from_text(root)


def extract_2gis_card(card) -> Optional[CompanyLead]:
    name = first_text(
        card,
        ["a._zjunba", "a[data-testid='card_title']", "a[href*='/firm/']"],
    )
    if not name:
        return None
    phone = resolve_phone(card, ["a[href^='tel:']", "span._b0ke8", "div[class*='phone']"])
    website = first_href(
        card,
        [
            "a[href*='http']:not([href*='2gis.ru']):not([href*='dgis.ru'])",
            "a[data-testid='contact-site-link']",
        ],
    )
    return CompanyLead(name=name, phone=phone, website=website, source="2gis")


def extract_yandex_card(card) -> Optional[CompanyLead]:
    name = first_text(
        card,
        [
            "a.search-business-snippet-view__title-link",
            "a.orgpage-header-view__title-link",
            "a[href*='/org/']",
        ],
    )
    if not name:
        return None
    phone = resolve_phone(
        card,
        [
            "div.search-business-snippet-view__phones",
            "a[href^='tel:']",
            "div.card-phones-view__phone-number",
        ],
    )
    website = first_href(
        card,
        [
            "a.search-business-snippet-view__link",
            "a[href^='http']:not([href*='yandex.ru'])",
        ],
    )
    return CompanyLead(name=name, phone=phone, website=website, source="yandex")


def extract_from_yandex_details(driver: webdriver.Chrome, fallback_name: str, fallback_site: str) -> CompanyLead:
    """
    Try to extract phone/site from opened Yandex organization details panel.
    Falls back to values from search card if detail selectors are absent.
    """
    root = driver
    name = first_text(
        root,
        [
            "h1.orgpage-header-view__header",
            "h1[class*='orgpage-header-view']",
        ],
    ) or fallback_name

    phone = resolve_phone(
        root,
        [
            "div.orgpage-phones-view__phone-number",
            "a[href^='tel:']",
            "div[class*='phone']",
        ],
    )
    if not phone:
        # Last-resort attempt: parse raw page source.
        phone = extract_phone_from_html(driver.page_source)
    website = first_href(
        root,
        [
            "a.business-urls-view__link",
            "a[href^='http']:not([href*='yandex.ru'])",
        ],
    ) or fallback_site

    return CompanyLead(name=name, phone=phone, website=website, source="yandex")


def open_yandex_card_details(card) -> bool:
    """Open organization details by clicking title/link from a search card."""
    click_selectors = [
        "a.search-business-snippet-view__title-link",
        "a.orgpage-header-view__title-link",
        "a[href*='/org/']",
    ]
    for selector in click_selectors:
        try:
            target = card.find_element(By.CSS_SELECTOR, selector)
            target.click()
            return True
        except Exception:
            continue
    return False


def collect_from_2gis(driver: webdriver.Chrome, query: str, city_2gis: str, max_results: int) -> List[CompanyLead]:
    print("[2GIS] Opening search page...")
    url = f"https://2gis.ru/{city_2gis}/search/{quote_plus(query)}"
    driver.get(url)
    time.sleep(5)
    for _ in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.6)
    cards = []
    for selector in ["div._1kf6gff", "div[data-testid='search-result']", "div[class*='search-snippet-view']"]:
        found = driver.find_elements(By.CSS_SELECTOR, selector)
        if found:
            cards = found
            break
    leads: List[CompanyLead] = []
    for card in cards:
        lead = extract_2gis_card(card)
        if lead:
            leads.append(lead)
        if len(leads) >= max_results:
            break
    print(f"[2GIS] Collected: {len(leads)}")
    return leads


def collect_from_yandex(driver: webdriver.Chrome, query: str, city_yandex: str, max_results: int) -> List[CompanyLead]:
    print("[Yandex] Opening search page...")
    url = f"https://yandex.ru/maps/?text={quote_plus((query + ' ' + city_yandex).strip())}"
    driver.get(url)
    time.sleep(6)
    for _ in range(8):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
    cards = []
    for selector in ["li.search-snippet-view", "div.search-business-snippet-view", "div.orgpage-snippet-view"]:
        found = driver.find_elements(By.CSS_SELECTOR, selector)
        if found:
            cards = found
            break
    leads: List[CompanyLead] = []
    for card in cards:
        list_lead = extract_yandex_card(card)
        if not list_lead:
            continue

        detail_lead = list_lead
        if open_yandex_card_details(card):
            try:
                WebDriverWait(driver, 5).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='tel:']")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.orgpage-phones-view__phone-number")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.orgpage-header-view__header")),
                    )
                )
            except Exception:
                pass
            detail_lead = extract_from_yandex_details(
                driver, fallback_name=list_lead.name, fallback_site=list_lead.website
            )

        leads.append(detail_lead)
        if len(leads) >= max_results:
            break
    print(f"[Yandex] Collected: {len(leads)}")
    return leads


def deduplicate(leads: List[CompanyLead]) -> List[CompanyLead]:
    unique: List[CompanyLead] = []
    seen = set()
    for lead in leads:
        key = (lead.name.lower(), lead.phone.lower(), lead.website.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    return unique


def save_csv(leads: List[CompanyLead], filename: str) -> None:
    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        # Excel in RU locale usually opens ';' separated CSV correctly.
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["Название компании", "Телефон", "Веб-сайт", "Источник"])
        for item in leads:
            writer.writerow([item.name, item.phone, item.website, item.source])


def save_xlsx(leads: List[CompanyLead], filename: str) -> bool:
    """
    Save leads to XLSX.
    Returns True when file was created, False if openpyxl is missing.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        return False

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Leads"
    sheet.append(["Название компании", "Телефон", "Веб-сайт", "Источник"])
    for item in leads:
        sheet.append([item.name, item.phone, item.website, item.source])
    workbook.save(filename)
    return True


def safe_filename(base_name: str) -> str:
    """Build alternate filename with timestamp when base file is locked."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if "." in base_name:
        stem, ext = base_name.rsplit(".", 1)
        return f"{stem}_{timestamp}.{ext}"
    return f"{base_name}_{timestamp}"


def save_csv_with_fallback(leads: List[CompanyLead], filename: str) -> str:
    """Save CSV. If file is locked, save to timestamped alternative."""
    try:
        save_csv(leads, filename)
        return filename
    except PermissionError:
        alt_name = safe_filename(filename)
        save_csv(leads, alt_name)
        return alt_name


def save_xlsx_with_fallback(leads: List[CompanyLead], filename: str) -> tuple[bool, str]:
    """
    Save XLSX with fallback name if target file is locked.
    Returns: (saved, filename_used).
    """
    try:
        saved = save_xlsx(leads, filename)
        return saved, filename
    except PermissionError:
        alt_name = safe_filename(filename)
        saved = save_xlsx(leads, alt_name)
        return saved, alt_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lead scraper from 2GIS/Yandex")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Search phrase")
    parser.add_argument("--source", choices=["2gis", "yandex", "both"], default="both", help="Data source")
    parser.add_argument("--city-2gis", default="moscow", help="2GIS city slug")
    parser.add_argument("--city-yandex", default="Москва", help="Yandex city name")
    parser.add_argument("--max-results", type=int, default=50, help="Max results per source")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    driver = build_driver(headless=args.headless)
    try:
        print(f"Start source={args.source}, query='{args.query}'")
        all_leads: List[CompanyLead] = []
        if args.source in ("2gis", "both"):
            all_leads.extend(collect_from_2gis(driver, args.query, args.city_2gis, args.max_results))
        if args.source in ("yandex", "both"):
            all_leads.extend(collect_from_yandex(driver, args.query, args.city_yandex, args.max_results))
        all_leads = deduplicate(all_leads)
        csv_name = save_csv_with_fallback(all_leads, OUTPUT_FILE)
        xlsx_saved, xlsx_name = save_xlsx_with_fallback(all_leads, OUTPUT_XLSX_FILE)
        print(f"Done. Saved {len(all_leads)} rows to {csv_name}")
        if xlsx_saved:
            print(f"Also saved Excel file: {xlsx_name}")
        else:
            print("XLSX was not created. Install openpyxl: pip install openpyxl")
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C). Partial results are not saved.")
    finally:
        try:
            driver.quit()
        except Exception:
            # Browser may already be closed after interruption.
            pass


if __name__ == "__main__":
    main()

