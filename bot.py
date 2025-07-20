import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, ChatJoinRequest
import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import threading
import time
import sqlite3
from datetime import datetime, timedelta
import random
from pyCryptoPayAPI import pyCryptoPayAPI
from db import add_user, set_captcha_passed, has_passed_captcha, add_subscription, get_subscription, remove_subscription, add_referral, get_referrals, get_free_requests, add_free_request, use_free_request, get_all_subscriptions, get_all_users, add_channel, remove_channel, get_channels, reset_all_captcha
import psycopg2
import traceback
from telebot.apihelper import ApiTelegramException
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re

# Токен бота
TOKEN = "8048206902:AAEmlK8ihhGGSZ3OxN2yeyfnvYntpZKDMVU"
    
# Telegram API credentials (получите их на https://my.telegram.org)
API_ID = 27683579  # int, не строка
API_HASH = "a1d0fc7d0c9a41ff5e0ae6a6ed8e2dbb"  # Ваш API_HASH

# Session string (читается из файла)
def load_session_string():
    """Загружает session string из файла"""
    try:
        with open("session_string.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("❌ Файл session_string.txt не найден!")
        print("💡 Запустите create_session.py для создания session string")
        return None

SESSION_STRING = load_session_string()

# Создаем экземпляр бота
bot = telebot.TeleBot(TOKEN)

# Получаем информацию о боте
try:
    bot_info = bot.get_me()
    print(f"🤖 Информация о боте:")
    print(f"   ID: {bot_info.id}")
    print(f"   Username: @{bot_info.username}")
    print(f"   Имя: {bot_info.first_name}")
except Exception as e:
    print(f"❌ Ошибка получения информации о боте: {e}")

# Создаем Telethon клиент для поиска
telethon_client = None
telethon_loop = None

# Конфигурация канала для проверки подписки
CHANNEL_ID = "-1002560851236"  # ID канала 'Белый'
CHANNEL_LINK = "https://t.me/+WpK8oeax0iU2NTc0"  # Ссылка на канал 'Белый'
CHANNEL_NAME = "Белый"

# Конфигурация оплаты
CRYPTO_TOKEN = "429741:AAXorUNHqEtXjRMwoOy4bha83bt4FioBrAt"
crypto = pyCryptoPayAPI(api_token=CRYPTO_TOKEN)

# Цены подписок
PRICES = {
    "7": 3,    # 7 дней - 3$
    "14": 5,   # 14 дней - 5$
    "30": 10,  # месяц - 10$
    "365": 20, # год - 20$
    "infinity": 33  # навсегда - 33$
}

def create_main_keyboard():
    """Создает основную клавиатуру с яркими эмодзи"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💚 Поиск", callback_data="start_search"),
        InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
        InlineKeyboardButton("🎁 Реферал", callback_data="referral"),
        InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        InlineKeyboardButton("ℹ️ О боте", callback_data="about"),
        InlineKeyboardButton("🆓 Бесплатная подписка", callback_data="free_sub")
    )
    return keyboard

def create_search_method_keyboard():
    """Создает клавиатуру для выбора метода поиска"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📱 Поиск по номеру", callback_data="search_phone"),
        InlineKeyboardButton("👤 Поиск по имени", callback_data="search_name"),
        InlineKeyboardButton("🖤 Назад", callback_data="back_to_main")
    )
    return keyboard

