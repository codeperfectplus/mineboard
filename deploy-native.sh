#!/bin/bash

#############################################
# Mineboard Native Deployment Script
# Standalone installer - clones repo and deploys
#############################################

set -e

# Configuration
REPO_URL="https://github.com/codeperfectplus/mineboard.git"
TEMP_DIR="/tmp/mineboard-installer-$$"
INSTALL_DIR="/opt/mineboard"
SERVICE_NAME="mineboard"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
APP_USER="mineboard"
APP_PORT="${PORT:-5090}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
show_usage() {
    echo ""
    echo "Mineboard Native Deployment Script"
    echo "Usage: sudo bash deploy-native.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install     Install Mineboard"
    echo "  --uninstall   Uninstall Mineboard"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo bash deploy-native.sh --install"
    echo "  sudo bash deploy-native.sh --uninstall"
    echo ""
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if Git is installed
check_git() {
    if ! command -v git &> /dev/null; then
        print_info "Installing Git..."
        apt-get update -qq && apt-get install -y git -qq || {
            print_error "Failed to install Git. Please install it manually."
            exit 1
        }
    fi
}

# Check if Python 3.8+ is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    # Check for pip silently, suppress all output and errors
    if ! python3 -m pip --version &> /dev/null; then
        python3 -m ensurepip --default-pip >/dev/null 2>&1 || true
    fi
}

# Clone repository
clone_repo() {
    print_info "⬇  Downloading Mineboard..."
    
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR" 2>/dev/null
    fi
    
    git clone -q "$REPO_URL" "$TEMP_DIR" 2>/dev/null || {
        print_error "Failed to download"
        exit 1
    }
}

# Create application user
create_user() {
    if ! id "$APP_USER" &>/dev/null; then
        useradd --system --no-create-home --shell /bin/false $APP_USER 2>/dev/null
    fi
}

# Create installation directory
create_install_dir() {
    if [ -d "$INSTALL_DIR" ]; then
        systemctl stop $SERVICE_NAME 2>/dev/null || true
        rm -rf "$INSTALL_DIR" 2>/dev/null
    fi
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/data"
}

# Copy application files
copy_files() {
    print_info "📦 Installing application files..."
    
    cd "$TEMP_DIR"
    
    # Copy all files except .git, __pycache__, venv, etc.
    rsync -a --quiet \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='venv' \
        --exclude='data' \
        --exclude='minecraft-data' \
        --exclude='docker-compose.yml' \
        --exclude='Dockerfile' \
        "$TEMP_DIR/" "$INSTALL_DIR/" 2>/dev/null || {
            # Fallback to cp if rsync is not available
            cp -r "$TEMP_DIR/"* "$INSTALL_DIR/" 2>/dev/null || true
            find "$TEMP_DIR" -name ".*" ! -name "." ! -name ".." -exec cp -r {} "$INSTALL_DIR/" \; 2>/dev/null || true
        }
}

# Create virtual environment and install dependencies
setup_python_env() {
    print_info "📚 Installing Python dependencies (this may take a minute)..."
    
    cd "$INSTALL_DIR"
    
    # Try to create venv, if it fails, continue anyway
    if python3 -m venv venv 2>/dev/null; then
        : # Success, do nothing
    else
        python3 -m venv --without-pip venv 2>/dev/null || {
            mkdir -p venv/bin
            ln -sf $(which python3) venv/bin/python
            ln -sf $(which pip3) venv/bin/pip 2>/dev/null || true
        }
    fi
    
    # Install dependencies quietly
    if [ -f "$INSTALL_DIR/venv/bin/pip" ]; then
        "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
        "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
        "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    else
        python3 -m pip install -q -r "$INSTALL_DIR/requirements.txt" --user 2>/dev/null || \
        python3 -m pip install -r "$INSTALL_DIR/requirements.txt" --user
    fi
}

# Create .env file if it doesn't exist
create_env_file() {
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        cat > "$INSTALL_DIR/.env" << EOF
# Mineboard Configuration
SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | base64)

# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
PORT=$APP_PORT

# Database Path
DB_PATH=/opt/mineboard/data/data.db

# Optional: Set default admin credentials
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=changeme

# Optional: Set URL prefix if running behind a reverse proxy
# URL_PREFIX=/mineboard
EOF
        chmod 600 "$INSTALL_DIR/.env"
    fi
}

# Update app.py to use environment port
update_app_py() {
    # Check if app.py needs updating
    if ! grep -q "if __name__ == '__main__':" "$INSTALL_DIR/app.py"; then
        cat >> "$INSTALL_DIR/app.py" << 'EOF'

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5090))
    app.run(host='0.0.0.0', port=port, debug=False)
EOF
    fi
}

