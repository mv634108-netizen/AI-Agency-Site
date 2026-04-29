import csv
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- НАСТРОЙКИ ---
# Список профилей Instagram для анализа (без @)
TARGET_PROFILES = [
    'apartments_moscow', 
    'novostroyki_moskvy', 
    'realestate_moscow'
]

# Ключевые слова для поиска лидов
KEYWORDS = ['+', 'хочу', 'куплю', 'интересуюсь', 'какой жк', 'жк', 'сколько стоит', 'цена', 'стоимость']

# Настройки поиска телефонов
PHONE_PATTERN = r'(\+7|8|7)[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}'

def extract_phone(text):
    match = re.search(PHONE_PATTERN, text)
    return match.group(0) if match else "Не указан"

def main():
    # Инициализация драйвера (Chrome)
    # Убедитесь, что у вас установлен Google Chrome
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # Можно включить после отладки
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument("--disable-notifications")
    
    driver = webdriver.Chrome(options=options)
    
    leads = []

    try:
        # 1. Сначала нужно залогиниться вручную или через код
        driver.get("https://www.instagram.com/")
        print("ПОЖАЛУЙСТА, ВОЙДИТЕ В СВОЙ АККАУНТ ИНСТАГРАМ В ОТКРЫТОМ ОКНЕ.")
        print("У вас есть 60 секунд на авторизацию...")
        time.sleep(60) # Даем время на ручной вход
        
        for profile in TARGET_PROFILES:
            print(f"Обработка профиля: {profile}...")
            driver.get(f"https://www.instagram.com/{profile}/")
            time.sleep(5)
            
            # Собираем ссылки на последние посты (из сетки)
            posts = driver.find_elements(By.TAG_NAME, 'a')
            post_links = []
            for post in posts:
                href = post.get_attribute('href')
                if href and '/p/' in href:
                    post_links.append(href)
            
            # Берем первые 5 постов для примера
            for link in post_links[:5]:
                print(f"  Проверка поста: {link}")
                driver.get(link)
                time.sleep(3)
                
                # Пытаемся раскрыть комментарии (если есть кнопка "Загрузить еще")
                try:
                    for _ in range(3): # Кликаем несколько раз "загрузить еще"
                        load_more_btn = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Load more comments') or contains(@aria-label, 'Еще')]")
                        load_more_btn.click()
                        time.sleep(2)
                except:
                    pass

                # Собираем блоки комментариев
                comment_elements = driver.find_elements(By.XPATH, "//ul[contains(@class, 'Gy9S8')] | //div[contains(@role, 'menuitem')]")
                
                # В разных версиях Instagram классы отличаются, поэтому пробуем более общие селекторы
                if not comment_elements:
                    comment_elements = driver.find_elements(By.TAG_NAME, 'li')

                for comment_el in comment_elements:
                    try:
                        text = comment_el.text.lower()
                        if any(word in text for word in KEYWORDS):
                            # Извлекаем автора (обычно первое слово или отдельный тег a)
                            author_el = comment_el.find_element(By.TAG_NAME, 'a')
                            username = author_el.text
                            user_id_link = author_el.get_attribute('href')
                            
                            phone = extract_phone(text)
                            
                            leads.append({
                                'Name': username,
                                'ID': user_id_link,
                                'Phone': phone,
                                'Comment': text.replace('\n', ' ')
                            })
                            print(f"    [НАЙДЕН ЛИД]: {username}")
                    except:
                        continue
                
    except Exception as e:
        print(f"Произошла ошибка: {e}")
    finally:
        # Сохранение результатов
        if leads:
            with open('leads_insta.csv', 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['Name', 'ID', 'Phone', 'Comment'])
                writer.writeheader()
                writer.writerows(leads)
            print(f"Сбор завершен. Найдено {len(leads)} лидов. Результат в leads_insta.csv")
        else:
            print("Лидов не найдено.")
        
        driver.quit()

if __name__ == "__main__":
    main()

# --- ИНСТРУКЦИЯ ---
# 1. Установите selenium: pip install selenium
# 2. Убедитесь, что у вас есть Chrome. Драйвер скачается автоматически в новых версиях Selenium.
# 3. Запустите скрипт: python instagram_real_estate_scraper.py
# 4. В открывшемся окне браузера войдите в Instagram (у вас будет 60 секунд).