def create_shop_keyboard():
    """Создает клавиатуру магазина"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💚 7 дней - 3$", callback_data="buy_7"),
        InlineKeyboardButton("💚 14 дней - 5$", callback_data="buy_14"),
        InlineKeyboardButton("💚 Месяц - 10$", callback_data="buy_30"),
        InlineKeyboardButton("💚 Год - 20$", callback_data="buy_365"),
        InlineKeyboardButton("💚 Навсегда - 33$", callback_data="buy_infinity"),
        InlineKeyboardButton("🖤 Назад", callback_data="back_to_main")
    )
    return keyboard

def create_emoji_captcha_keyboard(correct_emoji, wrong_emojis):
    """Создает клавиатуру для капчи с эмодзи"""
    emojis = wrong_emojis + [correct_emoji]
    random.shuffle(emojis)
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(emoji, callback_data=f"captcha_{emoji}") for emoji in emojis]
    keyboard.add(*buttons)
    return keyboard

def check_channel_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    try:
        # Сначала проверяем, может ли бот получить информацию о канале
        chat_info = bot.get_chat(CHANNEL_ID)
        print(f"🔍 Отладка: Информация о канале: {chat_info.title}")
        
        # Теперь проверяем подписку пользователя
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        print(f"🔍 Отладка: Статус пользователя {user_id}: {member.status}")
        
        # Проверяем, что пользователь является участником, администратором или создателем
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"❌ Ошибка проверки подписки на канал: {e}")
        # Если бот не может получить доступ к каналу, возвращаем True (пропускаем проверку)
        if "chat not found" in str(e) or "Bad Request" in str(e):
            print("🔍 Отладка: Бот не может получить доступ к каналу, пропускаем проверку")
            return True
        return False

def can_use_bot(user_id):
    """Проверяет, может ли пользователь использовать бота"""
    # Сначала проверяем подписку на канал
    if not check_channel_subscription(user_id):
        return False
    # Затем проверяем остальные условия
    return has_subscription(user_id) or has_free_request(user_id)

def get_referral_link(user_id):
    """Генерирует реферальную ссылку"""
    return f"https://t.me/{(bot.get_me()).username}?start=ref{user_id}"

def run_telethon_loop():
    """Запускает event loop для Telethon в отдельном потоке"""
    global telethon_loop
    telethon_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(telethon_loop)
    telethon_loop.run_forever()

def init_telethon_client():
    global telethon_client, telethon_loop
    if not SESSION_STRING:
        return False
    thread = threading.Thread(target=run_telethon_loop, daemon=True)
    thread.start()
    time.sleep(1)
    if telethon_loop is None:
        return False
    future = asyncio.run_coroutine_threadsafe(create_telethon_client(), telethon_loop)
    telethon_client = future.result()
    return telethon_client is not None

async def create_telethon_client():
    if not SESSION_STRING:
        return None
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        return None
    return client

def search_phone_number_sync(phone_number):
    """Синхронная обертка для поиска номера телефона"""
    if not telethon_client or not telethon_loop:
        return "❌ Telethon клиент не инициализирован"
    
    try:
        future = asyncio.run_coroutine_threadsafe(search_phone_number(phone_number), telethon_loop)
        return future.result(timeout=30)  # 30 секунд таймаут
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

def search_by_name_sync(name):
    """Синхронная обертка для поиска по имени"""
    if not telethon_client or not telethon_loop:
        return "❌ Telethon клиент не инициализирован"
    
    try:
        future = asyncio.run_coroutine_threadsafe(search_by_name(name), telethon_loop)
        return future.result(timeout=30)  # 30 секунд таймаут
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

async def search_phone_number(phone_number):
    """Поиск информации по номеру телефона через @Userrsboxx_bot"""
    try:
        # Находим бота @Userrsboxx_bot
        bot_entity = await telethon_client.get_entity("@Userrsboxx_bot")
        
        # Очищаем чат с ботом перед поиском
        print("🧹 Очищаем чат с @Userrsboxx_bot...")
        await telethon_client.delete_dialog(bot_entity)
        
        # Ждем немного после очистки
        await asyncio.sleep(1)
        
        # Отправляем номер телефона
        await telethon_client.send_message(bot_entity, phone_number)
        
        # Ждем немного перед получением сообщений
        await asyncio.sleep(2)
        
        # Получаем последние сообщения от бота
        messages = []
        async for message in telethon_client.iter_messages(bot_entity, limit=3):
            if message.text and message.text != phone_number:
                messages.append(message.text)
        
        # Проверяем результат
        if messages:
            result = messages[1] if len(messages) >= 2 else messages[0]
            
            # Отладочная информация
            print(f"Получен ответ от бота: {result}")
            
            # Проверяем, не скрыты ли данные
            if "🛡️" in result and "Владелец номера скрыл свои данные" in result:
                print("Обнаружены скрытые данные, заменяем сообщение")
                return "❌ Информация не найдена"
            
            # Если данные найдены и не скрыты, возвращаем результат
            return result
        
        return "❌ Информация не найдена"
        
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

async def search_by_name(name):
    """Поиск информации по имени через @Probiv_Probitdri_Bot"""
    try:
        # Находим бота @Probiv_Probitdri_Bot
        bot_entity = await telethon_client.get_entity("@Probiv_Probitdri_Bot")
        
        # Очищаем чат с ботом перед поиском
        print("🧹 Очищаем чат с @Probiv_Probitdri_Bot...")
        await telethon_client.delete_dialog(bot_entity)
        
        # Ждем немного после очистки
        await asyncio.sleep(1)
        
        # Отправляем имя для поиска
        await telethon_client.send_message(bot_entity, name)
        
        # Ждем немного перед получением сообщений
        await asyncio.sleep(2)
        
        # Получаем последние сообщения от бота
        messages = []
        async for message in telethon_client.iter_messages(bot_entity, limit=3):
            if message.text and message.text != name:
                messages.append(message.text)
        
        # Проверяем результат
        if messages:
            result = messages[1] if len(messages) >= 2 else messages[0]
            
            # Отладочная информация
            print(f"Получен ответ от бота: {result}")
            
            # Проверяем, не скрыты ли данные
            if "🛡️" in result and "Владелец скрыл свои данные" in result:
                print("Обнаружены скрытые данные, заменяем сообщение")
                return "❌ Информация не найдена"
            
            # Если данные найдены и не скрыты, возвращаем результат
            return result
        
        return "❌ Информация не найдена"
        
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

def generate_xml_report(search_type, query, result, user_id, username):
    """Генерирует красивый XML файл с результатами поиска"""
    try:
        # Создаем корневой элемент
        root = ET.Element("SearchReport")
        root.set("version", "1.0")
        root.set("generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        root.set("bot", "Maniac Info Bot")
        
        # Метаданные поиска
        metadata = ET.SubElement(root, "Metadata")
        ET.SubElement(metadata, "SearchType").text = search_type
        ET.SubElement(metadata, "Query").text = query
        ET.SubElement(metadata, "UserID").text = str(user_id)
        ET.SubElement(metadata, "Username").text = username or "Unknown"
        ET.SubElement(metadata, "Timestamp").text = datetime.now().isoformat()
        ET.SubElement(metadata, "BotVersion").text = "1.0"
        
        # Результаты поиска
        results = ET.SubElement(root, "Results")
        
        if result and result != "❌ Информация не найдена" and "❌ Ошибка поиска" not in result:
            # Очищаем результат от HTML тегов
            clean_result = result.replace('<b>', '').replace('</b>', '')
            
            # Если есть результат, парсим его и структурируем
            result_text = ET.SubElement(results, "Result")
            result_text.set("status", "found")
            result_text.text = clean_result
            
            # Структурированная информация
            info_section = ET.SubElement(results, "StructuredInfo")
            
            # Парсим данные по секциям
            sections = clean_result.split('👳‍')
            if len(sections) > 1:
                # Основная информация (до лиц)
                main_info = sections[0]
                parse_main_info(info_section, main_info)
                
                # Информация о лицах и остальное
                if len(sections) > 1:
                    remaining_info = '👳‍' + sections[1]
                    parse_detailed_info(info_section, remaining_info)
            else:
                # Если нет разделителя, парсим все как есть
                parse_main_info(info_section, clean_result)
        else:
            # Если результат не найден
            no_result = ET.SubElement(results, "Result")
            no_result.set("status", "not_found")
            no_result.text = "Информация не найдена"
        
        # Добавляем информацию о боте
        bot_info = ET.SubElement(root, "BotInfo")
        ET.SubElement(bot_info, "Name").text = "Maniac Info Bot"
        ET.SubElement(bot_info, "Description").text = "Бот для поиска информации по номеру телефона и имени"
        ET.SubElement(bot_info, "GeneratedAt").text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Создаем красивый XML
        rough_string = ET.tostring(root, 'unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Создаем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_report_{search_type}_{timestamp}.xml"
        
        # Сохраняем файл
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка генерации XML: {e}")
        return None

def parse_main_info(info_section, text):
    """Парсит основную информацию (телефон, страна, регион, оператор)"""
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if '├─Телефон:' in line:
            phone = line.split('├─Телефон:')[1].strip()
            ET.SubElement(info_section, "Phone").text = phone
        elif '├─Страна:' in line:
            country = line.split('├─Страна:')[1].strip()
            ET.SubElement(info_section, "Country").text = country
        elif '├─Регион:' in line:
            region = line.split('├─Регион:')[1].strip()
            ET.SubElement(info_section, "Region").text = region
        elif '└─Оператор:' in line:
            operator = line.split('└─Оператор:')[1].strip()
            ET.SubElement(info_section, "Operator").text = operator

def parse_detailed_info(info_section, text):
    """Парсит детальную информацию (лица, даты, автомобили, почты, телефоны, ИНН)"""
    sections = text.split('🎉')
    
    # Парсим лица
    if '👳‍ Лица:' in sections[0]:
        faces_section = sections[0].split('👳‍ Лица:')[1]
        faces = extract_list_items(faces_section)
        for face in faces:
            if face.strip():
                ET.SubElement(info_section, "Person").text = face.strip()
    
    # Парсим даты рождения
    if len(sections) > 1:
        dates_section = sections[1]
        dates = extract_list_items(dates_section)
        for date in dates:
            if date.strip():
                ET.SubElement(info_section, "BirthDate").text = date.strip()
    
    # Парсим автомобили
    if '🚘 Автомобили:' in text:
        cars_section = text.split('🚘 Автомобили:')[1].split('📧')[0]
        cars = extract_list_items(cars_section)
        for car in cars:
            if car.strip():
                ET.SubElement(info_section, "Car").text = car.strip()
    
    # Парсим почты
    if '📧 Электронные почты:' in text:
        emails_section = text.split('📧 Электронные почты:')[1].split('📱')[0]
        emails = extract_list_items(emails_section)
        for email in emails:
            if email.strip() and '@' in email:
                ET.SubElement(info_section, "Email").text = email.strip()
    
    # Парсим телефоны
    if '📱 Телефоны:' in text:
        phones_section = text.split('📱 Телефоны:')[1].split('🏛')[0]
        phones = extract_list_items(phones_section)
        for phone in phones:
            if phone.strip() and ('+' in phone or phone.isdigit()):
                ET.SubElement(info_section, "AdditionalPhone").text = phone.strip()
    
    # Парсим ИНН
    if '🏛 ИНН:' in text:
        inn_section = text.split('🏛 ИНН:')[1]
        inns = extract_list_items(inn_section)
        for inn in inns:
            if inn.strip() and inn.strip().isdigit():
                ET.SubElement(info_section, "INN").text = inn.strip()

def extract_list_items(text):
    """Извлекает элементы списка из текста"""
    items = []
    # Убираем лишние символы
    text = text.replace('└', '').replace('`', '').replace('__ и еще', '').replace('__', '')
    text = text.replace('├─', '').replace('├', '').replace('─', '')
    
    # Разделяем по запятым
    parts = text.split(',')
    for part in parts:
        part = part.strip()
        if part and len(part) > 2:
            items.append(part)
    
    return items

def generate_html_report(search_type, query, result, user_id, username):
    """Генерирует HTML отчет"""
    try:
        # Очищаем результат
        clean_result = clean_result_for_telegram(result)
        parsed_data = parse_result_for_html(clean_result)
        
        # Создаем HTML без лишних пробелов
        html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maniac Info Report</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        :root {{
            --primary-color: #00d4ff;
            --secondary-color: #ff0080;
            --bg-gradient: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 25%, #16213e 50%, #0f3460 75%, #533483 100%);
            --card-bg: rgba(255, 255, 255, 0.03);
            --text-color: #ffffff;
            --border-color: rgba(255, 255, 255, 0.1);
        }}
        
        [data-theme="light"] {{
            --primary-color: #2563eb;
            --secondary-color: #dc2626;
            --bg-gradient: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 25%, #cbd5e1 50%, #94a3b8 75%, #64748b 100%);
            --card-bg: rgba(0, 0, 0, 0.05);
            --text-color: #1e293b;
            --border-color: rgba(0, 0, 0, 0.1);
        }}
        
        [data-theme="light"] .info-card {{
            background: linear-gradient(135deg, rgba(0, 0, 0, 0.08) 0%, rgba(0, 0, 0, 0.03) 100%);
            border: 1px solid rgba(0, 0, 0, 0.1);
        }}
        
        [data-theme="light"] .info-card h3 {{
            color: #2563eb !important;
        }}
        
        [data-theme="light"] .info-card p {{
            color: #1e293b !important;
            text-shadow: none;
        }}
        
        [data-theme="light"] .section-title {{
            color: #2563eb;
        }}
        
        [data-theme="light"] .logo {{
            background: linear-gradient(135deg, #2563eb 0%, #dc2626 30%, #ea580c 60%, #2563eb 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-gradient);
            color: var(--text-color);
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
            transition: all 0.3s ease;
        }}
        
        body::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: 
                radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.4) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255, 119, 198, 0.4) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(120, 219, 255, 0.3) 0%, transparent 50%),
                radial-gradient(circle at 60% 60%, rgba(255, 107, 53, 0.2) 0%, transparent 50%);
            pointer-events: none;
            z-index: -1;
            animation: backgroundShift 10s ease-in-out infinite;
        }}
        
        @keyframes backgroundShift {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.8; }}
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px 20px;
            position: relative;
        }}
        
        .main-content {{
            background: var(--card-bg);
            border-radius: 30px;
            padding: 40px;
            box-shadow: 
                0 25px 50px rgba(0, 0, 0, 0.5),
                inset 0 1px 0 var(--border-color);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
            margin: 0;
        }}
        
        .main-content::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--primary-color), var(--secondary-color), var(--primary-color), transparent);
            animation: borderFlow 3s linear infinite;
        }}
        
        @keyframes borderFlow {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 50px;
            position: relative;
        }}
        
        .header::after {{
            content: '';
            position: absolute;
            bottom: -20px;
            left: 50%;
            transform: translateX(-50%);
            width: 100px;
            height: 3px;
            background: linear-gradient(90deg, #00d4ff, #ff0080, #00d4ff);
            border-radius: 2px;
        }}
        
        .logo {{
            font-size: 4em;
            font-weight: 900;
            margin-bottom: 15px;
            background: linear-gradient(135deg, #00d4ff 0%, #ff0080 30%, #ff6b35 60%, #00d4ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: textGlow 2s ease-in-out infinite alternate;
            text-shadow: 0 0 30px rgba(0, 212, 255, 0.5);
            letter-spacing: 2px;
        }}
        
        @keyframes textGlow {{
            from {{ 
                filter: drop-shadow(0 0 20px rgba(0, 212, 255, 0.5));
                text-shadow: 0 0 30px rgba(0, 212, 255, 0.5);
            }}
            to {{ 
                filter: drop-shadow(0 0 30px rgba(255, 0, 128, 0.5));
                text-shadow: 0 0 40px rgba(255, 0, 128, 0.5);
            }}
        }}
        
        .search-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
            margin-bottom: 50px;
        }}
        
        .info-card {{
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.02) 100%);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }}
        
        .info-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
            transition: left 0.6s ease;
        }}
        
        .info-card:hover::before {{
            left: 100%;
        }}
        
        .info-card:hover {{
            transform: translateY(-15px) scale(1.05) rotate(2deg);
            box-shadow: 
                0 35px 70px rgba(0, 0, 0, 0.6),
                0 0 0 3px rgba(0, 212, 255, 0.6),
                0 0 40px rgba(0, 212, 255, 0.3),
                0 0 80px rgba(255, 0, 128, 0.2);
            border-color: rgba(0, 212, 255, 0.7);
            filter: brightness(1.2) contrast(1.2) saturate(1.1);
        }}
        
        .info-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.05) 50%, transparent 70%);
            opacity: 0;
            transition: opacity 0.4s ease;
            pointer-events: none;
        }}
        
        .info-card:hover::after {{
            opacity: 1;
        }}
        
        .info-card h3 {{
            margin: 0 0 15px 0;
            font-size: 1.3em;
            color: #00d4ff;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .info-card h3::before {{
            content: '';
            width: 4px;
            height: 20px;
            background: linear-gradient(180deg, #00d4ff, #ff0080);
            border-radius: 2px;
        }}
        
        .info-card p {{
            margin: 0;
            font-size: 1.1em;
            color: #ffffff !important;
            font-weight: 400;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
        }}
        
        .result-section {{
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.03) 100%);
            border-radius: 30px;
            padding: 50px;
            border: 2px solid rgba(255, 255, 255, 0.15);
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(20px);
            margin: 0;
            box-shadow: 
                0 25px 50px rgba(0, 0, 0, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.1);
        }}
        
        .result-section::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #00d4ff, #ff0080, #00d4ff);
            animation: borderPulse 2s ease-in-out infinite;
        }}
        
        @keyframes borderPulse {{
            0%, 100% {{ opacity: 1; transform: scaleX(1); }}
            50% {{ opacity: 0.7; transform: scaleX(0.95); }}
        }}
        
        .section-title {{
            font-size: 2.2em;
            color: #00d4ff;
            text-align: center;
            font-weight: 600;
            position: relative;
            margin: 0 0 25px 0;
            padding: 0;
        }}
        
        .section-title::after {{
            content: '';
            position: absolute;
            bottom: -10px;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 2px;
            background: linear-gradient(90deg, #00d4ff, #ff0080);
            border-radius: 1px;
        }}
        
        .status-container {{
            display: flex;
            align-items: center;
            gap: 20px;
            margin: 0 0 30px 0;
            padding: 0;
        }}
        
        .status-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        }}
        
        .status-found {{
            background: linear-gradient(135deg, #00d4ff 0%, #ff0080 30%, #ff6b35 60%, #00d4ff 100%);
            color: white;
            box-shadow: 
                0 12px 35px rgba(0, 212, 255, 0.5),
                0 0 0 2px rgba(0, 212, 255, 0.3),
                0 0 20px rgba(255, 0, 128, 0.3);
            animation: statusPulse 2s ease-in-out infinite;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        
        @keyframes statusPulse {{
            0%, 100% {{ 
                transform: scale(1);
                box-shadow: 0 12px 35px rgba(0, 212, 255, 0.5);
            }}
            50% {{ 
                transform: scale(1.08);
                box-shadow: 0 20px 50px rgba(0, 212, 255, 0.7);
            }}
        }}
        
        .status-icon {{
            font-size: 1.1em;
            animation: iconBounce 1s ease-in-out infinite;
        }}
        
        @keyframes iconBounce {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-3px); }}
        }}
        

        
        .data-item {{
            background: rgba(0, 0, 0, 0.4);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
            font-size: 1.1em;
            line-height: 1.7;
            color: #ffffff;
            white-space: pre-wrap;
            overflow-x: auto;
            position: relative;
            backdrop-filter: blur(10px);
            margin: 0;
            padding: 0;
        }}
        
        .data-item::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, #00d4ff, transparent);
        }}
        
        .phone-number {{
            font-size: 1.5em;
            font-weight: bold;
            color: #00d4ff;
            text-align: center;
            margin-bottom: 30px;
            text-shadow: 0 0 20px rgba(0, 212, 255, 0.5);
        }}
        
        .person-item {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
            transition: all 0.3s ease;
        }}
        
        .person-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }}
        
        .email-item {{
            background: linear-gradient(135deg, #f093fb, #f5576c);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(240, 147, 251, 0.3);
            transition: all 0.3s ease;
        }}
        
        .email-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(240, 147, 251, 0.4);
        }}
        
        .car-item {{
            background: linear-gradient(135deg, #4facfe, #00f2fe);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(79, 172, 254, 0.3);
            transition: all 0.3s ease;
        }}
        
        .car-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(79, 172, 254, 0.4);
        }}
        
        .inn-item {{
            background: linear-gradient(135deg, #43e97b, #38f9d7);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(67, 233, 123, 0.3);
            transition: all 0.3s ease;
        }}
        
        .inn-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(67, 233, 123, 0.4);
        }}
        
        .date-item {{
            background: linear-gradient(135deg, #fa709a, #fee140);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(250, 112, 154, 0.3);
            transition: all 0.3s ease;
        }}
        
        .date-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(250, 112, 154, 0.4);
        }}
        
        .database-item {{
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 500;
            box-shadow: 0 5px 15px rgba(255, 107, 107, 0.3);
            transition: all 0.3s ease;
        }}
        
        .database-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4);
        }}
        
        .footer {{
            text-align: center;
            margin-top: 50px;
            color: rgba(255, 255, 255, 0.6);
            font-size: 0.95em;
            font-weight: 300;
        }}
        
        .theme-toggle {{
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
        }}
        
        .theme-btn {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 25px;
            padding: 12px 20px;
            color: var(--text-color);
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .theme-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
            border-color: var(--primary-color);
        }}
        
        .theme-icon {{
            font-size: 16px;
            transition: transform 0.3s ease;
        }}
        
        .theme-btn:hover .theme-icon {{
            transform: rotate(180deg);
        }}
        
        ::-webkit-scrollbar {{
            width: 12px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: var(--card-bg);
            border-radius: 6px;
            margin: 4px;
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: linear-gradient(180deg, var(--primary-color), var(--secondary-color));
            border-radius: 6px;
            border: 2px solid var(--card-bg);
            transition: all 0.3s ease;
        }}
        
        ::-webkit-scrollbar-thumb:hover {{
            background: linear-gradient(180deg, var(--secondary-color), var(--primary-color));
            transform: scale(1.1);
        }}
        
        ::-webkit-scrollbar-corner {{
            background: transparent;
        }}
        
        .glow-effect {{
            position: relative;
        }}
        
        .glow-effect::after {{
            content: '';
            position: absolute;
            top: -3px;
            left: -3px;
            right: -3px;
            bottom: -3px;
            background: linear-gradient(45deg, var(--primary-color), var(--secondary-color), var(--primary-color));
            border-radius: inherit;
            z-index: -1;
            opacity: 0;
            transition: opacity 0.4s ease;
            animation: glowPulse 2s ease-in-out infinite;
        }}
        
        .glow-effect:hover::after {{
            opacity: 0.4;
        }}
        
        @keyframes glowPulse {{
            0%, 100% {{ opacity: 0; }}
            50% {{ opacity: 0.2; }}
        }}
        
        .code-particles {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1;
            overflow: hidden;
        }}
        
        .code-particle {{
            position: absolute;
            color: var(--primary-color);
            font-family: 'Courier New', monospace;
            font-size: 14px;
            opacity: 0.8;
            animation: codeFall 8s linear infinite;
            text-shadow: 0 0 12px var(--primary-color);
            font-weight: bold;
            filter: blur(0.5px);
        }}
        
        @keyframes codeFall {{
            0% {{
                transform: translateY(-100px) rotate(0deg);
                opacity: 0;
            }}
            10% {{
                opacity: 0.8;
            }}
            90% {{
                opacity: 0.8;
            }}
            100% {{
                transform: translateY(100vh) rotate(360deg);
                opacity: 0;
            }}
        }}
        
        .smooth-transition {{
            transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        

        
        @keyframes slideInLeft {{
            from {{
                opacity: 0;
                transform: translateX(-30px);
            }}
            to {{
                opacity: 1;
                transform: translateX(0);
            }}
        }}
        
        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(40px) scale(0.95);
            }}
            to {{
                opacity: 1;
                transform: translateY(0) scale(1);
            }}
        }}
        

        
        @media (max-width: 768px) {{
            .container {{
                padding: 10px 5px;
            }}
            
            .main-content {{
                padding: 20px 12px;
                animation: none;
                border-radius: 25px;
                background: linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0.2) 100%);
                backdrop-filter: blur(25px);
                border: 2px solid rgba(0, 212, 255, 0.3);
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.6),
                    0 0 0 1px rgba(0, 212, 255, 0.2),
                    0 0 30px rgba(0, 212, 255, 0.1);
            }}
            
            .logo {{
                font-size: 2.5em;
                letter-spacing: 2px;
                margin-bottom: 15px;
                text-shadow: 0 0 20px rgba(0, 212, 255, 0.8);
                animation: mobileLogoGlow 2s ease-in-out infinite alternate;
            }}
            
            @keyframes mobileLogoGlow {{
                from {{ filter: drop-shadow(0 0 15px rgba(0, 212, 255, 0.6)); }}
                to {{ filter: drop-shadow(0 0 25px rgba(255, 0, 128, 0.8)); }}
            }}
            
            .search-info {{
                grid-template-columns: 1fr;
                gap: 20px;
            }}
            
            .info-card {{
                padding: 25px;
                transition: none;
                transform: none !important;
                color: #ffffff !important;
                background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(255, 0, 128, 0.05) 100%);
                border: 1px solid rgba(0, 212, 255, 0.3);
                border-radius: 20px;
                box-shadow: 
                    0 15px 30px rgba(0, 0, 0, 0.4),
                    0 0 0 1px rgba(0, 212, 255, 0.2),
                    0 0 20px rgba(0, 212, 255, 0.1);
                position: relative;
                overflow: hidden;
            }}
            
            .info-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, #00d4ff, #ff0080, #00d4ff);
                animation: borderFlow 3s linear infinite;
            }}
            
            .info-card h3 {{
                color: #00d4ff !important;
                font-size: 1.3em;
                margin-bottom: 15px;
                font-weight: 700;
                text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            }}
            
            .info-card p {{
                color: #ffffff !important;
                font-size: 1.1em;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.7);
                font-weight: 500;
                line-height: 1.4;
            }}
            
            .result-section {{
                padding: 35px 20px;
                border-radius: 25px;
                background: linear-gradient(135deg, rgba(0, 0, 0, 0.3) 0%, rgba(0, 0, 0, 0.1) 100%);
                border: 2px solid rgba(0, 212, 255, 0.2);
                box-shadow: 
                    0 20px 40px rgba(0, 0, 0, 0.5),
                    0 0 0 1px rgba(0, 212, 255, 0.1);
            }}
            
            .section-title {{
                font-size: 2em;
                text-shadow: 0 0 15px rgba(0, 212, 255, 0.6);
            }}
            
            .status-badge {{
                padding: 8px 16px;
                font-size: 0.9em;
                border-radius: 25px;
                background: linear-gradient(135deg, #00d4ff 0%, #ff0080 100%);
                box-shadow: 0 8px 20px rgba(0, 212, 255, 0.4);
            }}
            
            .data-item {{
                font-size: 1em;
                padding: 18px;
                border-radius: 18px;
                background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(255, 0, 128, 0.05) 100%);
                border: 1px solid rgba(0, 212, 255, 0.2);
                margin-bottom: 12px;
            }}
            
            .raw-result {{
                padding: 20px !important;
                font-size: 0.9em !important;
                line-height: 1.6 !important;
                background: linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0.2) 100%);
                border-radius: 15px;
                border: 1px solid rgba(0, 212, 255, 0.2);
            }}
            
            .footer {{
                margin-top: 40px;
                font-size: 0.9em;
                text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            }}
            
            /* Скрываем кнопку смены темы */
            .theme-toggle {{
                display: none !important;
            }}
            
            .header {{
                padding-right: 0;
            }}
            
            /* Отключаем анимации для мобильных */
            .code-particles {{
                display: none;
            }}
            
            .glow-effect::after {{
                display: none;
            }}
            
            .info-card::before {{
                display: none;
            }}
            
            .info-card::after {{
                display: none;
            }}
            
            .main-content::before {{
                display: none;
            }}
            
            .result-section::after {{
                display: none;
            }}
            
            .header::after {{
                display: none;
            }}
            
            .section-title::after {{
                display: none;
            }}
        }}
        
        /* Дополнительные стили для очень маленьких экранов */
        @media (max-width: 480px) {{
            .container {{
                padding: 8px 3px;
            }}
            
            .main-content {{
                padding: 15px 10px;
                border-radius: 20px;
            }}
            
            .logo {{
                font-size: 2em;
                letter-spacing: 1px;
            }}
            
            .info-card {{
                padding: 20px;
                color: #ffffff !important;
                border-radius: 18px;
            }}
            
            .info-card h3 {{
                color: #00d4ff !important;
                font-size: 1.2em;
                margin-bottom: 12px;
            }}
            
            .info-card p {{
                color: #ffffff !important;
                font-size: 1em;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.7);
            }}
            
            .result-section {{
                padding: 25px 15px;
                border-radius: 20px;
            }}
            
            .section-title {{
                font-size: 1.8em;
            }}
            
            .data-item {{
                font-size: 0.9em;
                padding: 15px;
                border-radius: 15px;
            }}
            
            .raw-result {{
                padding: 15px !important;
                font-size: 0.85em !important;
                word-wrap: break-word;
                overflow-wrap: break-word;
            }}
            
            .status-badge {{
                padding: 6px 12px;
                font-size: 0.8em;
            }}
            
            /* Скрываем кнопку смены темы */
            .theme-toggle {{
                display: none !important;
            }}
        }}
        }}
    </style>
</head>
<body>
    <div class="code-particles" id="codeParticles"></div>
    <div class="container">
        <div class="main-content smooth-transition">

            <div class="header">
                <div class="logo">🔍 Maniac Info Report</div>
                <p>Отчет о поиске информации</p>
            </div>
            
            <div class="search-info">
                <div class="info-card" style="--animation-order: 0;">
                    <h3>Тип поиска</h3>
                    <p>{search_type.title()}</p>
                </div>
                <div class="info-card" style="--animation-order: 1;">
                    <h3>Запрос</h3>
                    <p>{query}</p>
                </div>
                <div class="info-card" style="--animation-order: 2;">
                    <h3>Пользователь</h3>
                    <p>{username or 'Unknown'}</p>
                </div>
                <div class="info-card" style="--animation-order: 3;">
                    <h3>Дата</h3>
                    <p>{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
                </div>
            </div>
            <div class="result-section">
                <h2 class="section-title">📄 Результат поиска</h2>
                <div class="status-container">
                    <div class="status-badge status-found">
                        <span class="status-icon">✅</span>
                        <span class="status-text">Найдено</span>
                    </div>
                </div>
                <div id="reportData" class="data-item" style="margin: 0; padding: 0;">
                    {generate_html_sections(parsed_data, result)}
                </div>
            </div>
            <div class="footer">
                <p>📄 Отчет сгенерирован ботом Maniac Info</p>
                <p>🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
            </div>
        </div>
    </div>

    <script>
        // Проверяем, является ли устройство мобильным
        function isMobile() {{
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;
        }}
        
        // Создаем падающие частички кода только для десктопа
        function createCodeParticles() {{
            if (isMobile()) {{
                return; // Не создаем частички на мобильных
            }}
            
            const particlesContainer = document.getElementById('codeParticles');
            const codeSymbols = ['{', '}', '[', ']', '<', '>', '/', '*', '+', '-', '=', ';', ':', '|', '&', '^', '%', '$', '#', '@', '!', '?', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
            const particleCount = 80;
            
            for (let i = 0; i < particleCount; i++) {{
                const particle = document.createElement('div');
                particle.className = 'code-particle';
                particle.textContent = codeSymbols[Math.floor(Math.random() * codeSymbols.length)];
                particle.style.left = Math.random() * 100 + '%';
                particle.style.animationDelay = Math.random() * 10 + 's';
                particle.style.animationDuration = (Math.random() * 6 + 8) + 's';
                particle.style.fontSize = (Math.random() * 8 + 10) + 'px';
                particlesContainer.appendChild(particle);
            }}
        }}
        
        // Создаем частички при загрузке
        createCodeParticles();
        
        // Устанавливаем темную тему по умолчанию
        document.documentElement.setAttribute('data-theme', 'dark');
        

        
        // Добавляем анимации при скролле только для десктопа
        if (!isMobile()) {{
            const observerOptions = {{
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px'
            }};
            
            const observer = new IntersectionObserver((entries) => {{
                entries.forEach(entry => {{
                    if (entry.isIntersecting) {{
                        entry.target.style.animation = 'fadeInUp 0.6s ease-out';
                    }}
                }});
            }}, observerOptions);
            
            document.querySelectorAll('.result-section').forEach(section => {{
                observer.observe(section);
            }});
            
            // Анимация загрузки данных
            setTimeout(() => {{
                document.querySelectorAll('.data-item').forEach((item, index) => {{
                    setTimeout(() => {{
                        item.style.animation = 'slideInLeft 0.5s ease-out';
                    }}, index * 100);
                }});
            }}, 500);
        }}
        
        // Добавляем эффект свечения к карточкам только для десктопа
        if (!isMobile()) {{
            document.querySelectorAll('.info-card').forEach(card => {{
                card.classList.add('glow-effect');
            }});
        }}
        

    </script>
</body>
</html>"""
        
        # Создаем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_report_{search_type}_{timestamp}.html"
        
        # Сохраняем файл
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка генерации HTML: {e}")
        return None

