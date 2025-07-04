#!/usr/bin/env python3
"""
Скрипт для запуска Telegram бота в отдельном процессе
Бот работает параллельно с основным мониторингом
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Добавляем текущую папку в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from telegram_bot import initialize_bot

logger = logging.getLogger(__name__)


class BotRunner:
    """Класс для управления запуском и остановкой бота"""
    
    def __init__(self):
        self.bot = None
        self.running = False
    
    async def start_bot(self):
        """Запускает бота"""
        logger.info("🚀 Запуск Telegram бота...")
        
        # Инициализируем бота
        self.bot = await initialize_bot()
        if not self.bot:
            logger.error("❌ Не удалось инициализировать бота")
            return
        
        self.running = True
        
        try:
            # Запускаем в режиме polling
            await self.bot.start_polling()
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise
        finally:
            self.running = False
    
    async def stop_bot(self):
        """Останавливает бота"""
        if self.bot and self.running:
            logger.info("🛑 Остановка Telegram бота...")
            await self.bot.stop()
            self.running = False
    
    def setup_signal_handlers(self):
        """Настраивает обработчики сигналов для корректного завершения"""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}, завершаем работу...")
            asyncio.create_task(self.stop_bot())
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Основная функция"""
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/telegram_bot.log"),
            logging.StreamHandler()
        ]
    )
    
    logger.info("=" * 50)
    logger.info("🤖 TELEGRAM BOT RUNNER STARTED")
    logger.info("=" * 50)
    
    # Проверяем конфигурацию
    if not config.telegram_bot_token:
        logger.error("❌ Telegram Bot Token не настроен")
        logger.error("   Установите переменную окружения TELEGRAM_BOT_TOKEN")
        return
    
    # Создаем и запускаем бота
    runner = BotRunner()
    runner.setup_signal_handlers()
    
    try:
        await runner.start_bot()
    except KeyboardInterrupt:
        logger.info("👋 Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await runner.stop_bot()
        logger.info("👋 Telegram бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())