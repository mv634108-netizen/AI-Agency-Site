"""
Скрипт для сбора лидов из публичного каталога 2ГИС через Selenium.

Что собираем:
1) Название компании
2) Телефон
3) Веб-сайт

Поисковый запрос по умолчанию:
"Грузоперевозки и аренда спецтехники"

------------------------------------------------------------
КАК ЗАПУСТИТЬ
------------------------------------------------------------
1. Установите Python 3.10+ (если еще не установлен).

2. Установите зависимости:
   pip install selenium webdriver-manager

3. Запустите скрипт:
   python scrape_leads.py

4. Результат сохранится в файл:
   leads.csv

Дополнительно (параметры):
   python scrape_leads.py --city moscow --max-results 80 --headless

Примечание:
- CSS-классы на сайтах каталогов могут меняться, поэтому периодически
  может потребоваться обновить селекторы в функции extract_company_data().
- Используйте скрипт только в рамках правил сайта, законодательства
  и политики обработки персональных данных.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from typing import List, Optional
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
    """Модель одной найденной компании."""

    name: str
    phone: str
    website: str


def build_driver(headless: bool) -> webdriver.Chrome:
    """
    Создает и настраивает Chrome WebDriver.

    headless=True позволяет запускать браузер без графического окна.
    """
    chrome_options = Options()
    if headless:
        # Новый headless-режим для современных версий Chrome.
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=ru-RU")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def first_text_by_selectors(root, selectors: List[str]) -> str:
    """
    Возвращает текст первого найденного элемента среди списка CSS-селекторов.
    Если ничего не найдено — пустая строка.
    """
    for css in selectors:
        try:
            element = root.find_element(By.CSS_SELECTOR, css)
            text = element.text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def first_href_by_selectors(root, selectors: List[str]) -> str:
    """
    Возвращает href первого найденного элемента среди списка CSS-селекторов.
    Если ничего не найдено — пустая строка.
    """
    for css in selectors:
        try:
            element = root.find_element(By.CSS_SELECTOR, css)
            href = (element.get_attribute("href") or "").strip()
            if href:
                return href
        except NoSuchElementException:
            continue
    return ""


def extract_company_data(card) -> Optional[CompanyLead]:
    """
    Пытается извлечь данные из карточки компании.

    Так как верстка 2ГИС может меняться, используем несколько fallback-селекторов.
    """
    # Селекторы названия компании
    name_selectors = [
        "a._zjunba",             # часто встречающийся элемент названия
        "a[data-testid='card_title']",
        "a[href*='/firm/']",
    ]

    # Селекторы телефона
    phone_selectors = [
        "a[href^='tel:']",
        "span._b0ke8",           # fallback-класс (может измениться)
        "div[class*='phone']",
    ]

    # Селекторы сайта
    website_selectors = [
        "a[href*='http']:not([href*='2gis.ru']):not([href*='dgis.ru'])",
        "a[data-testid='contact-site-link']",
    ]

    name = first_text_by_selectors(card, name_selectors)
    if not name:
        return None

    phone = first_text_by_selectors(card, phone_selectors)
    website = first_href_by_selectors(card, website_selectors)

    return CompanyLead(name=name, phone=phone, website=website)


def collect_from_2gis(
    driver: webdriver.Chrome,
    query: str,
    city: str,
    max_results: int,
    scroll_rounds: int = 20,
) -> List[CompanyLead]:
    """
    Открывает поиск в 2ГИС и собирает лиды из списка компаний.

    Параметры:
    - query: поисковая фраза
    - city: slug города в URL 2ГИС (например: moscow, spb)
    - max_results: сколько максимум записей собрать
    - scroll_rounds: сколько раз скроллить список для подгрузки новых карточек
    """
    encoded_query = quote_plus(query)
    url = f"https://2gis.ru/{city}/search/{encoded_query}"
    driver.get(url)
    time.sleep(5)

    # Пробуем прокрутить страницу, чтобы подгрузить больше карточек.
    for _ in range(scroll_rounds):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.8)

    # Набор селекторов карточек результатов (с fallback).
    card_selectors = [
        "div._1kf6gff",                  # встречается у карточек в результатах
        "div[data-testid='search-result']",
        "div[class*='search-snippet-view']",
    ]

    cards = []
    for css in card_selectors:
        found = driver.find_elements(By.CSS_SELECTOR, css)
        if found:
            cards = found
            break

    leads: List[CompanyLead] = []
    seen = set()

    for card in cards:
        lead = extract_company_data(card)
        if lead is None:
            continue

        # Дедупликация: по связке name + phone + website
        key = (lead.name.lower(), lead.phone.lower(), lead.website.lower())
        if key in seen:
            continue
        seen.add(key)
        leads.append(lead)

        if len(leads) >= max_results:
            break

    return leads


def save_to_csv(leads: List[CompanyLead], filename: str) -> None:
    """Сохраняет список лидов в CSV."""
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Название компании", "Телефон", "Веб-сайт"])
        for lead in leads:
            writer.writerow([lead.name, lead.phone, lead.website])


def parse_args() -> argparse.Namespace:
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Сбор лидов из 2ГИС: название, телефон, сайт."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Поисковая фраза (по умолчанию: грузоперевозки и аренда спецтехники).",
    )
    parser.add_argument(
        "--city",
        default="moscow",
        help="Город в URL 2ГИС (пример: moscow, spb, krasnodar).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Максимум компаний для сохранения.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запуск Chrome в headless-режиме (без окна браузера).",
    )
    return parser.parse_args()


def main() -> None:
    """
    Точка входа:
    1) Запускаем браузер
    2) Собираем данные
    3) Сохраняем в leads.csv
    """
    args = parse_args()

    driver = build_driver(headless=args.headless)
    try:
        leads = collect_from_2gis(
            driver=driver,
            query=args.query,
            city=args.city,
            max_results=args.max_results,
        )
        save_to_csv(leads, OUTPUT_FILE)
        print(f"Готово! Собрано {len(leads)} компаний. Файл: {OUTPUT_FILE}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

