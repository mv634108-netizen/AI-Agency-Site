"""
Скрипт для сбора публично доступных профилей ВКонтакте по запросам:
- Недвижимость Москва
- Новостройки Москва
- ЖК Москва

Собираемые поля:
- имя
- профиль / ID
- никнейм
- телефон (если виден публично)

Результат сохраняется в файл leads.csv.

Как запустить:
1. Установите Python 3.10+.
2. Установите зависимости:
   pip install selenium webdriver-manager
3. Запустите скрипт:
   python scrape_social_leads.py

Важно:
- Собирайте только публичные данные.
- Любые персональные данные должны обрабатываться в соответствии с правилами ВКонтакте и законодательством.
- Телефоны в большинстве случаев не видны без авторизации, поэтому поле может оставаться пустым.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from typing import List

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

KEYWORDS = [
    "Недвижимость Москва",
    "Новостройки Москва",
    "ЖК Москва",
]
OUTPUT_FILE = "leads.csv"

PHONE_PATTERN = re.compile(
    r"(\+7[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}|8[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})"
)

@dataclass
class Lead:
    name: str
    profile_url: str
    profile_id: str
    nickname: str
    phone: str
    keyword: str


def build_driver(headless: bool) -> webdriver.Chrome:
    """Создает WebDriver для Chrome."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def extract_profile_info(card) -> Lead | None:
    """Извлекает информацию из карточки результата поиска."""
    try:
        link = card.find_element(By.CSS_SELECTOR, "a[href^='https://vk.com'], a[href^='/']")
    except NoSuchElementException:
        return None

    profile_url = (link.get_attribute("href") or "").strip()
    if not profile_url:
        return None

    name = (link.text or "").strip()
    if not name:
        return None

    profile_id, nickname = normalize_vk_profile(profile_url)
    phone = extract_phone(card.text)

    return Lead(
        name=name,
        profile_url=profile_url,
        profile_id=profile_id,
        nickname=nickname,
        phone=phone,
        keyword="",
    )


def normalize_vk_profile(url: str) -> tuple[str, str]:
    """Возвращает ID/ник из URL профиля ВКонтакте."""
    url = url.split("?")[0].split("#")[0].rstrip("/")
    if not url:
        return "", ""
    if url.startswith("/"):
        url = f"https://vk.com{url}"
    parts = url.split("/")
    if not parts:
        return "", ""

    handle = parts[-1]
    if not handle:
        return "", ""

    return handle, handle


def extract_phone(text: str) -> str:
    """Ищет явный телефонный номер в тексте карточки."""
    if not text:
        return ""
    match = PHONE_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def collect_vk_people(driver: webdriver.Chrome, query: str, max_results: int) -> List[Lead]:
    """Собирает профили пользователей из поиска ВКонтакте по ключевому запросу."""
    encoded_query = query.replace(" ", "+")
    url = f"https://vk.com/search?c%5Bq%5D={encoded_query}&c%5Bsection%5D=people"
    driver.get(url)
    time.sleep(5)

    # Скроллим страницу, чтобы загрузить больше результатов.
    for _ in range(4):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    cards = driver.find_elements(By.CSS_SELECTOR, "div.person, div.friends_row, div.search_item, div.author, div.page_block")
    leads: List[Lead] = []
    seen_urls = set()

    for card in cards:
        lead = extract_profile_info(card)
        if lead is None:
            continue
        if lead.profile_url in seen_urls:
            continue

        seen_urls.add(lead.profile_url)
        lead.keyword = query
        leads.append(lead)
        if len(leads) >= max_results:
            break

    return leads


def save_to_csv(leads: List[Lead], filename: str) -> None:
    """Сохраняет результаты в CSV."""
    with open(filename, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Name", "ProfileURL", "ProfileID", "Nickname", "Phone", "Keyword"])
        for lead in leads:
            writer.writerow([lead.name, lead.profile_url, lead.profile_id, lead.nickname, lead.phone, lead.keyword])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сбор публичных лидов ВКонтакте по запросам о недвижимости в Москве."
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Максимальное количество результатов для каждого запроса.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запустить браузер в headless-режиме.",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help="Имя выходного CSV-файла.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    driver = build_driver(headless=args.headless)

    try:
        all_leads: List[Lead] = []
        for keyword in KEYWORDS:
            print(f"Собираем профили для запроса: {keyword}")
            leads = collect_vk_people(driver, keyword, args.max_results)
            all_leads.extend(leads)
            time.sleep(2)

        save_to_csv(all_leads, args.output)
        print(f"Готово: {len(all_leads)} записей сохранены в {args.output}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
