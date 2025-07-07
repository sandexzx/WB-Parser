# sheets_parser.py - Работа с Google Sheets
"""
Модуль для работы с Google Sheets
Читает настройки мониторинга из таблицы заказчика
"""
import asyncio
import gspread
import os
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging
import re
import time
from gspread.exceptions import APIError

# Load environment variables first
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from wb_api import WildberriesAPI
from config import config

# Update config with environment variables
config.wb_api_key = os.getenv("WB_API_KEY", config.wb_api_key)
config.google_sheets_url = os.getenv("GOOGLE_SHEETS_URL", config.google_sheets_url)

logger = logging.getLogger(__name__)


@dataclass
class MonitoringTask:
    """
    Задача мониторинга из Google Sheets
    Представляет одну строку таблицы с параметрами для отслеживания
    """
    barcode: str                    # Баркод товара
    quantity: int                   # Количество единиц
    allowed_warehouses: List[int]   # Список ID складов, куда можно поставлять
    max_coefficient: float          # Максимальный коэффициент платной приемки
    date_from: date                 # С какой даты можно бронировать
    date_to: date                   # До какой даты можно бронировать
    is_active: bool = True          # Активна ли задача
    
    def is_date_valid(self) -> bool:
        """Проверяет, актуальна ли задача для мониторинга"""
        today = date.today()
        # Разрешаем мониторинг, если:
        # 1. Период еще не закончился (today <= date_to)
        # 2. И до начала периода осталось не более 30 дней (можно настроить)
        monitoring_start_buffer = 30  # дней до date_from когда можно начинать мониторинг
        earliest_monitoring_date = self.date_from - timedelta(days=monitoring_start_buffer)
        
        return earliest_monitoring_date <= today <= self.date_to


