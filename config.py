# config.py - Конфигурация
"""
Конфигурация для WB мониторинга слотов приемки
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    # WB API настройки
    wb_api_key: str = ""  # Сюда вставим ключ от заказчика
    wb_base_url: str = "https://supplies-api.wildberries.ru"
    
    # Rate limiting - WB разрешает максимум 30 запросов в минуту
    max_requests_per_minute: int = 30
    request_delay_seconds: float = 2.0  # 60/30 = 2 секунды между запросами
    
    # Google Sheets настройки
    google_sheets_credentials_file: str = "credentials.json"
    google_sheets_url: str = ""  # Ссылка на таблицу от заказчика
    
    # Telegram бот
    telegram_bot_token: str = ""  # Токен бота для уведомлений
    telegram_chat_id: str = ""   # ID чата для отправки уведомлений
    
    # База данных
    database_url: str = "sqlite:///wb_monitor.db"
    
    # Логирование
    log_level: str = "INFO"
    log_file: str = "wb_monitor.log"
    
    # Интервалы проверки
    check_interval_seconds: int = 120  # Проверяем каждые 2 минуты
    
    @classmethod
    def from_env(cls) -> 'Config':
        """
        Создает конфиг из переменных окружения
        Это удобно для продакшена - токены не светятся в коде
        """
        return cls(
            wb_api_key=os.getenv("WB_API_KEY", ""),
            google_sheets_url=os.getenv("GOOGLE_SHEETS_URL", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:///wb_monitor.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            google_sheets_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        )
    
    def validate(self) -> bool:
        """
        Проверяет, что все необходимые параметры заполнены
        """
        required_fields = [
            "wb_api_key", 
            "google_sheets_url", 
            "telegram_bot_token", 
            "telegram_chat_id"
        ]
        
        missing_fields = []
        for field in required_fields:
            if not getattr(self, field):
                missing_fields.append(field)
        
        if missing_fields:
            print(f"❌ Не заполнены обязательные поля: {', '.join(missing_fields)}")
            return False
        
        return True


# Глобальный экземпляр конфига
config = Config()