def parse_result_for_html(result):
    """Парсит результат для HTML отчета"""
    data = {
        'phone': '',
        'country': '',
        'region': '',
        'operator': '',
        'persons': [],
        'emails': [],
        'phones': [],
        'cars': [],
        'inns': [],
        'birth_dates': [],
        'databases': []
    }
    
    if not result:
        return data
    
    # print(f"[DEBUG] Парсинг результата: {result[:200]}...")
    
    # Парсим основную информацию
    lines = result.split('\n')
    for line in lines:
        line = line.strip()
        if '├─**Телефон**:' in line:
            data['phone'] = line.split('├─**Телефон**:')[1].strip()
        elif '├─**Страна**:' in line:
            data['country'] = line.split('├─**Страна**:')[1].strip()
        elif '├─**Регион**:' in line:
            data['region'] = line.split('├─**Регион**:')[1].strip()
        elif '└─**Оператор**:' in line:
            data['operator'] = line.split('└─**Оператор**:')[1].strip()
    
    # Парсим детальную информацию
    result_text = result
    
    # Лица
    if '**👳‍♂️  Лица:**' in result_text:
        faces_section = result_text.split('**👳‍♂️  Лица:**')[1]
        # Ищем следующий заголовок
        if '**🎉  Даты рождения:**' in faces_section:
            faces_section = faces_section.split('**🎉  Даты рождения:**')[0]
        elif '**🚘  Автомобили:**' in faces_section:
            faces_section = faces_section.split('**🚘  Автомобили:**')[0]
        elif '**📧  Электронные почты:**' in faces_section:
            faces_section = faces_section.split('**📧  Электронные почты:**')[0]
        elif '**📱  Телефоны:**' in faces_section:
            faces_section = faces_section.split('**📱  Телефоны:**')[0]
        elif '**🏛️  ИНН:**' in faces_section:
            faces_section = faces_section.split('**🏛️  ИНН:**')[0]
        data['persons'] = extract_list_items(faces_section)
    
    # Даты рождения
    if '**🎉  Даты рождения:**' in result_text:
        dates_section = result_text.split('**🎉  Даты рождения:**')[1]
        # Ищем следующий заголовок
        if '**🚘  Автомобили:**' in dates_section:
            dates_section = dates_section.split('**🚘  Автомобили:**')[0]
        elif '**📧  Электронные почты:**' in dates_section:
            dates_section = dates_section.split('**📧  Электронные почты:**')[0]
        elif '**📱  Телефоны:**' in dates_section:
            dates_section = dates_section.split('**📱  Телефоны:**')[0]
        elif '**🏛️  ИНН:**' in dates_section:
            dates_section = dates_section.split('**🏛️  ИНН:**')[0]
        data['birth_dates'] = extract_list_items(dates_section)
    
    # Автомобили
    if '**🚘  Автомобили:**' in result_text:
        cars_section = result_text.split('**🚘  Автомобили:**')[1]
        # Ищем следующий заголовок
        if '**📧  Электронные почты:**' in cars_section:
            cars_section = cars_section.split('**📧  Электронные почты:**')[0]
        elif '**📱  Телефоны:**' in cars_section:
            cars_section = cars_section.split('**📱  Телефоны:**')[0]
        elif '**🏛️  ИНН:**' in cars_section:
            cars_section = cars_section.split('**🏛️  ИНН:**')[0]
        data['cars'] = extract_list_items(cars_section)
    
    # Почты
    if '**📧  Электронные почты:**' in result_text:
        emails_section = result_text.split('**📧  Электронные почты:**')[1]
        # Ищем следующий заголовок
        if '**📱  Телефоны:**' in emails_section:
            emails_section = emails_section.split('**📱  Телефоны:**')[0]
        elif '**🏛️  ИНН:**' in emails_section:
            emails_section = emails_section.split('**🏛️  ИНН:**')[0]
        data['emails'] = extract_list_items(emails_section)
    
    # Телефоны
    if '**📱  Телефоны:**' in result_text:
        phones_section = result_text.split('**📱  Телефоны:**')[1]
        # Ищем следующий заголовок
        if '**🏛️  ИНН:**' in phones_section:
            phones_section = phones_section.split('**🏛️  ИНН:**')[0]
        data['phones'] = extract_list_items(phones_section)
    
    # ИНН
    if '**🏛️  ИНН:**' in result_text:
        inn_section = result_text.split('**🏛️  ИНН:**')[1]
        data['inns'] = extract_list_items(inn_section)
    
    # Определяем базы данных
    data['databases'] = detect_database_sources(result)
    
    return data

