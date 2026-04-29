import requests
import csv
import re
import time

# --- НАСТРОЙКИ ---
# Ваш токен (я очистил его от лишних символов, которые попали в код при прошлой попытке)
VK_TOKEN = 'vk1.a.uususfm1STBJw-7cF2KstHAYd3QoutG257oqewhtNIiBLK8PztU4j-PpWF3IHCpew5IFJN0SkGnNk_qrKB1j8Jwz4gPVaQGW-Q5rd0fE6904_73y8YGgZBFpPIqQP9J3XnQq6lQwcsvuIpmPcfqfAMmWo4MbjR1hcRE6t2y_96vM4aRjRqWn8dg8j2A0OCokWO-2z1EJRAwlf0JDKe7M0A' 
API_VERSION = '5.131'

# РАСШИРЕННЫЙ список ключевых слов (чтобы найти больше людей)
KEYWORDS = [
    'куплю', 'цена', 'сколько стоит', 'за сколько', 'интересует', 
    'хочу купить', 'варианты', 'подбор', 'ипотека', 'сдача', 
    'новостройка', 'жк', 'квартира', 'дом', 'сдан', 'бронь'
]

# Сообщества для поиска
COMMUNITIES = ['nedvizhimost_moscow_piter', 'novostroyki_moskva_spb', 'zhk_moskvy']

def get_group_id(screen_name):
    url = "https://api.vk.com/method/utils.resolveScreenName"
    params = {'access_token': VK_TOKEN, 'v': API_VERSION, 'screen_name': screen_name}
    try:
        res = requests.get(url, params=params).json()
        if 'response' in res and res['response']['type'] == 'group':
            return res['response']['object_id']
        if 'error' in res:
            print(f"Ошибка API (resolveScreenName): {res['error']['error_msg']}")
    except Exception as e:
        print(f"Ошибка сети: {e}")
    return None

def get_posts(owner_id, count=30): # Увеличил количество постов
    url = "https://api.vk.com/method/wall.get"
    params = {'access_token': VK_TOKEN, 'v': API_VERSION, 'owner_id': -owner_id, 'count': count}
    try:
        res = requests.get(url, params=params).json()
        if 'error' in res:
            print(f"Ошибка API (wall.get): {res['error']['error_msg']}")
            return []
        return res.get('response', {}).get('items', [])
    except Exception as e:
        print(f"Ошибка сети: {e}")
        return []

def get_comments(owner_id, post_id):
    url = "https://api.vk.com/method/wall.getComments"
    params = {
        'access_token': VK_TOKEN, 
        'v': API_VERSION, 
        'owner_id': -owner_id, 
        'post_id': post_id, 
        'count': 100, 
        'extended': 1
    }
    try:
        res = requests.get(url, params=params).json()
        return res.get('response', {})
    except Exception as e:
        return {}

def extract_phone(text):
    phone_pattern = r'(\+7|8|7)[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}'
    match = re.search(phone_pattern, text)
    return match.group(0) if match else "Не указан"

def main():
    if 'ВАШ_ТОКЕН' in VK_TOKEN:
        print("ОШИБКА: Токен не найден.")
        return

    leads = []
    print(f"Начинаю сбор данных по {len(COMMUNITIES)} сообществам...")

    for community in COMMUNITIES:
        print(f"--- Проверка: {community} ---")
        group_id = get_group_id(community)
        if not group_id: continue

        posts = get_posts(group_id)
        print(f"Найдено {len(posts)} постов. Проверяю комментарии...")

        for post in posts:
            comments_data = get_comments(group_id, post['id'])
            items = comments_data.get('items', [])
            profiles = {p['id']: f"{p.get('first_name', '')} {p.get('last_name', '')}" for p in comments_data.get('profiles', [])}

            for comment in items:
                text = comment.get('text', '').lower()
                user_id = comment.get('from_id', 0)

                if any(word in text for word in KEYWORDS) and user_id > 0:
                    name = profiles.get(user_id, f"ID {user_id}")
                    phone = extract_phone(text)
                    leads.append({
                        'Name': name,
                        'ID': f"https://vk.com/id{user_id}",
                        'Phone': phone,
                        'Comment': text.replace('\n', ' ')
                    })
            time.sleep(0.35)

    if leads:
        with open('leads.csv', 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['Name', 'ID', 'Phone', 'Comment'])
            writer.writeheader()
            writer.writerows(leads)
        print(f"\nУСПЕХ! Найдено лидов: {len(leads)}")
        print("Данные сохранены в leads.csv")
    else:
        print("\nЗавершено. По указанным ключевым словам в последних комментариях ничего не найдено.")
    
    print("\n" + "="*30)
    input("Нажмите Enter, чтобы закрыть окно...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: {e}")
        input("Нажмите Enter, чтобы закрыть...")