class GoogleSheetsParser:
    """
    Класс для работы с Google Sheets API
    Читает конфигурацию мониторинга из таблицы
    """
    
    def __init__(self, credentials_file: str, sheet_url: str):
        self.credentials_file = credentials_file
        self.sheet_url = sheet_url
        self.client = None
        self.workbook = None
        self._warehouse_cache = {}  # Кэш для складов
        self._tasks_cache = {}      # Кэш для задач мониторинга
        self._last_cache_update = None  # Время последнего обновления кэша
        
        # Области доступа для Google Sheets API
        self.scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

    async def get_monitoring_tasks_from_cells(self, worksheet_name: str = None) -> List[MonitoringTask]:
        """
        Читает задачи мониторинга из конкретных ячеек таблицы (новый формат заказчика)
        Если worksheet_name не указан, читает все листы
        ОПТИМИЗИРОВАНО: читает диапазоны ячеек вместо отдельных запросов
        """
        if not self.workbook:
            self._open_workbook()
        
        all_tasks = []
        
        try:
            # Если указан конкретный лист, читаем только его
            if worksheet_name:
                worksheets = [self.workbook.worksheet(worksheet_name)]
            else:
                # Читаем все листы
                worksheets = self.workbook.worksheets()
            
            logger.info(f"📄 Будем читать {len(worksheets)} листов")
            
            for worksheet in worksheets:
                logger.info(f"📄 Читаем лист: {worksheet.title}")
                
                try:
                    # ОПТИМИЗАЦИЯ: читаем все нужные ячейки одним запросом с обработкой ошибок
                    # Читаем конфигурацию (B4:B6) и данные (B8:C100) за два запроса вместо 200+
                    config_range = self._safe_range_request(worksheet, 'B4:B6')
                    data_range = self._safe_range_request(worksheet, 'B8:C100')
                    
                    # Извлекаем конфигурационные данные
                    warehouse_names_str = config_range[0].value or ""  # B4
                    date_from_str = config_range[1].value or ""        # B5  
                    date_to_str = config_range[2].value or ""          # B6
                    
                    logger.info(f"🏢 Склады из B4: {warehouse_names_str}")
                    logger.info(f"📅 Период: {date_from_str} - {date_to_str}")
                    
                    # Проверяем, заполнена ли ячейка со складами
                    if not warehouse_names_str or warehouse_names_str.strip() == "":
                        logger.warning(f"⚠️ Пропускаем лист {worksheet.title}: не указаны склады в ячейке B4")
                        continue
                    
                    # Парсим общие настройки
                    date_from = self._parse_date(date_from_str)
                    date_to = self._parse_date(date_to_str)
                    
                    # Получаем ID складов по их названиям для этого листа
                    worksheet_allowed_warehouses = await self._get_warehouse_ids_by_names(warehouse_names_str)
                    
                    # ОПТИМИЗАЦИЯ: обрабатываем данные из уже загруженного диапазона
                    tasks = []
                    empty_rows_count = 0
                    
                    # data_range содержит ячейки B8:C100, обрабатываем их парами
                    for i in range(0, len(data_range), 2):
                        if i + 1 >= len(data_range):
                            break
                            
                        barcode_cell = data_range[i]      # B колонка
                        quantity_cell = data_range[i + 1] # C колонка
                        row_number = 8 + i // 2
                        
                        # Нормализуем данные
                        barcode_clean = str(barcode_cell.value).strip() if barcode_cell.value else ""
                        quantity_clean = str(quantity_cell.value).strip() if quantity_cell.value else ""
                        
                        # Проверяем состояние строки
                        has_barcode = barcode_clean != ""
                        has_quantity = quantity_clean != ""
                        
                        # Логика валидации строки
                        if not has_barcode and not has_quantity:
                            # Обе ячейки пустые
                            empty_rows_count += 1
                            logger.debug(f"🔍 Строка {row_number}: пустая ({empty_rows_count} подряд)")
                            
                            if empty_rows_count >= 2:
                                logger.info(f"⏹️ Две пустые строки подряд, прекращаем чтение листа {worksheet.title}")
                                break
                                
                        elif has_barcode and not has_quantity:
                            # Есть баркод, но нет количества
                            logger.warning(f"⚠️ Строка {row_number}: пропускаем - есть баркод '{barcode_clean}', но нет количества")
                            empty_rows_count = 0
                            
                        elif not has_barcode and has_quantity:
                            # Есть количество, но нет баркода
                            logger.warning(f"⚠️ Строка {row_number}: пропускаем - есть количество '{quantity_clean}', но нет баркода")
                            empty_rows_count = 0
                            
                        else:
                            # Есть и баркод, и количество - валидная строка
                            empty_rows_count = 0
                            
                            try:
                                quantity = int(quantity_clean)
                            except ValueError:
                                logger.warning(f"⚠️ Строка {row_number}: неверное количество '{quantity_clean}', используем 1")
                                quantity = 1
                            
                            # Создаем задачу мониторинга
                            task = MonitoringTask(
                                barcode=barcode_clean,
                                quantity=quantity,
                                allowed_warehouses=worksheet_allowed_warehouses,
                                max_coefficient=1.0,  # Пока ищем только бесплатные слоты
                                date_from=date_from,
                                date_to=date_to,
                                is_active=True
                            )
                            
                            tasks.append(task)
                            logger.info(f"✅ Добавлена задача: {barcode_clean} ({quantity} шт) из листа {worksheet.title}")
                    
                    logger.info(f"✅ Загружено {len(tasks)} задач из листа {worksheet.title}")
                    all_tasks.extend(tasks)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка чтения листа {worksheet.title}: {e}")
                    continue
            
            logger.info(f"✅ Итого загружено {len(all_tasks)} задач мониторинга из {len(worksheets)} листов")
            return all_tasks
            
        except Exception as e:
            logger.error(f"❌ Ошибка чтения таблицы: {e}")
            raise
    
    async def _get_warehouse_ids_by_names(self, warehouse_names_str: str) -> List[int]:
        """
        Получает ID складов по их названиям
        Использует WB API для получения списка всех складов и сопоставления по именам
        """
        if not warehouse_names_str:
            return []
        
        # Парсим названия складов
        warehouse_names = [name.strip() for name in warehouse_names_str.split(',')]
        logger.info(f"🔍 Ищем ID для складов: {warehouse_names}")
        
        # Получаем все склады через API
        api = WildberriesAPI(config.wb_api_key)
        
        try:
            all_warehouses = await api.get_warehouses()
            logger.info(f"📋 Получено {len(all_warehouses)} складов от API")

            # Показываем примеры складов для отладки
            logger.info("🔍 Примеры складов из API (первые 10):")
            for i, warehouse in enumerate(all_warehouses[:10]):
                wh_name = warehouse.get('name', 'Без названия')
                wh_id = warehouse.get('id', 0)
                logger.info(f"  {i+1}. ID: {wh_id}, Название: '{wh_name}'")
            
            # Ищем соответствия
            found_warehouses = []

            search_results = {}  # Для детальной диагностики

            for warehouse in all_warehouses:
                warehouse_name = warehouse.get('name', '')
                warehouse_id = warehouse.get('id', 0)
                
                # Проверяем точное совпадение или вхождение
                for target_name in warehouse_names:
                    target_lower = target_name.lower().strip()
                    warehouse_lower = warehouse_name.lower()
                    
                    # Различные способы сопоставления
                    exact_match = target_lower == warehouse_lower
                    target_in_warehouse = target_lower in warehouse_lower
                    warehouse_in_target = warehouse_lower in target_lower
                    
                    # Дополнительная логика для городов
                    # Убираем общие слова для более точного поиска
                    clean_target = target_lower.replace('склад', '').replace('warehouse', '').strip()
                    clean_warehouse = warehouse_lower.replace('склад', '').replace('warehouse', '').strip()
                    
                    city_match = (clean_target in clean_warehouse or 
                                clean_warehouse in clean_target) and len(clean_target) > 2
                    
                    if exact_match or target_in_warehouse or warehouse_in_target or city_match:
                        if target_name not in search_results:
                            search_results[target_name] = []
                        
                        search_results[target_name].append({
                            'id': warehouse_id,
                            'name': warehouse_name,
                            'match_type': 'exact' if exact_match else 
                                        'target_in_warehouse' if target_in_warehouse else
                                        'warehouse_in_target' if warehouse_in_target else 'city_match'
                        })

            # Анализируем результаты поиска
            logger.info("🔍 Результаты поиска складов:")
            for target_name, matches in search_results.items():
                logger.info(f"\n  🏢 Для '{target_name}' найдено {len(matches)} совпадений:")
                
                # Сортируем по типу совпадения (exact сначала)
                matches.sort(key=lambda x: ['exact', 'target_in_warehouse', 'city_match', 'warehouse_in_target'].index(x['match_type']))
                
                for i, match in enumerate(matches[:5]):  # Показываем первые 5
                    logger.info(f"    {i+1}. ID: {match['id']}, Название: '{match['name']}', Тип: {match['match_type']}")
                
                # Берем лучшее совпадение (первое после сортировки)
                if matches:
                    best_match = matches[0]
                    found_warehouses.append(best_match['id'])
                    logger.info(f"  ✅ Выбран: ID {best_match['id']} - '{best_match['name']}'")
                else:
                    logger.warning(f"  ❌ Не найдено совпадений для '{target_name}'")
             
            
            if not found_warehouses:
                logger.warning(f"⚠️ Не найдены склады для названий: {warehouse_names}")
                logger.info("💡 Показываем все доступные склады для справки:")
            for warehouse in all_warehouses:
                wh_name = warehouse.get('name', '')
                wh_id = warehouse.get('id', 0)
                # Показываем склады, которые содержат хотя бы одно из ключевых слов
                for target in warehouse_names:
                    if target.lower()[:3] in wh_name.lower():  # Первые 3 буквы
                        logger.info(f"  💡 Возможно подходит: ID {wh_id} - '{wh_name}'")
                        break
            
            logger.info("💡 Если подходящие склады не найдены, будем искать на всех складах")
             
            logger.info(f"✅ Итого найдено складов: {len(found_warehouses)} - {found_warehouses}")
            return found_warehouses
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения складов: {e}")
            return []
    
    def _authenticate(self):
        """
        Авторизация в Google Sheets API
        Использует service account credentials
        """
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            self.client = gspread.authorize(creds)
            logger.info("✅ Успешная авторизация в Google Sheets")
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации в Google Sheets: {e}")
            raise
    
    def _open_workbook(self):
        """Открывает таблицу по URL с обработкой ошибок лимитов"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                if not self.client:
                    self._authenticate()
                
                # Извлекаем ID таблицы из URL
                sheet_id = self._extract_sheet_id(self.sheet_url)
                logger.info(f"📋 Пытаемся открыть таблицу с ID: {sheet_id}")
                self.workbook = self.client.open_by_key(sheet_id)
                logger.info(f"📊 Открыта таблица: {self.workbook.title}")
                return
                
            except APIError as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"⏳ Превышен лимит API, ждем {wait_time} секунд перед повтором (попытка {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("❌ Превышен лимит API после всех попыток")
                        raise
                else:
                    raise
                    
            except Exception as e:
                logger.error(f"❌ Ошибка открытия таблицы: {e}")
                # Добавляем детальную диагностику
                if "404" in str(e):
                    logger.error("💡 Возможные причины ошибки 404:")
                    logger.error("  1. Service Account не имеет доступа к таблице")
                    logger.error("  2. Неправильный URL или ID таблицы")
                    logger.error("  3. Таблица удалена или перемещена")
                    logger.error("🔧 Решение: добавьте email из credentials.json в доступ к таблице")
                raise
    
    def _extract_sheet_id(self, url: str) -> str:
        """
        Извлекает ID таблицы из Google Sheets URL
        Поддерживает разные форматы URL
        """

        logger.info(f"🔍 Извлекаем ID из URL: {url}")

        patterns = [
            r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'key=([a-zA-Z0-9-_]+)',
            r'/d/([a-zA-Z0-9-_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                sheet_id = match.group(1)
                logger.info(f"✅ Найден ID таблицы: {sheet_id}")
                return sheet_id

        
        raise ValueError(f"Не удалось извлечь ID из URL: {url}")
    
    def _parse_date(self, date_str: str) -> date:
        """
        Парсит дату из строки
        Поддерживает форматы: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD, DD.MM (текущий год)
        """
        if not date_str or date_str.strip() == "":
            return date.today()
        
        date_str = date_str.strip()
        current_year = date.today().year
        
        # Пробуем разные форматы
        formats = [
            "%d.%m.%Y",   # 15.07.2025
            "%d/%m/%Y",   # 15/07/2025
            "%Y-%m-%d",   # 2025-07-15
            "%d.%m.%y",   # 15.07.25
            "%d/%m/%y",   # 15/07/25
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Пробуем формат без года (DD.MM или DD/MM)
        short_formats = [
            "%d.%m",      # 12.07
            "%d/%m",      # 12/07
        ]
        
        for fmt in short_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                # Подставляем текущий год
                return parsed_date.replace(year=current_year)
            except ValueError:
                continue
        
        logger.warning(f"⚠️ Не удалось распарсить дату: {date_str}, используем сегодня")
        return date.today()
    
    def _parse_warehouses(self, warehouses_str: str) -> List[int]:
        """
        Парсит список складов из строки
        Поддерживает форматы: "123,456,789" или "123; 456; 789" или "все"
        """
        if not warehouses_str or warehouses_str.strip() == "":
            return []
        
        warehouses_str = warehouses_str.strip().lower()
        
        # Если указано "все" или аналогичное - возвращаем пустой список (значит все склады)
        if warehouses_str in ["все", "all", "любые", "*"]:
            return []
        
        # Парсим числа через запятую или точку с запятой
        separators = [",", ";", "|"]
        for sep in separators:
            if sep in warehouses_str:
                parts = warehouses_str.split(sep)
                break
        else:
            # Если разделителей нет, считаем что это один склад
            parts = [warehouses_str]
        
        warehouse_ids = []
        for part in parts:
            try:
                warehouse_id = int(part.strip())
                warehouse_ids.append(warehouse_id)
            except ValueError:
                logger.warning(f"⚠️ Не удалось распарсить ID склада: {part}")
        
        return warehouse_ids
    
    async def get_monitoring_tasks(self, worksheet_name: str = None, use_cache: bool = True) -> List[MonitoringTask]:
        """
        Основная функция для чтения задач мониторинга
        Автоматически определяет формат таблицы и использует подходящий парсер
        С кэшированием для уменьшения количества запросов к API
        """
        # Проверяем кэш
        if use_cache and self._should_use_cache():
            cache_key = f"{worksheet_name or 'all'}"
            if cache_key in self._tasks_cache:
                logger.info(f"🚀 Используем кэшированные данные для {cache_key}")
                return self._tasks_cache[cache_key]
        
        try:
            # Пробуем новый формат с ячейками (формат заказчика)
            logger.info("🔄 Пытаемся прочитать таблицу в формате ячеек...")
            tasks = await self.get_monitoring_tasks_from_cells(worksheet_name)
            
            # Сохраняем в кэш
            if use_cache:
                self._update_cache(worksheet_name, tasks)
            
            return tasks
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось прочитать формат ячеек: {e}")
            
            # Fallback на старый табличный формат
            logger.info("🔄 Пробуем старый табличный формат...")
            tasks = self._get_monitoring_tasks_table_format(worksheet_name)
            
            # Сохраняем в кэш
            if use_cache:
                self._update_cache(worksheet_name, tasks)
            
            return tasks
    
    def _get_monitoring_tasks_table_format(self, worksheet_name: str = None) -> List[MonitoringTask]:
        """
        Читает задачи в старом табличном формате (для совместимости)
        Если worksheet_name не указан, читает все листы
        """
        if not self.workbook:
            self._open_workbook()
        
        all_tasks = []
        
        try:
            # Если указан конкретный лист, читаем только его
            if worksheet_name:
                worksheets = [self.workbook.worksheet(worksheet_name)]
            else:
                # Читаем все листы
                worksheets = self.workbook.worksheets()
            
            logger.info(f"📄 Будем читать {len(worksheets)} листов в табличном формате")
            
            for worksheet in worksheets:
                logger.info(f"📄 Читаем лист: {worksheet.title}")
                
                try:
                    # Получаем все данные
                    all_values = worksheet.get_all_values()
                    
                    if len(all_values) < 2:
                        logger.warning(f"⚠️ В листе {worksheet.title} нет данных (только заголовки или пустой)")
                        continue
                    
                    # Первая строка - заголовки
                    headers = [h.strip().lower() for h in all_values[0]]
                    
                    # Ищем нужные колонки (гибко, по ключевым словам)
                    column_mapping = self._detect_columns(headers)
                    
                    tasks = []
                    for row_idx, row in enumerate(all_values[1:], start=2):
                        try:
                            task = self._parse_row(row, column_mapping, row_idx)
                            if task:
                                tasks.append(task)
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка в строке {row_idx} листа {worksheet.title}: {e}")
                            continue
                    
                    logger.info(f"✅ Загружено {len(tasks)} задач из листа {worksheet.title}")
                    all_tasks.extend(tasks)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка чтения листа {worksheet.title}: {e}")
                    continue
            
            logger.info(f"✅ Итого загружено {len(all_tasks)} задач мониторинга из {len(worksheets)} листов")
            return all_tasks
            
        except Exception as e:
            logger.error(f"❌ Ошибка чтения таблицы: {e}")
            raise
    
    def _detect_columns(self, headers: List[str]) -> Dict[str, int]:
        """
        Автоматически определяет, какая колонка за что отвечает
        Ищет по ключевым словам в заголовках
        """
        column_mapping = {}
        
        # Словарь соответствий: ключ -> список возможных названий
        keywords = {
            "barcode": ["баркод", "штрихкод", "barcode", "штрих-код", "код товара"],
            "quantity": ["количество", "кол-во", "quantity", "шт", "штук"],
            "warehouses": ["склады", "склад", "warehouses", "warehouse", "wh"],
            "max_coefficient": ["коэффициент", "коэф", "coefficient", "макс коэф", "max_coef"],
            "date_from": ["дата с", "с даты", "from", "начало", "date_from"],
            "date_to": ["дата до", "до даты", "to", "конец", "date_to"],
            "active": ["активно", "active", "включено", "enabled"]
        }
        
        for col_idx, header in enumerate(headers):
            for field, possible_names in keywords.items():
                if any(keyword in header for keyword in possible_names):
                    column_mapping[field] = col_idx
                    break
        
        logger.info(f"🔍 Определены колонки: {column_mapping}")
        return column_mapping
    
    def _parse_row(self, row: List[str], column_mapping: Dict[str, int], 
                   row_number: int) -> Optional[MonitoringTask]:
        """
        Парсит одну строку таблицы в объект MonitoringTask
        """
        try:
            # Проверяем обязательные поля
            if "barcode" not in column_mapping or "quantity" not in column_mapping:
                logger.error("❌ Не найдены обязательные колонки: баркод или количество")
                return None
            
            # Читаем баркод
            barcode = row[column_mapping["barcode"]].strip()
            if not barcode:
                return None  # Пропускаем пустые строки
            
            # Читаем количество
            try:
                quantity = int(row[column_mapping["quantity"]].strip())
            except ValueError:
                logger.warning(f"⚠️ Строка {row_number}: неверное количество")
                return None
            
            # Читаем остальные поля с значениями по умолчанию
            warehouses = []
            if "warehouses" in column_mapping:
                warehouses_str = row[column_mapping["warehouses"]]
                warehouses = self._parse_warehouses(warehouses_str)
            
            max_coefficient = 1.0  # По умолчанию только бесплатные
            if "max_coefficient" in column_mapping:
                try:
                    coef_str = row[column_mapping["max_coefficient"]].strip()
                    if coef_str:
                        # Убираем "x" если есть (например "x5" -> "5")
                        coef_str = coef_str.replace("x", "").replace("X", "")
                        max_coefficient = float(coef_str)
                except ValueError:
                    logger.warning(f"⚠️ Строка {row_number}: неверный коэффициент")
            
            # Даты
            date_from = date.today()
            date_to = date.today()
            
            if "date_from" in column_mapping:
                date_from = self._parse_date(row[column_mapping["date_from"]])
            
            if "date_to" in column_mapping:
                date_to = self._parse_date(row[column_mapping["date_to"]])
            
            # Активность
            is_active = True
            if "active" in column_mapping:
                active_str = row[column_mapping["active"]].strip().lower()
                is_active = active_str not in ["нет", "no", "false", "0", "выкл", "disabled"]
            
            return MonitoringTask(
                barcode=barcode,
                quantity=quantity,
                allowed_warehouses=warehouses,
                max_coefficient=max_coefficient,
                date_from=date_from,
                date_to=date_to,
                is_active=is_active
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга строки {row_number}: {e}")
            return None

    def _should_use_cache(self) -> bool:
        """
        Проверяет, нужно ли использовать кэш
        Кэш актуален в течение 2 минут
        """
        if self._last_cache_update is None:
            return False
            
        cache_age = (datetime.now() - self._last_cache_update).total_seconds()
        return cache_age < 120  # 2 минуты
    
    def _update_cache(self, worksheet_name: str, tasks: List[MonitoringTask]):
        """
        Обновляет кэш с новыми задачами
        """
        cache_key = f"{worksheet_name or 'all'}"
        self._tasks_cache[cache_key] = tasks
        self._last_cache_update = datetime.now()
        logger.info(f"💾 Кэш обновлен для {cache_key}: {len(tasks)} задач")
    
    def clear_cache(self):
        """
        Очищает кэш принудительно
        """
        self._tasks_cache.clear()
        self._last_cache_update = None
        logger.info("🗑️ Кэш очищен")
    
    def _safe_range_request(self, worksheet, range_name: str, max_retries: int = 3):
        """
        Безопасный запрос диапазона ячеек с обработкой ошибок лимитов API
        """
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                return worksheet.range(range_name)
                
            except APIError as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"⏳ Превышен лимит API при чтении {range_name}, ждем {wait_time} секунд (попытка {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ Превышен лимит API после всех попыток для {range_name}")
                        raise
                else:
                    logger.error(f"❌ Ошибка API при чтении {range_name}: {e}")
                    raise
                    
            except Exception as e:
                logger.error(f"❌ Неизвестная ошибка при чтении {range_name}: {e}")
                raise


# Пример использования
async def test_sheets_parser():
    """
    Тестовая функция для проверки парсера
    """
    # Заглушка для тестирования без реальной таблицы
    parser = GoogleSheetsParser("credentials.json", "url_таблицы")
    
    # Когда получим реальную таблицу, раскомментируем:
    # tasks = parser.get_monitoring_tasks()
    # for task in tasks:
    #     print(f"📦 {task.barcode}: {task.quantity} шт, макс коэф {task.max_coefficient}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_sheets_parser())
