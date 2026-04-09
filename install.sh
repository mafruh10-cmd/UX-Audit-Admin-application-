#!/bin/bash
#
# One-liner install script for UX Audit Admin (Local)
# 
# Team members can run this with:
# curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/install.sh | bash
#
# This will:
#   - Install the application to ~/UX-Audit-Admin-application-
#   - Create a "UX Audit Admin" icon on the Desktop
#   - Set up local data storage (no cloud)
#

set -e

echo "🚀 UX Audit Admin - Local Version Installer"
echo ""
echo "This script will:"
echo "  • Install UX Audit Admin to ~/UX-Audit-Admin-application-"
echo "  • Create a Desktop icon you can click to run"
echo "  • Store all data locally on your Mac"
echo ""

# Download and run the full setup script
SETUP_URL="https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/setup-mac.sh"
TEMP_SCRIPT="/tmp/ux-audit-setup.sh"

echo "📥 Downloading setup script..."
curl -fsSL "$SETUP_URL" -o "$TEMP_SCRIPT"
chmod +x "$TEMP_SCRIPT"

echo "🔧 Running setup..."
bash "$TEMP_SCRIPT"

# Cleanup
rm -f "$TEMP_SCRIPT"

echo ""
echo "✅ Installation complete! Look for 'UX Audit Admin' on your Desktop."
