#!/usr/bin/env python3
"""
Полное тестирование цикла мониторинга с реальными данными заказчика
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor import SlotMonitor
from config import config

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env файл загружен")
except ImportError:
    pass

# Настраиваем конфигурацию из переменных окружения
config.wb_api_key = os.getenv("WB_API_KEY", config.wb_api_key)
config.google_sheets_url = os.getenv("GOOGLE_SHEETS_URL", config.google_sheets_url)

async def test_real_monitoring_cycle():
    """
    Тестируем полный цикл мониторинга с реальными данными заказчика
    """
    print("🚀 ФИНАЛЬНОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ МОНИТОРИНГА")
    print("="*60)
    
    # Проверяем готовность конфигурации
    if not config.wb_api_key:
        print("❌ WB API ключ не найден! Установите WB_API_KEY в .env")
        return False
    
    if not config.google_sheets_url:
        print("❌ URL таблицы не найден! Установите GOOGLE_SHEETS_URL в .env")
        return False
    
    print("✅ Конфигурация готова к тестированию")
    
    # Создаем экземпляр монитора
    monitor = SlotMonitor()
    
    print(f"\n📊 ЭТАП 1: Чтение задач из Google Sheets")
    print("-" * 50)
    
    try:
        # Читаем задачи из таблицы заказчика
        tasks = await monitor.sheets_parser.get_monitoring_tasks()
        print(f"✅ Успешно загружено {len(tasks)} задач из таблицы")
        
        if not tasks:
            print("⚠️ В таблице нет задач для мониторинга")
            return False
        
        # Показываем детали каждой задачи
        for i, task in enumerate(tasks, 1):
            print(f"\n📦 Задача {i}:")
            print(f"  • Баркод товара: {task.barcode}")
            print(f"  • Количество для поставки: {task.quantity} единиц")
            
            # Преобразуем ID складов в понятные названия
            warehouse_names = []
            if 117986 in task.allowed_warehouses:
                warehouse_names.append("Казань")
            if 208277 in task.allowed_warehouses:
                warehouse_names.append("Невинномысск") 
            if 686 in task.allowed_warehouses:
                warehouse_names.append("Новосибирск")
            
            print(f"  • Целевые склады: {', '.join(warehouse_names)} (ID: {task.allowed_warehouses})")
            print(f"  • Период бронирования: с {task.date_from} до {task.date_to}")
            print(f"  • Максимальный коэффициент: x{task.max_coefficient}")
            print(f"  • Статус: {'🟢 Активна' if task.is_active else '🔴 Неактивна'}")
            print(f"  • Даты валидны: {'✅ Да' if task.is_date_valid() else '❌ Нет'}")
        
    except Exception as e:
        print(f"❌ Ошибка при чтении таблицы: {e}")
        return False
    
    print(f"\n🔍 ЭТАП 2: Проверка доступности слотов")
    print("-" * 50)
    
    # Фильтруем только активные задачи с валидными датами
    active_tasks = [task for task in tasks if task.is_active and task.is_date_valid()]
    print(f"📋 Активных задач для проверки: {len(active_tasks)}")
    
    if not active_tasks:
        print("⚠️ Нет активных задач с корректными датами")
        return False
    
    try:
        # Тестируем работу с реальными баркодами через WB API
        print("🔄 Проверяем доступность слотов для реальных товаров...")
        
        # Выполняем один полный цикл мониторинга
        await monitor._perform_monitoring_cycle()
        
        print("✅ Цикл мониторинга выполнен успешно")
        
    except Exception as e:
        print(f"❌ Ошибка в процессе мониторинга: {e}")
        print(f"   Детали ошибки: {type(e).__name__}")
        return False
    
    print(f"\n📈 ЭТАП 3: Анализ результатов")
    print("-" * 50)
    
    # Получаем статистику работы системы
    stats = await monitor.get_statistics()
    
    print(f"📊 Общая статистика:")
    print(f"  • Циклов проверки выполнено: {stats['checks_performed']}")
    print(f"  • Подходящих слотов найдено: {stats['slots_found']}")
    print(f"  • Ошибок в процессе: {stats['errors_count']}")
    print(f"  • Время последней проверки: {stats['last_check_str']}")
    print(f"  • Уведомлений отправлено: {stats['notified_slots_count']}")
    
    # Проверяем, создались ли файлы с найденными слотами
    today_str = datetime.now().strftime('%Y-%m-%d')
    slots_file = f"found_slots/slots_{today_str}.json"
    
    if os.path.exists(slots_file):
        try:
            with open(slots_file, "r", encoding="utf-8") as f:
                found_slots = json.load(f)
            
            print(f"\n🎯 Найденные слоты (сохранены в {slots_file}):")
            print(f"  • Общее количество: {len(found_slots)}")
            
            if found_slots:
                # Группируем по товарам для удобства анализа
                slots_by_barcode = {}
                for slot in found_slots:
                    barcode = slot.get('barcode', 'неизвестно')
                    if barcode not in slots_by_barcode:
                        slots_by_barcode[barcode] = []
                    slots_by_barcode[barcode].append(slot)
                
                for barcode, barcode_slots in slots_by_barcode.items():
                    print(f"\n  📦 Товар {barcode}:")
                    print(f"    Найдено слотов: {len(barcode_slots)}")
                    
                    # Показываем лучшие варианты
                    for i, slot in enumerate(barcode_slots[:3], 1):  # Первые 3 слота
                        warehouse_name = slot.get('warehouse_name', 'Неизвестно')
                        coefficient = slot.get('coefficient', -1)
                        date = slot.get('date', 'Неизвестно')
                        is_available = slot.get('is_available', False)
                        matches_criteria = slot.get('matches_criteria', False)
                        
                        status = "✅ ПОДХОДИТ" if matches_criteria else "⚠️ НЕ ПОДХОДИТ"
                        availability = "🟢 Доступен" if is_available else "🔴 Недоступен"
                        
                        print(f"    {i}. {status} | {availability}")
                        print(f"       Склад: {warehouse_name}")
                        print(f"       Коэффициент: x{coefficient}")
                        print(f"       Дата: {date[:10] if len(date) > 10 else date}")
                        
            else:
                print(f"  ℹ️ В этом цикле подходящих слотов не найдено")
                print(f"     Это нормально - хорошие слоты появляются редко")
                
        except Exception as e:
            print(f"⚠️ Ошибка анализа файла слотов: {e}")
    else:
        print(f"\nℹ️ Файл с найденными слотами не создан")
        print(f"   Это означает, что в данном цикле подходящих слотов не было")
    
    print(f"\n🎉 РЕЗУЛЬТАТ ТЕСТИРОВАНИЯ")
    print("="*60)
    
    if stats['errors_count'] == 0:
        print("✅ ВСЕ КОМПОНЕНТЫ СИСТЕМЫ РАБОТАЮТ КОРРЕКТНО!")
        print("🚀 Система готова к запуску постоянного мониторинга")
        print("💡 Для запуска используйте: python wb_monitor/main.py")
        
        if stats['slots_found'] > 0:
            print("🎯 БОНУС: В процессе тестирования найдены подходящие слоты!")
        else:
            print("ℹ️ Подходящих слотов в данный момент нет (это нормально)")
            
        return True
    else:
        print("⚠️ Обнаружены ошибки в работе системы")
        print("🔧 Требуется дополнительная отладка")
        return False

if __name__ == "__main__":
    asyncio.run(test_real_monitoring_cycle())