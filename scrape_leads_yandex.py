"""
Скрипт для сбора лидов из Яндекс.Карт через Selenium.

Что собираем:
1) Название компании
2) Телефон
3) Веб-сайт

Поисковый запрос по умолчанию:
"Грузоперевозки и аренда спецтехники"

------------------------------------------------------------
КАК ЗАПУСТИТЬ
------------------------------------------------------------
1. Установите Python 3.10+.
2. Установите зависимости:
   pip install selenium webdriver-manager
3. Запустите:
   python scrape_leads_yandex.py
4. Результат сохранится в:
   leads.csv

Пример с параметрами:
   python scrape_leads_yandex.py --city "Москва" --max-results 40 --headless

Важно:
- Верстка Яндекс.Карт периодически меняется. Если сайт обновится, может
  понадобиться подправить CSS-селекторы в функциях extract_*.
- Используйте только в рамках правил сайта и законодательства.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_QUERY = "Грузоперевозки и аренда спецтехники"
OUTPUT_FILE = "leads.csv"


@dataclass
class CompanyLead:
    name: str
    phone: str
    website: str


def build_driver(headless: bool) -> webdriver.Chrome:
    """Создает Chrome WebDriver с базовыми настройками."""
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
    """Возвращает текст первого элемента по списку селекторов."""
    for selector in selectors:
        try:
            el = root.find_element(By.CSS_SELECTOR, selector)
            text = el.text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def first_href(root, selectors: List[str]) -> str:
    """Возвращает href первого элемента по списку селекторов."""
    for selector in selectors:
        try:
            el = root.find_element(By.CSS_SELECTOR, selector)
            href = (el.get_attribute("href") or "").strip()
            if href:
                return href
        except NoSuchElementException:
            continue
    return ""


def extract_card_data(card) -> CompanyLead | None:
    """
    Извлекает название, телефон и сайт из карточки результата.
    Используем fallback-селекторы, чтобы пережить мелкие изменения верстки.
    """
    name_selectors = [
        "a.search-business-snippet-view__title-link",
        "a.orgpage-header-view__title-link",
        "a[href*='/org/']",
    ]
    phone_selectors = [
        "div.search-business-snippet-view__phones",
        "a[href^='tel:']",
        "div.card-phones-view__phone-number",
    ]
    site_selectors = [
        "a.search-business-snippet-view__link",
        "a[href^='http']:not([href*='yandex.ru'])",
    ]

    name = first_text(card, name_selectors)
    if not name:
        return None

    phone = first_text(card, phone_selectors)
    website = first_href(card, site_selectors)
    return CompanyLead(name=name, phone=phone, website=website)


def collect_from_yandex_maps(
    driver: webdriver.Chrome, query: str, city: str, max_results: int
) -> List[CompanyLead]:
    """Открывает Яндекс.Карты, ищет компании и собирает лиды."""
    # Формируем строку поиска: "запрос + город"
    full_query = f"{query} {city}".strip()
    encoded = quote_plus(full_query)
    url = f"https://yandex.ru/maps/?text={encoded}"
    driver.get(url)

    # Даем странице время загрузить панель результатов.
    time.sleep(6)

    # Прокрутка для подгрузки новых карточек.
    for _ in range(20):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

    card_selectors = [
        "li.search-snippet-view",
        "div.search-business-snippet-view",
        "div.orgpage-snippet-view",
    ]

    cards = []
    for selector in card_selectors:
        found = driver.find_elements(By.CSS_SELECTOR, selector)
        if found:
            cards = found
            break

    leads: List[CompanyLead] = []
    seen = set()

    for card in cards:
        lead = extract_card_data(card)
        if lead is None:
            continue

        # Убираем дубли по комбинации name/phone/website.
        key = (lead.name.lower(), lead.phone.lower(), lead.website.lower())
        if key in seen:
            continue

        seen.add(key)
        leads.append(lead)
        if len(leads) >= max_results:
            break

    return leads


def save_csv(leads: List[CompanyLead], filename: str) -> None:
    """Сохраняет список компаний в CSV."""
    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["Название компании", "Телефон", "Веб-сайт"])
        for item in leads:
            writer.writerow([item.name, item.phone, item.website])


def parse_args() -> argparse.Namespace:
    """Парсит CLI-аргументы."""
    parser = argparse.ArgumentParser(
        description="Сбор компаний из Яндекс.Карт в leads.csv"
    )
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Поисковая фраза")
    parser.add_argument("--city", default="Москва", help="Город для поиска")
    parser.add_argument(
        "--max-results", type=int, default=50, help="Максимум компаний"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Запуск без окна браузера"
    )
    return parser.parse_args()


def main() -> None:
    """Точка входа скрипта."""
    args = parse_args()
    driver = build_driver(headless=args.headless)
    try:
        leads = collect_from_yandex_maps(
            driver=driver,
            query=args.query,
            city=args.city,
            max_results=args.max_results,
        )
        save_csv(leads, OUTPUT_FILE)
        print(f"Готово! Найдено: {len(leads)}. Файл: {OUTPUT_FILE}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

