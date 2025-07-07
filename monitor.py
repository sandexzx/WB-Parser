"""
Основной модуль мониторинга слотов приемки WB
Содержит логику проверки доступности и бронирования слотов
"""
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from wb_api import WildberriesAPI, ProductInfo, SlotInfo, AcceptanceCoefficient
from sheets_parser import GoogleSheetsParser, MonitoringTask
from config import config
import telegram_bot

logger = logging.getLogger(__name__)


@dataclass
class FoundSlot:
    """
    Информация о найденном подходящем слоте с коэффициентом приемки
    """
    barcode: str
    warehouse_id: int
    warehouse_name: str
    coefficient: float
    box_type_name: str
    date: datetime
    allow_unload: bool
    found_at: datetime
    monitoring_task: MonitoringTask
    
    def is_really_available(self) -> bool:
        """Проверяет, действительно ли слот доступен по всем критериям"""
        return (self.coefficient == 0 or self.coefficient == 1) and self.allow_unload
    
    def matches_criteria(self) -> bool:
        """Проверяет, соответствует ли слот критериям из задачи мониторинга"""
        # Проверяем коэффициент
        if self.coefficient > self.monitoring_task.max_coefficient:
            return False
        
        # Проверяем разрешенные склады
        if (self.monitoring_task.allowed_warehouses and 
            self.warehouse_id not in self.monitoring_task.allowed_warehouses):
            return False
        
        # Проверяем даты
        slot_date = self.date.date()
        if not (self.monitoring_task.date_from <= slot_date <= self.monitoring_task.date_to):
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для сериализации"""
        return {
            "barcode": self.barcode,
            "warehouse_id": self.warehouse_id,
            "warehouse_name": self.warehouse_name,
            "coefficient": self.coefficient,
            "box_type_name": self.box_type_name,
            "date": self.date.isoformat(),
            "allow_unload": self.allow_unload,
            "found_at": self.found_at.isoformat(),
            "is_available": self.is_really_available(),
            "matches_criteria": self.matches_criteria(),
            "task": {
                "barcode": self.monitoring_task.barcode,
                "quantity": self.monitoring_task.quantity,
                "allowed_warehouses": self.monitoring_task.allowed_warehouses,
                "max_coefficient": self.monitoring_task.max_coefficient,
                "date_from": self.monitoring_task.date_from.isoformat(),
                "date_to": self.monitoring_task.date_to.isoformat(),
                "is_active": self.monitoring_task.is_active
            }
        }


class SlotMonitor:
    """
    Основной класс для мониторинга слотов приемки
    """
    
    def __init__(self):
        self.wb_api = WildberriesAPI(config.wb_api_key)
        self.sheets_parser = GoogleSheetsParser(
            config.google_sheets_credentials_file,
            config.google_sheets_url
        )
        
        # Кэш для предотвращения дублирования уведомлений
        self.notified_slots: Set[str] = set()
        
        # Статистика работы
        self.stats = {
            "checks_performed": 0,
            "slots_found": 0,
            "errors_count": 0,
            "last_check": None
        }
        
        # Telegram бот для уведомлений
        self.telegram_bot = None
        
        # Отслеживание циклов мониторинга для соблюдения лимита 6/минуту
        self.monitoring_cycles = []  # Времена запуска циклов
        self.current_minute_start = None  # Начало текущей минуты
        self.cycles_in_current_minute = 0  # Счетчик циклов в текущей минуте
    
    async def start_monitoring(self):
        """
        Запускает основной цикл мониторинга
        Работает бесконечно, проверяя слоты с адаптивным интервалом
        """
        logger.info("🚀 Запуск адаптивного мониторинга слотов WB")
        
        # Инициализируем Telegram бота
        self.telegram_bot = await telegram_bot.initialize_bot()
        if self.telegram_bot:
            logger.info("✅ Telegram бот инициализирован для уведомлений")
        else:
            logger.warning("⚠️ Telegram бот не инициализирован - уведомления отключены")
        
        # Проверяем подключение к API
        if not await self.wb_api.test_connection():
            logger.error("❌ Не удалось подключиться к WB API")
            return
        
        # Адаптивный интервал мониторинга
        last_cycle_duration = 0
        
        while True:
            try:
                cycle_start = time.time()
                await self._perform_monitoring_cycle()
                cycle_duration = time.time() - cycle_start
                
                # Вычисляем паузу для равномерного распределения циклов
                pause_duration = self._calculate_dynamic_pause(cycle_duration)
                
                logger.info(f"😴 Цикл завершен за {cycle_duration:.1f}с, пауза {pause_duration:.1f}с")
                if pause_duration > 0:
                    await asyncio.sleep(pause_duration)
                
            except KeyboardInterrupt:
                logger.info("⏹️ Получен сигнал остановки")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
                self.stats["errors_count"] += 1
                # При ошибке ждем меньше, чтобы быстрее восстановиться
                await asyncio.sleep(30)
    
    def _calculate_dynamic_pause(self, cycle_duration: float) -> float:
        """
        Вычисляет динамическую паузу для равномерного распределения 6 циклов на минуту
        """
        if not config.enable_adaptive_monitoring:
            return config.check_interval_seconds
        
        now = time.time()
        
        # Если это первый цикл или прошла минута - начинаем новую минуту
        if (self.current_minute_start is None or 
            now - self.current_minute_start >= 60):
            self.current_minute_start = now
            self.cycles_in_current_minute = 1
            logger.info(f"🕐 Начинаем новую минуту, цикл 1/6")
        else:
            self.cycles_in_current_minute += 1
            logger.info(f"🕐 Цикл {self.cycles_in_current_minute}/6 в текущей минуте")
        
        # Если цикл медленный (>10 секунд) - запускаем следующий сразу
        if cycle_duration >= 10:
            logger.info(f"🐌 Медленный цикл ({cycle_duration:.1f}с) - запускаем следующий сразу")
            return 0.1
        
        # Если выполнили 6 циклов - ждем до начала следующей минуты
        if self.cycles_in_current_minute >= 6:
            time_to_next_minute = 60 - (now - self.current_minute_start)
            if time_to_next_minute > 0:
                logger.info(f"✅ Выполнили 6 циклов, ждем до следующей минуты: {time_to_next_minute:.1f}с")
                return time_to_next_minute
            return 0.1
        
        # Рассчитываем равномерное распределение оставшихся циклов
        elapsed_time = now - self.current_minute_start
        remaining_time = 60 - elapsed_time
        remaining_cycles = 6 - self.cycles_in_current_minute
        
        if remaining_cycles <= 0:
            return 0.1
        
        # Пауза = оставшееся время / количество оставшихся циклов
        optimal_pause = remaining_time / remaining_cycles
        
        # Минимальная пауза 0.1 секунды для корректной работы
        pause = max(0.1, optimal_pause)
        
        logger.info(f"📊 Осталось {remaining_cycles} циклов за {remaining_time:.1f}с → пауза {pause:.1f}с")
        return pause
    
    async def _perform_monitoring_cycle(self):
        """
        Выполняет один цикл мониторинга:
        1. Читает задачи из Google Sheets
        2. Проверяет доступные слоты для каждой задачи
        3. Отправляет уведомления о найденных слотах
        """
        self.stats["checks_performed"] += 1
        self.stats["last_check"] = datetime.now()
        
        logger.info("🔄 Начинаем цикл мониторинга...")
        
        # Читаем актуальные задачи из таблицы
        try:
            monitoring_tasks = await self.sheets_parser.get_monitoring_tasks()
            active_tasks = [task for task in monitoring_tasks if task.is_active and task.is_date_valid()]
            
            logger.info(f"📋 Загружено {len(monitoring_tasks)} задач, активных: {len(active_tasks)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка чтения таблицы: {e}")
            return
        
        if not active_tasks:
            logger.info("ℹ️ Нет активных задач для мониторинга")
            return
        
        # Группируем задачи для оптимизации запросов к API
        grouped_tasks = self._group_tasks_for_api(active_tasks)
        
        # Проверяем каждую группу
        for group in grouped_tasks:
            try:
                await self._check_task_group(group)
                # Небольшая пауза между группами для соблюдения rate limit
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"❌ Ошибка проверки группы задач: {e}")
                continue
    
    def _group_tasks_for_api(self, tasks: List[MonitoringTask]) -> List[List[MonitoringTask]]:
        """
        Группирует задачи для оптимизации API запросов
        WB позволяет проверять до 5000 товаров в одном запросе
        """
        # Пока делаем простую группировку по 50 товаров на запрос
        # Это безопасно и оставляет запас по лимитам
        groups = []
        group_size = 50
        
        for i in range(0, len(tasks), group_size):
            groups.append(tasks[i:i + group_size])
        
        logger.info(f"📦 Разбили {len(tasks)} задач на {len(groups)} групп")
        return groups
    
    async def _check_task_group(self, tasks: List[MonitoringTask]):
        """
        Проверяет группу задач мониторинга с использованием реальных коэффициентов приемки
        """
        # Конвертируем задачи в формат для API
        products = []
        for task in tasks:
            products.append(ProductInfo(
                barcode=task.barcode,
                quantity=task.quantity
            ))
        
        # Получаем доступные слоты для товаров
        try:
            slots = await self.wb_api.check_acceptance_options(products)
        except Exception as e:
            logger.error(f"❌ Ошибка API запроса опций приемки: {e}")
            return
        
        # Собираем все уникальные ID складов из доступных слотов
        all_warehouse_ids = set()
        for slot in slots:
            if not slot.is_error and slot.warehouses:
                for warehouse in slot.warehouses:
                    all_warehouse_ids.add(warehouse.warehouse_id)
        
        if not all_warehouse_ids:
            logger.info("ℹ️ Нет доступных складов для данной группы товаров")
            return
        
        # Получаем коэффициенты приемки для найденных складов
        try:
            logger.info(f"📊 Получаем коэффициенты для {len(all_warehouse_ids)} складов")
            coefficients = await self.wb_api.get_acceptance_coefficients(list(all_warehouse_ids))
        except Exception as e:
            logger.error(f"❌ Ошибка получения коэффициентов: {e}")
            return
        
        # Создаем индекс коэффициентов по складу и дате для быстрого поиска
        coef_index = {}
        for coef in coefficients:
            key = (coef.warehouse_id, coef.date.date(), coef.box_type_id)
            coef_index[key] = coef
        
        # Анализируем каждый товар
        for slot in slots:
            if slot.is_error:
                logger.warning(f"⚠️ Ошибка для товара {slot.barcode}: {slot.error}")
                continue
            
            # Находим соответствующую задачу по баркоду
            task = next((t for t in tasks if t.barcode == slot.barcode), None)
            if not task:
                logger.warning(f"⚠️ Не найдена задача для товара {slot.barcode}")
                continue
            
            # Ищем подходящие слоты для этого товара
            suitable_slots = self._find_suitable_slots_with_coefficients(
                slot, task, coef_index
            )
            
            if suitable_slots:
                logger.info(f"🎯 Найдено {len(suitable_slots)} подходящих слотов для {slot.barcode}")
                
                # Отправляем уведомления
                await self._notify_about_found_slots(suitable_slots)
    
    def _find_suitable_slots_with_coefficients(self, slot: SlotInfo, task: MonitoringTask, 
                                              coef_index: Dict) -> List[FoundSlot]:
        """
        Находит подходящие слоты с учетом коэффициентов приемки и критериев задачи
        """
        suitable_slots = []
        
        for warehouse in slot.warehouses:
            warehouse_id = warehouse.warehouse_id
            
            # Проверяем, разрешен ли этот склад в задаче
            if task.allowed_warehouses and warehouse_id not in task.allowed_warehouses:
                continue
            
            # Ищем коэффициенты для этого склада в разрешенном диапазоне дат
            current_date = datetime.now().date()
            
            # Проверяем каждый день в диапазоне задачи
            check_date = max(task.date_from, current_date)
            end_date = task.date_to
            
            while check_date <= end_date:
                # Проверяем разные типы упаковки
                for box_type_id in [1, 2, 6]:  # Основные типы: обычная, монопаллет, суперсейф
                    coef_key = (warehouse_id, check_date, box_type_id)
                    
                    if coef_key in coef_index:
                        coef = coef_index[coef_key]
                        
                        # Проверяем все критерии
                        if (coef.is_slot_available() and  # Слот доступен (коэф 0-1 + allowUnload)
                            coef.coefficient <= task.max_coefficient and  # Коэффициент в пределах лимита
                            check_date >= task.date_from and check_date <= task.date_to):  # Дата подходит
                            
                            found_slot = FoundSlot(
                                barcode=slot.barcode,
                                warehouse_id=warehouse_id,
                                warehouse_name=coef.warehouse_name,
                                coefficient=coef.coefficient,
                                box_type_name=coef.box_type_name,
                                date=coef.date,
                                allow_unload=coef.allow_unload,
                                found_at=datetime.now(),
                                monitoring_task=task
                            )
                            
                            suitable_slots.append(found_slot)
                
                # Переходим к следующему дню
                check_date = check_date + timedelta(days=1)
        
        return suitable_slots
    
    async def _notify_about_found_slots(self, found_slots: List[FoundSlot]):
        """
        Отправляет уведомления о найденных подходящих слотах
        """
        for slot in found_slots:
            # Создаем уникальный ключ для предотвращения дублирования уведомлений
            slot_key = f"{slot.barcode}_{slot.warehouse_id}_{slot.date.date()}_{slot.box_type_name}"
            
            if slot_key in self.notified_slots:
                continue  # Уже уведомляли об этом слоте
            
            self.notified_slots.add(slot_key)
            self.stats["slots_found"] += 1
            
            # Формируем детальное сообщение
            message = f"""
