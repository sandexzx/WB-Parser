"""
Telegram бот для уведомлений о найденных слотах WB
Поддерживает подписку/отписку пользователей и отправку уведомлений
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.formatting import Text, Bold, Italic, Code

from config import config

logger = logging.getLogger(__name__)


@dataclass
class TelegramUser:
    """Информация о пользователе бота"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    subscribed: bool = True
    created_at: datetime = None
    last_seen: datetime = None
    notification_settings: Dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_seen is None:
            self.last_seen = datetime.now()
        if self.notification_settings is None:
            self.notification_settings = {
                "max_coefficient": 1.0,
                "min_coefficient": 0.0,
                "preferred_warehouses": [],
                "quiet_hours": {"start": 23, "end": 7},
                "instant_notifications": True
            }


class TelegramDatabase:
    """Простая база данных для хранения пользователей бота"""
    
    def __init__(self, db_path: str = "telegram_users.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Создает таблицы в базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                subscribed BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notification_settings TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user: TelegramUser):
        """Добавляет нового пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, subscribed, created_at, last_seen, notification_settings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.user_id,
            user.username,
            user.first_name,
            user.last_name,
            user.subscribed,
            user.created_at,
            user.last_seen,
            json.dumps(user.notification_settings)
        ))
        
        conn.commit()
        conn.close()
    
    def get_user(self, user_id: int) -> Optional[TelegramUser]:
        """Получает пользователя по ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return TelegramUser(
                user_id=row[0],
                username=row[1],
                first_name=row[2],
                last_name=row[3],
                subscribed=bool(row[4]),
                created_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
                last_seen=datetime.fromisoformat(row[6]) if row[6] else datetime.now(),
                notification_settings=json.loads(row[7]) if row[7] else {}
            )
        return None
    
    def get_subscribed_users(self) -> List[TelegramUser]:
        """Возвращает список всех подписанных пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE subscribed = 1')
        rows = cursor.fetchall()
        
        conn.close()
        
        users = []
        for row in rows:
            users.append(TelegramUser(
                user_id=row[0],
                username=row[1],
                first_name=row[2],
                last_name=row[3],
                subscribed=bool(row[4]),
                created_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
                last_seen=datetime.fromisoformat(row[6]) if row[6] else datetime.now(),
                notification_settings=json.loads(row[7]) if row[7] else {}
            ))
        
        return users
    
    def update_subscription(self, user_id: int, subscribed: bool):
        """Обновляет статус подписки пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET subscribed = ?, last_seen = ? WHERE user_id = ?',
            (subscribed, datetime.now(), user_id)
        )
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE subscribed = 1')
        subscribed_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE last_seen > ?', 
                      (datetime.now() - timedelta(days=7),))
        active_users = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_users": total_users,
            "subscribed_users": subscribed_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users
        }


