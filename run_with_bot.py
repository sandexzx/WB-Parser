#!/usr/bin/env python3
"""
Скрипт для запуска полной системы мониторинга с Telegram ботом
Запускает мониторинг слотов и Telegram бота параллельно
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Добавляем текущую папку в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from monitor import SlotMonitor
from telegram_bot import initialize_bot

logger = logging.getLogger(__name__)


class WBSlotsSystem:
    """Основной класс для управления всей системой мониторинга"""
    
    def __init__(self):
        self.monitor = SlotMonitor()
        self.telegram_bot = None
        self.running = False
        self.tasks = []
    
    async def start_system(self):
        """Запускает всю систему мониторинга"""
        logger.info("🚀 Запуск системы мониторинга WB Slots с Telegram ботом")
        
        # Инициализируем Telegram бота
        self.telegram_bot = await initialize_bot()
        if self.telegram_bot:
            logger.info("✅ Telegram бот инициализирован")
        else:
            logger.warning("⚠️ Telegram бот не инициализирован - уведомления отключены")
        
        self.running = True
        
        try:
            # Создаем задачи для параллельного выполнения
            tasks = []
            
            # Задача мониторинга слотов
            monitoring_task = asyncio.create_task(
                self.monitor.start_monitoring(),
                name="monitoring"
            )
            tasks.append(monitoring_task)
            
            # Задача Telegram бота (если инициализирован)
            if self.telegram_bot:
                bot_task = asyncio.create_task(
                    self.telegram_bot.start_polling(),
                    name="telegram_bot"
                )
                tasks.append(bot_task)
            
            self.tasks = tasks
            
            # Ждем завершения любой из задач
            logger.info(f"🔄 Запущено {len(tasks)} задач...")
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Если одна из задач завершилась, останавливаем остальные
            logger.info("⚠️ Одна из задач завершилась, останавливаем систему...")
            
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Проверяем результаты завершенных задач
            for task in done:
                try:
                    result = await task
                    logger.info(f"✅ Задача {task.get_name()} завершена успешно")
                except Exception as e:
                    logger.error(f"❌ Задача {task.get_name()} завершена с ошибкой: {e}")
        
        except Exception as e:
            logger.error(f"❌ Ошибка в системе мониторинга: {e}")
            raise
        finally:
            self.running = False
    
    async def stop_system(self):
        """Останавливает систему мониторинга"""
        if self.running:
            logger.info("🛑 Остановка системы мониторинга...")
            
            # Отменяем все задачи
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            
            # Останавливаем Telegram бота
            if self.telegram_bot:
                await self.telegram_bot.stop()
            
            self.running = False
            logger.info("✅ Система остановлена")
    
    def setup_signal_handlers(self):
        """Настраивает обработчики сигналов для корректного завершения"""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}, завершаем работу...")
            asyncio.create_task(self.stop_system())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def get_system_status(self):
        """Возвращает статус системы"""
        monitor_stats = await self.monitor.get_statistics()
        
        if self.telegram_bot:
            from telegram_bot import get_bot_stats
            bot_stats = await get_bot_stats()
        else:
            bot_stats = {"error": "Бот не инициализирован"}
        
        return {
            "running": self.running,
            "monitor": monitor_stats,
            "telegram_bot": bot_stats,
            "tasks_count": len(self.tasks)
        }


async def main():
    """Основная функция"""
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler()
        ]
    )
    
    logger.info("=" * 60)
    logger.info("🚀 WB SLOTS MONITOR WITH TELEGRAM BOT STARTED")
    logger.info("=" * 60)
    
    # Проверяем конфигурацию
    if not config.validate():
        logger.error("❌ Ошибка конфигурации, завершение работы")
        return
    
    # Создаем и запускаем систему
    system = WBSlotsSystem()
    system.setup_signal_handlers()
    
    try:
        await system.start_system()
    except KeyboardInterrupt:
        logger.info("👋 Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await system.stop_system()
        logger.info("👋 Система полностью остановлена")


if __name__ == "__main__":
    asyncio.run(main())