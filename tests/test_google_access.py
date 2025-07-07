#!/usr/bin/env python3
"""
Диагностический скрипт для проверки доступа к Google Sheets
"""

import os
import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def check_credentials_file():
    """Проверяем файл credentials.json"""
    print("🔐 ПРОВЕРКА ФАЙЛА CREDENTIALS.JSON")
    print("="*50)
    
    if not os.path.exists("credentials.json"):
        print("❌ Файл credentials.json не найден!")
        return False
    
    try:
        with open("credentials.json", "r") as f:
            creds_data = json.load(f)
        
        print("✅ Файл credentials.json найден и корректен")
        
        # Показываем важную информацию
        client_email = creds_data.get("client_email", "НЕ НАЙДЕН")
        project_id = creds_data.get("project_id", "НЕ НАЙДЕН")
        
        print(f"📧 Service Account Email: {client_email}")
        print(f"🏗️ Project ID: {project_id}")
        
        print(f"\n💡 ВАЖНО: Добавьте email {client_email}")
        print("   в настройки доступа к Google Sheets таблице!")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка в JSON файле: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return False

def check_sheets_url():
    """Проверяем URL таблицы"""
    print(f"\n📊 ПРОВЕРКА URL ТАБЛИЦЫ")
    print("="*50)
    
    sheets_url = os.getenv("GOOGLE_SHEETS_URL", "")
    
    if not sheets_url:
        print("❌ GOOGLE_SHEETS_URL не установлен в .env файле!")
        return None
    
    print(f"🔗 URL: {sheets_url}")
    
    # Извлекаем ID таблицы
    patterns = [
        r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
        r'key=([a-zA-Z0-9-_]+)',
        r'/d/([a-zA-Z0-9-_]+)'
    ]
    
    sheet_id = None
    for pattern in patterns:
        match = re.search(pattern, sheets_url)
        if match:
            sheet_id = match.group(1)
            break
    
    if sheet_id:
        print(f"✅ Извлечен ID таблицы: {sheet_id}")
        print(f"🔗 Прямая ссылка: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        return sheet_id
    else:
        print("❌ Не удалось извлечь ID из URL!")
        print("💡 URL должен быть вида:")
        print("   https://docs.google.com/spreadsheets/d/SHEET_ID/edit")
        return None

async def test_direct_api_access():
    """Тестируем прямой доступ к Google Sheets API"""
    print(f"\n🔌 ТЕСТ ПРЯМОГО ДОСТУПА К API")
    print("="*50)
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        # Авторизуемся
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        client = gspread.authorize(creds)
        
        print("✅ Авторизация в Google API успешна")
        
        # Пробуем получить список доступных таблиц
        try:
            spreadsheets = client.list_permissions()
            print(f"📋 Найдено доступных таблиц: {len(spreadsheets)}")
        except:
            print("ℹ️ Не удалось получить список таблиц (это нормально)")
        
        # Пробуем открыть конкретную таблицу
        sheet_id = check_sheets_url()
        if sheet_id:
            try:
                workbook = client.open_by_key(sheet_id)
                print(f"✅ Таблица успешно открыта: {workbook.title}")
                
                # Получаем список листов
                worksheets = workbook.worksheets()
                print(f"📄 Листов в таблице: {len(worksheets)}")
                
                for i, ws in enumerate(worksheets):
                    print(f"  {i+1}. {ws.title}")
                
                return True
                
            except Exception as e:
                print(f"❌ Ошибка открытия таблицы: {e}")
                
                if "404" in str(e):
                    print("💡 Ошибка 404 означает:")
                    print("  - Service Account нет доступа к таблице")
                    print("  - Или таблица не существует")
                
                return False
        
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False

def print_solution_steps():
    """Выводим пошаговое решение проблемы"""
    print(f"\n🛠️ ПОШАГОВОЕ РЕШЕНИЕ")
    print("="*50)
    
    print("1. 📧 Найдите email Service Account в credentials.json")
    print("   (поле 'client_email')")
    
    print("\n2. 🔗 Откройте вашу Google Sheets таблицу в браузере")
    
    print("\n3. 📤 Нажмите кнопку 'Поделиться' (Share) в правом верхнем углу")
    
    print("\n4. ➕ Добавьте email Service Account с правами:")
    print("   - 'Редактор' (Editor) или 'Читатель' (Viewer)")
    
    print("\n5. ✅ Убедитесь, что таблица НЕ имеет ограниченного доступа")
    print("   (не должно быть 'Ограничено определенным пользователям')")
    
    print("\n6. 🔄 Повторите тест")

async def main():
    """Основная функция диагностики"""
    print("🔍 ДИАГНОСТИКА ДОСТУПА К GOOGLE SHEETS")
    print("="*60)
    
    # Проверяем все компоненты по очереди
    creds_ok = check_credentials_file()
    
    if not creds_ok:
        print("\n❌ Сначала исправьте проблемы с credentials.json")
        return
    
    sheet_id = check_sheets_url()
    
    if not sheet_id:
        print("\n❌ Сначала исправьте URL таблицы в .env файле")
        return
    
    # Тестируем прямой доступ
    api_ok = await test_direct_api_access()
    
    if not api_ok:
        print_solution_steps()
    else:
        print("\n🎉 ВСЕ РАБОТАЕТ! Можно запускать основное тестирование.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())