#!/bin/bash
#
# UX Audit Admin - macOS Setup Script
# This script automates the installation for team members
#

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if running on macOS
check_macos() {
    if [[ "$OSTYPE" != "darwin"* ]]; then
        print_error "This script is designed for macOS only."
        exit 1
    fi
    print_success "Running on macOS"
}

# Auto-install Homebrew
install_homebrew() {
    if command -v brew &> /dev/null; then
        print_success "Homebrew already installed"
        return
    fi
    
    print_header "Installing Homebrew"
    print_info "This is a package manager for macOS (one-time setup)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for Apple Silicon Macs
    if [[ $(uname -m) == "arm64" ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    
    print_success "Homebrew installed"
}

# Auto-install Git
install_git() {
    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version)
        print_success "Found $GIT_VERSION"
        return
    fi
    
    print_header "Installing Git"
    brew install git
    print_success "Git installed"
}

# Auto-install Python 3.9+
install_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
        if [ "$PYTHON_MINOR" -ge 9 ]; then
            PYTHON_VERSION=$(python3 --version)
            print_success "Found $PYTHON_VERSION"
            return
        else
            print_warning "Python 3.$PYTHON_MINOR found, but 3.9+ required"
        fi
    fi
    
    print_header "Installing Python 3"
    brew install python@3.11
    
    # Link python3 command
    brew link python@3.11 --force 2>/dev/null || true
    
    # Add to PATH if needed
    if [[ $(uname -m) == "arm64" ]]; then
        export PATH="/opt/homebrew/opt/python@3.11/libexec/bin:$PATH"
        echo 'export PATH="/opt/homebrew/opt/python@3.11/libexec/bin:$PATH"' >> ~/.zprofile
    else
        export PATH="/usr/local/opt/python@3.11/libexec/bin:$PATH"
        echo 'export PATH="/usr/local/opt/python@3.11/libexec/bin:$PATH"' >> ~/.zprofile
    fi
    
    print_success "Python $(python3 --version) installed"
}

# Check and auto-install all prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    print_info "Installing anything that's missing..."
    
    # Install Homebrew first (needed for other installs)
    install_homebrew
    
    # Install Git
    install_git
    
    # Install Python
    install_python
    
    print_success "All prerequisites ready!"
}

# Clone repository
clone_repo() {
    print_header "Cloning Repository"
    
    REPO_URL="https://github.com/mafruh10-cmd/UX-Audit-Admin-application-.git"
    INSTALL_DIR="$HOME/UX-Audit-Admin-application-"
    
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Directory already exists at $INSTALL_DIR"
        read -p "Do you want to update it? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd "$INSTALL_DIR"
            git pull origin local
            print_success "Updated existing repository"
        else
            print_info "Using existing directory"
            cd "$INSTALL_DIR"
        fi
    else
        print_info "Cloning from GitHub..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        print_success "Repository cloned to $INSTALL_DIR"
    fi
}

# Switch to local branch
switch_branch() {
    print_header "Switching to Local Branch"
    
    git checkout local
    print_success "Switched to 'local' branch"
}

# Create virtual environment
setup_venv() {
    print_header "Setting Up Virtual Environment"
    
    if [ -d ".venv" ]; then
        print_warning "Virtual environment already exists"
    else
        print_info "Creating virtual environment..."
        python3 -m venv .venv
        print_success "Virtual environment created"
    fi
    
    print_info "Activating virtual environment..."
    source .venv/bin/activate
    print_success "Virtual environment activated"
}

# Install dependencies
install_deps() {
    print_header "Installing Dependencies"
    
    print_info "Upgrading pip..."
    pip install --upgrade pip
    
    print_info "Installing requirements..."
    pip install -r requirements.txt
    
    print_success "Dependencies installed"
}

# Setup environment file
setup_env() {
    print_header "Setting Up Environment"
    
    if [ -f ".env" ]; then
        print_warning ".env file already exists"
        read -p "Do you want to update the API key? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env file"
            return
        fi
    fi
    
    print_info "Creating .env file..."
    
    # Prompt for API key
    echo ""
    echo -e "${YELLOW}Please enter your Anthropic API Key:${NC}"
    echo "(Get it from: https://console.anthropic.com/)"
    echo ""
    read -s ANTHROPIC_KEY
    echo ""
    
    if [ -z "$ANTHROPIC_KEY" ]; then
        print_warning "No API key provided. You'll need to edit .env manually later."
        ANTHROPIC_KEY="your_key_here"
    fi
    
    # Create .env file
    cat > .env << EOF
# UX Audit Admin - Local Environment Configuration
# This is the LOCAL version - data stored on your machine

# Anthropic API Key for AI analysis
# Get from: https://console.anthropic.com/
ANTHROPIC_API_KEY=$ANTHROPIC_KEY

# Local data directory (auto-created)
# Data is stored in: local_data/
EOF
    
    print_success ".env file created"
}

