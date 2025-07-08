#!/bin/bash

# =============================================================================
# WB SLOTS MONITOR - ВТОРАЯ ЧАСТЬ ДЕПЛОЯ НА UBUNTU 24.04
# =============================================================================
# Автоматическая установка и настройка телеграм-бота для мониторинга слотов WB
# ВТОРАЯ ЧАСТЬ: Создание сервиса, запуск и настройка автозапуска
# =============================================================================

set -e  # Остановка скрипта при любой ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Переменные
PROJECT_NAME="wb-slots-monitor"
PROJECT_DIR="/opt/$PROJECT_NAME"
SERVICE_NAME="wb-slots-monitor"
USER_NAME="root"
PYTHON_VERSION="3.12"
VENV_PATH="$PROJECT_DIR/.venv"

# Логирование
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${PURPLE}[STEP]${NC} $1"
}

# Проверка запуска от root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Этот скрипт должен запускаться от имени root"
        log_info "Запустите: sudo bash $0"
        exit 1
    fi
}

# Приветствие и информация
show_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                  🚀 WB SLOTS MONITOR 🚀                      ║"
    echo "║                                                              ║"
    echo "║            ЧАСТЬ 2: ЗАПУСК И НАСТРОЙКА СЕРВИСА              ║"
    echo "║                                                              ║"
    echo "║  Создание systemd сервиса и запуск бота                     ║"
    echo "║                                                              ║"
    echo "║  🔄 Systemd сервис с автозапуском                           ║"
    echo "║  ⚡ Автоматическое управление                               ║"
    echo "║  📊 Мониторинг и логирование                                ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo
}

# Проверка готовности к второму этапу
check_prerequisites() {
    log_step "Проверка готовности к запуску"
    
    # Проверка существования директории проекта
    if [[ ! -d "$PROJECT_DIR" ]]; then
        log_error "Директория проекта не найдена: $PROJECT_DIR"
        log_info "Запустите сначала первую часть: deploy_wb_bot_first.sh"
        exit 1
    fi
    
    # Проверка наличия .env файла
    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        log_error "Файл .env не найден в $PROJECT_DIR"
        log_info "Запустите сначала первую часть: deploy_wb_bot_first.sh"
        exit 1
    fi
    
    # Проверка наличия credentials.json
    if [[ ! -f "$PROJECT_DIR/credentials.json" ]]; then
        log_error "Файл credentials.json не найден в $PROJECT_DIR"
        log_info "Создайте файл credentials.json с данными Google Service Account"
        log_info "Пример содержимого:"
        echo "{"
        echo "  \"type\": \"service_account\","
        echo "  \"project_id\": \"your-project-id\","
        echo "  \"private_key_id\": \"...\","
        echo "  \"private_key\": \"...\","
        echo "  \"client_email\": \"...\","
        echo "  \"client_id\": \"...\","
        echo "  \"auth_uri\": \"https://accounts.google.com/o/oauth2/auth\","
        echo "  \"token_uri\": \"https://oauth2.googleapis.com/token\""
        echo "}"
        exit 1
    fi
    
    # Проверка наличия виртуального окружения
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Виртуальное окружение не найдено: $VENV_PATH"
        log_info "Запустите сначала первую часть: deploy_wb_bot_first.sh"
        exit 1
    fi
    
    log_success "Все предварительные условия выполнены"
}

# Определение главного файла для запуска
detect_main_file() {
    log_step "Определение главного файла для запуска"
    
    cd "$PROJECT_DIR"
    
    # Главный файл всегда run_with_bot.py
    if [[ -f "run_with_bot.py" ]]; then
        MAIN_FILE="run_with_bot.py"
        log_info "Установлен run_with_bot.py как главный файл для запуска."
    else
        log_error "Файл run_with_bot.py не найден в директории проекта ($PROJECT_DIR)!"
        log_info "Убедитесь, что run_with_bot.py присутствует для корректного запуска."
        exit 1
    fi
    
    log_success "Главный файл: $MAIN_FILE"
}