# Set proper permissions
set_permissions() {
    chown -R $APP_USER:$APP_USER "$INSTALL_DIR" 2>/dev/null
    chmod -R 755 "$INSTALL_DIR" 2>/dev/null
    chmod 600 "$INSTALL_DIR/.env" 2>/dev/null
    chmod -R 775 "$INSTALL_DIR/data" 2>/dev/null
}

# Install systemd service
install_service() {
    print_info "⚙️  Configuring system service..."
    
    # Copy service file
    cp "$INSTALL_DIR/mineboard-native.service" "$SERVICE_FILE"
    
    # Reload systemd
    systemctl daemon-reload
}

# Enable and start service
start_service() {
    print_info "🚀 Starting Mineboard..."
    
    # Enable service to start on boot
    systemctl enable $SERVICE_NAME 2>/dev/null
    
    # Start the service
    systemctl start $SERVICE_NAME
    
    # Wait a moment for the service to start
    sleep 2
    
    # Check status
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_success "✓ Mineboard is running!"
    else
        print_error "Failed to start Mineboard"
        echo ""
        echo "Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

# Cleanup temp directory
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR" 2>/dev/null
    fi
}

# Display final information
show_install_info() {
    echo ""
    echo -e "\033[1;32m==============================================\033[0m"
    echo -e "\033[1;32m   🎉 Mineboard Installed Successfully! 🎉   \033[0m"
    echo -e "\033[1;32m==============================================\033[0m"
    echo ""
    echo -e "\033[1;36mWhere to find things:\033[0m"
    echo -e "   \033[1;37m📁 Install Dir:\033[0m     $INSTALL_DIR"
    echo -e "   \033[1;37m🛡️  Service Name:\033[0m   $SERVICE_NAME"
    echo -e "   \033[1;37m👤 Runs as:\033[0m         $APP_USER"
    echo ""
    echo -e "\033[1;36mOpen your browser:\033[0m"
    echo -e "   \033[1;32m🌐 http://localhost:$APP_PORT\033[0m"
    echo ""
    echo -e "\033[1;33m==============================================\033[0m"
    echo -e "\033[1;33m           👤 Login Information               \033[0m"
    echo -e "\033[1;33m==============================================\033[0m"
    echo ""
    echo -e "\033[1;37mOn your first visit, you'll create an admin account.\033[0m"
    echo ""
    echo -e "\033[1;37mIf you set default credentials in .env:\033[0m"
    echo -e "   \033[1;36mUsername:\033[0m admin"
    echo -e "   \033[1;36mPassword:\033[0m admin"
    echo ""
    echo -e "\033[1;31m⚠️  IMPORTANT: Change the default password after first login!\033[0m"
    echo ""
    echo -e "\033[1;34m==============================================\033[0m"
    echo -e "\033[1;34m         🛠️  Service Management              \033[0m"
    echo -e "\033[1;34m==============================================\033[0m"
    echo ""
    echo -e "   \033[1;37mStart:\033[0m    sudo systemctl start $SERVICE_NAME"
    echo -e "   \033[1;37mStop:\033[0m     sudo systemctl stop $SERVICE_NAME"
    echo -e "   \033[1;37mRestart:\033[0m  sudo systemctl restart $SERVICE_NAME"
    echo -e "   \033[1;37mStatus:\033[0m   sudo systemctl status $SERVICE_NAME"
    echo -e "   \033[1;37mLogs:\033[0m     sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo -e "\033[1;36m💡 Next: Configure your RCON settings in the Settings page to connect to your Minecraft server!\033[0m"
    echo ""
}

# Uninstall function
uninstall() {
    echo ""
    echo "======================================"
    echo "  Uninstalling Mineboard"
    echo "======================================"
    echo ""
    
    print_info "Removing Mineboard..."
    
    systemctl stop $SERVICE_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true
    rm -f $SERVICE_FILE 2>/dev/null
    rm -rf $INSTALL_DIR 2>/dev/null
    userdel $APP_USER 2>/dev/null || true
    systemctl daemon-reload 2>/dev/null
    
    echo ""
    print_success "Mineboard has been uninstalled!"
    echo ""
}

# Install function
install() {
    echo ""
    echo "====================================="
    echo "     Mineboard Installation"
    echo "====================================="
    echo ""
    
    check_root
    check_git
    check_python
    clone_repo
    create_user
    create_install_dir
    copy_files
    setup_python_env
    create_env_file
    update_app_py
    set_permissions
    install_service
    start_service
    cleanup
    show_install_info
}

# Main script logic
main() {
    case "${1:-}" in
        --install)
            install
            ;;
        --uninstall)
            check_root
            uninstall
            ;;
        --help)
            show_usage
            ;;
        *)
            print_error "Invalid option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
