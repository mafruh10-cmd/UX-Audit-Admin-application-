#!/bin/bash
#
# UX Audit Admin - One-Command Installer for macOS
#
# 💻 Copy and paste this ONE command in Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/install.sh | bash
#
# ✅ This will automatically install EVERYTHING needed:
#    • Homebrew (package manager) - if missing
#    • Git (version control) - if missing  
#    • Python 3.11 - if missing or outdated
#    • All Python dependencies (Flask, Pillow, OpenAI, etc.)
#    • The UX Audit Admin app
#    • A Desktop icon for one-click launch
#
# 📝 Notes:
#    • May ask for your Mac password (for Homebrew installation)
#    • Will prompt for Anthropic API key at the end
#    • All data stored locally (not in cloud)
#

set -e

echo "🚀 UX Audit Admin Installer"
echo ""
echo "This will install everything automatically."
echo "Sit back and relax... ☕️"
echo ""

# Download and run the full setup script
SETUP_URL="https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/setup-mac.sh"
TEMP_SCRIPT="/tmp/ux-audit-setup.sh"

echo "📥 Downloading installer..."
curl -fsSL "$SETUP_URL" -o "$TEMP_SCRIPT"
chmod +x "$TEMP_SCRIPT"

echo "🔧 Running setup (this may take a few minutes)..."
bash "$TEMP_SCRIPT"

# Cleanup
rm -f "$TEMP_SCRIPT"

echo ""
echo "✅ Done! Look for 'UX Audit Admin' on your Desktop."