def generate_html_sections(data, raw_result):
    """Генерирует HTML секции для отчета"""
    sections = []
    
    # Показываем сырой результат от бота
    if raw_result:
        # Форматируем результат для HTML
        formatted_result = raw_result.replace('\n', '<br>')
        sections.append(f"""
            <div class="raw-result" style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 10px; font-family: 'Courier New', monospace; white-space: pre-wrap; line-height: 1.6; margin-top: 20px;">
                {formatted_result}
            </div>
        """)
    
    return ''.join(sections)

def generate_navigation_sections(data):
    """Генерирует навигацию по базам данных"""
    navigation_items = []
    
    # Основная информация
    if data['phone'] or data['country'] or data['region'] or data['operator']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">📱 Основная информация</div>')
    
    # Базы данных
    if data['databases']:
        for db in data['databases'][:10]:  # Показываем первые 10
            navigation_items.append(f'<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">{db["emoji"]} {db["name"]} [{db["date"]}]</div>')
    
    # Лица
    if data['persons']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">👳‍♂️ Лица ({len(data["persons"])})</div>')
    
    # Даты рождения
    if data['birth_dates']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">🎉 Даты рождения ({len(data["birth_dates"])})</div>')
    
    # Автомобили
    if data['cars']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">🚘 Автомобили ({len(data["cars"])})</div>')
    
    # Почты
    if data['emails']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">📧 Электронные почты ({len(data["emails"])})</div>')
    
    # Телефоны
    if data['phones']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">📱 Телефоны ({len(data["phones"])})</div>')
    
    # ИНН
    if data['inns']:
        navigation_items.append('<div class="nav-item" style="color: #ffffff; padding: 10px; margin-bottom: 10px; border-radius: 8px; background: rgba(255,255,255,0.1);">🏛️ ИНН ({len(data["inns"])})</div>')
    
    return ''.join(navigation_items)

