#!/usr/bin/env python3
"""
Тест для проверки работы адаптивной системы мониторинга
"""
import asyncio
import logging
import time
import sys
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor import SlotMonitor
from config import config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_dynamic_pause_calculation():
    """
    Тестирует работу динамической паузы для равномерного распределения циклов
    """
    logger.info("🧪 Тест динамической паузы")
    
    monitor = SlotMonitor()
    
    # Симулируем быстрые циклы
    logger.info("📋 Тестируем быстрые циклы (должны равномерно распределяться)")
    total_start = time.time()
    
    for i in range(8):
        cycle_start = time.time()
        
        # Симулируем быстрый цикл (2 секунды)
        await asyncio.sleep(2)
        cycle_duration = time.time() - cycle_start
        
        # Вычисляем паузу
        pause = monitor._calculate_dynamic_pause(cycle_duration)
        current_time = time.time() - total_start
        
        logger.info(f"  Цикл {i+1}: {cycle_duration:.1f}с, пауза {pause:.1f}с (время {current_time:.1f}с)")
        
        if pause > 0:
            await asyncio.sleep(pause)
    
    total_duration = time.time() - total_start
    logger.info(f"📊 Общее время: {total_duration:.1f}с")
    logger.info("✅ Тест динамической паузы завершен")


def test_adaptive_monitoring_interval():
    """
    Тестирует вычисление адаптивного интервала мониторинга
    """
    logger.info("🧪 Тест адаптивного интервала мониторинга")
    
    # Имитируем класс монитора для тестирования
    class TestMonitor:
        def _calculate_adaptive_monitoring_interval(self, cycle_duration: float) -> float:
            if not config.enable_adaptive_monitoring:
                return config.check_interval_seconds
            
            # Если цикл быстрый (менее 10 секунд) - добавляем минимальную паузу
            if cycle_duration < 10:
                return max(1.0, config.min_monitoring_interval)
            
            # Если цикл медленный (больше 10 секунд) - запускаем следующий сразу
            return 0.1
    
    monitor = TestMonitor()
    
    # Тестируем разные сценарии
    test_cases = [
        (5.0, "быстрый цикл"),
        (8.0, "средне-быстрый цикл"),
        (12.0, "медленный цикл"),
        (30.0, "очень медленный цикл"),
    ]
    
    for cycle_duration, description in test_cases:
        interval = monitor._calculate_adaptive_monitoring_interval(cycle_duration)
        logger.info(f"  {description} ({cycle_duration}с) -> интервал {interval}с")
    
    logger.info("✅ Тест адаптивного интервала завершен")

async def test_optimized_sheets_parsing():
    """
    Тестирует оптимизированный парсинг Google Sheets
    """
    logger.info("🧪 Тест оптимизированного парсинга Google Sheets")
    
    try:
        from sheets_parser import GoogleSheetsParser
        
        # Создаем парсер
        parser = GoogleSheetsParser(
            credentials_file=config.google_credentials_file,
            sheet_url=config.google_sheets_url
        )
        
        # Тест 1: Первый запрос (без кэша)
        logger.info("📋 Тест 1: Первый запрос к таблице")
        start_time = time.time()
        
        tasks = await parser.get_monitoring_tasks()
        
        duration = time.time() - start_time
        logger.info(f"✅ Первый запрос завершен за {duration:.2f} секунд")
        logger.info(f"📦 Загружено {len(tasks)} задач мониторинга")
        
        # Показываем примеры задач
        if tasks:
            logger.info("📋 Примеры задач:")
            for i, task in enumerate(tasks[:3]):
                logger.info(f"  {i+1}. {task.barcode} - {task.quantity} шт, склады: {task.allowed_warehouses}")
        
        # Тест 2: Второй запрос (с кэшем)
        logger.info("📋 Тест 2: Второй запрос (должен использовать кэш)")
        start_time = time.time()
        
        tasks_cached = await parser.get_monitoring_tasks()
        
        duration_cached = time.time() - start_time
        logger.info(f"✅ Второй запрос завершен за {duration_cached:.2f} секунд")
        logger.info(f"📦 Загружено {len(tasks_cached)} задач из кэша")
        
        # Тест 3: Принудительная очистка кэша
        logger.info("📋 Тест 3: Очистка кэша и повторный запрос")
        parser.clear_cache()
        
        start_time = time.time()
        tasks_fresh = await parser.get_monitoring_tasks()
        duration_fresh = time.time() - start_time
        
        logger.info(f"✅ Запрос после очистки кэша завершен за {duration_fresh:.2f} секунд")
        logger.info(f"📦 Загружено {len(tasks_fresh)} задач")
        
        # Статистика
        logger.info("📊 Статистика производительности:")
        logger.info(f"  Первый запрос: {duration:.2f} сек")
        logger.info(f"  Запрос с кэшем: {duration_cached:.2f} сек (ускорение в {duration/duration_cached:.1f}x)")
        logger.info(f"  Запрос без кэша: {duration_fresh:.2f} сек")
        
        # Проверка консистентности
        if len(tasks) == len(tasks_cached) == len(tasks_fresh):
            logger.info("✅ Все запросы вернули одинаковое количество задач")
        else:
            logger.warning("⚠️ Количество задач отличается между запросами")
            
        logger.info("✅ Тест оптимизированного парсинга завершен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка во время теста парсинга: {e}")
        logger.info("ℹ️  Возможно, Google Sheets API недоступен или неправильно настроен")

async def main():
    """
    Основная функция для запуска всех тестов
    """
    logger.info("🚀 Запуск тестов адаптивной системы мониторинга")
    logger.info("=" * 50)
    
    # Тест 1: Динамическая пауза
    await test_dynamic_pause_calculation()
    logger.info("")
    
    # Тест 2: Адаптивный интервал мониторинга
    test_adaptive_monitoring_interval()
    logger.info("")
    
    # Тест 3: Оптимизированный парсинг Google Sheets
    await test_optimized_sheets_parsing()
    logger.info("")
    
    logger.info("🎉 Все тесты завершены!")
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())