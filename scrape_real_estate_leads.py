"""
Скрипт для сбора контактов застройщиков и агентств недвижимости из Яндекс.Карт.

Что собираем:
1) Название компании (застройщик, агентство)
2) Телефон
3) Адрес (бонус)

Поисковые запросы по умолчанию:
- "Недвижимость Москва"
- "Новостройки Москва"
- "ЖК Москва"

============================================================
УСТАНОВКА И ЗАПУСК
============================================================

1. Установите Python 3.8+:
   https://www.python.org/downloads/

2. Установите зависимости в терминале:
   pip install selenium webdriver-manager

3. Запустите скрипт:
   python scrape_real_estate_leads.py

4. Результаты будут сохранены в файл:
   leads.csv

ДОПОЛНИТЕЛЬНЫЕ ПАРАМЕТРЫ:
   python scrape_real_estate_leads.py --max-results 50 --headless

Параметры:
  --max-results    Максимальное количество результатов (по умолчанию 30)
  --headless       Запустить браузер без графического интерфейса (быстрее)

ПРИМЕЧАНИЯ:
- Скрипт работает с Яндекс.Картами, которые требуют JavaScript
- Перед использованием проверьте Terms of Service сайта
- Соблюдайте законы о защите персональных данных (GDPR, ФЗ РФ)
- Используйте паузы между запросами, чтобы не перегружать сервер

ВЫВОД:
После запуска в консоли вы увидите:
- Статус скрейпинга (скачано X компаний)
- Список собранных компаний
- Сообщение об успешном сохранении в CSV
"""

from __future__ import annotations

import argparse
import csv
import time
import logging
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

# Поисковые запросы для сбора данных
SEARCH_QUERIES = [
    "Недвижимость Москва",
    "Новостройки Москва",
    "ЖК Москва",
    "Застройщики Москва",
    "Агентства недвижимости Москва",
]

# Файл для сохранения результатов
OUTPUT_FILE = "leads.csv"

# Задержка между запросами (в секундах) - соблюдаем вежливый скрейпинг
DELAY_BETWEEN_REQUESTS = 2

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# МОДЕЛЬ ДАННЫХ
# ============================================================

@dataclass
class Lead:
    """Класс для хранения информации о лиде (компании)"""
    name: str
    phone: str
    address: str = ""
    website: str = ""
    search_query: str = ""

    def to_dict(self) -> dict:
        """Преобразование в словарь для сохранения в CSV"""
        return {
            'Компания': self.name,
            'Телефон': self.phone,
            'Адрес': self.address,
            'Сайт': self.website,
            'Поисковый запрос': self.search_query,
        }

# ============================================================
# ОСНОВНОЙ ФУНКЦИОНАЛ
# ============================================================

