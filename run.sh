#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PORT=5001

if [ ! -d ".venv" ]; then
  echo "  Setting up virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

# Apply Desktop icon once (skipped if already done)
if [ ! -f "assets/.icon_applied" ]; then
  python make_icon.py && touch assets/.icon_applied
fi

echo ""
echo "  Saasfactor UX Audit — Admin Tool"
echo "  http://localhost:${PORT}"
echo ""

# Wait for server to respond, then open the browser
(
  for i in $(seq 1 30); do
    sleep 0.5
    if curl -s "http://localhost:${PORT}/api/health" > /dev/null 2>&1; then
      open "http://localhost:${PORT}"
      break
    fi
  done
) &

export PORT
python app.py
