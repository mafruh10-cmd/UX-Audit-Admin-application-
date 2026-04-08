# UX Audit Admin Tool

A Flask-based admin tool for conducting UX audits with AI-powered analysis.

## Quick Start

### Prerequisites
- Python 3.9 or higher
- macOS (optimized for Mac, but works on Linux/Windows too)

### 1. Clone the Repository

```bash
git clone https://github.com/mafruh10-cmd/UX-Audit-Admin-application-.git
cd UX-Audit-Admin-application-
```

### 2. Set Up Environment Variables

Copy the example environment file and configure your keys:

```bash
cp .env.example .env
```

Edit `.env` and add your Supabase credentials:

```env
SUPABASE_SERVICE_KEY=your_service_role_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here  # Optional, for AI features
```

**Where to get these keys:**

1. **SUPABASE_SERVICE_KEY**: 
   - Go to your Supabase Dashboard → Project Settings → API
   - Copy the `service_role` key (NOT the anon key)
   - This key has full admin access to the database

2. **ANTHROPIC_API_KEY** (optional):
   - Get from: https://console.anthropic.com/
   - Required for AI-powered audit analysis

### 3. Run the Application

```bash
./run.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app will start on `http://localhost:5001` and automatically open in your browser.

## Configuration Status

Check if your configuration is correct by visiting:
```
http://localhost:5001/api/config
```

This will show:
- Whether Supabase is connected
- Which keys are configured
- Database connection status

## Troubleshooting

### "Supabase not configured" warnings
- Make sure you've created the `.env` file
- Ensure `SUPABASE_SERVICE_KEY` is set correctly
- Restart the application after editing `.env`

### Images not loading
- Check that your Supabase Storage bucket "ux-audits" exists
- Verify the service key has storage permissions
- Check browser console for specific errors

### AI analysis not working
- The `ANTHROPIC_API_KEY` is required for AI features
- Get a key from https://console.anthropic.com/
- Add it to your `.env` file

## Features

- 📤 Upload screenshots for UX analysis
- 🤖 AI-powered UX issue detection (via Claude)
- 📝 Generate detailed audit reports
- 🎨 Dribbble reference integration
- 🔄 Design comparison tools
- 📊 Score tracking and history

## Development

### Project Structure
```
.
├── app.py              # Main Flask application
├── run.sh              # Quick start script
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── templates/          # HTML templates
├── static/            # CSS, JS, images
└── training_data/     # AI training references
```

### Database Schema

The app uses Supabase with the following tables:
- `audits` - Stores audit metadata
- `audit_data` - Stores detailed audit data

Storage bucket:
- `ux-audits` - Stores uploaded images and generated files

## Shared Database Setup

This application uses a shared Supabase database. All users running this app will connect to the same database instance. Make sure you:

1. Share the `SUPABASE_SERVICE_KEY` securely with your team
2. Set up appropriate Row Level Security (RLS) policies if needed
3. Consider creating separate projects for production vs. development

## Deployment

See `DEPLOYMENT.md` for production deployment instructions.

## License

Internal use only.
