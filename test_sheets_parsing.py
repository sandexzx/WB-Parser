#!/usr/bin/env python3
"""
Тестовый скрипт для проверки парсинга Google Sheets в новом формате
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sheets_parser import GoogleSheetsParser
from config import config

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print(f"✅ .env файл загружен")
except ImportError:
    print("⚠️ Модуль python-dotenv не установлен. Переменные окружения из .env не будут загружены.")
    pass

# Инициализируем конфиг из переменных окружения
config = config.from_env()

async def test_sheets_parsing():
    """
    Тестируем парсинг таблицы заказчика
    """
    print("📊 ТЕСТИРОВАНИЕ ПАРСИНГА GOOGLE SHEETS")
    print("="*60)
    
    # URL таблицы от заказчика
    sheets_url = os.getenv("GOOGLE_SHEETS_URL", config.google_sheets_url)
    
    if not sheets_url:
        print("❌ URL таблицы не найден! Установите GOOGLE_SHEETS_URL в .env")
        return
    
    print(f"🔗 Используем таблицу: {sheets_url}") # Вот тут добавим вывод ссылки
    
    parser = GoogleSheetsParser(config.google_sheets_credentials_file, sheets_url)
    
    try:
        print("🔄 Читаем задачи из таблицы...")
        tasks = await parser.get_monitoring_tasks()
        
        print(f"✅ Загружено {len(tasks)} задач")
        
        for i, task in enumerate(tasks, 1):
            print(f"\n📦 Задача {i}:")
            print(f"  Баркод: {task.barcode}")
            print(f"  Количество: {task.quantity}")
            print(f"  Склады: {task.allowed_warehouses}")
            print(f"  Период: {task.date_from} - {task.date_to}")
            print(f"  Макс коэффициент: {task.max_coefficient}")
            print(f"  Активна: {task.is_active}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(test_sheets_parsing())