# --- Удалены все in-memory словари ---

# --- Вспомогательные функции ---
def register_user(user_id, username):
    add_user(user_id, username)

# --- Капча ---
def need_captcha(user_id):
    return not has_passed_captcha(user_id)

# --- START ---
user_states = {}
last_search_time = {}
SEARCH_COOLDOWN = 120
pending_invoices = {}

@bot.callback_query_handler(func=lambda call: call.data in ["search_phone", "search_name"])
def handle_search_states(call: CallbackQuery):
    user_id = call.from_user.id
    global last_search_time
    now = time.time()
    if user_id in last_search_time and now - last_search_time[user_id] < SEARCH_COOLDOWN:
        bot.answer_callback_query(call.id, "🖤 Подождите 2 минуты между поисками.", show_alert=True)
        return
    if call.data == "search_phone":
        user_states[user_id] = {"state": "waiting_for_phone"}
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📱 <b>Поиск по номеру телефона</b>\n\nВведите номер телефона для поиска:\n\n<code>+7XXXXXXXXXX</code>\nПример: <code>+79123456789</code>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    elif call.data == "search_name":
        user_states[user_id] = {"state": "waiting_for_name"}
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "👤 <b>Поиск по имени</b>\n\nВведите имя пользователя для поиска:\n\n<b>Поддерживаются:</b> буквы, символы, пробелы\n<b>Не поддерживаются:</b> цифры\nПример: <code>Иван Иванов</code>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )

@bot.message_handler(commands=['start'])
def start_command(message: Message, edit=False):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    from db import get_all_users
    already_registered = any(row[0] == user_id for row in get_all_users())
    register_user(user_id, username)
    greetings = [
        "👋 Привет, {username}! Добро пожаловать в Maniac Info!",
        "💫 Рад тебя видеть, {username}!",
        "🔥 Здравствуй, {username}! Готов к поиску информации?",
        "✨ Приветствуем, {username}!"
    ]
    greet = random.choice(greetings).format(username=f"@{username}" if username else f"ID:{user_id}")
    short_desc = "<b>💚 Maniac Info — быстрый поиск по номеру и имени, рефералы, подписки, бонусы!</b>"
    # --- Капча только один раз ---
    if need_captcha(user_id):
        correct_emoji = random.choice(["🍏", "🍎", "🍌", "🍊", "🍋", "🍉", "🍇", "🍓", "🍒", "🥝", "🥑", "🍍"])
        wrong_emojis = random.sample([e for e in ["🍏", "🍎", "🍌", "🍊", "🍋", "🍉", "🍇", "🍓", "🍒", "🥝", "🥑", "🍍"] if e != correct_emoji], 2)
        bot.send_message(
            message.chat.id,
            f"🖤 Для продолжения выбери <b>правильный эмодзи</b> из списка ниже:\n\n<b>Выбери: {correct_emoji}</b>",
            parse_mode='HTML',
            reply_markup=create_emoji_captcha_keyboard(correct_emoji, wrong_emojis)
        )
        return
    # --- Проверка подписки на канал ---
    if not check_channel_subscription(user_id):
        channel_keyboard = InlineKeyboardMarkup(row_width=1)
        channel_keyboard.add(
            InlineKeyboardButton("💚 Подписаться на канал", url=CHANNEL_LINK),
            InlineKeyboardButton("🖤 Проверить подписку", callback_data="check_subscription")
        )
        bot.send_message(
            message.chat.id,
            f"🖤 ***Для использования бота необходимо подписаться на канал!***\n\n"
            f"*Подпишитесь на наш канал <b>{CHANNEL_NAME}</b> для получения доступа к боту:*\n"
            f"<b>{CHANNEL_NAME}</b>\n\n"
            f"*После подписки нажмите 'Проверить подписку'*",
            parse_mode='HTML',
            reply_markup=channel_keyboard
        )
        return
    # --- Реферальная система ---
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                from db import get_referrals
                if referrer_id == user_id:
                    # Сам себе — только 1 раз
                    if user_id not in get_referrals(user_id):
                        add_referral(user_id, user_id)
                        add_free_request(user_id)
                        bot.send_message(message.chat.id, "⚠️ Вы пригласили сами себя. Это сработает только 1 раз! Вам начислен 1 бесплатный запрос.")
                        print(f"[REFERRAL] user_id={user_id} пригласил сам себя — 1 раз, бонус выдан")
                    else:
                        bot.send_message(message.chat.id, "⚠️ Вы уже получали бонус за самоприглашение. Повторно нельзя!")
                        print(f"[REFERRAL] user_id={user_id} пытался повторно пригласить сам себя — отказано")
                else:
                    # Не сам себе
                    if user_id not in get_referrals(referrer_id):
                        add_referral(referrer_id, user_id)
                        add_free_request(referrer_id)
                        print(f"[REFERRAL] referrer_id={referrer_id} user_id={user_id} -> начислен бесплатный запрос только пригласившему")
                        bot.send_message(referrer_id, f"💚 По вашей реферальной ссылке присоединился новый пользователь! ID: {user_id}\nВам начислен бесплатный запрос!")
                    else:
                        bot.send_message(referrer_id, f"🖤 По вашей реферальной ссылке уже заходил пользователь ID: {user_id}, бонус не начислен повторно.")
            except Exception as e:
                print(f"[REFERRAL] Ошибка начисления бонуса: {e}")
    # --- Приветствие ---
    bot.send_message(
        message.chat.id,
        f"{greet}\n\n{short_desc}",
        parse_mode='HTML',
        reply_markup=create_main_keyboard()
    )

# --- Капча обработчик ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("captcha_"))
def handle_captcha_emoji(call: CallbackQuery):
    user_id = call.from_user.id
    set_captcha_passed(user_id)
    bot.answer_callback_query(call.id, "💚 Капча пройдена!")
    # Теперь редактируем исходное сообщение, а не отправляем новое
    start_command(call.message, edit=True)

# --- Бесплатные запросы ---
def has_free_request(user_id):
    return get_free_requests(user_id) > 0

# --- Подписки ---
def has_subscription(user_id):
    sub = get_subscription(user_id)
    return sub and sub[0] and sub[1] > time.time()

def has_free_sub(user_id):
    # Проверка: получал ли пользователь бесплатную подписку (через базу или in-memory)
    # Для простоты — in-memory, но лучше хранить в БД
    if not hasattr(has_free_sub, 'used'):
        has_free_sub.used = set()
    return user_id in has_free_sub.used

def set_free_sub_used(user_id):
    if not hasattr(has_free_sub, 'used'):
        has_free_sub.used = set()
    has_free_sub.used.add(user_id)

