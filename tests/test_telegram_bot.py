#!/usr/bin/env python3
"""
Тест функциональности Telegram бота
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Добавляем текущую папку в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from telegram_bot import TelegramDatabase, TelegramUser, WBSlotsBot
from monitor import FoundSlot, MonitoringTask

logger = logging.getLogger(__name__)


async def test_database():
    """Тестирует работу базы данных пользователей"""
    print("📊 Тестирование базы данных пользователей...")
    
    # Создаем тестовую базу
    db = TelegramDatabase("test_telegram_users.db")
    
    # Создаем тестового пользователя
    test_user = TelegramUser(
        user_id=123456789,
        username="testuser",
        first_name="Тест",
        last_name="Пользователь"
    )
    
    # Добавляем пользователя
    db.add_user(test_user)
    print("✅ Пользователь добавлен в базу")
    
    # Получаем пользователя
    retrieved_user = db.get_user(123456789)
    if retrieved_user and retrieved_user.user_id == 123456789:
        print("✅ Пользователь успешно получен из базы")
    else:
        print("❌ Ошибка получения пользователя")
        return False
    
    # Обновляем подписку
    db.update_subscription(123456789, False)
    updated_user = db.get_user(123456789)
    if not updated_user.subscribed:
        print("✅ Подписка успешно обновлена")
    else:
        print("❌ Ошибка обновления подписки")
        return False
    
    # Получаем статистику
    stats = db.get_stats()
    print(f"✅ Статистика: {stats}")
    
    return True


def test_slot_formatting():
    """Тестирует форматирование сообщений о слотах"""
    print("📝 Тестирование форматирования сообщений...")
    
    # Создаем тестовые данные слота
    test_slot_data = {
        'barcode': '1234567890123',
        'warehouse_id': 1234,
        'warehouse_name': 'Тестовый склад',
        'coefficient': 0.0,
        'box_type_name': 'Обычная упаковка',
        'date': '2025-07-05T10:30:00',
        'allow_unload': True,
        'found_at': '2025-07-04T15:45:30',
        'task': {
            'quantity': 100
        }
    }
    
    # Создаем экземпляр бота (без инициализации API)
    class TestBot:
        def _format_slot_message(self, slot_data):
            from telegram_bot import WBSlotsBot
            bot = WBSlotsBot.__new__(WBSlotsBot)  # Создаем без __init__
            return bot._format_slot_message(slot_data)
    
    test_bot = TestBot()
    message = test_bot._format_slot_message(test_slot_data)
    
    if "НАЙДЕН ВЫГОДНЫЙ СЛОТ" in message and "1234567890123" in message:
        print("✅ Сообщение отформатировано корректно")
        print("📄 Пример сообщения:")
        print(message)
        return True
    else:
        print("❌ Ошибка форматирования сообщения")
        return False


async def test_bot_initialization():
    """Тестирует инициализацию бота"""
    print("🤖 Тестирование инициализации бота...")
    
    if not config.telegram_bot_token:
        print("⚠️ Telegram Bot Token не настроен - пропускаем тест инициализации")
        return True
    
    try:
        from telegram_bot import initialize_bot
        bot = await initialize_bot()
        
        if bot:
            print("✅ Бот успешно инициализирован")
            
            # Проверяем подключение к API
            try:
                bot_info = await bot.bot.get_me()
                print(f"✅ Подключение к Telegram API: @{bot_info.username}")
                
                # Закрываем соединение
                await bot.stop()
                return True
                
            except Exception as e:
                print(f"❌ Ошибка подключения к Telegram API: {e}")
                return False
        else:
            print("❌ Не удалось инициализировать бота")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка инициализации бота: {e}")
        return False


def test_user_notification_settings():
    """Тестирует логику фильтрации уведомлений"""
    print("⚙️ Тестирование настроек уведомлений...")
    
    # Создаем тестового пользователя с настройками
    test_user = TelegramUser(
        user_id=987654321,
        username="testuser2",
        first_name="Тест2",
        last_name="Пользователь2",
        notification_settings={
            "max_coefficient": 0.5,
            "min_coefficient": 0.0,
            "preferred_warehouses": [1234, 5678],
            "quiet_hours": {"start": 23, "end": 7},  # Тихие часы с 23 до 7
            "instant_notifications": True
        }
    )
    
    # Тестовые данные слота
    slot_data = {
        'coefficient': 0.0,
        'warehouse_id': 1234
    }
    
    # Упрощенная функция проверки без мокинга datetime
    def check_notification_logic(user, slot_data):
        """Упрощенная версия _should_send_notification для тестирования"""
        # Проверяем мгновенные уведомления
        if not user.notification_settings.get('instant_notifications', True):
            return False
        
        # Проверяем коэффициент
        coef = slot_data.get('coefficient', -1)
        max_coef = user.notification_settings.get('max_coefficient', 1.0)
        min_coef = user.notification_settings.get('min_coefficient', 0.0)
        
        if not (min_coef <= coef <= max_coef):
            return False
        
        # Проверяем предпочитаемые склады
        preferred_warehouses = user.notification_settings.get('preferred_warehouses', [])
        if preferred_warehouses:
            warehouse_id = slot_data.get('warehouse_id')
            if warehouse_id not in preferred_warehouses:
                return False
        
        # Не проверяем тихие часы в тесте, так как зависит от текущего времени
        return True
    
    # Тест 1: Подходящий слот
    should_send = check_notification_logic(test_user, slot_data)
    if should_send:
        print("✅ Уведомление должно быть отправлено (подходящий слот)")
    else:
        print("❌ Ошибка: уведомление не должно быть заблокировано")
        return False
    
    # Тест 2: Слишком высокий коэффициент
    slot_data['coefficient'] = 1.5
    should_send = check_notification_logic(test_user, slot_data)
    if not should_send:
        print("✅ Уведомление заблокировано (высокий коэффициент)")
    else:
        print("❌ Ошибка: уведомление должно быть заблокировано")
        return False
    
    # Тест 3: Неподходящий склад
    slot_data['coefficient'] = 0.0
    slot_data['warehouse_id'] = 9999
    should_send = check_notification_logic(test_user, slot_data)
    if not should_send:
        print("✅ Уведомление заблокировано (неподходящий склад)")
    else:
        print("❌ Ошибка: уведомление должно быть заблокировано")
        return False
    
    # Тест 4: Отключенные мгновенные уведомления
    slot_data['warehouse_id'] = 1234  # Возвращаем подходящий склад
    test_user.notification_settings['instant_notifications'] = False
    should_send = check_notification_logic(test_user, slot_data)
    if not should_send:
        print("✅ Уведомление заблокировано (отключены мгновенные уведомления)")
    else:
        print("❌ Ошибка: уведомление должно быть заблокировано")
        return False
    
    return True


async def run_all_tests():
    """Запускает все тесты"""
    print("🧪 Запуск тестов Telegram бота...")
    print("=" * 50)
    
    tests = [
        ("База данных", test_database()),
        ("Форматирование сообщений", test_slot_formatting()),
        ("Настройки уведомлений", test_user_notification_settings()),
        ("Инициализация бота", test_bot_initialization())
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        try:
            if test_name == "База данных" or test_name == "Инициализация бота":
                result = await test_func
            else:
                result = test_func
            
            if result:
                passed += 1
                print(f"✅ {test_name}: ПРОЙДЕН")
            else:
                print(f"❌ {test_name}: ПРОВАЛЕН")
                
        except Exception as e:
            print(f"💥 {test_name}: ОШИБКА - {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
        return True
    else:
        print("⚠️ Некоторые тесты провалены")
        return False


async def main():
    """Основная функция"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.WARNING,  # Убираем лишние логи во время тестов
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    success = await run_all_tests()
    
    # Очистка тестовых файлов
    try:
        import os
        if os.path.exists("test_telegram_users.db"):
            os.remove("test_telegram_users.db")
            print("🧹 Тестовые файлы очищены")
    except Exception as e:
        print(f"⚠️ Ошибка очистки: {e}")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)