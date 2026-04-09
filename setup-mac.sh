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

# Check for required tools
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check for Python 3
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        print_success "Found $PYTHON_VERSION"
    else
        print_error "Python 3 not found. Please install Python 3.9 or higher."
        echo "Visit: https://www.python.org/downloads/mac-osx/"
        exit 1
    fi
    
    # Check for Git
    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version)
        print_success "Found $GIT_VERSION"
    else
        print_error "Git not found. Please install Git."
        echo "Run: brew install git"
        exit 1
    fi
    
    # Check Python version (need 3.9+)
    PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    if [ "$PYTHON_MINOR" -lt 9 ]; then
        print_warning "Python 3.9+ recommended. Current version may work but is not tested."
    fi
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
    echo -e "${BLUE}To start the application:${NC}"
    echo "  cd $INSTALL_DIR"
    echo "  ./run.sh"
    echo ""
    echo -e "${BLUE}Then open in your browser:${NC}"
    echo "  http://localhost:5001"
    echo ""
    echo -e "${BLUE}To stop the application:${NC}"
    echo "  Press Ctrl+C in the terminal"
    echo ""
    echo -e "${BLUE}To update to latest version:${NC}"
    echo "  cd $INSTALL_DIR"
    echo "  git pull origin local"
    echo ""
    echo -e "${YELLOW}Important Notes:${NC}"
    echo "  • All audit data is stored locally in: $INSTALL_DIR/local_data/"
    echo "  • Data is NOT synced to GitHub or other team members"
    echo "  • Each team member has their own separate data"
    echo "  • Export HTML reports to share audits with team"
    echo ""
    echo -e "${BLUE}Need help?${NC}"
    echo "  Read README_LOCAL.md for detailed instructions"
    echo ""
}

# Main execution
main() {
    print_header "UX Audit Admin - macOS Setup"
    echo ""
    echo "This script will set up the local version of UX Audit Admin."
    echo "All data will be stored on your machine (not in the cloud)."
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
    test_installation
    print_final_instructions
}

# Run main function
main
