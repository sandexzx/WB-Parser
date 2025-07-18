"""
Telegram бот для уведомлений о найденных слотах WB
Поддерживает подписку/отписку пользователей и отправку уведомлений
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta, date
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.formatting import Text, Bold, Italic, Code

from config import config
from slot_utils import get_current_active_slots

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                slot_id TEXT,
                barcode TEXT,
                warehouse_id INTEGER,
                slot_date TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                UNIQUE(user_id, slot_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_stats (
                id INTEGER PRIMARY KEY,
                sent_today INTEGER DEFAULT 0,
                sent_total INTEGER DEFAULT 0,
                failed_today INTEGER DEFAULT 0,
                failed_total INTEGER DEFAULT 0,
                last_notification TEXT,
                last_reset_date TEXT DEFAULT (date('now'))
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Инициализируем статистику, если она не существует
        self._init_stats()
    
    def _init_stats(self):
        """Инициализирует статистику уведомлений в базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM notification_stats WHERE id = 1')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO notification_stats (id, sent_today, sent_total, failed_today, failed_total, last_notification, last_reset_date)
                VALUES (1, 0, 0, 0, 0, NULL, date('now'))
            ''')
        
        conn.commit()
        conn.close()
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """Получает статистику уведомлений из базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM notification_stats WHERE id = 1')
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {
                "sent_today": row[1],
                "sent_total": row[2],
                "failed_today": row[3],
                "failed_total": row[4],
                "last_notification": row[5],
                "last_reset_date": row[6]
            }
        return {
            "sent_today": 0,
            "sent_total": 0,
            "failed_today": 0,
            "failed_total": 0,
            "last_notification": None,
            "last_reset_date": date.today().isoformat()
        }
    
    def update_notification_stats(self, sent_count: int = 0, failed_count: int = 0):
        """Обновляет статистику уведомлений"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Проверяем, нужно ли сбросить дневные счетчики
        today = date.today().isoformat()
        cursor.execute('SELECT last_reset_date FROM notification_stats WHERE id = 1')
        last_reset = cursor.fetchone()
        
        if last_reset and last_reset[0] != today:
            # Сбрасываем дневные счетчики
            cursor.execute('''
                UPDATE notification_stats 
                SET sent_today = 0, failed_today = 0, last_reset_date = ?
                WHERE id = 1
            ''', (today,))
        
        # Обновляем статистику
        cursor.execute('''
            UPDATE notification_stats 
            SET sent_today = sent_today + ?, 
                sent_total = sent_total + ?,
                failed_today = failed_today + ?,
                failed_total = failed_total + ?,
                last_notification = CASE 
                    WHEN ? > 0 THEN ? 
                    ELSE last_notification 
                END
            WHERE id = 1
        ''', (sent_count, sent_count, failed_count, failed_count, sent_count, datetime.now().strftime('%d.%m.%Y %H:%M')))
        
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
    
    def add_user_notification(self, user_id: int, slot_data: Dict[str, Any]):
        """Добавляет запись об отправленном уведомлении"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        slot_id = f"{slot_data.get('barcode', '')}-{slot_data.get('warehouse_id', '')}-{slot_data.get('date', '')}"
        
        cursor.execute('''
            INSERT OR IGNORE INTO user_notifications 
            (user_id, slot_id, barcode, warehouse_id, slot_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            slot_id,
            slot_data.get('barcode', ''),
            slot_data.get('warehouse_id', 0),
            slot_data.get('date', '')
        ))
        
        conn.commit()
        conn.close()
    
    def has_user_seen_slot(self, user_id: int, slot_data: Dict[str, Any]) -> bool:
        """Проверяет, видел ли пользователь уведомление об этом слоте"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        slot_id = f"{slot_data.get('barcode', '')}-{slot_data.get('warehouse_id', '')}-{slot_data.get('date', '')}"
        
        cursor.execute(
            'SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND slot_id = ?',
            (user_id, slot_id)
        )
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    
    def get_unseen_slots_for_user(self, user_id: int, available_slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Возвращает слоты, которые пользователь еще не видел"""
        unseen_slots = []
        
        for slot_data in available_slots:
            if not self.has_user_seen_slot(user_id, slot_data):
                unseen_slots.append(slot_data)
        
        return unseen_slots
    
    def get_available_slots_from_files(self, days_back: int = 3) -> List[Dict[str, Any]]:
        """Получает слоты из файлов за последние N дней"""
        slots = []
        today = date.today()
        
        for days in range(days_back):
            check_date = today - timedelta(days=days)
            filename = f"found_slots/slots_{check_date.strftime('%Y-%m-%d')}.json"
            
            if os.path.exists(filename):
                try:
                    with open(filename, "r", encoding="utf-8") as f:
                        day_slots = json.load(f)
                        slots.extend(day_slots)
                except Exception as e:
                    logger.error(f"Ошибка чтения файла {filename}: {e}")
        
        return slots


class WBSlotsBot:
    """Основной класс Telegram бота"""
    
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.database = TelegramDatabase()
        
        # Настройка обработчиков
        self._setup_handlers()
        
        # Загружаем статистику уведомлений из базы данных
        self.notification_stats = self.database.get_notification_stats()
    
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
/stats - статистика бота
/help - помощь

