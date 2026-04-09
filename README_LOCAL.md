# UX Audit Admin — Local Version

This is the **local version** of the UX Audit Admin tool that stores all data on your machine instead of Supabase.

## Differences from Cloud Version

| Feature | Local Version | Cloud Version |
|---------|--------------|---------------|
| **Data Storage** | Local files (`local_data/`) | Supabase Database |
| **Authentication** | None (open access) | Supabase Auth |
| **File Storage** | Local disk | Supabase Storage |
| **AI APIs** | Online (Claude, Gemini) | Online (Claude, Gemini) |
| **Team Sharing** | Export HTML reports | Share via web links |

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/mafruh10-cmd/UX-Audit-Admin-application-.git
cd UX-Audit-Admin-application-
```

### 2. Switch to Local Branch

```bash
git checkout local
```

### 3. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Set Up Environment

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```env
ANTHROPIC_API_KEY=your_key_here
```

### 5. Run the App

```bash
./run.sh
```

The app will start on `http://localhost:5001`

## Data Location

All audit data is stored in the `local_data/` folder:

```
local_data/
├── audits.json          # Index of all audits
└── storage/
    └── {audit-id}/
        ├── screenshot.jpg
        ├── annotated.jpg
        ├── audit_data.json
        ├── report.html
        └── claude_prompt.txt
```

**Important**: The `local_data/` folder is in `.gitignore` and will NOT be committed to GitHub. Each team member has their own local data.

## Team Workflow

### Sharing Audits

Since data is local, share audits by:
1. Export HTML report from the app
2. Email/send the HTML file to team member
3. Team member can view in any browser

### Getting Updates

To get the latest app updates:
```bash
git pull origin local
```

This updates the code but keeps your local data intact.

### Switching Between Local and Cloud

```bash
# For local version (data on your machine)
git checkout local

# For cloud version (data on Supabase)
git checkout main
```

## Troubleshooting

### App won't start
Check that `.env` file exists with your API keys.

### Data disappeared
Make sure you're on the `local` branch and the `local_data/` folder exists.

### Need to reset data
Delete the `local_data/` folder and restart the app.

## Branch Structure

- **`main`**: Cloud version with Supabase
- **`local`**: Local version with file storage (this branch)

## Support

For issues specific to the local version, check:
1. Terminal output for error messages
2. That `local_data/` folder has correct permissions
3. That you have sufficient disk space
