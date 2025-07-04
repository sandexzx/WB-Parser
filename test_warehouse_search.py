#!/usr/bin/env python3
"""
Специальный тест для диагностики поиска складов по названиям
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from wb_api import WildberriesAPI
from config import config

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env файл загружен")
except ImportError:
    pass

config.wb_api_key = os.getenv("WB_API_KEY", config.wb_api_key)

async def analyze_warehouse_names():
    """
    Анализируем все доступные склады, чтобы понять,
    как правильно искать Казань, Новосибирск и Невинномысск
    """
    print("🏢 АНАЛИЗ НАЗВАНИЙ СКЛАДОВ WB")
    print("="*60)
    
    if not config.wb_api_key:
        print("❌ WB API ключ не найден!")
        return
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        warehouses = await api.get_warehouses()
        print(f"📋 Получено {len(warehouses)} складов от WB API")
        
        # Ищем склады, содержащие наши целевые города
        target_cities = ["казань", "новосибирск", "невинномысск"]
        
        print(f"\n🔍 Поиск складов для городов: {target_cities}")
        print("-" * 60)
        
        for city in target_cities:
            print(f"\n🏙️ Поиск складов для '{city.title()}':")
            found_count = 0
            
            for warehouse in warehouses:
                wh_name = warehouse.get('name', '').lower()
                wh_id = warehouse.get('id', 0)
                
                # Различные способы поиска
                if city in wh_name:
                    found_count += 1
                    print(f"  ✅ ID: {wh_id:6} | {warehouse.get('name', '')}")
                    
                    # Дополнительная информация о складе
                    if 'address' in warehouse:
                        print(f"       Адрес: {warehouse['address']}")
                    if 'city' in warehouse:
                        print(f"       Город: {warehouse['city']}")
            
            if found_count == 0:
                print(f"  ❌ Прямых совпадений не найдено")
                
                # Ищем частичные совпадения
                print(f"  🔍 Ищем частичные совпадения:")
                for warehouse in warehouses:
                    wh_name = warehouse.get('name', '').lower()
                    wh_id = warehouse.get('id', 0)
                    
                    # Проверяем первые несколько букв
                    if city[:3] in wh_name or city[:4] in wh_name:
                        print(f"    💡 Похоже: ID: {wh_id:6} | {warehouse.get('name', '')}")
        
        print(f"\n📊 ОБЩАЯ СТАТИСТИКА СКЛАДОВ")
        print("-" * 60)
        
        # Анализируем структуру данных о складах
        if warehouses:
            example_warehouse = warehouses[0]
            print(f"🔑 Доступные поля в данных склада:")
            for key in example_warehouse.keys():
                print(f"  • {key}")
            
            print(f"\n📋 Пример склада:")
            for key, value in example_warehouse.items():
                print(f"  {key}: {value}")
        
        # Группируем склады по регионам/городам для понимания структуры
        city_groups = {}
        for warehouse in warehouses:
            wh_name = warehouse.get('name', '')
            # Извлекаем предполагаемый город из названия
            words = wh_name.split()
            if words:
                potential_city = words[0]  # Первое слово часто город
                if potential_city not in city_groups:
                    city_groups[potential_city] = 0
                city_groups[potential_city] += 1
        
        print(f"\n🏙️ ТОП-15 групп складов по первому слову в названии:")
        sorted_cities = sorted(city_groups.items(), key=lambda x: x[1], reverse=True)
        for city, count in sorted_cities[:15]:
            print(f"  {city}: {count} складов")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

async def test_specific_search():
    """
    Тестируем конкретный поиск для наших целевых городов
    с улучшенной логикой
    """
    print(f"\n🎯 ТЕСТИРОВАНИЕ УЛУЧШЕННОГО ПОИСКА")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        warehouses = await api.get_warehouses()
        target_names = ["Казань", "Новосибирск", "Невинномысск"]
        
        for target_name in target_names:
            print(f"\n🔍 Поиск для '{target_name}':")
            
            matches = []
            target_lower = target_name.lower().strip()
            
            for warehouse in warehouses:
                warehouse_name = warehouse.get('name', '')
                warehouse_id = warehouse.get('id', 0)
                warehouse_lower = warehouse_name.lower()
                
                # Различные способы сопоставления
                exact_match = target_lower == warehouse_lower
                target_in_warehouse = target_lower in warehouse_lower
                warehouse_in_target = warehouse_lower in target_lower
                
                # Очистка от общих слов
                clean_target = target_lower.replace('склад', '').replace('warehouse', '').strip()
                clean_warehouse = warehouse_lower.replace('склад', '').replace('warehouse', '').strip()
                
                city_match = (clean_target in clean_warehouse or 
                            clean_warehouse in clean_target) and len(clean_target) > 2
                
                if exact_match:
                    matches.append((warehouse_id, warehouse_name, 'ТОЧНОЕ'))
                elif target_in_warehouse:
                    matches.append((warehouse_id, warehouse_name, 'ГОРОД_В_НАЗВАНИИ'))
                elif warehouse_in_target:
                    matches.append((warehouse_id, warehouse_name, 'НАЗВАНИЕ_В_ГОРОДЕ'))
                elif city_match:
                    matches.append((warehouse_id, warehouse_name, 'ГОРОД_СОВПАДЕНИЕ'))
            
            if matches:
                print(f"  ✅ Найдено {len(matches)} совпадений:")
                for wh_id, wh_name, match_type in matches[:5]:  # Первые 5
                    print(f"    ID: {wh_id:6} | {match_type:15} | {wh_name}")
            else:
                print(f"  ❌ Совпадений не найдено")
    except Exception as e:
        print(f"❌ Ошибка в test_specific_search: {e}")

if __name__ == "__main__":
    asyncio.run(analyze_warehouse_names())
    asyncio.run(test_specific_search())