⚡ <b>Вы автоматически подписаны на уведомления!</b>
Слоты разбирают за секунды, поэтому уведомления приходят мгновенно.
        """
        
        await message.reply(welcome_text, parse_mode="HTML")
        
        # Отправляем актуальные слоты новому пользователю
        current_active_slots = get_current_active_slots()
        if current_active_slots:
            await self.send_missed_notifications(user_id, current_active_slots)
    
    async def _handle_help(self, message: Message):
        """Обработчик команды /help"""
        help_text = """
📖 <b>Помощь по боту WB Slots Monitor</b>

🎯 <b>Основные команды:</b>
/start - начать работу с ботом
/subscribe - подписаться на уведомления
/unsubscribe - отписаться от уведомлений
/status - проверить статус подписки
/stats - статистика бота

🔔 <b>Уведомления:</b>
Бот автоматически отправляет уведомления о найденных слотах с коэффициентом 0-1.
В уведомлении указывается:
• Баркод товара
• Название склада
• Коэффициент приемки
• Дата слота
• Тип упаковки

💡 <b>Советы:</b>
• Слоты разбирают очень быстро, действуйте мгновенно
• Следите за коэффициентами - 0 самый выгодный
• Бот автоматически отправляет все подходящие уведомления
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
            "",
            parse_mode="HTML"
        )
        
        # Отправляем актуальные слоты новому подписчику
        current_active_slots = get_current_active_slots()
        if current_active_slots:
            await self.send_missed_notifications(user_id, current_active_slots)
    
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
• Мгновенные уведомления: {'✅' if user.notification_settings.get('instant_notifications', True) else '❌'}

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
    
    
    async def send_missed_notifications(self, user_id: int, available_slots: List[Dict[str, Any]]):
        """
        Отправляет пропущенные уведомления новому подписчику
        
        Args:
            user_id: ID пользователя
            available_slots: Список доступных слотов
        """
        user = self.database.get_user(user_id)
        if not user or not user.subscribed:
            return
        
        # Получаем слоты, которые пользователь еще не видел
        unseen_slots = self.database.get_unseen_slots_for_user(user_id, available_slots)
        
        if not unseen_slots:
            return
        
        sent_count = 0
        failed_count = 0
        
        for slot_data in unseen_slots:
            try:
                # Проверяем настройки пользователя
                if not self._should_send_notification(user, slot_data):
                    continue
                
                # Проверяем, не видел ли пользователь это уведомление
                if self.database.has_user_seen_slot(user.user_id, slot_data):
                    continue
                
                message_text = self._format_slot_message(slot_data)
                
                await self.bot.send_message(
                    chat_id=user.user_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                
                # Записываем, что уведомление отправлено
                self.database.add_user_notification(user.user_id, slot_data)
                
                sent_count += 1
                
                # Небольшая задержка между сообщениями
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Ошибка отправки пропущенного уведомления пользователю {user_id}: {e}")
                failed_count += 1
        
        # Обновляем статистику в базе данных
        self.database.update_notification_stats(sent_count, failed_count)
        
        # Обновляем локальную статистику
        self.notification_stats = self.database.get_notification_stats()
        
        if sent_count > 0:
            # Отправляем итоговое сообщение
            summary_text = f"📊 Отправлено {sent_count} пропущенных уведомлений о слотах"
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=summary_text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки итогового сообщения пользователю {user_id}: {e}")
        
        logger.info(f"Пользователю {user_id} отправлено {sent_count} пропущенных уведомлений, ошибок: {failed_count}")
    
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
                
                # Проверяем, не видел ли пользователь это уведомление раньше
                if self.database.has_user_seen_slot(user.user_id, slot_data):
                    continue
                
                await self.bot.send_message(
                    chat_id=user.user_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                
                # Записываем, что уведомление отправлено
                self.database.add_user_notification(user.user_id, slot_data)
                
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user.user_id}: {e}")
                failed_count += 1
        
        # Обновляем статистику в базе данных
        self.database.update_notification_stats(sent_count, failed_count)
        
        # Обновляем локальную статистику
        self.notification_stats = self.database.get_notification_stats()
        
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
⏰ <b>Найдено:</b> {self._format_time_with_offset(slot_data.get('found_at', ''))}

        """
        
        return message.strip()
    
    def _format_time_with_offset(self, found_at: str) -> str:
        """Форматирует время с учетом часового пояса (+3 часа к UTC)"""
        if not found_at:
            return 'N/A'
        
        try:
            # Парсим время из строки
            if 'T' in found_at:
                time_part = found_at.split('T')[1][:5]  # Берем только HH:MM
                # Преобразуем в datetime для добавления 3 часов
                dt = datetime.fromisoformat(found_at.replace('Z', '+00:00'))
                # Добавляем 3 часа
                dt_moscow = dt + timedelta(hours=3)
                return dt_moscow.strftime('%H:%M')
            else:
                return found_at
        except Exception:
            return found_at if found_at else 'N/A'
    
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


async def send_missed_notifications_to_user(user_id: int, available_slots: List[Dict[str, Any]] = None):
    """Отправляет пропущенные уведомления пользователю"""
    global telegram_bot
    
    if not telegram_bot:
        logger.warning("⚠️ Telegram бот не инициализирован")
        return
    
    if available_slots is None:
        available_slots = get_current_active_slots()
    
    if available_slots:
        await telegram_bot.send_missed_notifications(user_id, available_slots)


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
