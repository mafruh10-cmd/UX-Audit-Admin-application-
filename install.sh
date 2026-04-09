#!/bin/bash
#
# One-liner install script for UX Audit Admin (Local)
# 
# Team members can run this with:
# curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/install.sh | bash
#

set -e

echo "🚀 UX Audit Admin - Local Version Installer"
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
