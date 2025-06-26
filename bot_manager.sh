#!/bin/bash
set -e

# Reddit Telegram Forwarder Bot - Setup and Management Script
# Usage: ./bot_manager.sh [setup|start|stop|restart|update|status|logs]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_NAME="reddit-telegram-forwarder"
SERVICE_NAME="reddit-telegram-bot"
VENV_DIR=".venv"
PYTHON_SCRIPT="main.py"
LOG_FILE="logs/bot.log"
PID_FILE="bot.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        warning "Running as root. Consider running as a regular user for security."
    fi
}

# Create virtual environment
setup_venv() {
    log "Setting up Python virtual environment..."
    
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        success "Virtual environment created"
    else
        log "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install requirements
    log "Installing Python dependencies..."
    pip install -r requirements.txt
    
    success "Dependencies installed"
}

# Setup directories
setup_directories() {
    log "Creating necessary directories..."
    
    mkdir -p logs
    mkdir -p data
    mkdir -p temp
    
    success "Directories created"
}

# Setup environment file
setup_env() {
    if [ ! -f ".env" ]; then
        log "Creating .env file from template..."
        cp .env.example .env
        
        warning "Please edit .env file with your actual tokens and configuration:"
        echo "  - TELEGRAM_BOT_TOKEN: Get from @BotFather on Telegram"
        echo "  - REDDIT_CLIENT_ID: Get from Reddit App preferences"
        echo "  - REDDIT_CLIENT_SECRET: Get from Reddit App preferences"
        echo ""
        echo "Edit the file with: nano .env"
        
        return 1
    else
        log ".env file already exists"
        return 0
    fi
}

# Setup systemd service (Linux only)
setup_service() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        log "Setting up systemd service..."
        
        cat > "/tmp/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Reddit Telegram Forwarder Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=$SCRIPT_DIR/$VENV_DIR/bin
ExecStart=$SCRIPT_DIR/$VENV_DIR/bin/python $SCRIPT_DIR/$PYTHON_SCRIPT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        sudo mv "/tmp/${SERVICE_NAME}.service" "/etc/systemd/system/"
        sudo systemctl daemon-reload
        sudo systemctl enable "$SERVICE_NAME"
        
        success "Systemd service installed"
    else
        log "Systemd service setup skipped (not on Linux)"
    fi
}

# Full setup
setup() {
    log "Starting setup for $PROJECT_NAME..."
    check_root
    
    setup_directories
    setup_venv
    
    if ! setup_env; then
        error "Setup incomplete. Please configure .env file and run setup again."
        exit 1
    fi
    
    setup_service
    
    success "Setup completed! You can now:"
    echo "  1. Edit admins.txt to add admin Telegram IDs"
    echo "  2. Start the bot with: ./bot_manager.sh start"
    echo "  3. Check logs with: ./bot_manager.sh logs"
}

# Start the bot
start() {
    if is_running; then
        warning "Bot is already running (PID: $(cat $PID_FILE))"
        return 0
    fi
    
    log "Starting $PROJECT_NAME..."
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        error ".env file not found. Run ./bot_manager.sh setup first."
        exit 1
    fi
    
    # Check if virtual environment exists
    if [ ! -d "$VENV_DIR" ]; then
        error "Virtual environment not found. Run ./bot_manager.sh setup first."
        exit 1
    fi
    
    # Activate virtual environment and start bot
    source "$VENV_DIR/bin/activate"
    
    if [[ "$OSTYPE" == "linux-gnu"* ]] && systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
        # Use systemd on Linux if service is installed
        sudo systemctl start "$SERVICE_NAME"
        success "Bot started via systemd"
    else
        # Start manually
        nohup python "$PYTHON_SCRIPT" > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        success "Bot started (PID: $!)"
    fi
}

# Stop the bot
stop() {
    log "Stopping $PROJECT_NAME..."
    
    if [[ "$OSTYPE" == "linux-gnu"* ]] && systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
        # Use systemd on Linux if service is installed
        sudo systemctl stop "$SERVICE_NAME"
        success "Bot stopped via systemd"
    else
        # Stop manually
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                kill "$PID"
                rm -f "$PID_FILE"
                success "Bot stopped (PID: $PID)"
            else
                warning "Bot was not running"
                rm -f "$PID_FILE"
            fi
        else
            warning "PID file not found. Bot may not be running."
        fi
    fi
}

# Restart the bot
restart() {
    log "Restarting $PROJECT_NAME..."
    stop
    sleep 2
    start
}

# Update the bot
update() {
    log "Updating $PROJECT_NAME..."
    
    # Check if we're in a git repository
    if [ -d ".git" ]; then
        log "Pulling latest changes from git..."
        git pull
        
        # Stop bot if running
        if is_running; then
            stop
            RESTART_AFTER_UPDATE=true
        fi
        
        # Update dependencies
        source "$VENV_DIR/bin/activate"
        pip install -r requirements.txt --upgrade
        
        # Restart if it was running
        if [ "$RESTART_AFTER_UPDATE" = true ]; then
            start
        fi
        
        success "Update completed"
    else
        warning "Not a git repository. Manual update required."
    fi
}

# Check if bot is running
is_running() {
    if [[ "$OSTYPE" == "linux-gnu"* ]] && systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
        systemctl is-active --quiet "$SERVICE_NAME"
    else
        [ -f "$PID_FILE" ] && ps -p "$(cat $PID_FILE)" > /dev/null 2>&1
    fi
}

# Show bot status
status() {
    log "Checking $PROJECT_NAME status..."
    
    if is_running; then
        if [[ "$OSTYPE" == "linux-gnu"* ]] && systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
            success "Bot is running (systemd service)"
            systemctl status "$SERVICE_NAME" --no-pager -l
        else
            PID=$(cat "$PID_FILE" 2>/dev/null || echo "unknown")
            success "Bot is running (PID: $PID)"
        fi
    else
        warning "Bot is not running"
    fi
    
    # Show recent logs
    echo ""
    log "Recent logs:"
    if [ -f "$LOG_FILE" ]; then
        tail -n 10 "$LOG_FILE"
    else
        warning "Log file not found"
    fi
}

# Show logs
logs() {
    if [ -f "$LOG_FILE" ]; then
        log "Showing logs (press Ctrl+C to exit)..."
        tail -f "$LOG_FILE"
    else
        error "Log file not found: $LOG_FILE"
    fi
}

# Show help
help() {
    echo "Reddit Telegram Forwarder Bot Manager"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup     - Initial setup (install dependencies, create config)"
    echo "  start     - Start the bot"
    echo "  stop      - Stop the bot"
    echo "  restart   - Restart the bot"
    echo "  update    - Update bot from git and restart if needed"
    echo "  status    - Show bot status and recent logs"
    echo "  logs      - Show live logs"
    echo "  help      - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 setup"
    echo "  $0 start"
    echo "  $0 logs"
}

# Main script logic
case "${1:-help}" in
    setup)
        setup
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    update)
        update
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    help|--help|-h)
        help
        ;;
    *)
        error "Unknown command: $1"
        echo ""
        help
        exit 1
        ;;
esac
