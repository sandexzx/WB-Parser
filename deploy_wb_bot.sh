#!/bin/bash

# =============================================================================
# WB SLOTS MONITOR - АВТОМАТИЧЕСКИЙ ДЕПЛОЙ НА UBUNTU 24.04
# =============================================================================
# Автоматическая установка и настройка телеграм-бота для мониторинга слотов WB
# Создан для проекта WB Parser
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
USER_NAME="wbmonitor"
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
    echo "║                    🚀 WB SLOTS MONITOR 🚀                    ║"
    echo "║                                                              ║"
    echo "║  Автоматический деплой телеграм-бота для мониторинга        ║"
    echo "║  слотов приемки на Wildberries                               ║"
    echo "║                                                              ║"
    echo "║  📦 Python 3.12 + aiogram 3.19.0                           ║"
    echo "║  🔄 Systemd сервис с автозапуском                           ║"
    echo "║  ⚡ Полная автоматизация настройки                          ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo
}

# Сбор конфигурации от пользователя
collect_configuration() {
    log_step "Сбор конфигурационных данных"
    echo
    
    # GitHub репозиторий
    echo -e "${CYAN}📂 Настройка источника кода:${NC}"
    GITHUB_URL="https://github.com/sandexzx/WB-Parser.git"
    log_info "Используется репозиторий по умолчанию: $GITHUB_URL"
    
    if [[ -n "$GITHUB_URL" ]]; then
        read -p "Введите ветку (по умолчанию: main): " GITHUB_BRANCH
        GITHUB_BRANCH=${GITHUB_BRANCH:-main}
        USE_GITHUB=true
    else
        USE_GITHUB=false
        log_info "Будет использована локальная установка (файлы должны быть в текущей директории)"
    fi
    
    echo
    echo -e "${CYAN}🔐 API ключи и токены (ОБЯЗАТЕЛЬНО):${NC}"
    
    # WB API ключ
    while [[ -z "$WB_API_KEY" ]]; do
        read -p "Введите WB API ключ: " WB_API_KEY
        if [[ -z "$WB_API_KEY" ]]; then
            log_warning "WB API ключ обязателен для работы мониторинга!"
        fi
    done
    
    # Telegram Bot Token
    while [[ -z "$TELEGRAM_BOT_TOKEN" ]]; do
        read -p "Введите Telegram Bot Token: " TELEGRAM_BOT_TOKEN
        if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
            log_warning "Telegram Bot Token обязателен для уведомлений!"
        fi
    done
    
    echo
    echo -e "${CYAN}📊 Google Sheets настройки:${NC}"
    read -p "Введите URL Google Sheets таблицы: " GOOGLE_SHEETS_URL
    
    if [[ -n "$GOOGLE_SHEETS_URL" ]]; then
        log_info "Убедитесь, что файл credentials.json находится в директории проекта"
        log_info "Service Account должен иметь доступ к указанной таблице"
    fi
    
    echo
    echo -e "${CYAN}⚙️ Дополнительные настройки:${NC}"
    
    # Интервал проверки
    read -p "Интервал проверки в секундах (по умолчанию: 120): " CHECK_INTERVAL
    CHECK_INTERVAL=${CHECK_INTERVAL:-120}
    
    # Уровень логирования
    echo "Выберите уровень логирования:"
    echo "1) DEBUG (подробные логи)"
    echo "2) INFO (стандартные логи)"
    echo "3) WARNING (только предупреждения и ошибки)"
    read -p "Введите номер (по умолчанию: 2): " LOG_LEVEL_CHOICE
    
    case $LOG_LEVEL_CHOICE in
        1) LOG_LEVEL="DEBUG" ;;
        3) LOG_LEVEL="WARNING" ;;
        *) LOG_LEVEL="INFO" ;;
    esac
    
    # Показываем сводку
    echo
    echo -e "${YELLOW}📋 СВОДКА КОНФИГУРАЦИИ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    if [[ "$USE_GITHUB" == "true" ]]; then
        echo "│ Источник: GitHub ($GITHUB_URL, ветка: $GITHUB_BRANCH)"
    else
        echo "│ Источник: Локальная директория"
    fi
    echo "│ WB API ключ: ${WB_API_KEY:0:10}..."
    echo "│ Telegram Token: ${TELEGRAM_BOT_TOKEN:0:15}..."
    echo "│ Google Sheets: ${GOOGLE_SHEETS_URL:0:40}..."
    echo "│ Интервал проверки: $CHECK_INTERVAL сек"
    echo "│ Уровень логирования: $LOG_LEVEL"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    
    read -p "Продолжить установку с этими настройками? (y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "Установка отменена пользователем"
        exit 0
    fi
}

