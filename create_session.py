from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio

# Telegram API credentials (получите их на https://my.telegram.org)
API_ID = "27683579"  # Ваш API_ID
API_HASH = "a1d0fc7d0c9a41ff5e0ae6a6ed8e2dbb"  # Ваш API_HASH

async def create_session():
    """Создает session string для использования в боте"""
    print("🔑 Создание Telegram Session String")
    print("=" * 40)
    
    # Запрашиваем номер телефона
    phone = input("📱 Введите ваш номер телефона (+7XXXXXXXXXX): ").strip()
    
    if not phone.startswith('+'):
        print("❌ Неверный формат номера! Используйте формат: +7XXXXXXXXXX")
        return
    
    try:
        # Создаем клиент
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        print("🔗 Подключение к Telegram...")
        
        if not await client.is_user_authorized():
            print("📤 Отправляем код подтверждения...")
            await client.send_code_request(phone)
            
            # Запрашиваем код
            code = input("📱 Введите код подтверждения из Telegram: ").strip()
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                # Если нужен пароль от двухфакторной аутентификации
                if "password" in str(e).lower():
                    password = input("🔐 Введите пароль от двухфакторной аутентификации: ")
                    await client.sign_in(password=password)
                    print("✅ Авторизация успешна!")
                else:
                    print(f"❌ Ошибка авторизации: {e}")
                    return
        else:
            print("✅ Уже авторизован!")
        
        # Получаем session string
        session_string = client.session.save()
        
        print("\n" + "=" * 40)
        print("🎉 Session String создан успешно!")
        print("=" * 40)
        print(f"Session String:\n{session_string}")
        print("=" * 40)
        
        # Сохраняем в файл
        with open("session_string.txt", "w", encoding="utf-8") as f:
            f.write(session_string)
        
        print("💾 Session String сохранен в файл 'session_string.txt'")
        print("\n📝 Скопируйте этот session string в переменную SESSION_STRING в файле бота!")
        
        await client.disconnect()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("⚠️  Не забудьте установить API_ID и API_HASH в начале файла!")
    print("📋 Получите их на https://my.telegram.org")
    print()
    
    # Проверяем, установлены ли API_ID и API_HASH
    if API_ID == "YOUR_API_ID" or API_HASH == "YOUR_API_HASH":
        print("❌ Ошибка: Установите API_ID и API_HASH в начале файла!")
        print("1. Зайдите на https://my.telegram.org")
        print("2. Войдите в свой аккаунт")
        print("3. Создайте приложение")
        print("4. Скопируйте API_ID и API_HASH")
        print("5. Замените значения в начале файла")
    else:
        asyncio.run(create_session()) 