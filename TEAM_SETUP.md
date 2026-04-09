# Team Setup Guide - UX Audit Admin (Local)

## 🚀 Quick Start (Easiest Method)

### Option 1: Automated Setup Script

Copy and paste this entire block into Terminal:

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/setup-mac.sh -o /tmp/setup-mac.sh && bash /tmp/setup-mac.sh
```

The script will:
1. ✅ Check Python and Git are installed
2. ✅ Clone the repository
3. ✅ Set up the local branch
4. ✅ Install all dependencies
5. ✅ Configure API keys
6. ✅ Test the installation

**Time: ~5 minutes**

---

## 📋 Manual Setup (If Script Doesn't Work)

### Step 1: Clone Repository
```bash
git clone https://github.com/mafruh10-cmd/UX-Audit-Admin-application-.git
cd UX-Audit-Admin-application-
```

### Step 2: Switch to Local Branch
```bash
git checkout local
```

### Step 3: Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure API Key
```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:
```
ANTHROPIC_API_KEY=your_key_here
```

### Step 5: Run
```bash
./run.sh
```

Open: http://localhost:5001

---

## 🔄 Daily Usage

### Start the App
```bash
cd UX-Audit-Admin-application-
./run.sh
```

### Get Updates
```bash
cd UX-Audit-Admin-application-
git pull origin local
./run.sh
```

### Stop the App
Press `Ctrl+C` in the terminal window.

---

## 📦 What's Installed

| Component | Location | Description |
|-----------|----------|-------------|
| **Application** | `~/UX-Audit-Admin-application-/` | Main app files |
| **Virtual Env** | `.venv/` | Python dependencies |
| **Data** | `local_data/` | Your audit files (not synced) |
| **Reports** | `local_data/storage/{id}/` | Screenshots, HTML reports |

---

## 🔧 Troubleshooting

### "Command not found: python3"
Install Python: https://www.python.org/downloads/mac-osx/

### "Permission denied: ./run.sh"
```bash
chmod +x run.sh
```

### "Port already in use"
```bash
PORT=5002 ./run.sh
```

### "Module not found"
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 📊 Data Storage

**Important**: Each team member has their own local data.

```
local_data/
├── audits.json          # Your audit list
└── storage/
    └── {audit-id}/
        ├── screenshot.jpg
        ├── annotated.jpg
        ├── report.html
        └── claude_prompt.txt
```

- ✅ Data stays on your Mac
- ✅ Not synced to GitHub
- ✅ Not shared with team
- ✅ Export HTML reports to share

---

## 🆘 Need Help?

1. Check terminal output for error messages
2. Read: `README_LOCAL.md`
3. Ask team lead for API key if needed

---

## 📝 Quick Reference Card

```bash
# First time setup
curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/setup-mac.sh | bash

# Daily start
cd UX-Audit-Admin-application- && ./run.sh

# Get updates
git pull origin local

# Open browser
open http://localhost:5001
```
