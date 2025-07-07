#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы с коэффициентами приемки WB
Проверяет новый endpoint /api/v1/acceptance/coefficients
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from wb_api import WildberriesAPI, AcceptanceCoefficient
from config import config

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Загружены переменные из .env файла")
except ImportError:
    print("⚠️ python-dotenv не установлен")

config.wb_api_key = os.getenv("WB_API_KEY", config.wb_api_key)


async def test_all_warehouses_coefficients():
    """
    Тестируем получение коэффициентов для всех складов
    Это может быть долгий запрос, но даст полную картину
    """
    print("\n" + "="*60)
    print("📊 ТЕСТ КОЭФФИЦИЕНТОВ ДЛЯ ВСЕХ СКЛАДОВ")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        print("🔄 Запрашиваем коэффициенты для всех складов...")
        print("   (Это может занять некоторое время из-за rate limiting)")
        
        coefficients = await api.get_acceptance_coefficients()
        
        print(f"✅ Получено {len(coefficients)} записей коэффициентов")
        
        if coefficients:
            # Анализируем полученные данные
            unique_warehouses = set(c.warehouse_id for c in coefficients)
            unique_dates = set(c.date.date() for c in coefficients)
            available_slots = [c for c in coefficients if c.is_slot_available()]
            
            print(f"📋 Статистика:")
            print(f"  • Уникальных складов: {len(unique_warehouses)}")
            print(f"  • Уникальных дат: {len(unique_dates)}")
            print(f"  • Доступных слотов: {len(available_slots)}")
            
            # Показываем примеры разных типов коэффициентов
            print(f"\n📊 Примеры коэффициентов:")
            
            # Группируем по коэффициентам
            coef_groups = {}
            for c in coefficients[:20]:  # Берем первые 20 для примера
                coef = c.coefficient
                if coef not in coef_groups:
                    coef_groups[coef] = []
                coef_groups[coef].append(c)
            
            for coef, items in sorted(coef_groups.items()):
                print(f"\n  Коэффициент {coef}:")
                for item in items[:3]:  # Показываем первые 3 примера
                    status = "✅ ДОСТУПЕН" if item.is_slot_available() else "❌ НЕДОСТУПЕН"
                    print(f"    {status} | {item.warehouse_name} | {item.box_type_name} | {item.date.strftime('%d.%m.%Y')}")
            
            # Сохраняем данные для анализа
            coefficients_data = []
            for c in coefficients:
                coefficients_data.append({
                    "date": c.date.isoformat(),
                    "coefficient": c.coefficient,
                    "warehouse_id": c.warehouse_id,
                    "warehouse_name": c.warehouse_name,
                    "allow_unload": c.allow_unload,
                    "box_type_name": c.box_type_name,
                    "box_type_id": c.box_type_id,
                    "is_available": c.is_slot_available(),
                    "is_sorting_center": c.is_sorting_center
                })
            
            with open("coefficients_all_warehouses.json", "w", encoding="utf-8") as f:
                json.dump(coefficients_data, f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 Все данные сохранены в coefficients_all_warehouses.json")
            
        return len(coefficients) > 0
        
    except Exception as e:
        print(f"❌ Ошибка при получении коэффициентов: {e}")
        return False


async def test_specific_warehouses_coefficients():
    """
    Тестируем получение коэффициентов для конкретных складов
    Используем несколько популярных складов из наших предыдущих тестов
    """
    print("\n" + "="*60)
    print("🏢 ТЕСТ КОЭФФИЦИЕНТОВ ДЛЯ КОНКРЕТНЫХ СКЛАДОВ")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    # Берем несколько складов из предыдущих тестов
    test_warehouses = [218987, 204939, 206236]  # Алматы, Астана, Белые Столбы
    
    try:
        print(f"🔄 Запрашиваем коэффициенты для складов: {test_warehouses}")
        
        coefficients = await api.get_acceptance_coefficients(test_warehouses)
        
        print(f"✅ Получено {len(coefficients)} записей")
        
        if coefficients:
            # Группируем по складам
            by_warehouse = {}
            for c in coefficients:
                wh_id = c.warehouse_id
                if wh_id not in by_warehouse:
                    by_warehouse[wh_id] = []
                by_warehouse[wh_id].append(c)
            
            print(f"\n📋 Детальная информация по складам:")
            
            for wh_id, wh_coefficients in by_warehouse.items():
                first_coef = wh_coefficients[0]
                print(f"\n🏢 {first_coef.warehouse_name} (ID: {wh_id})")
                
                # Группируем по датам для этого склада
                by_date = {}
                for c in wh_coefficients:
                    date_key = c.date.date()
                    if date_key not in by_date:
                        by_date[date_key] = []
                    by_date[date_key].append(c)
                
                # Показываем ближайшие несколько дней
                for date_key in sorted(by_date.keys())[:7]:  # Первые 7 дней
                    day_coefficients = by_date[date_key]
                    available_count = sum(1 for c in day_coefficients if c.is_slot_available())
                    
                    print(f"  📅 {date_key.strftime('%d.%m.%Y')}: {len(day_coefficients)} типов упаковки, {available_count} доступных")
                    
                    # Показываем детали доступных слотов
                    for c in day_coefficients:
                        if c.is_slot_available():
                            print(f"    ✅ {c.box_type_name} (коэф: {c.coefficient})")
                        else:
                            print(f"    ❌ {c.box_type_name} (коэф: {c.coefficient}, разгрузка: {c.allow_unload})")
        
        return len(coefficients) > 0
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


async def analyze_available_slots():
    """
    Анализируем доступные слоты для понимания паттернов
    """
    print("\n" + "="*60)
    print("🔍 АНАЛИЗ ДОСТУПНЫХ СЛОТОВ")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        print("🔄 Получаем коэффициенты для анализа...")
        coefficients = await api.get_acceptance_coefficients()
        
        if not coefficients:
            print("⚠️ Нет данных для анализа")
            return False
        
        # Фильтруем только доступные слоты
        available_slots = [c for c in coefficients if c.is_slot_available()]
        
        print(f"📊 Анализ доступности:")
        print(f"  • Всего записей: {len(coefficients)}")
        print(f"  • Доступных слотов: {len(available_slots)}")
        print(f"  • Процент доступности: {(len(available_slots) / len(coefficients) * 100):.1f}%")
        
        if available_slots:
            # Анализ по типам упаковки
            box_types = {}
            for slot in available_slots:
                box_type = slot.box_type_name
                if box_type not in box_types:
                    box_types[box_type] = 0
                box_types[box_type] += 1
            
            print(f"\n📦 Доступность по типам упаковки:")
            for box_type, count in sorted(box_types.items(), key=lambda x: x[1], reverse=True):
                print(f"  • {box_type}: {count} слотов")
            
            # Анализ по датам
            dates_analysis = {}
            for slot in available_slots:
                date_key = slot.date.date()
                if date_key not in dates_analysis:
                    dates_analysis[date_key] = 0
                dates_analysis[date_key] += 1
            
            print(f"\n📅 Доступность по датам (первые 7 дней):")
            for date_key in sorted(dates_analysis.keys())[:7]:
                count = dates_analysis[date_key]
                print(f"  • {date_key.strftime('%d.%m.%Y')}: {count} доступных слотов")
            
            # Анализ по складам
            warehouse_analysis = {}
            for slot in available_slots:
                wh_name = slot.warehouse_name
                if wh_name not in warehouse_analysis:
                    warehouse_analysis[wh_name] = 0
                warehouse_analysis[wh_name] += 1
            
            print(f"\n🏢 ТОП-10 складов по доступности:")
            top_warehouses = sorted(warehouse_analysis.items(), key=lambda x: x[1], reverse=True)[:10]
            for wh_name, count in top_warehouses:
                print(f"  • {wh_name}: {count} доступных слотов")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
        return False


async def test_rate_limiting_coefficients():
    """
    Тестируем rate limiting для endpoint коэффициентов
    Должно быть не более 6 запросов в минуту
    """
    print("\n" + "="*60)
    print("⏱️ ТЕСТ RATE LIMITING ДЛЯ КОЭФФИЦИЕНТОВ")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    print("🔄 Выполняем 3 запроса подряд к coefficients endpoint...")
    print("   (Должны видеть задержки, т.к. лимит 6 запросов/минуту)")
    
    start_time = asyncio.get_event_loop().time()
    
    # Используем небольшой список складов для быстрых запросов
    test_warehouses = [218987]
    
    for i in range(3):
        try:
            print(f"  Запрос {i+1}...", end=" ")
            request_start = asyncio.get_event_loop().time()
            
            coefficients = await api.get_acceptance_coefficients(test_warehouses)
            
            request_time = asyncio.get_event_loop().time() - request_start
            total_elapsed = asyncio.get_event_loop().time() - start_time
            
            print(f"✅ Готово за {request_time:.1f}с (всего {total_elapsed:.1f}с, записей: {len(coefficients)})")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    total_time = asyncio.get_event_loop().time() - start_time
    print(f"\n⏱️ Общее время: {total_time:.1f}с")
    
    # Для 6 запросов в минуту интервал должен быть ~10 секунд
    if total_time >= 20:  # 3 запроса с интервалом ~10 сек
        print("✅ Rate limiting для коэффициентов работает!")
        return True
    else:
        print("⚠️ Rate limiting может работать неправильно")
        return False


async def main():
    """
    Основная функция тестирования коэффициентов приемки
    """
    print("📊 ТЕСТИРОВАНИЕ КОЭФФИЦИЕНТОВ ПРИЕМКИ WB")
    print("="*60)
    print("Проверяем новый endpoint /api/v1/acceptance/coefficients")
    print("="*60)
    
    if not config.wb_api_key:
        print("❌ WB API ключ не найден!")
        return
    
    tests = [
        ("Коэффициенты для конкретных складов", test_specific_warehouses_coefficients),
        ("Анализ доступных слотов", analyze_available_slots),
        ("Rate limiting для коэффициентов", test_rate_limiting_coefficients),
        ("Коэффициенты для всех складов", test_all_warehouses_coefficients),  # Самый долгий тест в конце
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Тест: {test_name}")
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"💥 Критическая ошибка: {e}")
            results.append((test_name, False))
    
    # Итоги
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ КОЭФФИЦИЕНТОВ")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
        print(f"{status}: {test_name}")
    
    print(f"\n🎯 Итого: {passed}/{len(results)} тестов пройдено")
    
    if passed >= 3:
        print("🎉 Коэффициенты приемки работают! Теперь можем делать полноценный мониторинг.")
        print("💡 Проверьте JSON файлы для детального анализа данных.")
    else:
        print("⚠️ Есть проблемы с получением коэффициентов.")


if __name__ == "__main__":
    asyncio.run(main())