# Create local_data directory
setup_local_data() {
    print_header "Setting Up Local Data Directory"
    
    mkdir -p local_data/storage
    
    # Create .gitkeep if not exists
    if [ ! -f "local_data/.gitkeep" ]; then
        echo "# This file ensures the directory structure is preserved" > local_data/.gitkeep
        echo "# Your audit data will be stored here (not committed to git)" >> local_data/.gitkeep
    fi
    
    print_success "Local data directory ready"
    print_info "Your audit data will be stored in: $(pwd)/local_data/"
}

# Make run.sh executable
fix_permissions() {
    print_header "Setting Permissions"
    
    chmod +x run.sh
    chmod +x setup-mac.sh
    
    print_success "Permissions set"
}

# Create desktop icon (macOS app)
create_desktop_icon() {
    print_header "Creating Desktop Icon"
    
    INSTALL_DIR=$(pwd)
    APP_NAME="UX Audit Admin"
    APP_PATH="$HOME/Desktop/$APP_NAME.app"
    
    # Remove old version if exists
    if [ -d "$APP_PATH" ]; then
        rm -rf "$APP_PATH"
    fi
    
    # Create the AppleScript app
    osacompile -o "$APP_PATH" << EOF
#!/usr/bin/osascript
tell application "Terminal"
    do script "cd \"$INSTALL_DIR\" && ./run.sh"
    set frontmost to true
end tell
tell application "Safari"
    activate
    delay 3
    set URL of front document to "http://localhost:5001"
end tell
EOF
    
    # Set icon (use generic app icon)
    # Copy the app's Info.plist to set a custom name
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string '$APP_NAME'" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
    
    print_success "Desktop icon created: $APP_PATH"
    print_info "Double-click the icon to launch UX Audit Admin"
}

# Test the installation
test_installation() {
    print_header "Testing Installation"
    
    # Check if we can import key modules
    python3 -c "from flask import Flask; print('Flask OK')" || {
        print_error "Flask not installed properly"
        exit 1
    }
    
    python3 -c "from PIL import Image; print('Pillow OK')" || {
        print_warning "Pillow not installed (optional, for image annotations)"
    }
    
    python3 -c "from openai import OpenAI; print('OpenAI OK')" || {
        print_error "OpenAI package not installed properly"
        exit 1
    }
    
    print_success "Installation test passed"
}

# Print final instructions
print_final_instructions() {
    INSTALL_DIR=$(pwd)
    
    print_header "Setup Complete!"
    
    echo ""
    echo -e "${GREEN}The UX Audit Admin (Local Version) is ready to use!${NC}"
    echo ""
    echo ""
    echo -e "${GREEN}✅ UX Audit Admin is installed and ready!${NC}"
    echo ""
    echo -e "${YELLOW}🚀 TO START THE APP:${NC}"
    echo "   Double-click the 'UX Audit Admin' icon on your Desktop"
    echo ""
    echo -e "${BLUE}📍 What just got installed:${NC}"
    echo "   • App location: $INSTALL_DIR"
    echo "   • Desktop icon: ~/Desktop/UX Audit Admin.app"
    echo "   • Your data: $INSTALL_DIR/local_data/"
    echo ""
    echo -e "${BLUE}🌐 The app will open at:${NC}"
    echo "   http://localhost:5001"
    echo ""
    echo -e "${BLUE}⏹️  To stop the app:${NC}"
    echo "   Press Ctrl+C in the terminal window"
    echo ""
    echo -e "${YELLOW}⚠️  Important:${NC}"
    echo "   Your audit data is stored ONLY on this Mac."
    echo "   Export HTML reports to share with your team."
    echo ""
}

# Main execution
main() {
    print_header "UX Audit Admin - macOS Setup"
    echo ""
    echo "This will install UX Audit Admin on your Mac."
    echo ""
    echo "✓ Auto-installs: Homebrew, Git, Python (if missing)"
    echo "✓ Creates Desktop icon for one-click launch"
    echo "✓ Stores all data locally on your machine"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."
    
    check_macos
    check_prerequisites
    clone_repo
    switch_branch
    setup_venv
    install_deps
    setup_env
    setup_local_data
    fix_permissions
    create_desktop_icon
    test_installation
    print_final_instructions
}

# Run main function
main