def get_chrome_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Инициализирует и возвращает Chrome WebDriver.
    
    Args:
        headless: Если True, браузер запустится без UI (быстрее)
    
    Returns:
        Объект Chrome WebDriver
    """
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless")
    
    # Отключаем уведомления
    chrome_options.add_argument("--disable-notifications")
    # Игнорируем ошибки сертификатов
    chrome_options.add_argument("--ignore-certificate-errors")
    # User Agent (чтобы сайт не подумал, что это бот)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    # Инициализируем драйвер (автоматически скачивает нужную версию Chrome)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver


def extract_leads_from_page(driver: webdriver.Chrome, query: str, max_leads: int) -> List[Lead]:
    """
    Извлекает данные компаний со страницы Яндекс.Карт.
    
    Args:
        driver: WebDriver объект
        query: Поисковый запрос
        max_leads: Максимальное количество лидов для извлечения
    
    Returns:
        Список объектов Lead
    """
    leads = []
    
    try:
        # Ждем загрузки результатов поиска (до 10 секунд)
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "sidebar-tabs__pane"))
        )
        
        # Небольшая пауза для полной загрузки страницы
        time.sleep(2)
        
        # Ищем карточки организаций
        # ПРИМЕЧАНИЕ: Селекторы могут меняться при обновлении сайта Яндекс.Карт
        org_cards = driver.find_elements(By.CLASS_NAME, "org-snippets__item")
        
        logger.info(f"Найдено {len(org_cards)} организаций на странице")
        
        for idx, card in enumerate(org_cards[:max_leads]):
            try:
                # Пропускаем, если элемент уже не в DOM (Stale Element)
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                time.sleep(0.5)
                
                # Кликаем на карточку для загрузки подробной информации
                try:
                    card.click()
                except StaleElementReferenceException:
                    # Перезагружаем элемент, если он устарел
                    org_cards = driver.find_elements(By.CLASS_NAME, "org-snippets__item")
                    card = org_cards[idx]
                    card.click()
                
                time.sleep(1)
                
                # Извлекаем информацию из карточки организации
                lead = extract_company_info(driver, query)
                
                if lead:
                    leads.append(lead)
                    logger.info(f"[{idx + 1}] Добавлена компания: {lead.name}")
                
                # Небольшая пауза для вежливого скрейпинга
                time.sleep(DELAY_BETWEEN_REQUESTS)
                
            except Exception as e:
                logger.warning(f"Ошибка при обработке карточки #{idx + 1}: {e}")
                continue
        
    except TimeoutException:
        logger.error("Превышено время ожидания загрузки результатов поиска")
    except Exception as e:
        logger.error(f"Ошибка при извлечении лидов со страницы: {e}")
    
    return leads


def extract_company_info(driver: webdriver.Chrome, query: str) -> Optional[Lead]:
    """
    Извлекает информацию о компании из панели деталей.
    
    Args:
        driver: WebDriver объект
        query: Поисковый запрос (для отслеживания источника)
    
    Returns:
        Объект Lead с информацией о компании или None
    """
    try:
        # Ищем название компании
        name = extract_text_safely(
            driver,
            By.CLASS_NAME,
            "card__title"
        )
        
        if not name:
            return None
        
        # Ищем телефон
        phone = extract_text_safely(
            driver,
            By.CLASS_NAME,
            "card__phone-number"
        )
        
        # Ищем адрес
        address = extract_text_safely(
            driver,
            By.CLASS_NAME,
            "card__address"
        )
        
        # Ищем сайт
        website = extract_text_safely(
            driver,
            By.CLASS_NAME,
            "card__website"
        )
        
        return Lead(
            name=name,
            phone=phone,
            address=address,
            website=website,
            search_query=query
        )
        
    except Exception as e:
        logger.warning(f"Ошибка при извлечении информации о компании: {e}")
        return None


def extract_text_safely(
    driver: webdriver.Chrome,
    by: By,
    value: str,
    parent=None
) -> str:
    """
    Безопасно извлекает текст из элемента (не вызывает ошибку, если элемент не найден).
    
    Args:
        driver: WebDriver объект
        by: Тип селектора (By.CLASS_NAME, By.ID, и т.д.)
        value: Значение селектора
        parent: Родительский элемент для поиска (опционально)
    
    Returns:
        Текст элемента или пустая строка
    """
    try:
        search_context = parent if parent else driver
        element = search_context.find_element(by, value)
        return element.text.strip() if element.text else ""
    except NoSuchElementException:
        return ""
    except Exception as e:
        logger.debug(f"Ошибка при извлечении текста: {e}")
        return ""


def scrape_real_estate_leads(max_results: int = 30, headless: bool = False) -> List[Lead]:
    """
    Главная функция для сбора лидов по недвижимости.
    
    Args:
        max_results: Максимальное количество результатов на поисковый запрос
        headless: Запустить браузер в режиме без UI
    
    Returns:
        Список всех собранных лидов
    """
    driver = None
    all_leads = []
    unique_leads = {}  # Для дедупликации (по названию + телефону)
    
    try:
        logger.info("Инициализация браузера...")
        driver = get_chrome_driver(headless=headless)
        
        for query in SEARCH_QUERIES:
            logger.info(f"\n{'='*60}")
            logger.info(f"Поиск по запросу: '{query}'")
            logger.info(f"{'='*60}")
            
            try:
                # Формируем URL для поиска на Яндекс.Картах
                # Закодируем запрос в URL
                search_url = f"https://yandex.ru/maps/?text={quote_plus(query)}&sll=37.6173,55.7558&sspn=10.00,10.00"
                
                logger.info(f"Переходим на: {search_url}")
                driver.get(search_url)
                
                # Ждем загрузки карты (до 15 секунд)
                time.sleep(5)
                
                # Собираем лиды со страницы
                query_leads = extract_leads_from_page(driver, query, max_results)
                
                # Добавляем в список (с дедупликацией)
                for lead in query_leads:
                    # Используем комбинацию имени и телефона как уникальный ключ
                    key = f"{lead.name}_{lead.phone}"
                    if key not in unique_leads:
                        unique_leads[key] = lead
                        all_leads.append(lead)
                
                logger.info(f"Собрано {len(query_leads)} лидов по этому запросу")
                
                # Пауза между поисковыми запросами
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке запроса '{query}': {e}")
                continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"ИТОГО СОБРАНО: {len(all_leads)} уникальных лидов")
        logger.info(f"{'='*60}")
        
        return all_leads
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return all_leads
    
    finally:
        # Обязательно закрываем браузер
        if driver:
            logger.info("Закрытие браузера...")
            driver.quit()


def save_leads_to_csv(leads: List[Lead], filename: str = OUTPUT_FILE) -> None:
    """
    Сохраняет список лидов в CSV файл.
    
    Args:
        leads: Список объектов Lead
        filename: Имя файла для сохранения
    """
    if not leads:
        logger.warning("Нет лидов для сохранения")
        return
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Компания', 'Телефон', 'Адрес', 'Сайт', 'Поисковый запрос']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Записываем заголовок
            writer.writeheader()
            
            # Записываем данные
            for lead in leads:
                writer.writerow(lead.to_dict())
        
        logger.info(f"\n✓ Результаты успешно сохранены в файл: {filename}")
        logger.info(f"  Всего записей: {len(leads)}")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении в CSV: {e}")


def print_summary(leads: List[Lead]) -> None:
    """Печатает сводку собранных данных"""
    if not leads:
        print("\nНет собранных данных для вывода")
        return
    
    print(f"\n{'='*80}")
    print("СОБРАННЫЕ ДАННЫЕ:")
    print(f"{'='*80}")
    
    for idx, lead in enumerate(leads, 1):
        print(f"\n[{idx}] {lead.name}")
        print(f"    Телефон: {lead.phone}")
        if lead.address:
            print(f"    Адрес: {lead.address}")
        if lead.website:
            print(f"    Сайт: {lead.website}")
        print(f"    Источник: {lead.search_query}")
    
    print(f"\n{'='*80}")
    print(f"ИТОГО: {len(leads)} компаний")
    print(f"{'='*80}\n")


# ============================================================
# ТОЧКА ВХОДА
# ============================================================

if __name__ == "__main__":
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(
        description="Сбор контактов недвижимости из Яндекс.Карт",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python scrape_real_estate_leads.py
  python scrape_real_estate_leads.py --max-results 50
  python scrape_real_estate_leads.py --headless --max-results 100
        """
    )
    
    parser.add_argument(
        '--max-results',
        type=int,
        default=30,
        help='Максимальное количество результатов на поисковый запрос (по умолчанию: 30)'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Запустить браузер без UI (быстрее, но можно не видеть процесс)'
    )
    
    args = parser.parse_args()
    
    # Запускаем сбор данных
    logger.info("🚀 Начало сбора лидов по недвижимости Москвы")
    logger.info(f"Параметры: max_results={args.max_results}, headless={args.headless}")
    
    leads = scrape_real_estate_leads(
        max_results=args.max_results,
        headless=args.headless
    )
    
    # Сохраняем результаты
    save_leads_to_csv(leads)
    
    # Выводим сводку
    print_summary(leads)
    
    logger.info("✓ Скрипт завершил работу успешно!")
