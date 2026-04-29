"""
АЛЬТЕРНАТИВНЫЙ скрипт для сбора лидов с использованием Requests.

ОТЛИЧИЕ ОТ SELENIUM ВЕРСИИ:
- Requests работает с HTTP-запросами напрямую (без браузера)
- Быстрее, но требует анализа API сайтов
- Для Яндекс.Карт требуется обратный инжиниринг API (сложнее)

ЭТА ВЕРСИЯ использует упрощенный подход через веб-скрейпинг HTML.

УСТАНОВКА:
  pip install requests beautifulsoup4

ЗАПУСК:
  python scrape_with_requests.py
"""

import requests
from bs4 import BeautifulSoup
import csv
import time
import logging
from typing import List, Dict
from dataclasses import dataclass
from urllib.parse import quote_plus

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SEARCH_QUERIES = [
    "Недвижимость Москва",
    "Новостройки Москва",
    "ЖК Москва",
]

OUTPUT_FILE = "leads.csv"

# User Agent для избежания блокировки
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# ============================================================
# МОДЕЛЬ ДАННЫХ
# ============================================================

@dataclass
class CompanyLead:
    """Данные о компании"""
    name: str
    phone: str
    address: str = ""
    website: str = ""
    search_query: str = ""


# ============================================================
# ФУНКЦИИ ПОИСКА
# ============================================================

def search_2gis(query: str, limit: int = 20) -> List[CompanyLead]:
    """
    Поиск компаний в 2ГИС через публичный API.
    
    2ГИС имеет более открытый API для поиска.
    
    Args:
        query: Поисковый запрос
        limit: Количество результатов
    
    Returns:
        Список найденных компаний
    """
    leads = []
    
    try:
        # URL для поиска в 2ГИС
        # 2GIS API требует city_id (Москва = 1)
        url = "https://api.2gis.com/search"
        
        params = {
            'text': query,
            'city_id': 1,  # Москва
            'limit': limit,
            'api_key': 'rj575894b9c3a26aff6be87b5f',  # Публичный API ключ (может быть изменен)
        }
        
        logger.info(f"Выполняется поиск в 2ГИС: {query}")
        
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Проверяем результаты
        if 'result' not in data or 'items' not in data['result']:
            logger.warning("Нет результатов в 2ГИС")
            return leads
        
        for item in data['result']['items']:
            try:
                name = item.get('name', 'N/A')
                phone = ''
                address = item.get('address', '')
                website = ''
                
                # Ищем телефон в контактах
                if 'contact' in item:
                    for contact in item['contact']:
                        if contact.get('type') == 'phone':
                            phone = contact.get('value', '')
                            break
                
                if phone:  # Добавляем только если есть телефон
                    lead = CompanyLead(
                        name=name,
                        phone=phone,
                        address=address,
                        website=website,
                        search_query=query
                    )
                    leads.append(lead)
                    logger.info(f"✓ Найдена компания: {name}")
            
            except Exception as e:
                logger.warning(f"Ошибка парсинга результата: {e}")
                continue
        
        return leads
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к 2ГИС: {e}")
        return leads
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return leads


def search_google_maps_html(query: str) -> List[CompanyLead]:
    """
    Попытка извлечения данных из поисковых результатов Google.
    
    Примечание: Google активно блокирует автоматические запросы.
    Используйте только для образовательных целей или используйте платный API.
    
    Args:
        query: Поисковый запрос
    
    Returns:
        Список найденных компаний (вероятно пусто из-за блокировки)
    """
    leads = []
    
    try:
        # Поиск через Google локальные результаты
        search_query = f"{query} контакты телефон"
        url = "https://www.google.com/search"
        
        params = {
            'q': search_query,
            'gl': 'ru'
        }
        
        logger.warning("⚠️  Google.com часто блокирует автоматические запросы.")
        logger.warning("   Для надежного сбора используйте Selenium версию (scrape_real_estate_leads.py)")
        
        # Этот метод часто не работает
        # response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        # logger.warning("Google.com требует авторизации и часто блокирует скрейперы")
        
        return leads
    
    except Exception as e:
        logger.error(f"Ошибка при поиске в Google: {e}")
        return leads


