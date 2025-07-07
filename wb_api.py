"""
Клиент для работы с API Wildberries
Основные методы для мониторинга слотов приемки
"""
import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProductInfo:
    """Информация о товаре для проверки слотов"""
    barcode: str
    quantity: int


@dataclass
class WarehouseOption:
    """Информация о доступном складе"""
    warehouse_id: int
    can_box: bool
    can_monopollet: bool
    can_supersafe: bool


@dataclass
class SlotInfo:
    """Информация о слоте приемки"""
    barcode: str
    warehouses: List[WarehouseOption]
    error: Optional[Dict[str, str]] = None
    is_error: bool = False


@dataclass
class AcceptanceCoefficient:
    """Информация о коэффициенте приемки для конкретного склада и даты"""
    date: datetime
    coefficient: float
    warehouse_id: int
    warehouse_name: str
    allow_unload: bool
    box_type_name: str
    box_type_id: int
    storage_coef: Optional[float] = None
    delivery_coef: Optional[float] = None
    delivery_base_liter: Optional[float] = None
    delivery_additional_liter: Optional[float] = None
    storage_base_liter: Optional[float] = None
    storage_additional_liter: Optional[float] = None
    is_sorting_center: bool = False
    
    def is_slot_available(self) -> bool:
        """
        Проверяет, доступен ли слот для бронирования
        Согласно документации: coefficient должен быть 0 или 1 И allowUnload должен быть true
        """
        return (self.coefficient == 0 or self.coefficient == 1) and self.allow_unload


class SimpleRateLimiter:
    """
    Простой rate limiter для соблюдения базовых лимитов API
    """
    def __init__(self):
        # Минимальные интервалы между запросами для безопасности
        self.min_intervals = {
            'general': 1.0,      # 1 секунда между обычными запросами
            'coefficients': 1.0  # 1 секунда между запросами коэффициентов
        }
        self.last_request_time = {endpoint: 0 for endpoint in self.min_intervals.keys()}
    
    async def wait_if_needed(self, endpoint_type: str = 'general'):
        """Ждет минимальный интервал между запросами"""
        if endpoint_type not in self.min_intervals:
            endpoint_type = 'general'
        
        now = time.time()
        min_interval = self.min_intervals[endpoint_type]
        time_since_last = now - self.last_request_time[endpoint_type]
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            logger.debug(f"⏳ Пауза между запросами: {sleep_time:.1f}с")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time[endpoint_type] = time.time()