🎯 НАЙДЕН ВЫГОДНЫЙ СЛОТ!

📦 Товар: {slot.barcode}
📦 Количество: {slot.monitoring_task.quantity} шт
🏢 Склад: {slot.warehouse_name} (ID: {slot.warehouse_id})
💰 Коэффициент: x{slot.coefficient} (лимит: x{slot.monitoring_task.max_coefficient})
📦 Тип упаковки: {slot.box_type_name}
📅 Дата: {slot.date.strftime('%d.%m.%Y')}
🚚 Разгрузка разрешена: {'✅ Да' if slot.allow_unload else '❌ Нет'}
⏰ Найдено: {slot.found_at.strftime('%H:%M:%S')}

            """
            
            logger.info(f"🔔 {message}")
            
            # Отправляем уведомление в Telegram
            await self._send_telegram_notification(slot)
            
            # Сохраняем информацию о найденном слоте для аналитики
            await self._save_found_slot(slot)
    
    async def _send_telegram_notification(self, slot: FoundSlot):
        """
        Отправляет уведомление о найденном слоте в Telegram
        """
        try:
            if self.telegram_bot:
                # Конвертируем данные слота в формат для Telegram бота
                slot_data = slot.to_dict()
                await telegram_bot.send_slot_notification(slot_data)
                logger.info(f"✅ Telegram уведомление отправлено для слота {slot.barcode}")
            else:
                logger.warning("⚠️ Telegram бот не инициализирован - пропускаем уведомление")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram уведомления: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику работы мониторинга
        """
        return {
            **self.stats,
            "last_check_str": self.stats["last_check"].strftime('%Y-%m-%d %H:%M:%S') 
                             if self.stats["last_check"] else "Никогда",
            "notified_slots_count": len(self.notified_slots)
        }
    
    async def manual_check(self, barcode: str, quantity: int) -> List[SlotInfo]:
        """
        Ручная проверка конкретного товара (для отладки)
        """
        logger.info(f"🔍 Ручная проверка товара {barcode}")
        
        products = [ProductInfo(barcode=barcode, quantity=quantity)]
        slots = await self.wb_api.check_acceptance_options(products)
        
        for slot in slots:
            if slot.is_error:
                logger.warning(f"⚠️ Ошибка: {slot.error}")
            else:
                logger.info(f"✅ Доступно складов: {len(slot.warehouses)}")
                for wh in slot.warehouses:
                    logger.info(f"  🏢 Склад {wh.warehouse_id}: box={wh.can_box}, mono={wh.can_monopollet}")
        
    async def _save_found_slot(self, slot: FoundSlot):
        """
        Сохраняет информацию о найденном слоте для аналитики и истории
        """
        try:
            # Создаем папку для сохранения если ее нет
            import os
            os.makedirs("found_slots", exist_ok=True)
            
            # Формируем имя файла с датой
            filename = f"found_slots/slots_{datetime.now().strftime('%Y-%m-%d')}.json"
            
            # Читаем существующие данные или создаем новый список
            import json
            slots_data = []
            
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    slots_data = json.load(f)
            except FileNotFoundError:
                pass  # Файл не существует, создаем новый
            
            # Добавляем новый слот
            slots_data.append(slot.to_dict())
            
            # Сохраняем обновленные данные
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(slots_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"💾 Слот сохранен в {filename}")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка сохранения слота: {e}")
    
    async def get_found_slots_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику найденных слотов за разные периоды
        """
        try:
            import os
            import json
            from datetime import date, timedelta
            
            stats = {
                "today": 0,
                "yesterday": 0,
                "this_week": 0,
                "total": 0,
                "best_coefficients": [],
                "top_warehouses": {}
            }
            
            # Анализируем файлы за последние 7 дней
            today = date.today()
            
            for days_back in range(7):
                check_date = today - timedelta(days=days_back)
                filename = f"found_slots/slots_{check_date.strftime('%Y-%m-%d')}.json"
                
                if os.path.exists(filename):
                    try:
                        with open(filename, "r", encoding="utf-8") as f:
                            day_slots = json.load(f)
                        
                        count = len(day_slots)
                        stats["total"] += count
                        stats["this_week"] += count
                        
                        if days_back == 0:
                            stats["today"] = count
                        elif days_back == 1:
                            stats["yesterday"] = count
                        
                        # Анализируем коэффициенты и склады
                        for slot_data in day_slots:
                            coef = slot_data.get("coefficient", -1)
                            warehouse_name = slot_data.get("warehouse_name", "Неизвестно")
                            
                            if coef >= 0:
                                stats["best_coefficients"].append(coef)
                            
                            if warehouse_name in stats["top_warehouses"]:
                                stats["top_warehouses"][warehouse_name] += 1
                            else:
                                stats["top_warehouses"][warehouse_name] = 1
                                
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка чтения {filename}: {e}")
            
            # Обрабатываем статистику коэффициентов
            if stats["best_coefficients"]:
                stats["best_coefficients"].sort()
                stats["avg_coefficient"] = sum(stats["best_coefficients"]) / len(stats["best_coefficients"])
                stats["min_coefficient"] = min(stats["best_coefficients"])
                stats["max_coefficient"] = max(stats["best_coefficients"])
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {"error": str(e)}


# Простая функция для быстрого тестирования
async def quick_test():
    """
    Быстрый тест основных компонентов
    """
    logger.info("🧪 Запуск быстрого теста...")
    
    # Проверяем конфигурацию
    if not config.validate():
        logger.error("❌ Неверная конфигурация")
        return
    
    # Создаем монитор
    monitor = SlotMonitor()
    
    # Тестируем подключение к API
    if await monitor.wb_api.test_connection():
        logger.info("✅ WB API работает")
    else:
        logger.error("❌ Проблемы с WB API")
    
    # Тестируем Google Sheets (если доступно)
    try:
        tasks = monitor.sheets_parser.get_monitoring_tasks()
        logger.info(f"✅ Google Sheets: загружено {len(tasks)} задач")
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets недоступен: {e}")
    
    logger.info("🧪 Тест завершен")


# Главная функция для запуска
async def main():
    """
    Основная точка входа в приложение
    """
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler()
        ]
    )
    
    logger.info("=" * 50)
    logger.info("🚀 WB SLOTS MONITOR STARTED")
    logger.info("=" * 50)
    
    # Проверяем конфигурацию
    if not config.validate():
        logger.error("❌ Ошибка конфигурации, завершение работы")
        return
    
    # Создаем и запускаем монитор
    monitor = SlotMonitor()
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        logger.info("👋 Завершение работы монитора")


if __name__ == "__main__":
    asyncio.run(main())