# Создание systemd сервиса
create_systemd_service() {
    log_step "Создание systemd сервиса"
    
    log_info "Создание файла сервиса /etc/systemd/system/$SERVICE_NAME.service..."
    cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=WB Slots Monitor - Telegram Bot for Wildberries Slot Monitoring
Documentation=https://github.com/sandexzx/WB-Parser
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$VENV_PATH/bin
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$VENV_PATH/bin/python $PROJECT_DIR/$MAIN_FILE
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Безопасность (упрощенная для root)
NoNewPrivileges=false

# Лимиты ресурсов
LimitNOFILE=65536
MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF
    
    # Перезагрузка systemd
    log_info "Перезагрузка конфигурации systemd..."
    systemctl daemon-reload
    
    log_success "Systemd сервис создан"
}

# Финальная настройка прав доступа
setup_final_permissions() {
    log_step "Финальная настройка прав доступа"
    
    # Настройка прав на credentials.json
    chmod 600 "$PROJECT_DIR/credentials.json"
    
    # Проверка и создание необходимых директорий
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/found_slots"
    chmod 755 "$PROJECT_DIR/logs"
    chmod 755 "$PROJECT_DIR/found_slots"
    
    log_success "Финальные права доступа настроены"
}

# Предварительное тестирование
test_configuration() {
    log_step "Тестирование конфигурации"
    
    cd "$PROJECT_DIR"
    
    # Проверка Python окружения
    log_info "Проверка Python окружения..."
    if "$VENV_PATH/bin/python" -c "import sys; print(f'Python {sys.version}')" > /dev/null 2>&1; then
        log_success "Python окружение работает корректно"
    else
        log_error "Проблема с Python окружением"
        return 1
    fi
    
    # Проверка зависимостей
    log_info "Проверка ключевых зависимостей..."
    if "$VENV_PATH/bin/python" -c "import aiogram, aiohttp, gspread; print('Зависимости OK')" > /dev/null 2>&1; then
        log_success "Основные зависимости установлены"
    else
        log_error "Проблема с зависимостями"
        return 1
    fi
    
    # Проверка доступности credentials.json
    log_info "Проверка credentials.json..."
    if "$VENV_PATH/bin/python" -c "import json; json.load(open('credentials.json')); print('Credentials OK')" > /dev/null 2>&1; then
        log_success "Файл credentials.json валиден"
    else
        log_error "Проблема с файлом credentials.json"
        return 1
    fi
    
    # Проверка переменных окружения
    log_info "Проверка .env файла..."
    if source "$PROJECT_DIR/.env" && [[ -n "$TELEGRAM_BOT_TOKEN" && -n "$TELEGRAM_CHAT_ID" && -n "$WB_API_KEY" ]]; then
        log_success "Основные переменные окружения настроены"
    else
        log_error "Проблема с переменными окружения в .env"
        return 1
    fi
    
    log_success "Конфигурация протестирована"
}

# Запуск сервиса
start_service() {
    log_step "Запуск и настройка автозапуска сервиса"
    
    # Включение автозапуска
    log_info "Включение автозапуска сервиса..."
    systemctl enable "$SERVICE_NAME"
    
    # Запуск сервиса
    log_info "Запуск сервиса..."
    systemctl start "$SERVICE_NAME"
    
    # Проверка статуса
    sleep 5
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Сервис успешно запущен и работает"
    else
        log_warning "Сервис запущен, но могут быть проблемы"
        log_info "Проверьте логи: journalctl -u $SERVICE_NAME -f"
    fi
}