class WBSlotsBot:
    """Основной класс Telegram бота"""
    
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.database = TelegramDatabase()
        
        # Настройка обработчиков
        self._setup_handlers()
        
        # Статистика отправленных уведомлений
        self.notification_stats = {
            "sent_today": 0,
            "sent_total": 0,
            "failed_today": 0,
            "failed_total": 0,
            "last_notification": None
        }
    
    def _setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            await self._handle_start(message)
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            await self._handle_help(message)
        
        @self.dp.message(Command("subscribe"))
        async def cmd_subscribe(message: Message):
            await self._handle_subscribe(message)
        
        @self.dp.message(Command("unsubscribe"))
        async def cmd_unsubscribe(message: Message):
            await self._handle_unsubscribe(message)
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: Message):
            await self._handle_status(message)
        
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: Message):
            await self._handle_stats(message)
        
        @self.dp.message(Command("settings"))
        async def cmd_settings(message: Message):
            await self._handle_settings(message)
    
    async def _handle_start(self, message: Message):
        """Обработчик команды /start"""
        user_id = message.from_user.id
        
        # Создаем или обновляем пользователя
        user = TelegramUser(
            user_id=user_id,
            username=message.from_user.username or "",
            first_name=message.from_user.first_name or "",
            last_name=message.from_user.last_name or "",
            subscribed=True
        )
        
        self.database.add_user(user)
        
        welcome_text = f"""
🎯 <b>Добро пожаловать в WB Slots Monitor!</b>

Я буду уведомлять вас о найденных выгодных слотах приемки на Wildberries.

🔥 <b>Что я умею:</b>
• Мгновенные уведомления о слотах с коэффициентом 0-1
• Фильтрация по складам и датам
• Настройка персональных уведомлений
• Статистика найденных слотов

📱 <b>Команды:</b>
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/status - проверить статус подписки
/settings - настроить уведомления
/stats - статистика бота
/help - помощь

⚡ <b>Вы автоматически подписаны на уведомления!</b>
Слоты разбирают за секунды, поэтому уведомления приходят мгновенно.
        """
        
        await message.reply(welcome_text, parse_mode="HTML")
    
    async def _handle_help(self, message: Message):
        """Обработчик команды /help"""
        help_text = """
📖 <b>Помощь по боту WB Slots Monitor</b>

🎯 <b>Основные команды:</b>
/start - начать работу с ботом
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/status - проверить статус подписки
/settings - настроить уведомления
/stats - статистика бота

🔔 <b>Уведомления:</b>
Бот автоматически отправляет уведомления о найденных слотах с коэффициентом 0-1.
В уведомлении указывается:
• Баркод товара
• Название склада
• Коэффициент приемки
• Дата слота
• Тип упаковки

⚙️ <b>Настройки:</b>
• Максимальный коэффициент для уведомлений
• Предпочитаемые склады
• Тихие часы (когда не присылать уведомления)
• Мгновенные уведомления вкл/выкл

💡 <b>Советы:</b>
• Слоты разбирают очень быстро, действуйте мгновенно
• Следите за коэффициентами - 0 самый выгодный
• Настройте уведомления под свои потребности
        """
        
        await message.reply(help_text, parse_mode="HTML")
    
    async def _handle_subscribe(self, message: Message):
        """Обработчик команды /subscribe"""
        user_id = message.from_user.id
        
        # Проверяем, есть ли пользователь в базе
        user = self.database.get_user(user_id)
        if not user:
            # Создаем нового пользователя
            user = TelegramUser(
                user_id=user_id,
                username=message.from_user.username or "",
                first_name=message.from_user.first_name or "",
                last_name=message.from_user.last_name or "",
                subscribed=True
            )
            self.database.add_user(user)
        else:
            # Обновляем подписку
            self.database.update_subscription(user_id, True)
        
        await message.reply(
            "✅ <b>Подписка активирована!</b>\n\n"
            "Теперь вы будете получать уведомления о найденных слотах приемки.\n"
            "Используйте /settings для настройки уведомлений.",
            parse_mode="HTML"
        )
    
    async def _handle_unsubscribe(self, message: Message):
        """Обработчик команды /unsubscribe"""
        user_id = message.from_user.id
        
        self.database.update_subscription(user_id, False)
        
        await message.reply(
            "❌ <b>Подписка отключена</b>\n\n"
            "Вы больше не будете получать уведомления о слотах.\n"
            "Используйте /subscribe для возобновления подписки.",
            parse_mode="HTML"
        )
    
    async def _handle_status(self, message: Message):
        """Обработчик команды /status"""
        user_id = message.from_user.id
        user = self.database.get_user(user_id)
        
        if not user:
            await message.reply(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для начала работы."
            )
            return
        
        status_emoji = "✅" if user.subscribed else "❌"
        status_text = "активна" if user.subscribed else "отключена"
        
        status_info = f"""
📊 <b>Ваш статус в системе:</b>

{status_emoji} Подписка: <b>{status_text}</b>
👤 Имя: {user.first_name} {user.last_name}
📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}
🕒 Последняя активность: {user.last_seen.strftime('%d.%m.%Y %H:%M')}

⚙️ <b>Настройки уведомлений:</b>
• Макс. коэффициент: {user.notification_settings.get('max_coefficient', 1.0)}
• Мин. коэффициент: {user.notification_settings.get('min_coefficient', 0.0)}
• Тихие часы: {user.notification_settings.get('quiet_hours', {}).get('start', 23)}:00 - {user.notification_settings.get('quiet_hours', {}).get('end', 7)}:00
• Мгновенные уведомления: {'✅' if user.notification_settings.get('instant_notifications', True) else '❌'}

Используйте /settings для изменения настроек.
        """
        
        await message.reply(status_info, parse_mode="HTML")
    
    async def _handle_stats(self, message: Message):
        """Обработчик команды /stats"""
        user_stats = self.database.get_stats()
        
        stats_text = f"""
📈 <b>Статистика бота:</b>

👥 <b>Пользователи:</b>
• Всего: {user_stats['total_users']}
• Подписано: {user_stats['subscribed_users']}
• Активных за неделю: {user_stats['active_users']}
• Неактивных: {user_stats['inactive_users']}

📨 <b>Уведомления:</b>
• Отправлено сегодня: {self.notification_stats['sent_today']}
• Всего отправлено: {self.notification_stats['sent_total']}
• Ошибок сегодня: {self.notification_stats['failed_today']}
• Всего ошибок: {self.notification_stats['failed_total']}

⏰ Последнее уведомление: {self.notification_stats['last_notification'] or 'никогда'}
        """
        
        await message.reply(stats_text, parse_mode="HTML")
    
    async def _handle_settings(self, message: Message):
        """Обработчик команды /settings"""
        user_id = message.from_user.id
        user = self.database.get_user(user_id)
        
        if not user:
            await message.reply(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для начала работы."
            )
            return
        
        settings_text = """
⚙️ <b>Настройки уведомлений</b>

Для изменения настроек используйте команды:

🔢 <b>Коэффициенты:</b>
• <code>/set_max_coef 1.0</code> - максимальный коэффициент
• <code>/set_min_coef 0.0</code> - минимальный коэффициент

🏢 <b>Склады:</b>
• <code>/set_warehouses 1234,5678</code> - предпочитаемые склады

🔇 <b>Тихие часы:</b>
• <code>/set_quiet_hours 23 7</code> - не беспокоить с 23:00 до 07:00

⚡ <b>Мгновенные уведомления:</b>
• <code>/instant_on</code> - включить
• <code>/instant_off</code> - выключить

📊 Текущие настройки смотрите командой /status
        """
        
        await message.reply(settings_text, parse_mode="HTML")
    
    async def send_slot_notification(self, slot_data: Dict[str, Any], user_ids: List[int] = None):
        """
        Отправляет уведомление о найденном слоте
        
        Args:
            slot_data: Данные о слоте (из FoundSlot.to_dict())
            user_ids: Список ID пользователей для отправки (если None - всем подписанным)
        """
        if user_ids is None:
            users = self.database.get_subscribed_users()
        else:
            users = [self.database.get_user(uid) for uid in user_ids]
            users = [u for u in users if u and u.subscribed]
        
        if not users:
            logger.warning("Нет подписанных пользователей для отправки уведомления")
            return
        
        # Формируем сообщение
        message_text = self._format_slot_message(slot_data)
        
        # Отправляем уведомления
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                # Проверяем настройки пользователя
                if not self._should_send_notification(user, slot_data):
                    continue
                
                await self.bot.send_message(
                    chat_id=user.user_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user.user_id}: {e}")
                failed_count += 1
        
        # Обновляем статистику
        self.notification_stats["sent_today"] += sent_count
        self.notification_stats["sent_total"] += sent_count
        self.notification_stats["failed_today"] += failed_count
        self.notification_stats["failed_total"] += failed_count
        self.notification_stats["last_notification"] = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        logger.info(f"Уведомление отправлено {sent_count} пользователям, ошибок: {failed_count}")
    
    def _format_slot_message(self, slot_data: Dict[str, Any]) -> str:
        """Форматирует сообщение об найденном слоте"""
        
        # Определяем эмодзи для коэффициента
        coef = slot_data.get('coefficient', -1)
        if coef == 0:
            coef_emoji = "🔥"
        elif coef == 1:
            coef_emoji = "✅"
        else:
            coef_emoji = "💰"
        
        # Форматируем дату
        date_str = slot_data.get('date', '')
        if date_str:
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str = date_obj.strftime('%d.%m.%Y')
            except:
                pass
        
        message = f"""
🎯 <b>НАЙДЕН ВЫГОДНЫЙ СЛОТ!</b>

📦 <b>Товар:</b> <code>{slot_data.get('barcode', 'N/A')}</code>
📦 <b>Количество:</b> {slot_data.get('task', {}).get('quantity', 'N/A')} шт
🏢 <b>Склад:</b> {slot_data.get('warehouse_name', 'N/A')} (ID: {slot_data.get('warehouse_id', 'N/A')})
{coef_emoji} <b>Коэффициент:</b> x{coef}
📦 <b>Тип упаковки:</b> {slot_data.get('box_type_name', 'N/A')}
📅 <b>Дата:</b> {date_str}
🚚 <b>Разгрузка:</b> {'✅ Разрешена' if slot_data.get('allow_unload', False) else '❌ Запрещена'}
⏰ <b>Найдено:</b> {slot_data.get('found_at', '').split('T')[1][:5] if slot_data.get('found_at') else 'N/A'}

🔥 <b>ДЕЙСТВУЙТЕ БЫСТРО!</b> Слоты разбирают за секунды.
        """
        
        return message.strip()
    
    def _should_send_notification(self, user: TelegramUser, slot_data: Dict[str, Any]) -> bool:
        """Проверяет, нужно ли отправлять уведомление пользователю"""
        
        # Проверяем мгновенные уведомления
        if not user.notification_settings.get('instant_notifications', True):
            return False
        
        # Проверяем коэффициент
        coef = slot_data.get('coefficient', -1)
        max_coef = user.notification_settings.get('max_coefficient', 1.0)
        min_coef = user.notification_settings.get('min_coefficient', 0.0)
        
        if not (min_coef <= coef <= max_coef):
            return False
        
        # Проверяем предпочитаемые склады
        preferred_warehouses = user.notification_settings.get('preferred_warehouses', [])
        if preferred_warehouses:
            warehouse_id = slot_data.get('warehouse_id')
            if warehouse_id not in preferred_warehouses:
                return False
        
        # Проверяем тихие часы
        quiet_hours = user.notification_settings.get('quiet_hours', {})
        if quiet_hours:
            current_hour = datetime.now().hour
            start_hour = quiet_hours.get('start', 23)
            end_hour = quiet_hours.get('end', 7)
            
            if start_hour > end_hour:  # Через полночь
                if current_hour >= start_hour or current_hour <= end_hour:
                    return False
            else:  # В пределах одного дня
                if start_hour <= current_hour <= end_hour:
                    return False
        
        return True
    
    async def send_broadcast_message(self, message: str, user_ids: List[int] = None):
        """Отправляет сообщение всем подписанным пользователям"""
        if user_ids is None:
            users = self.database.get_subscribed_users()
        else:
            users = [self.database.get_user(uid) for uid in user_ids]
            users = [u for u in users if u and u.subscribed]
        
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                await self.bot.send_message(
                    chat_id=user.user_id,
                    text=message,
                    parse_mode="HTML"
                )
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка отправки broadcast пользователю {user.user_id}: {e}")
                failed_count += 1
        
        logger.info(f"Broadcast отправлен {sent_count} пользователям, ошибок: {failed_count}")
        return sent_count, failed_count
    
    async def start_polling(self):
        """Запускает бота в режиме polling"""
        logger.info("🤖 Запуск Telegram бота...")
        
        try:
            # Проверяем подключение к API
            bot_info = await self.bot.get_me()
            logger.info(f"✅ Бот запущен: @{bot_info.username}")
            
            # Запускаем polling
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise
    
    async def stop(self):
        """Останавливает бота"""
        logger.info("🛑 Остановка Telegram бота...")
        await self.bot.session.close()


