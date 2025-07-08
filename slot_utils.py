"""
Утилиты для работы со слотами, разделенные чтобы избежать циклических импортов
"""

from typing import List, Dict, Any
import json
import logging
import os

logger = logging.getLogger(__name__)


def get_current_active_slots() -> List[Dict[str, Any]]:
    """
    Возвращает текущие активные слоты для новых пользователей
    Читает из файла current_active_slots.json
    """
    active_slots_file = "current_active_slots.json"
    
    try:
        if os.path.exists(active_slots_file):
            with open(active_slots_file, "r", encoding="utf-8") as f:
                slots_data = json.load(f)
                logger.info(f"📥 Загружено {len(slots_data)} активных слотов")
                return slots_data
        else:
            logger.info("📂 Файл активных слотов не найден, возвращаем пустой список")
            return []
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки активных слотов: {e}")
        return []