class WildberriesAPI:
    """
    Основной клиент для работы с WB API
    """
    
    def __init__(self, api_key: str, base_url: str = "https://supplies-api.wildberries.ru"):
        self.api_key = api_key
        self.base_url = base_url
        self.rate_limiter = SimpleRateLimiter()
        
        # Заголовки для всех запросов
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "WB-Monitor/1.0"
        }
    
    async def _make_request(self, method: str, endpoint: str, 
                          data: Optional[Dict] = None, 
                          params: Optional[Dict] = None,
                          endpoint_type: str = 'general') -> Dict[str, Any]:
        """
        Универсальный метод для выполнения HTTP запросов к WB API
        Автоматически соблюдает rate limiting с учетом типа endpoint
        """
        await self.rate_limiter.wait_if_needed(endpoint_type)
        
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data,
                    params=params
                ) as response:
                    
                    # Измеряем время выполнения запроса
                    request_duration = time.time() - start_time
                    
                    # Логируем запрос для отладки
                    logger.info(f"🔄 {method} {endpoint} -> {response.status} ({request_duration:.1f}с)")
                    
                    response_text = await response.text()
                    
                    if response.status == 429:
                        logger.warning("⚠️ Получили 429 (Too Many Requests)")
                        raise Exception("Rate limit exceeded")
                    
                    if response.status == 401:
                        logger.error("❌ Ошибка авторизации (401) - проверьте API ключ")
                        raise Exception("Authorization failed")
                    
                    if response.status not in [200, 201]:
                        logger.error(f"❌ HTTP {response.status}: {response_text}")
                        raise Exception(f"HTTP {response.status}: {response_text}")
                    
                    return json.loads(response_text)
                    
            except aiohttp.ClientError as e:
                logger.error(f"❌ Ошибка соединения: {e}")
                raise Exception(f"Connection error: {e}")
    
    async def get_warehouses(self) -> List[Dict[str, Any]]:
        """
        Получает список всех складов WB
        GET /api/v1/warehouses
        """
        logger.info("📋 Получаем список складов...")
        
        result = await self._make_request("GET", "/api/v1/warehouses")
        
        # API может возвращать либо массив напрямую, либо объект с полем result
        if isinstance(result, list):
            # Нормализуем поля для совместимости с нашим кодом
            normalized_warehouses = []
            for warehouse in result:
                # Создаем нормализованную версию склада
                normalized = {
                    'id': warehouse.get('ID', 0),  # Важно: поле ID с большой буквы!
                    'name': warehouse.get('name', ''),
                    'address': warehouse.get('address', ''),
                    'workTime': warehouse.get('workTime', ''),
                    'acceptsQR': warehouse.get('acceptsQR', False),
                    'isActive': warehouse.get('isActive', False),
                    'isTransitActive': warehouse.get('isTransitActive', False)
                }
                normalized_warehouses.append(normalized)
            return normalized_warehouses
        else:
            # Аналогично для случая, когда API возвращает объект с result
            warehouses_data = result.get("result", [])
            normalized_warehouses = []
            for warehouse in warehouses_data:
                normalized = {
                    'id': warehouse.get('ID', 0),  # И здесь тоже!
                    'name': warehouse.get('name', ''),
                    'address': warehouse.get('address', ''),
                    'workTime': warehouse.get('workTime', ''),
                    'acceptsQR': warehouse.get('acceptsQR', False),
                    'isActive': warehouse.get('isActive', False),
                    'isTransitActive': warehouse.get('isTransitActive', False)
                }
                normalized_warehouses.append(normalized)
            return normalized_warehouses
    
    async def check_acceptance_options(self, products: List[ProductInfo], 
                                     warehouse_id: Optional[int] = None) -> List[SlotInfo]:
        """
        Проверяет доступные опции приемки для списка товаров
        POST /api/v1/acceptance/options
        """
        # Готовим данные для запроса
        request_data = []
        for product in products:
            request_data.append({
                "quantity": product.quantity,
                "barcode": product.barcode
            })
        
        params = {}
        if warehouse_id:
            params["warehouseID"] = str(warehouse_id)
        
        logger.info(f"🔍 Проверяем опции приемки для {len(products)} товаров")
        
        response = await self._make_request("POST", "/api/v1/acceptance/options", 
                                          data=request_data, params=params)
        
        # Парсим ответ - API может возвращать либо массив, либо объект с result
        response_data = response
        if isinstance(response, dict) and "result" in response:
            response_data = response["result"]
        elif not isinstance(response, list):
            logger.warning("⚠️ Неожиданная структура ответа от API")
            response_data = []
        
        # Парсим ответ
        slots = []
        for item in response_data:
            warehouses = []
            
            if item.get("warehouses"):
                for wh in item["warehouses"]:
                    warehouses.append(WarehouseOption(
                        warehouse_id=wh["warehouseID"],
                        can_box=wh.get("canBox", False),
                        can_monopollet=wh.get("canMonopallet", False),
                        can_supersafe=wh.get("canSupersafe", False)
                    ))
            
            slots.append(SlotInfo(
                barcode=item["barcode"],
                warehouses=warehouses,
                error=item.get("error"),
                is_error=item.get("isError", False)
            ))
        
        return slots
        
    async def get_acceptance_coefficients(self, warehouse_ids: Optional[List[int]] = None) -> List[AcceptanceCoefficient]:
        """
        Получает коэффициенты приемки для конкретных складов на ближайшие 14 дней
        GET /api/v1/acceptance/coefficients
        
        Args:
            warehouse_ids: Список ID складов. Если None, возвращает данные по всем складам
            
        Returns:
            Список коэффициентов приемки с полной информацией о доступности слотов
        """
        params = {}
        if warehouse_ids:
            # Конвертируем список ID в строку формата "507,117501"
            params["warehouseIDs"] = ",".join(map(str, warehouse_ids))
        
        logger.info(f"📊 Получаем коэффициенты приемки для {len(warehouse_ids) if warehouse_ids else 'всех'} складов")
        
        # Используем специальный endpoint_type для соблюдения лимита 6 запросов/минуту
        response = await self._make_request("GET", "/api/v1/acceptance/coefficients", 
                                          params=params, endpoint_type='coefficients')
        
        # Парсим ответ - согласно документации это должен быть массив
        coefficients_data = response
        if isinstance(response, dict) and "result" in response:
            coefficients_data = response["result"]
        elif not isinstance(response, list):
            logger.warning("⚠️ Неожиданная структура ответа от coefficients API")
            return []
        
        # Конвертируем в объекты AcceptanceCoefficient
        coefficients = []
        for item in coefficients_data:
            try:
                # Парсим дату из ISO формата
                date_str = item.get("date", "")
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                
                coefficient = AcceptanceCoefficient(
                    date=date_obj,
                    coefficient=item.get("coefficient", -1),
                    warehouse_id=item.get("warehouseID", 0),
                    warehouse_name=item.get("warehouseName", ""),
                    allow_unload=item.get("allowUnload", False),
                    box_type_name=item.get("boxTypeName", ""),
                    box_type_id=item.get("boxTypeID", 0),
                    storage_coef=item.get("storageCoef"),
                    delivery_coef=item.get("deliveryCoef"),
                    delivery_base_liter=item.get("deliveryBaseLiter"),
                    delivery_additional_liter=item.get("deliveryAdditionalLiter"),
                    storage_base_liter=item.get("storageBaseLiter"),
                    storage_additional_liter=item.get("storageAdditionalLiter"),
                    is_sorting_center=item.get("isSortingCenter", False)
                )
                
                coefficients.append(coefficient)
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка парсинга коэффициента: {e}")
                continue
        
        logger.info(f"✅ Получено {len(coefficients)} коэффициентов приемки")
        return coefficients
    
    async def test_connection(self) -> bool:
        """
        Тестирует соединение с API WB
        Полезно для проверки корректности API ключа
        """
        try:
            logger.info("🧪 Тестируем соединение с WB API...")
            warehouses = await self.get_warehouses()
            logger.info(f"✅ Соединение успешно! Доступно складов: {len(warehouses)}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при тестировании соединения: {e}")
            return False
    
    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику работы rate limiter
        """
        return {
            'general_last_request': self.rate_limiter.last_request_time.get('general', 0),
            'coefficients_last_request': self.rate_limiter.last_request_time.get('coefficients', 0)
        }


# Пример использования (для тестирования когда получим API ключ)
async def test_wb_api():
    """
    Тестовая функция для проверки работы с API
    """
    api = WildberriesAPI("ваш_api_ключ_здесь")
    
    # Тестируем соединение
    if not await api.test_connection():
        return
    
    # Тестируем проверку слотов
    test_products = [
        ProductInfo(barcode="test_barcode_1", quantity=1),
        ProductInfo(barcode="test_barcode_2", quantity=5)
    ]
    
    slots = await api.check_acceptance_options(test_products)
    
    for slot in slots:
        if slot.is_error:
            print(f"❌ Ошибка для {slot.barcode}: {slot.error}")
        else:
            print(f"✅ {slot.barcode}: доступно складов - {len(slot.warehouses)}")


if __name__ == "__main__":
    # Запуск теста (раскомментируй когда получим API ключ)
    # asyncio.run(test_wb_api())
    pass