# Показ справки по управлению
show_management_help() {
    log_step "Справка по управлению ботом"
    
    echo
    echo -e "${CYAN}🔧 УПРАВЛЕНИЕ СЕРВИСОМ WB SLOTS MONITOR:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                     SYSTEMD КОМАНДЫ                        │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ Запуск:        systemctl start $SERVICE_NAME"
    echo "│ Остановка:     systemctl stop $SERVICE_NAME"
    echo "│ Перезапуск:    systemctl restart $SERVICE_NAME"
    echo "│ Статус:        systemctl status $SERVICE_NAME"
    echo "│ Автозапуск:    systemctl enable $SERVICE_NAME"
    echo "│ Отключить:     systemctl disable $SERVICE_NAME"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${CYAN}📊 МОНИТОРИНГ И ЛОГИ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│ Логи в реальном времени:                                   │"
    echo "│   journalctl -u $SERVICE_NAME -f"
    echo "│                                                             │"
    echo "│ Последние 50 строк логов:                                  │"
    echo "│   journalctl -u $SERVICE_NAME -n 50"
    echo "│                                                             │"
    echo "│ Логи за сегодня:                                           │"
    echo "│   journalctl -u $SERVICE_NAME --since today"
    echo "│                                                             │"
    echo "│ Файлы логов приложения:                                    │"
    echo "│   tail -f $PROJECT_DIR/logs/wb_monitor.log"
    echo "│   tail -f $PROJECT_DIR/logs/telegram_bot.log"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${CYAN}📁 ФАЙЛЫ И ДИРЕКТОРИИ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│ Проект:        $PROJECT_DIR"
    echo "│ Конфигурация:  $PROJECT_DIR/.env"
    echo "│ Credentials:   $PROJECT_DIR/credentials.json"
    echo "│ Логи:          $PROJECT_DIR/logs/"
    echo "│ Найденные слоты: $PROJECT_DIR/found_slots/"
    echo "│ Сервис:        /etc/systemd/system/$SERVICE_NAME.service"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${CYAN}🔧 ОБСЛУЖИВАНИЕ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│ Редактировать конфигурацию:                               │"
    echo "│   nano $PROJECT_DIR/.env"
    echo "│   systemctl restart $SERVICE_NAME"
    echo "│                                                             │"
    echo "│ Обновить код (если используется Git):                      │"
    echo "│   cd $PROJECT_DIR"
    echo "│   git pull origin main"
    echo "│   systemctl restart $SERVICE_NAME"
    echo "│                                                             │"
    echo "│ Проверить работу бота:                                     │"
    echo "│   curl -s https://api.telegram.org/bot\\$TELEGRAM_BOT_TOKEN/getMe"
    echo "│                                                             │"
    echo "│ Тестовый запуск (без сервиса):                             │"
    echo "│   cd $PROJECT_DIR"
    echo "│   $VENV_PATH/bin/python $MAIN_FILE"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${CYAN}📊 БЫСТРАЯ ПРОВЕРКА СТАТУСА:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│ Статус сервиса: $(systemctl is-active $SERVICE_NAME 2>/dev/null || echo 'неактивен')"
    echo "│ Автозапуск: $(systemctl is-enabled $SERVICE_NAME 2>/dev/null || echo 'отключен')"
    echo "│ Порт активности: $(netstat -tuln | grep -E ':(443|80|8080)' | wc -l) открытых портов"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${GREEN}✅ ПОЛНЫЙ ДЕПЛОЙ ЗАВЕРШЕН УСПЕШНО!${NC}"
    echo -e "${YELLOW}🚀 Бот запущен и готов к работе!${NC}"
    echo -e "${CYAN}📱 Проверьте работу бота в Telegram!${NC}"
    echo
}

# Функция очистки при ошибке
cleanup_on_error() {
    log_error "Произошла ошибка во время второго этапа установки"
    log_info "Выполняется очистка сервиса..."
    
    # Остановка сервиса если он был создан
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    
    # Удаление файла сервиса
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    
    log_info "Очистка завершена"
    log_info "Код проекта остался в $PROJECT_DIR"
    exit 1
}

# Основная функция
main() {
    # Установка trap для обработки ошибок
    trap cleanup_on_error ERR
    
    # Проверки и приветствие
    check_root
    show_banner
    
    # Проверка готовности
    check_prerequisites
    
    # Выполнение второго этапа
    log_info "Начинаем второй этап установки WB Slots Monitor..."
    echo
    
    detect_main_file
    create_systemd_service
    setup_final_permissions
    test_configuration
    start_service
    
    # Завершение
    echo
    show_management_help
}

# Запуск основной функции
main "$@"