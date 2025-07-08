#!/bin/bash

# =============================================================================
# WB SLOTS MONITOR - ПЕРВАЯ ЧАСТЬ ДЕПЛОЯ НА UBUNTU 24.04
# =============================================================================
# Автоматическая установка и настройка телеграм-бота для мониторинга слотов WB
# ПЕРВАЯ ЧАСТЬ: Развертывание кода, настройка env переменных, установка зависимостей
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
    echo "║             ЧАСТЬ 1: ПОДГОТОВКА И НАСТРОЙКА                 ║"
    echo "║                                                              ║"
    echo "║  Автоматический деплой телеграм-бота для мониторинга        ║"
    echo "║  слотов приемки на Wildberries                               ║"
    echo "║                                                              ║"
    echo "║  📦 Python 3.12 + aiogram 3.19.0                           ║"
    echo "║  🔧 Настройка окружения и зависимостей                      ║"
    echo "║  ⚙️ Сбор конфигурации                                       ║"
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
    
    # Telegram Chat ID (исправлено)
    while [[ -z "$TELEGRAM_CHAT_ID" ]]; do
        read -p "Введите Telegram Chat ID (кому отправлять сообщения): " TELEGRAM_CHAT_ID
        if [[ -z "$TELEGRAM_CHAT_ID" ]]; then
            log_warning "Telegram Chat ID обязателен для отправки уведомлений!"
        fi
    done
    
    echo
    echo -e "${CYAN}📊 Google Sheets настройки:${NC}"
    read -p "Введите URL Google Sheets таблицы: " GOOGLE_SHEETS_URL
    
    if [[ -n "$GOOGLE_SHEETS_URL" ]]; then
        log_info "Файл credentials.json нужно будет создать после этого этапа"
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
    echo "│ Telegram Chat ID: $TELEGRAM_CHAT_ID"
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
    
    # Установка необходимых пакетов (минимальный набор)
    log_info "Установка системных пакетов..."
    apt install -y \
        software-properties-common \
        build-essential \
        curl \
        wget \
        git \
        systemd \
        python3-pip \
        python3-venv \
        python3-dev \
        sqlite3 \
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

# Создание пользователя для сервиса (пропущено - работаем под root)
create_service_user() {
    log_step "Использование root пользователя для сервиса"
    log_info "Сервис будет работать под пользователем root"
    log_success "Настройка пользователя завершена"
}

# Настройка директории проекта
setup_project_directory() {
    log_step "Настройка директории проекта"
    
    # Создание директории
    log_info "Создание директории $PROJECT_DIR..."
    mkdir -p "$PROJECT_DIR"
    
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
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID

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

# Настройка прав доступа
setup_permissions() {
    log_step "Настройка прав доступа"
    
    # Создание необходимых директорий
    log_info "Создание необходимых директорий..."
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/found_slots"
    
    # Настройка прав на файлы (упрощенная для root)
    chmod 755 "$PROJECT_DIR"
    chmod 644 "$PROJECT_DIR"/.env 2>/dev/null || true
    chmod 755 "$PROJECT_DIR"/*.py 2>/dev/null || true
    chmod 755 "$PROJECT_DIR/logs"
    chmod 755 "$PROJECT_DIR/found_slots"
    
    log_success "Права доступа настроены"
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
    
    log_success "Базовое тестирование завершено"
}

# Показ инструкций для второго этапа
show_next_steps() {
    log_step "Инструкции для завершения установки"
    
    echo
    echo -e "${CYAN}🎯 ПЕРВЫЙ ЭТАП ЗАВЕРШЕН УСПЕШНО!${NC}"
    echo -e "${YELLOW}📋 СЛЕДУЮЩИЕ ШАГИ:${NC}"
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                                                             │"
    echo "│  1. Создайте файл credentials.json в директории проекта:    │"
    echo "│     $PROJECT_DIR/credentials.json                           │"
    echo "│                                                             │"
    echo "│  2. Скопируйте JSON-ключ вашего Google Service Account      │"
    echo "│     в файл credentials.json                                 │"
    echo "│                                                             │"
    echo "│  3. Убедитесь, что Service Account имеет доступ к Google    │"
    echo "│     Sheets таблице                                          │"
    echo "│                                                             │"
    echo "│  4. После создания credentials.json запустите вторую часть: │"
    echo "│     bash deploy_wb_bot_second.sh                            │"
    echo "│                                                             │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo
    echo -e "${GREEN}📁 Файлы проекта находятся в: $PROJECT_DIR${NC}"
    echo -e "${GREEN}📝 Конфигурация сохранена в: $PROJECT_DIR/.env${NC}"
    echo
    echo -e "${YELLOW}⚠️  ВАЖНО: Не забудьте создать credentials.json перед вторым этапом!${NC}"
    echo
}

# Функция очистки при ошибке
cleanup_on_error() {
    log_error "Произошла ошибка во время установки"
    log_info "Частичная очистка..."
    
    # Удаляем только то, что создали
    rm -rf "$PROJECT_DIR" 2>/dev/null || true
    
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
    log_info "Начинаем первый этап установки WB Slots Monitor..."
    echo
    
    setup_system
    create_service_user
    setup_project_directory
    setup_python_environment
    create_env_file
    setup_permissions
    test_installation
    
    # Завершение
    echo
    show_next_steps
}

# Запуск основной функции
main "$@"