# Обновление системы и установка зависимостей
setup_system() {
    log_step "Обновление системы и установка зависимостей"
    
    # Обновление пакетов
    log_info "Обновление списка пакетов..."
    apt update -qq
    
    # Установка необходимых пакетов
    log_info "Установка системных пакетов..."
    apt install -y \
        software-properties-common \
        build-essential \
        curl \
        wget \
        git \
        sudo \
        systemd \
        python3-pip \
        python3-venv \
        python3-dev \
        sqlite3 \
        nginx \
        ufw \
        htop \
        nano \
        vim \
        unzip \
        ca-certificates
    
    # Добавление репозитория Python 3.12 если нужно
    if ! command -v python3.12 &> /dev/null; then
        log_info "Установка Python 3.12..."
        add-apt-repository -y ppa:deadsnakes/ppa
        apt update -qq
        apt install -y python3.12 python3.12-venv python3.12-dev
    fi
    
    log_success "Системные зависимости установлены"
}

# Создание пользователя для сервиса
create_service_user() {
    log_step "Создание пользователя для сервиса"
    
    if ! id "$USER_NAME" &>/dev/null; then
        log_info "Создание пользователя $USER_NAME..."
        useradd --system --home-dir "$PROJECT_DIR" --shell /bin/bash "$USER_NAME"
        log_success "Пользователь $USER_NAME создан"
    else
        log_info "Пользователь $USER_NAME уже существует"
    fi
}