# --- Профиль ---
@bot.callback_query_handler(func=lambda call: call.data == "profile")
def handle_profile(call: CallbackQuery):
    user_id = call.from_user.id
    sub = get_subscription(user_id)
    if sub and sub[0] and sub[1] > time.time():
        sub_status = "<b>💚 Активна</b>"
        sub_until = time.strftime('%d.%m.%Y', time.localtime(sub[1]))
    else:
        sub_status = "<b>🖤 Нет</b>"
        sub_until = "-"
    free = get_free_requests(user_id)
    ref_count = len(get_referrals(user_id))
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Подписка:</b> {sub_status}\n"
        f"<b>До:</b> {sub_until}\n"
        f"<b>Бесплатные запросы:</b> <b>{free}</b> 💚\n"
        f"<b>Рефералов:</b> <b>{ref_count}</b> 🎁\n"
    )
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_back_keyboard(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    return

# --- Рефералы ---
@bot.callback_query_handler(func=lambda call: call.data == "referral")
def handle_referral(call: CallbackQuery):
    user_id = call.from_user.id
    ref_link = get_referral_link(user_id)
    ref_count = len(get_referrals(user_id))
    text = (
        f"🎁 ***Ваша реферальная ссылка:***\n"
        f"`{ref_link}`\n\n"
        f"Приглашено пользователей: **{ref_count}** 💚\n\n"
        f"Каждый приглашённый получает 1 бесплатный запрос! 💰"
    )
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_back_keyboard(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id)
    return

# --- Поиск ---
# (оставить существующую логику поиска, только бесплатные запросы и подписки проверять через базу)

@bot.message_handler(func=lambda message: not message.text.startswith('/') and message.from_user.id not in admin_states)
def handle_all_messages(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    msg_id = message.message_id
    text = message.text.strip()
    now = time.time()
    # Удаляем сообщение пользователя
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass
    # Если нет bot_msg_id, создаём ОДНО сообщение, иначе всегда edit_message_text
    if user_id not in user_states or "bot_msg_id" not in user_states[user_id]:
        bot_msg = bot.send_message(chat_id, "🖤 Ожидание...", parse_mode='HTML')
        if user_id not in user_states:
            user_states[user_id] = {}
        user_states[user_id]["bot_msg_id"] = bot_msg.message_id
    bot_msg_id = user_states[user_id]["bot_msg_id"]
    # --- Поиск по номеру ---
    if user_id in user_states and user_states[user_id].get("state") == "waiting_for_phone":
        # Проверка кулдауна и формата
        if user_id in last_search_time and now - last_search_time[user_id] < SEARCH_COOLDOWN:
            bot.edit_message_text("🖤 Подождите 2 минуты между поисками.", chat_id=chat_id, message_id=bot_msg_id)
            del user_states[user_id]
            return
        if not text.startswith('+') or len(text) < 10:
            bot.edit_message_text("🖤 Неверный формат номера! Используйте формат: <code>+7XXXXXXXXXX</code>", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
            return
        if not has_subscription(user_id):
            if get_free_requests(user_id) <= 0:
                bot.edit_message_text("🖤 У вас закончились бесплатные запросы или подписка!", chat_id=chat_id, message_id=bot_msg_id)
                del user_states[user_id]
                return
            if not use_free_request(user_id):
                bot.edit_message_text("🖤 У вас закончились бесплатные запросы или подписка!", chat_id=chat_id, message_id=bot_msg_id)
                del user_states[user_id]
                return
        last_search_time[user_id] = now
        # Анимация поиска (можно сделать простую смену текста)
        bot.edit_message_text(f"💚 <b>Поиск по номеру:</b> {text}\n\n💚 Выполняем поиск...", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
        try:
            result = search_phone_number_sync(text)
            # Очищаем результат для безопасной отправки
            result = clean_result_for_telegram(result)
            
            # Генерируем HTML отчет
            username = message.from_user.username or "Unknown"
            html_filename = generate_html_report("phone", text, result, user_id, username)
            
            # Логируем поиск для админов
            log_search_for_admins(user_id, username, "phone", text, result)
            
            # Отправляем результат и HTML файл
            # Ограничиваем размер сообщения
            if len(result) > 4000:
                result = result[:4000] + "..."
            bot.edit_message_text(f"📱 Результат поиска по номеру:\n\n{result}", chat_id=chat_id, message_id=bot_msg_id, reply_markup=create_back_keyboard())
            
            # Отправляем HTML файл, если он был создан
            if html_filename and os.path.exists(html_filename):
                try:
                    with open(html_filename, 'rb') as html_file:
                        bot.send_document(chat_id, html_file, caption="🎨 Красивый HTML отчет с результатами поиска")
                    # Удаляем временный файл
                    os.remove(html_filename)
                except Exception as e:
                    print(f"❌ Ошибка отправки HTML файла: {e}")
                    
        except Exception as e:
            bot.edit_message_text(f"❌ <b>Ошибка поиска:</b> {str(e)}", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        del user_states[user_id]
        return
    # --- Поиск по имени ---
    if user_id in user_states and user_states[user_id].get("state") == "waiting_for_name":
        if user_id in last_search_time and now - last_search_time[user_id] < SEARCH_COOLDOWN:
            bot.edit_message_text("🖤 Подождите 2 минуты между поисками.", chat_id=chat_id, message_id=bot_msg_id)
            del user_states[user_id]
            return
        if any(char.isdigit() for char in text):
            bot.edit_message_text("🖤 Имя не должно содержать цифры! Используйте только буквы, символы и пробелы.", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
            return
        if len(text) < 2:
            bot.edit_message_text("🖤 Имя должно содержать минимум 2 символа!", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
            return
        if not has_subscription(user_id):
            if get_free_requests(user_id) <= 0:
                bot.edit_message_text("🖤 У вас закончились бесплатные запросы или подписка!", chat_id=chat_id, message_id=bot_msg_id)
                del user_states[user_id]
                return
            if not use_free_request(user_id):
                bot.edit_message_text("🖤 У вас закончились бесплатные запросы или подписка!", chat_id=chat_id, message_id=bot_msg_id)
                del user_states[user_id]
                return
        last_search_time[user_id] = now
        bot.edit_message_text(f"💚 <b>Поиск по имени:</b> {text}\n\n💚 Выполняем поиск...", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
        try:
            result = search_by_name_sync(text)
            # Очищаем результат для безопасной отправки
            result = clean_result_for_telegram(result)
            
            # Генерируем HTML отчет
            username = message.from_user.username or "Unknown"
            html_filename = generate_html_report("name", text, result, user_id, username)
            
            # Логируем поиск для админов
            log_search_for_admins(user_id, username, "name", text, result)
            
            # Отправляем результат и HTML файл
            # Ограничиваем размер сообщения
            if len(result) > 4000:
                result = result[:4000] + "..."
            bot.edit_message_text(f"👤 Результат поиска по имени:\n\n{result}", chat_id=chat_id, message_id=bot_msg_id, reply_markup=create_back_keyboard())
            
            # Отправляем HTML файл, если он был создан
            if html_filename and os.path.exists(html_filename):
                try:
                    with open(html_filename, 'rb') as html_file:
                        bot.send_document(chat_id, html_file, caption="🎨 Красивый HTML отчет с результатами поиска")
                    # Удаляем временный файл
                    os.remove(html_filename)
                except Exception as e:
                    print(f"❌ Ошибка отправки HTML файла: {e}")
                    
        except Exception as e:
            bot.edit_message_text(f"❌ <b>Ошибка поиска:</b> {str(e)}", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        del user_states[user_id]
        return
    # --- Остальные сценарии (профиль, рефералы, магазин, ошибки и т.д.) ---
    # ... (аналогично: только edit_message_text(chat_id, bot_msg_id))

# --- Автоматическое принятие join request (для супергруппы) ---
@bot.chat_join_request_handler()
def approve_join_request(join_request: ChatJoinRequest):
    try:
        bot.approve_chat_join_request(join_request.chat.id, join_request.from_user.id)
        print(f"✅ Заявка от {join_request.from_user.id} в {join_request.chat.id} автоматически одобрена!")
    except Exception as e:
        print(f"❌ Ошибка автопринятия заявки: {e}")

def create_about_keyboard():
    """Создает клавиатуру для раздела 'О боте' с кнопкой 'Назад'"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🖤 Назад", callback_data="back_to_main"))
    return keyboard

# --- Для удаления канала ---
# После удаления канала сразу edit_message_text(bot_msg_id) с обновлённым списком каналов или сообщением 'Нет каналов'.
# Пример:
def remove_channel_and_update_message(user_id, chat_id):
    channels = get_channels()
    if not channels:
        bot.edit_message_text("🖤 Нет добавленных каналов.", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML')
    else:
        keyboard = InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            keyboard.add(InlineKeyboardButton(f"{ch[2]} ({ch[0]})", callback_data=f"remove_channel_{ch[0]}"))
        bot.edit_message_text("➖ <b>Удаление канала</b>\n\nВыберите канал для удаления:", chat_id=chat_id, message_id=bot_msg_id, parse_mode='HTML', reply_markup=keyboard)

# --- Клавиатура админ-панели ---
def create_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🦾 Добавить подписку", callback_data="admin_add_sub"),
        InlineKeyboardButton("🗑️ Удалить подписку", callback_data="admin_remove_sub"),
    )
    keyboard.add(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("💚 Только с подпиской", callback_data="admin_users_active"),
    )
    keyboard.add(
        InlineKeyboardButton("🤍 Все пользователи", callback_data="admin_users_all"),
    )
    keyboard.add(
        InlineKeyboardButton("➕ Админ", callback_data="admin_add_admin"),
        InlineKeyboardButton("➖ Админ", callback_data="admin_remove_admin"),
    )
    keyboard.add(
        InlineKeyboardButton("➕ Канал", callback_data="admin_add_channel"),
        InlineKeyboardButton("➖ Канал", callback_data="admin_remove_channel"),
    )
    keyboard.add(
        InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
    )
    return keyboard

# --- Состояния админ-панели ---
admin_states = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_panel(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return
    action = call.data
    # Сброс состояния, если админ возвращается в меню
    if action == "admin_back":
        if user_id in admin_states:
            del admin_states[user_id]
        bot.edit_message_text(
            "<b>🖤 Админ-панель</b>\n\nВыберите действие:",
            chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_admin_keyboard()
        )
        return
    # --- Добавить подписку ---
    if action == "admin_add_sub":
        admin_states[user_id] = {"step": "wait_user_id", "mode": "add_sub"}
        bot.edit_message_text(
            "🦾 Введите <b>ID пользователя</b> для добавления подписки:",
            chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard()
        )
        return
    # --- Удалить подписку ---
    if action == "admin_remove_sub":
        admin_states[user_id] = {"step": "wait_user_id", "mode": "remove_sub"}
        bot.edit_message_text(
            "🗑️ Введите <b>ID пользователя</b> для удаления подписки:",
            chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard()
        )
        return
    # --- Остальные действия (заглушки) ---
    if action == "admin_stats":
        from db import get_all_users, get_all_subscriptions
        users = get_all_users()
        subs = get_all_subscriptions()  # [(user_id, active, expires_at), ...]
        now = time.time()
        active_subs = sum(1 for sub in subs if sub[1] and sub[2] > now)
        total_subs = len(subs)
        total_users = len(users)
        stats_text = (
            f"📊 <b>Статистика</b>\n\n"
            f"👥 <b>Пользователей:</b> {total_users}\n"
            f"💚 <b>Активных подписок:</b> {active_subs}\n"
            f"🖤 <b>Всего подписок:</b> {total_subs}"
        )
        bot.edit_message_text(stats_text, chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_users_active":
        from db import get_all_users, get_subscription
        users = get_all_users()
        now = time.time()
        active_users = []
        for row in users:
            uid, username = row
            sub = get_subscription(uid)
            if sub and sub[0] and sub[1] > now:
                expires_date = time.strftime("%d.%m.%Y", time.localtime(sub[1]))
                active_users.append(f"💚 <b>ID:</b> {uid}\n👤 @{username}\n💰 <b>До:</b> {expires_date}")
        if not active_users:
            users_text = "💚 <b>Нет пользователей с активной подпиской</b>"
        else:
            users_text = "💚 <b>Пользователи с активной подпиской:</b>\n\n" + "\n\n".join(active_users)
        bot.edit_message_text(users_text, chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_users_all":
        from db import get_all_users, get_subscription
        users = get_all_users()
        now = time.time()
        all_users = []
        for row in users:
            uid, username = row
            sub = get_subscription(uid)
            if sub and sub[0] and sub[1] > now:
                expires_date = time.strftime("%d.%m.%Y", time.localtime(sub[1]))
                all_users.append(f"💚 <b>ID:</b> {uid}\n👤 @{username}\n💰 <b>До:</b> {expires_date}")
            elif sub and not sub[0]:
                all_users.append(f"💛 <b>ID:</b> {uid}\n👤 @{username} (истекла)")
            else:
                all_users.append(f"🤍 <b>ID:</b> {uid}\n👤 @{username} (нет подписки)")
        if not all_users:
            users_text = "🤍 <b>Нет пользователей</b>"
        else:
            users_text = "🤍 <b>Все пользователи:</b>\n\n" + "\n\n".join(all_users)
        bot.edit_message_text(users_text, chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_add_admin":
        admin_states[user_id] = {"step": "wait_admin_id", "mode": "add_admin"}
        bot.edit_message_text("➕ Введите <b>ID нового админа</b>:", chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_remove_admin":
        admin_states[user_id] = {"step": "wait_admin_id", "mode": "remove_admin"}
        bot.edit_message_text("➖ Введите <b>ID админа для удаления</b>:", chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_add_channel":
        admin_states[user_id] = {"step": "wait_channel_id", "mode": "add_channel"}
        bot.edit_message_text("➕ Введите <b>ID канала</b>:", chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_remove_channel":
        admin_states[user_id] = {"step": "wait_channel_id", "mode": "remove_channel"}
        bot.edit_message_text("➖ Введите <b>ID канала для удаления</b>:", chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return
    if action == "admin_broadcast":
        admin_states[user_id] = {"step": "wait_broadcast_text", "mode": "broadcast"}
        bot.edit_message_text("📢 Введите текст для рассылки:", chat_id=chat_id, message_id=msg_id, parse_mode='HTML', reply_markup=create_back_keyboard())
        return

# --- Клавиатура "Назад" ---
def create_back_keyboard(admin=False):
    kb = InlineKeyboardMarkup()
    if admin:
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
    else:
        kb.add(InlineKeyboardButton("🖤 Назад", callback_data="back_to_main"))
    return kb

@bot.message_handler(commands=['admin'])
def admin_command(message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "❌ У вас нет доступа к админ-панели!")
        return
    admin_text = (
        "<b>🖤 Админ-панель</b>\n\n"
        "Выберите действие:\n"
        "• 🦾 Добавить подписку\n"
        "• 🗑️ Удалить подписку\n"
        "• 📊 Статистика\n"
        "• 💚 Только с подпиской\n"
        "• 🤍 Все пользователи\n"
        "• ➕ Админ\n"
        "• ➖ Админ\n"
        "• ➕ Канал\n"
        "• ➖ Канал\n"
        "• 📢 Рассылка\n"
    )
    bot.send_message(message.chat.id, admin_text, parse_mode='HTML', reply_markup=create_admin_keyboard())

@bot.message_handler(func=lambda message: message.from_user.id in admin_states)
def handle_admin_steps(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    msg_id = message.message_id
    state = admin_states.get(user_id, {})
    step = state.get("step")
    mode = state.get("mode")
    text = message.text.strip()
    # Кнопка "Назад"
    if text == "⬅️ Назад":
        del admin_states[user_id]
        bot.send_message(chat_id, "<b>🖤 Админ-панель</b>\n\nВыберите действие:", parse_mode='HTML', reply_markup=create_admin_keyboard())
        return
    # --- Добавить подписку ---
    if mode == "add_sub":
        if step == "wait_user_id":
            if not text.isdigit():
                bot.send_message(chat_id, "❌ Введите корректный ID пользователя (число)", reply_markup=create_back_keyboard())
                return
            state["target_user_id"] = int(text)
            state["step"] = "wait_days"
            bot.send_message(chat_id, "Введите срок подписки в днях (например, 7, 30, 365, 9999 для навсегда):", reply_markup=create_back_keyboard())
            return
        if step == "wait_days":
            if not text.isdigit() or int(text) <= 0:
                bot.send_message(chat_id, "❌ Введите корректный срок (число дней)", reply_markup=create_back_keyboard())
                return
            days = int(text)
            target_user_id = state["target_user_id"]
            from db import add_subscription
            import time
            expires_at = time.time() + days*24*60*60 if days < 9999 else time.time() + 10*365*24*60*60
            add_subscription(target_user_id, expires_at, user_id)
            bot.send_message(chat_id, f"💚 Подписка добавлена пользователю <code>{target_user_id}</code> на {days if days < 9999 else 'навсегда'} дней!", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Удалить подписку ---
    if mode == "remove_sub":
        if step == "wait_user_id":
            if not text.isdigit():
                bot.send_message(chat_id, "❌ Введите корректный ID пользователя (число)", reply_markup=create_back_keyboard())
                return
            target_user_id = int(text)
            from db import get_subscription, add_subscription
            sub = get_subscription(target_user_id)
            if not sub or not sub[0]:
                bot.send_message(chat_id, f"🖤 У пользователя <code>{target_user_id}</code> нет активной подписки!", parse_mode='HTML', reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            # Делаем подписку неактивной и expires_at=0
            add_subscription(target_user_id, 0, user_id)
            bot.send_message(chat_id, f"🗑️ Подписка удалена у пользователя <code>{target_user_id}</code>!", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Добавить админа ---
    if mode == "add_admin":
        if step == "wait_admin_id":
            if not text.isdigit():
                bot.send_message(chat_id, "❌ Введите корректный ID пользователя (число)", reply_markup=create_back_keyboard())
                return
            target_admin_id = int(text)
            if target_admin_id in ADMIN_IDS:
                bot.send_message(chat_id, f"🖤 Пользователь <code>{target_admin_id}</code> уже админ!", parse_mode='HTML', reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            ADMIN_IDS.append(target_admin_id)
            bot.send_message(chat_id, f"💚 Пользователь <code>{target_admin_id}</code> добавлен в админы!", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Удалить админа ---
    if mode == "remove_admin":
        if step == "wait_admin_id":
            if not text.isdigit():
                bot.send_message(chat_id, "❌ Введите корректный ID пользователя (число)", reply_markup=create_back_keyboard())
                return
            target_admin_id = int(text)
            if target_admin_id == user_id:
                bot.send_message(chat_id, "❌ Нельзя удалить самого себя!", reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            if target_admin_id not in ADMIN_IDS:
                bot.send_message(chat_id, f"🖤 Пользователь <code>{target_admin_id}</code> не является админом!", parse_mode='HTML', reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            ADMIN_IDS.remove(target_admin_id)
            bot.send_message(chat_id, f"🖤 Пользователь <code>{target_admin_id}</code> удалён из админов!", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Добавить канал ---
    if mode == "add_channel":
        if step == "wait_channel_id":
            if not (text.startswith('-') and text[1:].isdigit()):
                bot.send_message(chat_id, "❌ ID канала должен начинаться с - и содержать только цифры!", reply_markup=create_back_keyboard())
                return
            state["channel_id"] = int(text)
            state["step"] = "wait_channel_link"
            bot.send_message(chat_id, "Введите ссылку на канал (https://...):", reply_markup=create_back_keyboard())
            return
        if step == "wait_channel_link":
            if not (text.startswith("http://") or text.startswith("https://")):
                bot.send_message(chat_id, "❌ Введите корректную ссылку на канал!", reply_markup=create_back_keyboard())
                return
            state["channel_link"] = text
            state["step"] = "wait_channel_name"
            bot.send_message(chat_id, "Введите название канала:", reply_markup=create_back_keyboard())
            return
        if step == "wait_channel_name":
            channel_id = state["channel_id"]
            channel_link = state["channel_link"]
            channel_name = text
            from db import get_channels, add_channel
            channels = get_channels()
            if any(str(c[0]) == str(channel_id) for c in channels):
                bot.send_message(chat_id, "🖤 Такой канал уже добавлен!", reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            add_channel(channel_id, channel_link, channel_name)
            reset_all_captcha()
            bot.send_message(chat_id, f"💚 Канал <b>{channel_name}</b> добавлен! ID: <code>{channel_id}</code>", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Удалить канал ---
    if mode == "remove_channel":
        if step == "wait_channel_id":
            if not (text.startswith('-') and text[1:].isdigit()):
                bot.send_message(chat_id, "❌ ID канала должен начинаться с - и содержать только цифры!", reply_markup=create_back_keyboard())
                return
            channel_id = int(text)
            from db import get_channels, remove_channel
            channels = get_channels()
            if not any(str(c[0]) == str(channel_id) for c in channels):
                bot.send_message(chat_id, "🖤 Такого канала нет!", reply_markup=create_back_keyboard())
                del admin_states[user_id]
                return
            remove_channel(channel_id)
            bot.send_message(chat_id, f"🖤 Канал с ID <code>{channel_id}</code> удалён!", parse_mode='HTML', reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return
    # --- Рассылка ---
    if mode == "broadcast":
        if step == "wait_broadcast_text":
            from db import get_all_users
            users = get_all_users()
            text_to_send = text
            success = 0
            fail = 0
            for row in users:
                uid = row[0]
                try:
                    bot.send_message(uid, text_to_send)
                    success += 1
                except Exception:
                    fail += 1
            bot.send_message(chat_id, f"📢 Рассылка завершена!\nУспешно: {success}\nОшибок: {fail}", reply_markup=create_back_keyboard())
            del admin_states[user_id]
            return

# --- Админ-панель ---
ADMIN_IDS = [7438900969, 821204149, 415990673]  # Пример: сюда можно добавить свои Telegram user_id

def is_admin(user_id):
    return user_id in ADMIN_IDS

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username or ""
    greetings = [
        "👋 Привет, {username}! Добро пожаловать в Maniac Info!",
        "💫 Рад тебя видеть, {username}!",
        "🔥 Здравствуй, {username}! Готов к поиску информации?",
        "✨ Приветствуем, {username}!"
    ]
    greet = random.choice(greetings).format(username=f"@{username}" if username else f"ID:{user_id}")
    short_desc = "<b>💚 Maniac Info — быстрый поиск по номеру и имени, рефералы, подписки, бонусы!</b>"
    bot.edit_message_text(
        f"{greet}\n\n{short_desc}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=create_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "about")
def handle_about(call: CallbackQuery):
    about_text = (
        "<b>💚 Maniac Info — бот для поиска информации</b>\n\n"
        "🖤 <b>Мощный инструмент для поиска и анализа данных в Telegram</b>\n\n"
        "<b>📱 Поиск по номеру телефона:</b>\n"
        "• Полная информация о владельце номера\n"
        "• Контакты, соцсети, мессенджеры\n"
        "• История активности и связанные аккаунты\n"
        "• Формат: <code>+7XXXXXXXXXX</code>\n\n"
        "<b>👤 Поиск по имени:</b>\n"
        "• Поиск пользователей по имени и фамилии\n"
        "• Найдет все связанные аккаунты и профили\n"
        "• Информация из различных источников\n"
        "• Поддерживает русские и английские имена\n\n"
        "<b>🔧 Возможности бота:</b>\n"
        "• 💚 Быстрый поиск в реальном времени\n"
        "• 🖤 Безопасная обработка данных\n"
        "• 💰 Подробные отчеты с результатами\n"
        "• 💸 Автоматическая система оплаты\n"
        "• 💚 Реферальная программа с бонусами\n"
        "• 🖤 Неограниченное количество запросов\n\n"
        "<b>💎 Преимущества:</b>\n"
        "• Высокая точность поиска\n"
        "• Обновляемая база данных\n"
        "• Мгновенные результаты\n"
        "• Простой и удобный интерфейс\n\n"
        "<b>🔑 Ключевые слова:</b> <code>поиск информации, пробив, анализ данных, поиск по номеру, поиск по имени, телеграм бот, информационный поиск, база данных, контакты, социальные сети</code>\n\n"
        "<i>Для возврата нажмите 'Назад'</i>"
    )
    bot.edit_message_text(
        about_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=create_back_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "start_search")
def handle_start_search(call: CallbackQuery):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "💚 <b>Выберите способ поиска:</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=create_search_method_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "shop")
def handle_shop(call: CallbackQuery):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "🛒 <b>Магазин подписок</b>\n\nВыберите вариант подписки:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=create_shop_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_tariff(call: CallbackQuery):
    user_id = call.from_user.id
    tariff = call.data.split("_", 1)[1]  # '7', '14', '30', '365', 'infinity'
    price = PRICES.get(tariff)
    if not price:
        bot.answer_callback_query(call.id, "❌ Неизвестный тариф!", show_alert=True) 
        return

    # Создание чека через CryptoPay
    try:
        invoice = crypto.create_invoice(
            asset="USDT",  # или другой asset, если нужно
            amount=price,
            description=f"Покупка подписки Maniac Info на {tariff} дней"
        )
        invoice_id = invoice["invoice_id"]
        pending_invoices[user_id] = {"invoice_id": invoice_id, "tariff": tariff}
        pay_url = invoice["pay_url"]
        check_keyboard = InlineKeyboardMarkup()
        check_keyboard.add(
            InlineKeyboardButton("💸 Оплатить", url=pay_url),
            InlineKeyboardButton("✅ Проверить оплату", callback_data="check_payment")
        )

        bot.edit_message_text(
            f"💸 <b>Оплата подписки</b>\n\n"
            f"Тариф: <b>{tariff} дней</b>\n"
            f"Сумма: <b>{price}$</b>\n",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML',
            reply_markup=check_keyboard
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка создания чека: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "check_payment")
def handle_check_payment(call: CallbackQuery):
    user_id = call.from_user.id
    invoice_info = pending_invoices.get(user_id)
    if not invoice_info:
        bot.answer_callback_query(call.id, "❌ Нет ожидающих оплат!", show_alert=True)
        print(f"[LOG] Нет ожидающих оплат для user_id={user_id}")
        return

    invoice_id = invoice_info["invoice_id"]
    tariff = invoice_info["tariff"]
    print(f"[LOG] Проверка оплаты: user_id={user_id}, invoice_id={invoice_id}, tariff={tariff}")

    try:
        old_invoice = crypto.get_invoices(invoice_ids=invoice_id)
        print(f"[LOG] Ответ get_invoices: {old_invoice}")
        if old_invoice and "items" in old_invoice and old_invoice["items"]:
            status = old_invoice["items"][0]["status"]
            print(f"[LOG] Статус инвойса: {status}")
            if status == "paid":
                days = 9999 if tariff == "infinity" else int(tariff)
                expires_at = time.time() + days * 24 * 60 * 60
                add_subscription(user_id, expires_at, user_id)
                bot.edit_message_text(
                    "💚 Оплата подтверждена! Вам выдана подписка.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode='HTML',
                    reply_markup=create_back_keyboard()
                )
                del pending_invoices[user_id]
                print(f"[LOG] Подписка выдана user_id={user_id} на {days} дней")
            else:
                bot.answer_callback_query(call.id, "🖤 Оплата не получена. Если вы оплатили — подождите 1-2 минуты и попробуйте снова.", show_alert=True)
                print(f"[LOG] Оплата не получена для invoice_id={invoice_id}, user_id={user_id}, статус={status}")
        else:
            bot.answer_callback_query(call.id, "❌ Не удалось получить информацию о платеже!", show_alert=True)
            print(f"[LOG] Не удалось получить информацию о платеже для invoice_id={invoice_id}, user_id={user_id}")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка проверки: {e}", show_alert=True)
        print(f"[LOG] Ошибка проверки оплаты: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "free_sub")
def handle_free_sub(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username or ""
    text = (
        "🆓 <b>Бесплатная подписка</b>\n\n"
        "Чтобы получить <b>7 дней подписки</b> бесплатно, добавь <b>@ManiacInfoBot</b> в свой ник Telegram.\n\n"
        "После этого нажми кнопку ниже для проверки.\n\n"
        "<i>Воспользоваться можно только 1 раз!</i>"
    )
    check_kb = InlineKeyboardMarkup()
    check_kb.add(InlineKeyboardButton("✅ Проверить ник", callback_data="check_free_sub"))
    check_kb.add(InlineKeyboardButton("🖤 Назад", callback_data="back_to_main"))
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=check_kb
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_free_sub")
def handle_check_free_sub(call: CallbackQuery):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or ""
    last_name = call.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".lower()
    print(f"[LOG] Проверка бесплатной подписки: user_id={user_id}, full_name={full_name}")
    if has_free_sub(user_id):
        bot.answer_callback_query(call.id, "❌ Вы уже получали бесплатную подписку!", show_alert=True)
        return
    if "maniacinfobot" in full_name:
        # Выдаём подписку на 7 дней
        expires_at = time.time() + 7 * 24 * 60 * 60
        add_subscription(user_id, expires_at, user_id)
        set_free_sub_used(user_id)
        bot.edit_message_text(
            "💚 Поздравляем! Бесплатная подписка на 7 дней активирована.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML',
            reply_markup=create_back_keyboard()
        )
        print(f"[LOG] Бесплатная подписка выдана user_id={user_id}")
    else:
        bot.answer_callback_query(call.id, "❌ В вашем нике нет @ManiacInfoBot!", show_alert=True)

def log_search_for_admins(user_id, username, search_type, query, result):
    """Отправляет логи о поисках админам"""
    try:
        # Список админов (можно вынести в конфиг)
        admin_ids = [7438900969]  # Добавьте сюда ID админов
        
        # Создаем сообщение для админов
        log_message = f"""
🔍 ЛОГ ПОИСКА

👤 Пользователь: {username} (ID: {user_id})
🔎 Тип поиска: {search_type}
📱 Запрос: {query}
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
        """
        
        # Отправляем лог всем админам
        for admin_id in admin_ids:
            try:
                bot.send_message(admin_id, log_message)
            except Exception as e:
                print(f"❌ Ошибка отправки лога админу {admin_id}: {e}")
                
    except Exception as e:
        print(f"❌ Ошибка логирования: {e}")

def detect_database_sources(result):
    """Определяет источники баз данных в результате поиска"""
    databases = []
    
    import re
    
    # Ищем паттерн: эмодзи + название + [дата]:
    pattern = r'([📱🏥📚🇷🇺📗🎽🏛📧🚘🎉👳‍📱📡🌍📍📄📅📊📈📉📋📌📎📏📐📑📒📓📔📕📖📗📘📙📚📛📜📝📞📟📠📡📢📣📤📥📦📧📨📩📪📫📬📭📮📯📰📱📲📳📴📵📶📷📸📹📺📻📼📽📾📿🔀🔁🔂🔃🔄🔅🔆🔇🔈🔉🔊🔋🔌🔍🔎🔏🔐🔑🔒🔓🔔🔕🔖🔗🔘🔙🔚🔛🔜🔝🔞🔟🔠🔡🔢🔣🔤🔥🔦🔧🔨🔩🔪🔫🔬🔭🔮🔯🔰🔱🔲🔳🔴🔵🔶🔷🔸🔹🔺🔻🔼🔽🔾🔿🕀🕁🕂🕃🕄🕅🕆🕇🕈🕉🕊🕋🕌🕍🕎🕏🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛🕜🕝🕞🕟🕠🕡🕢🕣🕤🕥🕦🕧🕨🕩🕪🕫🕬🕭🕮🕯🕰🕱🕲🕳🕴🕵🕶🕷🕸🕹🕺🕻🕼🕽🕾🕿🖀🖁🖂🖃🖄🖅🖆🖇🖈🖉🖊🖋🖌🖍🖎🖏🖐🖑🖒🖓🖔🖕🖖🖗🖘🖙🖚🖛🖜🖝🖞🖟🖠🖡🖢🖣🖤🖥🖦🖧🖨🖩🖪🖫🖬🖭🖮🖯🖰🖱🖲🖳🖴🖵🖶🖷🖸🖹🖺🖻🖼🖽🖾🖿🗀🗁🗂🗃🗄🗅🗆🗇🗈🗉🗊🗋🗌🗍🗎🗏🗐🗑🗒🗓🗔🗕🗖🗗🗘🗙🗚🗛🗜🗝🗞🗟🗠🗡🗢🗣🗤🗥🗦🗧🗨🗩🗪🗫🗬🗭🗮🗯🗰🗱🗲🗳🗴🗵🗶🗷🗸🗹🗺🗻🗼🗽🗾🗿])\s+([^[]+)\s*\[([^\]]+)\]:'
    
    matches = re.findall(pattern, result)
    for match in matches:
        emoji, db_name, date = match
        databases.append({
            'emoji': emoji,
            'name': db_name.strip(),
            'date': date.strip(),
            'full_match': f'{emoji} {db_name.strip()} [{date.strip()}]:'
        })
    
    return databases

def clean_result_for_telegram(result):
    """Очищает результат от HTML тегов для безопасной отправки в Telegram"""
    if isinstance(result, str):
        if "роюсь в данных" in result.lower():
            return "❌ Информация не найдена"
        else:
            # Убираем ** и очищаем от HTML тегов
            result = result.replace("**", "")
            result = re.sub(r'<[^>]+>', '', result)
            # Убираем обратные кавычки `
            result = result.replace('`', '')
            # Убираем все оставшиеся HTML символы
            result = result.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return result
    return result

def process_bot_file(file_path):
    """Обрабатывает файл от бота, извлекая текст"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # Удаляем временный файл
        import os
        os.remove(file_path)
        
        # Проверяем, не HTML ли это файл
        if file_content.strip().startswith('<!DOCTYPE html>') or file_content.strip().startswith('<html'):
            print("📄 Обнаружен HTML файл, извлекаем текст...")
            # Простая очистка HTML тегов
            # Убираем HTML теги
            clean_content = re.sub(r'<[^>]+>', '', file_content)
            # Убираем лишние пробелы
            clean_content = re.sub(r'\s+', ' ', clean_content).strip()
            # Ограничиваем размер
            if len(clean_content) > 4000:
                clean_content = clean_content[:4000] + "..."
            print(f"📄 Очищенное содержимое: {clean_content[:200]}...")
            return clean_content
        else:
            # Ограничиваем размер обычного текста
            if len(file_content) > 4000:
                file_content = file_content[:4000] + "..."
            print(f"📄 Содержимое файла: {file_content[:200]}...")
            return file_content
    except Exception as e:
        print(f"❌ Ошибка обработки файла: {e}")
        return "❌ Ошибка обработки файла"

def send_error_message(chat_id, message_id, error_text):
    """Безопасно отправляет сообщение об ошибке без HTML"""
    try:
        bot.edit_message_text(f"❌ Ошибка поиска: {error_text}", chat_id=chat_id, message_id=message_id, reply_markup=create_back_keyboard())
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения об ошибке: {e}")

if __name__ == "__main__":
    print("💚 Запуск бота...")
    print("🖤 Инициализация Telethon клиента...")
    
    # Инициализируем Telethon клиент
    if init_telethon_client():
        print("💚 Бот готов к работе!")
        bot.polling(none_stop=True)
    else:
        print("🖤 Не удалось инициализировать Telethon клиент!")
        print("💚 Проверьте session_string.txt и API credentials")
