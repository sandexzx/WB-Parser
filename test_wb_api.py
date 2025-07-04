#!/usr/bin/env python3
"""
Исправленный тестовый скрипт для проверки работы с WB API
Учитывает особенности реального API, выявленные в первом тесте
"""

import asyncio
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from wb_api import WildberriesAPI, ProductInfo
from config import config

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print("✅ Загружены переменные из .env файла")
except ImportError:
    print("⚠️ python-dotenv не установлен, используем переменные окружения")

config.wb_api_key = os.getenv("WB_API_KEY", config.wb_api_key)


async def test_warehouses_detailed():
    """
    Детальный тест получения складов с исправленным парсингом
    """
    print("\n" + "="*60)
    print("🏢 ДЕТАЛЬНЫЙ ТЕСТ СКЛАДОВ (ИСПРАВЛЕННАЯ ВЕРСИЯ)")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        # Делаем прямой запрос, чтобы увидеть сырую структуру
        raw_response = await api._make_request("GET", "/api/v1/warehouses")
        
        print(f"📡 Тип ответа: {type(raw_response)}")
        
        if isinstance(raw_response, list):
            print(f"✅ API возвращает массив напрямую")
            print(f"📊 Количество складов: {len(raw_response)}")
            
            if raw_response:
                print(f"\n📋 Структура первого склада:")
                first_warehouse = raw_response[0]
                for key, value in first_warehouse.items():
                    print(f"  {key}: {value}")
                
                # Сохраняем данные для анализа
                with open("warehouses_fixed_data.json", "w", encoding="utf-8") as f:
                    json.dump(raw_response, f, ensure_ascii=False, indent=2)
                
                print(f"\n💾 Данные складов сохранены в warehouses_fixed_data.json")
                
        elif isinstance(raw_response, dict):
            print(f"✅ API возвращает объект")
            print(f"🔑 Ключи: {list(raw_response.keys())}")
            
            if "result" in raw_response:
                warehouses = raw_response["result"]
                print(f"📊 Количество складов в result: {len(warehouses)}")
        
        # Теперь тестируем наш исправленный метод
        warehouses = await api.get_warehouses()
        print(f"\n✅ Исправленный метод get_warehouses() работает!")
        print(f"📊 Получено складов: {len(warehouses)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


async def analyze_warehouse_structure():
    """
    Анализируем структуру данных о складах для понимания,
    какие поля доступны для нашей логики
    """
    print("\n" + "="*60)
    print("🔍 АНАЛИЗ СТРУКТУРЫ ДАННЫХ СКЛАДОВ")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    try:
        warehouses = await api.get_warehouses()
        
        if not warehouses:
            print("⚠️ Список складов пуст")
            return False
        
        # Анализируем поля
        print(f"📊 Всего складов: {len(warehouses)}")
        
        # Собираем все уникальные поля
        all_fields = set()
        for warehouse in warehouses:
            if isinstance(warehouse, dict):
                all_fields.update(warehouse.keys())
        
        print(f"\n🔑 Найденные поля в данных складов:")
        for field in sorted(all_fields):
            print(f"  • {field}")
        
        # Показываем примеры разных складов
        print(f"\n📋 Примеры складов:")
        for i, warehouse in enumerate(warehouses[:5]):
            print(f"\n  Склад {i+1}:")
            if isinstance(warehouse, dict):
                for key, value in warehouse.items():
                    print(f"    {key}: {value}")
            else:
                print(f"    Неожиданный тип данных: {type(warehouse)}")
        
        # Ищем поля, которые могут быть связаны с приемкой
        acceptance_related_fields = []
        for field in all_fields:
            field_lower = field.lower()
            if any(keyword in field_lower for keyword in 
                   ['accept', 'приемк', 'coeff', 'коэф', 'rate', 'тариф', 'price', 'цен']):
                acceptance_related_fields.append(field)
        
        if acceptance_related_fields:
            print(f"\n💰 Поля, потенциально связанные с приемкой:")
            for field in acceptance_related_fields:
                print(f"  • {field}")
        else:
            print(f"\n⚠️ Не найдено полей, явно связанных с коэффициентами приемки")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка анализа структуры: {e}")
        return False


async def test_acceptance_with_analysis():
    """
    Тестируем acceptance options с детальным анализом структуры ответа
    """
    print("\n" + "="*60)
    print("📦 ДЕТАЛЬНЫЙ АНАЛИЗ ACCEPTANCE OPTIONS")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    # Используем те же тестовые данные
    test_products = [
        ProductInfo(barcode="1234567890123", quantity=1),
    ]
    
    try:
        # Делаем прямой запрос для анализа структуры
        request_data = [{"quantity": 1, "barcode": "1234567890123"}]
        raw_response = await api._make_request("POST", "/api/v1/acceptance/options", 
                                              data=request_data)
        
        print(f"📡 Тип ответа: {type(raw_response)}")
        print(f"🔍 Содержимое ответа:")
        print(json.dumps(raw_response, indent=2, ensure_ascii=False))
        
        # Анализируем структуру ошибки
        if isinstance(raw_response, dict) and "result" in raw_response:
            result = raw_response["result"]
            if result and isinstance(result[0], dict):
                error_item = result[0]
                print(f"\n📋 Структура ответа с ошибкой:")
                for key, value in error_item.items():
                    print(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


async def test_rate_limiter_fixed():
    """
    Тестируем rate limiter с правильными задержками
    """
    print("\n" + "="*60)
    print("⏱️ ТЕСТ RATE LIMITING (ИСПРАВЛЕННЫЙ)")
    print("="*60)
    
    api = WildberriesAPI(config.wb_api_key)
    
    print("🔄 Выполняем 3 запроса с соблюдением лимитов...")
    
    start_time = asyncio.get_event_loop().time()
    
    for i in range(3):
        try:
            print(f"  Запрос {i+1}...", end=" ")
            request_start = asyncio.get_event_loop().time()
            
            warehouses = await api.get_warehouses()
            
            request_time = asyncio.get_event_loop().time() - request_start
            total_elapsed = asyncio.get_event_loop().time() - start_time
            
            print(f"✅ Готово за {request_time:.1f}с (всего {total_elapsed:.1f}с, складов: {len(warehouses)})")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    total_time = asyncio.get_event_loop().time() - start_time
    print(f"\n⏱️ Общее время: {total_time:.1f}с")
    
    # Проверяем, что задержки работают
    if total_time >= 4:  # Должно быть минимум 4 секунды для 3 запросов
        print("✅ Rate limiting работает корректно!")
        return True
    else:
        print("⚠️ Rate limiting может работать неправильно")
        return False


async def main():
    """
    Основная функция исправленного тестирования
    """
    print("🔧 ИСПРАВЛЕННОЕ ТЕСТИРОВАНИЕ WB API")
    print("="*60)
    print("Тестируем с учетом особенностей реального API")
    print("="*60)
    
    if not config.wb_api_key:
        print("❌ WB API ключ не найден в .env файле!")
        return
    
    tests = [
        ("Детальный тест складов", test_warehouses_detailed),
        ("Анализ структуры складов", analyze_warehouse_structure),
        ("Анализ acceptance options", test_acceptance_with_analysis),
        ("Тест rate limiting", test_rate_limiter_fixed),
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
    print("📊 РЕЗУЛЬТАТЫ ИСПРАВЛЕННОГО ТЕСТИРОВАНИЯ")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
        print(f"{status}: {test_name}")
    
    print(f"\n🎯 Итого: {passed}/{len(results)} тестов пройдено")
    
    if passed >= 3:
        print("🎉 Основная функциональность работает! Можно продолжать разработку.")
    else:
        print("⚠️ Есть серьезные проблемы, требующие решения.")


if __name__ == "__main__":
    asyncio.run(main())