def fetch_company_details(company_data: Dict) -> CompanyLead:
    """
    Извлекает детальную информацию о компании.
    
    Args:
        company_data: Данные компании из API
    
    Returns:
        Объект CompanyLead
    """
    return CompanyLead(
        name=company_data.get('name', 'N/A'),
        phone=company_data.get('phone', ''),
        address=company_data.get('address', ''),
        website=company_data.get('website', ''),
        search_query=company_data.get('source', '')
    )


# ============================================================
# СОХРАНЕНИЕ ДАННЫХ
# ============================================================

def save_leads_to_csv(leads: List[CompanyLead], filename: str = OUTPUT_FILE) -> None:
    """
    Сохраняет лиды в CSV файл.
    
    Args:
        leads: Список лидов
        filename: Имя файла
    """
    if not leads:
        logger.warning("Нет данных для сохранения")
        return
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Компания', 'Телефон', 'Адрес', 'Сайт', 'Поисковый запрос']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for lead in leads:
                writer.writerow({
                    'Компания': lead.name,
                    'Телефон': lead.phone,
                    'Адрес': lead.address,
                    'Сайт': lead.website,
                    'Поисковый запрос': lead.search_query,
                })
        
        logger.info(f"\n✓ Данные сохранены в {filename}")
        logger.info(f"  Всего записей: {len(leads)}")
    
    except Exception as e:
        logger.error(f"Ошибка при сохранении CSV: {e}")


def print_summary(leads: List[CompanyLead]) -> None:
    """Выводит сводку собранных данных"""
    if not leads:
        print("\nНет данных для вывода")
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
    print(f"ИТОГО: {len(leads)} записей")
    print(f"{'='*80}\n")


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================

def scrape_leads_requests() -> None:
    """
    Главная функция сбора лидов через Requests.
    """
    all_leads = []
    unique_leads = {}  # Дедупликация
    
    logger.info("🚀 Запуск сбора лидов (Requests версия)")
    logger.info("="*60)
    
    for query in SEARCH_QUERIES:
        logger.info(f"\nПоиск по: '{query}'")
        
        # Поиск в 2ГИС
        try:
            leads = search_2gis(query, limit=20)
            
            for lead in leads:
                key = f"{lead.name}_{lead.phone}"
                if key not in unique_leads:
                    unique_leads[key] = lead
                    all_leads.append(lead)
            
            logger.info(f"Получено {len(leads)} результатов")
        
        except Exception as e:
            logger.error(f"Ошибка: {e}")
        
        # Пауза между запросами
        time.sleep(2)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"ИТОГО СОБРАНО: {len(all_leads)} уникальных лидов")
    logger.info(f"{'='*60}")
    
    # Сохраняем результаты
    save_leads_to_csv(all_leads)
    
    # Выводим сводку
    print_summary(all_leads)


# ============================================================
# ТОЧКА ВХОДА
# ============================================================

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║  СБОР ЛИДОВ - Requests версия                              ║
║  (Альтернатива Selenium)                                   ║
╚════════════════════════════════════════════════════════════╝

ПРИМЕЧАНИЕ:
  • Requests работает быстрее, но требует публичных API
  • Для Яндекс.Карт используйте Selenium версию
  • Текущая версия использует 2ГИС API

УСТАНОВКА ЗАВИСИМОСТЕЙ:
  pip install requests beautifulsoup4

ЗАПУСК:
  python scrape_with_requests.py
    """)
    
    try:
        scrape_leads_requests()
        logger.info("✓ Скрипт завершил работу успешно!")
    except KeyboardInterrupt:
        logger.warning("Скрипт прерван пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
