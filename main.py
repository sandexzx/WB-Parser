# main.py - Точка входа
#!/usr/bin/env python3
"""
WB Slots Monitor - Главный файл запуска
Мониторинг слотов приемки товаров на Wildberries

Использование:
    python main.py                 # Запуск мониторинга
    python main.py --test          # Быстрый тест системы
    python main.py --check BARCODE # Ручная проверка товара
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Добавляем текущую папку в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from monitor import SlotMonitor, quick_test


def setup_environment():
    """
    Настройка окружения перед запуском
    """
    # Создаем папки если их нет
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    # Если есть .env файл, загружаем переменные окружения
    try:
        from dotenv import load_dotenv
        if os.path.exists(".env"):
            load_dotenv()
            print("✅ Загружены переменные из .env файла")
    except ImportError:
        pass  # python-dotenv не установлен


def print_banner():
    """
    Выводит красивый баннер при запуске
    """
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                    🚀 WB SLOTS MONITOR 🚀                    ║
║                                                              ║
║  Автоматический мониторинг слотов приемки на Wildberries     ║
║                                                              ║
║  📦 Отслеживает доступность складов                          ║
║  💰 Находит выгодные коэффициенты                            ║
║  ⚡ Мгновенные уведомления в Telegram                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


async def run_monitoring():
    """
    Запускает основной мониторинг
    """
    print("🚀 Запуск мониторинга слотов...")
    
    monitor = SlotMonitor()
    await monitor.start_monitoring()


async def run_test():
    """
    Запускает быстрый тест системы
    """
    print("🧪 Запуск тестирования системы...")
    await quick_test()


async def check_product(barcode: str):
    """
    Проверяет конкретный товар
    """
    print(f"🔍 Проверка товара {barcode}...")
    
    monitor = SlotMonitor()
    
    # Запрашиваем количество
    try:
        quantity = int(input("Введите количество товара: "))
    except ValueError:
        quantity = 1
    
    slots = await monitor.manual_check(barcode, quantity)
    
    print(f"\n📊 Результаты проверки:")
    for slot in slots:
        if slot.is_error:
            print(f"❌ {slot.barcode}: {slot.error}")
        else:
            print(f"✅ {slot.barcode}: найдено {len(slot.warehouses)} складов")


def validate_config():
    """
    Проверяет конфигурацию перед запуском
    """
    print("🔧 Проверка конфигурации...")
    
    # Проверяем обязательные файлы
    required_files = [
        "config.py",
        "wb_api.py", 
        "sheets_parser.py",
        "monitor.py"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    # Проверяем настройки
    if not config.wb_api_key:
        print("⚠️  WB API ключ не установлен")
        print("   Установите в переменную окружения WB_API_KEY")
        print("   Или измените config.py")
    
    if not config.google_sheets_url:
        print("⚠️  URL Google Sheets не установлен")
    
    if not config.telegram_bot_token:
        print("⚠️  Telegram Bot токен не установлен")
    
    print("✅ Базовая проверка завершена")
    return True


def main():
    """
    Главная функция с обработкой аргументов командной строки
    """
    parser = argparse.ArgumentParser(
        description="WB Slots Monitor - мониторинг слотов приемки Wildberries"
    )
    
    parser.add_argument(
        "--test", 
        action="store_true",
        help="Запустить быстрый тест системы"
    )
    
    parser.add_argument(
        "--check",
        type=str,
        metavar="BARCODE",
        help="Проверить конкретный товар по баркоду"
    )
    
    parser.add_argument(
        "--config",
        action="store_true", 
        help="Показать текущую конфигурацию"
    )
    
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Не показывать баннер при запуске"
    )
    
    args = parser.parse_args()
    
    # Настройка окружения
    setup_environment()
    
    # Показываем баннер
    if not args.no_banner:
        print_banner()
    
    # Проверяем конфигурацию
    if not validate_config():
        print("❌ Ошибки в конфигурации, исправьте их перед запуском")
        sys.exit(1)
    
    # Выполняем нужное действие
    if args.config:
        print("\n📋 Текущая конфигурация:")
        print(f"WB API ключ: {'✅ Установлен' if config.wb_api_key else '❌ Не установлен'}")
        print(f"Google Sheets: {'✅ Установлен' if config.google_sheets_url else '❌ Не установлен'}")
        print(f"Telegram Bot: {'✅ Установлен' if config.telegram_bot_token else '❌ Не установлен'}")
        print(f"Интервал проверки: {config.check_interval_seconds} сек")
        print(f"Rate limit: {config.max_requests_per_minute} запросов/мин")
        return
    
    elif args.test:
        asyncio.run(run_test())
        return
    
    elif args.check:
        asyncio.run(check_product(args.check))
        return
    
    else:
        # Основной режим - мониторинг
        try:
            asyncio.run(run_monitoring())
        except KeyboardInterrupt:
            print("\n👋 Остановка по Ctrl+C")
        except Exception as e:
            print(f"\n💥 Критическая ошибка: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()