# Настройка директории проекта
setup_project_directory() {
    log_step "Настройка директории проекта"
    
    # Создание директории
    log_info "Создание директории $PROJECT_DIR..."
    mkdir -p "$PROJECT_DIR"
    mkdir -p "$PROJECT_DIR/found_slots"
    
    # Получение кода
    if [[ "$USE_GITHUB" == "true" ]]; then
        log_info "Клонирование репозитория из GitHub..."
        if [[ -d "$PROJECT_DIR/.git" ]]; then
            cd "$PROJECT_DIR"
            git fetch origin
            git reset --hard "origin/$GITHUB_BRANCH"
        else
            rm -rf "$PROJECT_DIR"/*
            git clone --branch "$GITHUB_BRANCH" "$GITHUB_URL" "$PROJECT_DIR"
        fi
    else
        log_info "Копирование файлов из текущей директории..."
        # Копируем все .py файлы и необходимые файлы
        cp -r ./*.py "$PROJECT_DIR/" 2>/dev/null || true
        cp -r ./requirements.txt "$PROJECT_DIR/" 2>/dev/null || true
        cp -r ./credentials.json "$PROJECT_DIR/" 2>/dev/null || true
        cp -r ./.env.example "$PROJECT_DIR/" 2>/dev/null || true
        cp -r ./tests "$PROJECT_DIR/" 2>/dev/null || true
        
        # Проверяем наличие основных файлов
        if [[ ! -f "$PROJECT_DIR/main.py" ]]; then
            log_error "Файл main.py не найден в текущей директории!"
            log_info "Убедитесь, что запускаете скрипт из директории с кодом проекта"
            exit 1
        fi
    fi
    
    log_success "Код проекта размещен в $PROJECT_DIR"
}

# Настройка Python окружения
setup_python_environment() {
    log_step "Настройка Python окружения"
    
    cd "$PROJECT_DIR"
    
    # Создание виртуального окружения
    log_info "Создание виртуального окружения..."
    python3.12 -m venv "$VENV_PATH"
    
    # Обновление pip
    log_info "Обновление pip..."
    "$VENV_PATH/bin/pip" install --upgrade pip setuptools wheel
    
    # Установка зависимостей
    log_info "Установка Python зависимостей..."
    if [[ -f "requirements.txt" ]]; then
        "$VENV_PATH/bin/pip" install -r requirements.txt
    else
        # Устанавливаем основные зависимости вручную
        log_warning "requirements.txt не найден, устанавливаем базовые зависимости..."
        "$VENV_PATH/bin/pip" install \
            aiogram==3.19.0 \
            aiohttp \
            gspread \
            google-auth \
            google-auth-oauthlib \
            google-auth-httplib2 \
            python-dotenv \
            python-dateutil \
            APScheduler \
            pydantic \
            pytest \
            pytest-asyncio
    fi
    
    log_success "Python окружение настроено"
}

# Создание конфигурационного файла .env
create_env_file() {
    log_step "Создание конфигурационного файла"
    
    log_info "Создание .env файла..."
    cat > "$PROJECT_DIR/.env" << EOF
# WB API конфигурация
WB_API_KEY=$WB_API_KEY
WB_BASE_URL=https://supplies-api.wildberries.ru

# Rate limiting настройки
MAX_REQUESTS_PER_MINUTE=30
REQUEST_DELAY_SECONDS=2.0
COEFFICIENTS_REQUESTS_PER_MINUTE=6

# Адаптивный мониторинг
ENABLE_ADAPTIVE_MONITORING=true
MIN_MONITORING_INTERVAL=10

# Google Sheets настройки
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEETS_URL=$GOOGLE_SHEETS_URL

# Telegram бот
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN

# База данных
DATABASE_URL=sqlite:///wb_monitor.db

# Логирование
LOG_LEVEL=$LOG_LEVEL
LOG_FILE=logs/wb_monitor.log

# Интервалы проверки
CHECK_INTERVAL_SECONDS=$CHECK_INTERVAL
EOF
    
    log_success "Конфигурационный файл .env создан"
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
Documentation=https://github.com/your-repo/wb-slots-monitor
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

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$PROJECT_DIR
ProtectHome=true

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

# Настройка прав доступа
setup_permissions() {
    log_step "Настройка прав доступа"
    
    # Изменение владельца директории
    log_info "Настройка владельца файлов..."
    chown -R "$USER_NAME:$USER_NAME" "$PROJECT_DIR"
    
    # Настройка прав на файлы
    chmod 755 "$PROJECT_DIR"
    chmod 644 "$PROJECT_DIR"/.env
    chmod 600 "$PROJECT_DIR"/credentials.json 2>/dev/null || true
    chmod 755 "$PROJECT_DIR"/*.py
    
    # Права на директории
    mkdir -p "$PROJECT_DIR/logs" # Создаем папку logs здесь
    chmod 755 "$PROJECT_DIR/logs"
    chmod 755 "$PROJECT_DIR/found_slots"
    
    log_success "Права доступа настроены"
}

# Настройка базовой безопасности
setup_security() {
    log_step "Настройка базовой безопасности"
    
    # Базовая настройка UFW
    log_info "Настройка базового firewall..."
    ufw --force reset > /dev/null 2>&1
    ufw default deny incoming > /dev/null 2>&1
    ufw default allow outgoing > /dev/null 2>&1
    ufw allow ssh > /dev/null 2>&1
    ufw --force enable > /dev/null 2>&1
    
    log_success "Базовая безопасность настроена"
}

# Тестирование установки
test_installation() {
    log_step "Тестирование установки"
    
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
        log_warning "Некоторые зависимости могут отсутствовать"
    fi
    
    # Проверка конфигурации
    log_info "Проверка конфигурации..."
    if [[ -f ".env" && -s ".env" ]]; then
        log_success "Конфигурационный файл создан"
    else
        log_error "Проблема с конфигурационным файлом"
        return 1
    fi
    
    # Проверка основного файла
    log_info "Проверка главного файла..."
    if "$VENV_PATH/bin/python" -c "import $MAIN_FILE" > /dev/null 2>&1 || true; then
        log_success "Главный файл доступен"
    else
        log_warning "Возможны проблемы с импортом главного файла"
    fi
    
    log_success "Базовое тестирование завершено"
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
    sleep 3
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
    echo "│ Логи:          $PROJECT_DIR/logs/"
    echo "│ Найденные слоты: $PROJECT_DIR/found_slots/"
    echo "│ Сервис:        /etc/systemd/system/$SERVICE_NAME.service"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${CYAN}🔧 ОБСЛУЖИВАНИЕ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│ Редактировать конфигурацию:                               │"
    echo "│   sudo nano $PROJECT_DIR/.env"
    echo "│   sudo systemctl restart $SERVICE_NAME"
    echo "│                                                             │"
    echo "│ Обновить код (если используется Git):                      │"
    echo "│   cd $PROJECT_DIR"
    echo "│   sudo -u $USER_NAME git pull origin $GITHUB_BRANCH"
    echo "│   sudo systemctl restart $SERVICE_NAME"
    echo "│                                                             │"
    echo "│ Проверить работу бота:                                     │"
    echo "│   curl -s https://api.telegram.org/bot\$TELEGRAM_BOT_TOKEN/getMe"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${GREEN}✅ ДЕПЛОЙ ЗАВЕРШЕН УСПЕШНО!${NC}"
    echo -e "${YELLOW}🚀 Бот запущен и готов к работе!${NC}"
    echo
}

# Функция очистки при ошибке
cleanup_on_error() {
    log_error "Произошла ошибка во время установки"
    log_info "Выполняется очистка..."
    
    # Остановка сервиса если он был создан
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    
    # Удаление файла сервиса
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    
    log_info "Очистка завершена"
    exit 1
}

# Основная функция
main() {
    # Установка trap для обработки ошибок
    trap cleanup_on_error ERR
    
    # Проверки и приветствие
    check_root
    show_banner
    
    # Сбор конфигурации
    collect_configuration
    
    # Выполнение установки
    log_info "Начинаем установку WB Slots Monitor..."
    echo
    
    setup_system
    create_service_user
    setup_project_directory
    detect_main_file
    setup_python_environment
    create_env_file
    create_systemd_service
    setup_permissions
    setup_security
    test_installation
    start_service
    
    # Завершение
    echo
    show_management_help
}

# Запуск основной функции
main "$@"
