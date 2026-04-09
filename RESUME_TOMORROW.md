# UX Audit Admin - Resume Instructions

**Created:** 2026-04-09  
**Status:** Installation in progress on Sohag's Mac-mini

---

## What We Did Today

1. ✅ **Local branch** - Fully removed all Supabase dependencies
2. ✅ **Auto-installer** - Created setup that installs Homebrew, Git, Python automatically
3. ✅ **Desktop icon** - Creates clickable icon to launch the app
4. 🔄 **Installation started** on Sohag's Mac-mini but had clipboard/paste issues

---

## Current Situation (Sohag's Mac)

- Homebrew: ✅ Installed
- Git: Should be installed via Homebrew
- Python: Should be installed via Homebrew
- UX Audit Admin: ⏳ Not yet installed (need to run installer)

---

## To Resume Tomorrow

### Step 1: Open Terminal
Press `Cmd + Space`, type `terminal`, press Enter

### Step 2: Run These Commands (ONE AT A TIME)

```bash
cd ~
```

```bash
curl -o install.sh "https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/install.sh"
```

```bash
bash install.sh
```

### Step 3: Follow Prompts
- Enter Mac password if asked
- Enter Anthropic API key when prompted
- Wait for installation to complete

### Step 4: Launch the App
**Double-click** the "UX Audit Admin" icon on Desktop

OR run in Terminal:
```bash
cd ~/UX-Audit-Admin-application- && ./run.sh
```

Then open: **http://localhost:5001**

---

## If Desktop Icon Doesn't Work

Delete broken icon and create new one:

```bash
rm -rf "$HOME/Desktop/UX Audit Admin.app"
```

Create simpler .command file:
```bash
cat > "$HOME/Desktop/UX-Audit-Admin.command" << 'EOF'
#!/bin/bash
cd "$HOME/UX-Audit-Admin-application-" && ./run.sh
EOF
chmod +x "$HOME/Desktop/UX-Audit-Admin.command"
```

Then double-click **UX-Audit-Admin.command** on Desktop.

---

## Team Member Install (Share This)

One-line installer for other Macs:

```bash
curl -fsSL https://raw.githubusercontent.com/mafruh10-cmd/UX-Audit-Admin-application-/local/install.sh | bash
```

---

## Quick Reference

| What | Command |
|------|---------|
| Start app | `./run.sh` or double-click Desktop icon |
| Stop app | Press `Ctrl+C` in Terminal |
| Update app | `git pull origin local` |
| Data location | `~/UX-Audit-Admin-application-/local_data/` |

---

## Need Help?

- Check `README_LOCAL.md` in the app folder
- Or re-run: `bash install.sh`
