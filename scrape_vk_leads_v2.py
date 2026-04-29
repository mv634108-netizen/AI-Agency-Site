"""
Скрипт для сбора публичных профилей из поиска ВКонтакте.

Собираемые поля:
- Имя пользователя
- ID / URL профиля
- Никнейм
- Телефон (если виден публично)

Поиск ведется по ключевым запросам:
- Недвижимость Москва
- Новостройки Москва
- ЖК Москва

УСТАНОВКА И ЗАПУСК:
==================

1. Установите зависимости:
   pip install selenium webdriver-manager

2. Запустите скрипт:
   python scrape_vk_leads_v2.py

3. Смотрите результаты в файле:
   leads.csv

Опции запуска:
   python scrape_vk_leads_v2.py --headless           # Скрыть браузер
   python scrape_vk_leads_v2.py --max-results 50     # Собрать 50 профилей на запрос
   python scrape_vk_leads_v2.py --delay 3            # Задержка 3 сек между действиями

ВАЖНО:
- Собирайте только ПУБЛИЧНЫЕ данные
- Обрабатывайте персональные данные согласно законодательству
- ВКонтакте может блокировать скрепер за частые запросы
- Используйте случайные задержки между запросами
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Поисковые запросы
KEYWORDS = [
    "Недвижимость Москва",
    "Новостройки Москва",
    "ЖК Москва",
]
OUTPUT_FILE = "leads.csv"

# Регулярное выражение для поиска телефонов
PHONE_PATTERN = re.compile(
    r"(\+7[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}|"
    r"8[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2})"
)


@dataclass
class Lead:
    """Модель одного профиля."""
    name: str
    profile_url: str
    profile_id: str
    nickname: str
    phone: str
    keyword: str


def build_driver(headless: bool) -> webdriver.Chrome:
    """
    Создает и настраивает Chrome WebDriver.
    
    Args:
        headless: Запускать ли браузер без графического окна
    
    Returns:
        Готовый к использованию WebDriver
    """
    options = Options()
    
    # Используем новый headless режим для Chrome
    if headless:
        options.add_argument("--headless=new")
    
    # Отключаем GPU для стабильности
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-default-apps")
    
    # Размер окна браузера
    options.add_argument("--window-size=1920,1080")
    
    # Язык интерфейса
    options.add_argument("--lang=ru-RU")
    
    # Отключаем песочницу (sandbox) для лучшей совместимости
    options.add_argument("--no-sandbox")
    
    # Другие полезные опции
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-web-resources")
    
    # User-Agent для выглядения как обычный браузер
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Ограничиваем время ожидания для элементов
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    
    return driver


def extract_phone(text: str) -> str:
    """
    Ищет телефонный номер в тексте.
    
    Args:
        text: Текст для поиска
    
    Returns:
        Найденный номер или пустая строка
    """
    if not text:
        return ""
    
    match = PHONE_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def extract_profile_url(element) -> Optional[str]:
    """
    Извлекает URL профиля из элемента.
    
    Args:
        element: DOM-элемент
    
    Returns:
        URL профиля или None
    """
    try:
        # Ищем ссылку на профиль
        href = element.get_attribute("href")
        if href and ("vk.com" in href or href.startswith("/")):
            return href
    except StaleElementReferenceException:
        return None
    except Exception:
        return None
    
    return None


def normalize_vk_profile(url: str) -> tuple[str, str]:
    """
    Нормализует URL профиля ВКонтакте и извлекает ID/никнейм.
    
    Args:
        url: URL профиля
    
    Returns:
        Кортеж (ID/nikname, никнейм)
    """
    # Убираем параметры и якоря
    url = url.split("?")[0].split("#")[0].rstrip("/")
    
    if not url:
        return "", ""
    
    # Добавляем базовый URL если относительная ссылка
    if url.startswith("/"):
        url = f"https://vk.com{url}"
    
    # Извлекаем ID/никнейм из конца URL
    parts = url.split("/")
    if not parts:
        return "", ""
    
    handle = parts[-1].strip()
    
    # Удаляем query параметры из handle
    handle = handle.split("?")[0]
    
    if not handle or handle in ("id", "vk.com", ""):
        return "", ""
    
    return handle, handle


def collect_vk_profiles(
    driver: webdriver.Chrome,
    query: str,
    max_results: int = 50,
    delay: float = 2.0,
    debug: bool = True,
) -> List[Lead]:
    """
    Собирает профили пользователей из поиска ВКонтакте.
    
    Args:
        driver: WebDriver для управления браузером
        query: Поисковый запрос
        max_results: Максимум профилей для сбора
        delay: Задержка между запросами (секунды)
        debug: Печатать ли отладочные сообщения
    
    Returns:
        Список найденных профилей
    """
    if debug:
        print(f"\n[DEBUG] Начинаем поиск по запросу: '{query}'")
    
    # Формируем URL для поиска людей в ВКонтакте
    # Параметр c[section]=people ограничивает поиск только профилями
    encoded_query = quote_plus(query)
    url = f"https://vk.com/search?c%5Bq%5D={encoded_query}&c%5Bsection%5D=people"
    
    try:
        # Переходим на страницу поиска
        if debug:
            print(f"[DEBUG] Открываем URL: {url}")
        driver.get(url)
        
        # Ждем загрузки основного содержимого (5 сек)
        time.sleep(5)
        
        # Прокручиваем страницу для подгрузки новых результатов
        if debug:
            print("[DEBUG] Прокручиваем страницу для загрузки результатов...")
        
        for scroll_num in range(5):
            # Скроллим до конца страницы
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(delay)
            
            if debug and scroll_num % 2 == 0:
                print(f"[DEBUG] Прокрутка {scroll_num + 1}/5")
        
        # Ищем карточки результатов поиска
        # Используем несколько селекторов для совместимости с разными версиями ВК
        profile_selectors = [
            "a.search_item__link",           # Новые версии ВК
            "a.service_msg_link",            # Старые версии
            ".people_item a",                # Альтернативный селектор
            "a[href*='/id']",                # Любые ссылки с /id
            "a[href*='/']",                  # Любые внутренние ссылки
        ]
        
        found_elements = []
        for selector in profile_selectors:
            try:
                found_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if found_elements:
                    if debug:
                        print(f"[DEBUG] Найден селектор '{selector}': {len(found_elements)} элементов")
                    break
            except NoSuchElementException:
                continue
        
        if debug:
            print(f"[DEBUG] Всего элементов найдено: {len(found_elements)}")
        
        # Если элементы не найдены, выводим содержимое страницы для отладки
        if not found_elements:
            if debug:
                page_source = driver.page_source[:1000]
                print(f"[DEBUG] HTML страницы (первые 1000 символов):\n{page_source}")
        
        leads: List[Lead] = []
        seen_urls = set()
        
        # Обрабатываем найденные элементы
        for idx, element in enumerate(found_elements):
            try:
                # Извлекаем URL профиля
                profile_url = extract_profile_url(element)
                
                if not profile_url:
                    if debug and idx < 3:
                        print(f"[DEBUG] Элемент {idx}: URL не найден")
                    continue
                
                # Проверяем, не дублирующий ли это профиль
                if profile_url in seen_urls:
                    if debug and idx < 3:
                        print(f"[DEBUG] Элемент {idx}: дублирующий профиль {profile_url}")
                    continue
                
                seen_urls.add(profile_url)
                
                # Извлекаем имя
                try:
                    name = element.text.strip()
                except:
                    name = ""
                
                if not name:
                    if debug and idx < 3:
                        print(f"[DEBUG] Элемент {idx}: имя не найдено")
                    continue
                
                # Нормализуем URL и извлекаем ID/никнейм
                profile_id, nickname = normalize_vk_profile(profile_url)
                
                if not profile_id:
                    if debug and idx < 3:
                        print(f"[DEBUG] Элемент {idx}: ID не извлечен из {profile_url}")
                    continue
                
                # Попытаемся извлечь телефон из текста элемента
                # (в большинстве случаев телефон недоступен без авторизации)
                try:
                    element_text = element.text
                    phone = extract_phone(element_text)
                except:
                    phone = ""
                
                # Создаем объект Lead
                lead = Lead(
                    name=name,
                    profile_url=profile_url,
                    profile_id=profile_id,
                    nickname=nickname,
                    phone=phone,
                    keyword=query,
                )
                
                leads.append(lead)
                
                if debug and idx < 5:
                    print(f"[DEBUG] Профиль {idx}: {name} ({profile_id})")
                
                # Проверяем, достаточно ли собрали профилей
                if len(leads) >= max_results:
                    break
            
            except StaleElementReferenceException:
                # Элемент больше не в DOM, пропускаем
                if debug:
                    print(f"[DEBUG] Элемент {idx}: stale element, пропускаем")
                continue
            
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Ошибка при обработке элемента {idx}: {e}")
                continue
        
        if debug:
            print(f"[DEBUG] Собрано профилей: {len(leads)} из {max_results}")
        
        return leads
    
    except TimeoutException:
        print(f"[ERROR] Timeout при загрузке страницы: {query}")
        return []
    
    except Exception as e:
        print(f"[ERROR] Ошибка при сборе данных по '{query}': {e}")
        return []


def save_to_csv(leads: List[Lead], filename: str) -> None:
    """
    Сохраняет профили в CSV файл.
    
    Args:
        leads: Список профилей
        filename: Имя файла для сохранения
    """
    with open(filename, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile, delimiter=",")
        
        # Заголовки
        writer.writerow(["Имя", "URL профиля", "ID/Никнейм", "Никнейм", "Телефон", "Поисковый запрос"])
        
        # Данные
        for lead in leads:
            writer.writerow([
                lead.name,
                lead.profile_url,
                lead.profile_id,
                lead.nickname,
                lead.phone,
                lead.keyword,
            ])
    
    print(f"\n✓ Результаты сохранены в файл: {filename}")


def parse_args() -> argparse.Namespace:
    """Парсит аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Сбор публичных профилей ВКонтакте по поисковым запросам о недвижимости.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python scrape_vk_leads_v2.py                          # Основной запуск
  python scrape_vk_leads_v2.py --headless               # Скрыть браузер
  python scrape_vk_leads_v2.py --max-results 30         # Собрать 30 профилей на запрос
  python scrape_vk_leads_v2.py --delay 3                # Задержка 3 сек между действиями
  python scrape_vk_leads_v2.py --output results.csv     # Сохранить в другой файл
        """
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запустить браузер в headless-режиме (без графического окна)",
    )
    
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Максимальное количество профилей для каждого поискового запроса (по умолчанию: 50)",
    )
    
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Задержка между запросами в секундах (по умолчанию: 2.0)",
    )
    
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help=f"Имя выходного CSV файла (по умолчанию: {OUTPUT_FILE})",
    )
    
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Отключить отладочные сообщения",
    )
    
    return parser.parse_args()


def main() -> None:
    """Главная функция скрипта."""
    args = parse_args()
    
    print("=" * 60)
    print("  Сбор публичных профилей ВКонтакте")
    print("=" * 60)
    print(f"Поисковые запросы: {', '.join(KEYWORDS)}")
    print(f"Макс. профилей на запрос: {args.max_results}")
    print(f"Задержка между действиями: {args.delay} сек")
    print(f"Файл результатов: {args.output}")
    print("=" * 60)
    
    # Создаем WebDriver
    driver = build_driver(headless=args.headless)
    
    try:
        all_leads: List[Lead] = []
        
        # Проходим по каждому поисковому запросу
        for i, keyword in enumerate(KEYWORDS, 1):
            print(f"\n[{i}/{len(KEYWORDS)}] Обработка запроса: '{keyword}'")
            
            # Собираем профили
            leads = collect_vk_profiles(
                driver,
                keyword,
                max_results=args.max_results,
                delay=args.delay,
                debug=not args.no_debug,
            )
            
            print(f"  → Собрано: {len(leads)} профилей")
            all_leads.extend(leads)
            
            # Ждем перед следующим запросом (чтобы не блокировали)
            if i < len(KEYWORDS):
                wait_time = args.delay + random.uniform(1, 3)
                print(f"  → Ожидание {wait_time:.1f} сек перед следующим запросом...")
                time.sleep(wait_time)
        
        # Сохраняем результаты
        print(f"\n{'-' * 60}")
        print(f"Всего собрано профилей: {len(all_leads)}")
        save_to_csv(all_leads, args.output)
        
    finally:
        # Закрываем браузер
        driver.quit()
        print("Браузер закрыт.")


if __name__ == "__main__":
    main()