# Глобальный экземпляр бота
telegram_bot = None


async def initialize_bot():
    """Инициализирует глобальный экземпляр бота"""
    global telegram_bot
    
    if not config.telegram_bot_token:
        logger.error("❌ Telegram bot token не настроен")
        return None
    
    telegram_bot = WBSlotsBot(config.telegram_bot_token)
    logger.info("✅ Telegram бот инициализирован")
    
    return telegram_bot


async def send_slot_notification(slot_data: Dict[str, Any]):
    """Отправляет уведомление о найденном слоте через бота"""
    global telegram_bot
    
    if not telegram_bot:
        logger.warning("⚠️ Telegram бот не инициализирован")
        return
    
    await telegram_bot.send_slot_notification(slot_data)


async def send_broadcast(message: str):
    """Отправляет broadcast сообщение всем пользователям"""
    global telegram_bot
    
    if not telegram_bot:
        logger.warning("⚠️ Telegram бот не инициализирован")
        return
    
    return await telegram_bot.send_broadcast_message(message)


async def get_bot_stats():
    """Возвращает статистику бота"""
    global telegram_bot
    
    if not telegram_bot:
        return {"error": "Бот не инициализирован"}
    
    user_stats = telegram_bot.database.get_stats()
    notification_stats = telegram_bot.notification_stats
    
    return {
        "users": user_stats,
        "notifications": notification_stats
    }


# Основная функция для тестирования
async def main():
    """Основная функция для запуска бота в standalone режиме"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Инициализация бота
    bot = await initialize_bot()
    if not bot:
        return
    
    try:
        # Запуск в режиме polling
        await bot.start_polling()
    except KeyboardInterrupt:
        logger.info("👋 Остановка бота по Ctrl+C")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        if bot:
            await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
