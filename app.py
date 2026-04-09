#!/usr/bin/env python3
"""Saasfactor UX Audit — Local Version (No Supabase, No Auth)

This version runs entirely on local machine:
- Data stored in local_data/ folder (not committed to git)
- No authentication required
- AI APIs still work (Claude, Gemini via OpenRouter)
"""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
import ssl as _ssl

# SSL context: disable verification for local dev, enable for production
if os.environ.get("ENVIRONMENT") == "production":
    _ssl_context = _ssl.create_default_context()
else:
    # Local development only - disable SSL verification for macOS compatibility
    _ssl_context = _ssl.create_default_context()
    _ssl_context.check_hostname = False
    _ssl_context.verify_mode = _ssl.CERT_NONE
from html.parser import HTMLParser

from flask import Flask, Response, g, jsonify, redirect, render_template, request, send_file, stream_with_context
from flask_cors import CORS

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[warn] Pillow not installed — annotation markers disabled")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import OpenAI as _OpenAI
from functools import wraps

# Note: Supabase removed - using local file system instead
# Note: JWT/Auth removed - open access for local use

# ─── Error Tracking System (Debug Support) ─────────────────────────────────────
# NON-BREAKING: This class adds error tracking without changing existing functionality

class ErrorTracker:
    """
    Captures errors with full context for debugging.
    User can copy error codes to send to developer.
    """
    MAX_LOGS = 50  # Keep last 50 errors
    
    def __init__(self):
        self._logs = []
        self._lock = threading.Lock()
    
    def log(self, code: str, exc: Exception, context: dict = None, location: str = None):
        """
        Log an error with full debug context.
        
        Args:
            code: Unique error code (e.g., 'ERR-STOR-001')
            exc: The exception that occurred
            context: Additional context (audit_id, filename, etc.)
            location: Manual location string, or auto-detected from traceback
        """
        import traceback
        import sys
        
        # Auto-detect location from traceback if not provided
        if location is None and exc.__traceback__:
            tb = traceback.extract_tb(exc.__traceback__)
            if tb:
                last_frame = tb[-1]
                location = f"{last_frame.filename}:{last_frame.name}:{last_frame.lineno}"
            else:
                location = "unknown"
        elif location is None:
            location = "unknown"
        
        entry = {
            "id": str(uuid.uuid4())[:8],
            "code": code,
            "location": location,
            "message": str(exc),
            "type": exc.__class__.__name__,
            "context": context or {},
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "traceback": traceback.format_exc() if exc else None
        }
        
        with self._lock:
            self._logs.append(entry)
            # Keep only last MAX_LOGS
            if len(self._logs) > self.MAX_LOGS:
                self._logs = self._logs[-self.MAX_LOGS:]
        
        # Also print to console for server logs
        context_str = json.dumps(context) if context else "{}"
        print(f"[ERROR {code}] {location} | {exc} | Context: {context_str}", file=sys.stderr)
        
        return entry
    
    def get_logs(self, limit=None):
        """Get recent error logs (newest first)"""
        with self._lock:
            logs = list(self._logs)
        logs.reverse()  # Newest first
        if limit:
            logs = logs[:limit]
        return logs
    
    def get_error_for_user(self, log_id: str) -> str:
        """Format error for user to copy/send to developer"""
        with self._lock:
            for log in self._logs:
                if log["id"] == log_id:
                    return self._format_for_user(log)
        return "Error not found"
    
    def _format_for_user(self, log: dict) -> str:
        """Format error in copy-paste friendly format"""
        lines = [
            f"Error Code: [{log['code']}]",
            f"Location: {log['location']}",
            f"Time: {log['timestamp']}",
            f"Message: {log['message']}",
        ]
        if log['context']:
            lines.append(f"Context: {json.dumps(log['context'], indent=2)}")
        return "\n".join(lines)

# Global error tracker instance
_error_tracker = ErrorTracker()

# Helper function for quick error logging
def log_error(code: str, exc: Exception, **context):
    """Quick helper to log an error with context"""
    return _error_tracker.log(code, exc, context)

# Error code reference (for documentation)
ERROR_CODES = {
    # Storage errors
    "ERR-STOR-001": "Supabase storage upload failed",
    "ERR-STOR-002": "Supabase signed URL generation failed", 
    "ERR-STOR-003": "Storage direct download failed",
    "ERR-STOR-004": "Storage file not found (404)",
    "ERR-STOR-005": "Storage authentication failed",
    
    # API/AI errors
    "ERR-API-001": "OpenRouter/OpenAI API call failed",
    "ERR-API-002": "AI service overloaded (529)",
    "ERR-API-003": "AI analysis timeout (>120s)",
    "ERR-API-004": "Invalid JSON response from AI",
    "ERR-API-005": "API rate limit exceeded",
    
    # Auth errors
    "ERR-AUTH-001": "JWT verification failed",
    "ERR-AUTH-002": "Supabase auth.get_user failed",
    "ERR-AUTH-003": "Session expired",
    
    # Database errors
    "ERR-DB-001": "Database query failed (load sessions)",
    "ERR-DB-002": "Database save failed (save audit meta)",
    "ERR-DB-003": "Database connection failed",
    
    # Network errors
    "ERR-NET-001": "Network connection failed",
    "ERR-NET-002": "Request timeout",
    
    # Validation errors
    "ERR-VAL-001": "Invalid file type",
    "ERR-VAL-002": "File too large (>20MB)",
    "ERR-VAL-003": "Missing required field",
    
    # System errors
    "ERR-SYS-001": "Unexpected server error",
    "ERR-SYS-002": "Thread execution error",
}

# ─── Setup ────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
CORS(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
print(f"[startup] ANTHROPIC_API_KEY loaded: {bool(ANTHROPIC_API_KEY)} (length: {len(ANTHROPIC_API_KEY)})")

# ─── Local Data Configuration ─────────────────────────────────────────────────

LOCAL_DATA_DIR = os.path.join(BASE_DIR, "local_data")
LOCAL_AUDITS_FILE = os.path.join(LOCAL_DATA_DIR, "audits.json")
LOCAL_STORAGE_DIR = os.path.join(LOCAL_DATA_DIR, "storage")

# Ensure local directories exist
os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

# Initialize audits index if not exists
if not os.path.exists(LOCAL_AUDITS_FILE):
    with open(LOCAL_AUDITS_FILE, 'w') as f:
        json.dump([], f)
    print(f"[init] Created {LOCAL_AUDITS_FILE}")

print(f"[info] Local data directory: {LOCAL_DATA_DIR}")

# ─── Local Data Index Helpers ─────────────────────────────────────────────────

def _load_audits_index():
    """Load the audits index from local JSON file."""
    try:
        with open(LOCAL_AUDITS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def _save_audits_index(audits):
    """Save the audits index to local JSON file."""
    with open(LOCAL_AUDITS_FILE, 'w') as f:
        json.dump(audits, f, indent=2, default=str)

# ─── Auth decorator (disabled for local version) ───────────────────────────────

def auth_required(f):
    """No-op decorator for local version - authentication disabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user_email = "local-user"
        return f(*args, **kwargs)
    return decorated

# ─── Local File Storage helpers ───────────────────────────────────────────────

def _storage_upload(sid, filename, data, content_type="application/octet-stream", cache_control=None):
    """Save file to local storage directory."""
    audit_dir = os.path.join(LOCAL_STORAGE_DIR, sid)
    os.makedirs(audit_dir, exist_ok=True)
    filepath = os.path.join(audit_dir, filename)
    try:
        mode = 'wb' if isinstance(data, bytes) else 'w'
        with open(filepath, mode) as f:
            f.write(data)
        return True
    except Exception as exc:
        print(f"[storage] Upload failed {filepath}: {exc}")
        log_error("ERR-STOR-001", exc, sid=sid, filename=filepath, operation="upload")
        return False

def _storage_signed_url(sid, filename, expires=3600):
    """For local version, return a direct API URL instead of signed URL."""
    filepath = os.path.join(LOCAL_STORAGE_DIR, sid, filename)
    if os.path.exists(filepath):
        # Return local API endpoint that serves the file directly
        return f"/api/local-file/{sid}/{filename}"
    return ""

def _to_bytes(data):
    """Convert any storage response value to bytes, or return None."""
    if data is None:
        return None
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    try:
        return bytes(data)
    except Exception:
        return None

def _storage_public_url(sid, filename):
    """Construct the public URL for a file (works if bucket is public)."""
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{sid}/{filename}"

def _storage_direct_download(sid, filename):
    """Read file from local storage."""
    filepath = os.path.join(LOCAL_STORAGE_DIR, sid, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except Exception as exc:
            print(f"[storage] Read failed {filepath}: {exc}")
    return None

def _storage_download(sid, filename):
    """Download (read) file from local storage."""
    return _storage_direct_download(sid, filename)

def _cached_storage_download(sid, filename):
    """Like _storage_download but caches the result in memory for FILE_CACHE_TTL seconds.
    Also checks local disk as fallback. Eliminates repeated Storage round-trips."""
    cache_key = (sid, filename)
    now = time.time()
    with _file_cache_lock:
        cached = _file_cache.get(cache_key)
        if cached and now < cached[1]:
            return cached[0]
    
    # Try Supabase Storage first
    data = _storage_direct_download(sid, filename)
    if not data:
        data = _storage_download(sid, filename)
    
    # Fallback to local disk
    if not data:
        local_path = os.path.join(AUDITS_DIR, sid, filename)
        if os.path.isfile(local_path):
            try:
                with open(local_path, "rb") as f:
                    data = f.read()
                print(f"[storage] Loaded {sid}/{filename} from local disk")
            except Exception as exc:
                print(f"[storage] Local file read failed: {exc}")
    
    if data:
        with _file_cache_lock:
            _file_cache[cache_key] = (data, now + _FILE_CACHE_TTL)
    return data

def _invalidate_file_cache(sid, *filenames):
    """Bust the in-memory cache for one or more files after they are written or deleted."""
    with _file_cache_lock:
        for fname in filenames:
            _file_cache.pop((sid, fname), None)

def _storage_delete_folder(sid):
    try:
        files = sb.storage.from_(STORAGE_BUCKET).list(sid)
        paths = [f"{sid}/{f['name']}" for f in (files or [])]
        if paths:
            sb.storage.from_(STORAGE_BUCKET).remove(paths)
    except Exception as exc:
        print(f"[storage] Delete folder failed {sid}: {exc}")
        log_error("ERR-STOR-001", exc, sid=sid, operation="delete_folder")

# ─── Model registry ───────────────────────────────────────────────────────────
# Pipeline mode: Gemini reads the screenshot → Opus reasons about findings
USE_SPLIT_PIPELINE = True
VISION_MODEL       = "google/gemini-2.5-pro"       # sees the image
REASONING_MODEL    = "anthropic/claude-opus-4.6"   # reasons with thinking
AUDIT_MODEL_LABEL  = "Gemini+Opus"

# Single-model fallback (used when USE_SPLIT_PIPELINE = False)
AUDIT_MODEL        = "anthropic/claude-opus-4.6"
CONTENT_GEN_MODEL  = "anthropic/claude-sonnet-4.6" # YouTube script + Dribbble

VISION_PROMPT = """You are a precise visual analyst examining a UI screenshot.

Provide an exhaustive inventory of EVERY visible element. Miss nothing.

Cover ALL of the following:
- Overall layout: header, sidebar, navigation, main content areas, footer, modals
- Every text element verbatim: headings, body copy, labels, placeholder text, button text, error messages, tooltips, badges
- Every interactive element: buttons (exact labels), input fields, dropdowns, checkboxes, toggles, radio buttons, sliders, links
- Navigation: all menu items, breadcrumbs, tabs, pagination — in exact order
- Icons: their position, what they visually represent, whether they have visible text labels
- Images and illustrations: position and what they depict
- Typography: relative sizes (large/medium/small), weights (bold/regular/light), colors
- Colors: backgrounds, text, borders, accents — note any contrast issues
- Spacing: which elements appear cramped or misaligned, which have generous whitespace
- Visual hierarchy: what draws the eye first, second, third
- Visible accessibility issues: icon-only buttons with no label, low-contrast text, form fields with placeholder-only labels, missing error states
- Any component states visible: loading spinners, empty states, disabled elements, selected states

Be exhaustive. Report only what you see — do not audit or judge yet."""

def _load_b64(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

LOGO_WHITE_B64 = _load_b64(os.path.join(BASE_DIR, "assets", "logo_white.png"))
LOGO_DARK_B64  = _load_b64(os.path.join(BASE_DIR, "assets", "logo_dark.png"))

sessions: dict = {}
_lock = threading.Lock()

# ─── Signed URL cache (avoids hammering Storage on every page load) ───────────
_signed_url_cache: dict = {}          # {(sid, filename): (url, expires_at)}
_SIGNED_URL_TTL = 3000                # seconds — refresh before Supabase's 3600 expiry

# ─── File content cache (avoids re-downloading audit files on every modal open) ─
_file_cache: dict = {}                # {(sid, filename): (bytes, expires_at)}
_FILE_CACHE_TTL = 1800               # 30 minutes — audit data is immutable after write
_file_cache_lock = threading.Lock()

AUDIT_STEPS = [
    "Parsing layout and structure",
    "Identifying UX friction points",
    "Evaluating visual hierarchy",
    "Checking accessibility and clarity",
    "Generating audit report",
]

# ─── Persistent audit storage ─────────────────────────────────────────────────

# Use LOCAL_STORAGE_DIR for the local version (not AUDITS_DIR)
# All audit files are stored in local_data/storage/{sid}/
AUDITS_DIR = LOCAL_STORAGE_DIR  # For compatibility with existing code

def _fix_json_escapes(text):
    # Valid JSON escapes: \" \\ \/ \b \f \n \r \t \uXXXX
    # Everything else (e.g. \s \e \p from CSS/regex in LLM output) is invalid.
    # Double the offending backslash so it becomes a literal backslash char.
    _valid = set('"\\/' + 'bfnrtu')
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in _valid:
                out.append(ch)
                out.append(nxt)
                i += 2
            else:
                out.append('\\\\')   # escape the stray backslash
                i += 1
        else:
            out.append(ch)
            i += 1
    return ''.join(out)

def _supabase_report_url(sid, filename):
    """Return a long-lived signed URL for a shareable HTML file."""
    return _storage_signed_url(sid, filename, expires=315360000)  # 10 years

def _save_audit_meta(sid):
    """Save audit metadata to local JSON index."""
    s = sessions.get(sid, {})
    analysis = s.get("analysis") or {}
    issues = analysis.get("issues", [])
    
    audits = _load_audits_index()
    
    # Find existing or create new
    existing_idx = next((i for i, a in enumerate(audits) if a.get("sid") == sid), None)
    
    meta = {
        "sid": sid,
        "date": s.get("date", datetime.utcnow().isoformat() + "Z"),
        "product_name": analysis.get("product_name", ""),
        "screen_name": analysis.get("screen_name", s.get("filename", "Unknown")),
        "overall_score": analysis.get("overall_score", 0),
        "score_label": analysis.get("score_label", ""),
        "accessibility_score": analysis.get("accessibility_score", 0),
        "filename": s.get("filename", ""),
        "website_url": s.get("website_url", ""),
        "has_script":   s.get("has_script", False),
        "has_dribbble": s.get("has_dribbble", False),
        "has_redesign": s.get("has_redesign", False),
        "model_label":  s.get("model_label", ""),
    }
    
    if existing_idx is not None:
        audits[existing_idx].update(meta)
    else:
        audits.append(meta)
    
    try:
        _save_audits_index(audits)
    except Exception as exc:
        print(f"[db] _save_audit_meta failed: {exc}")
        log_error("ERR-DB-002", exc, sid=sid, operation="save_audit_meta")

def _persist_audit(sid):
    """Save all audit artifacts to local storage."""
    s = sessions.get(sid, {})
    if not s:
        return
    
    # Ensure local storage directory exists
    audit_dir = os.path.join(LOCAL_STORAGE_DIR, sid)
    os.makedirs(audit_dir, exist_ok=True)

    # Annotated screenshot
    ann_b64 = s.get("annotated_b64") or s.get("image_b64", "")
    if ann_b64:
        try:
            ann_data = base64.b64decode(ann_b64)
            with open(os.path.join(audit_dir, "annotated.jpg"), "wb") as f:
                f.write(ann_data)
            print(f"[persist] Saved annotated.jpg")
        except Exception as exc:
            print(f"[persist] annotated save error: {exc}")

    analysis = s.get("analysis")
    if analysis:
        # Full JSON — immutable after first write
        audit_json = json.dumps(analysis, indent=2, ensure_ascii=False).encode()
        try:
            with open(os.path.join(audit_dir, "audit_data.json"), "wb") as f:
                f.write(audit_json)
            print(f"[persist] Saved audit_data.json")
        except Exception as exc:
            print(f"[persist] audit_data save error: {exc}")

        # HTML report
        try:
            ann_type = s.get("ann_type", s.get("media_type", "image/jpeg"))
            html = _build_report(analysis, ann_b64, ann_type)
            html_bytes = html.encode("utf-8")
            with open(os.path.join(audit_dir, "report.html"), "wb") as f:
                f.write(html_bytes)
            print(f"[persist] Saved report.html")
        except Exception as exc:
            print(f"[persist] report error: {exc}")

        # Claude redesign prompt
        try:
            prompt = _build_redesign_prompt(analysis)
            prompt_bytes = prompt.encode("utf-8")
            with open(os.path.join(audit_dir, "claude_prompt.txt"), "wb") as f:
                f.write(prompt_bytes)
            print(f"[persist] Saved claude_prompt.txt")
        except Exception as exc:
            print(f"[persist] prompt error: {exc}")

    _save_audit_meta(sid)

def _load_sessions_from_local():
    """Minimal startup load — only count audits from local file.
    
    LAZY LOADING ARCHITECTURE:
    - Don't load audit data at startup
    - Load individual audits on-demand when user clicks
    """
    try:
        audits = _load_audits_index()
        count = len(audits)
        print(f"[info] Local lazy loading: {count} audits available (loaded on-demand)")
    except Exception as exc:
        print(f"[db] _load_sessions_from_local failed: {exc}")

# Run minimal count at startup
_load_sessions_from_local()


def _load_single_audit(sid):
    """Load a single audit from local storage into sessions (lazy loading).
    
    Called when user clicks on an audit thumbnail.
    Returns True if loaded successfully, False otherwise.
    """
    # Load from local index
    try:
        audits = _load_audits_index()
        audit = next((a for a in audits if a.get("sid") == sid), None)
        if not audit:
            return False
        
        sessions[sid] = {
            "image_b64":       "",
            "media_type":      "image/jpeg",
            "filename":        audit.get("filename", ""),
            "status":          "ready" if audit.get("overall_score", 0) > 0 else "uploaded",
            "analysis":        None,  # Will be loaded from file on demand
            "date":            audit.get("date", ""),
            "website_url":     audit.get("website_url", ""),
            "website_context": "",
            "model_label":     audit.get("model_label", ""),
            "has_script":      audit.get("has_script", False),
            "has_dribbble":    audit.get("has_dribbble", False),
            "has_redesign":    audit.get("has_redesign", False),
            "loaded_from_local": True,
        }
        print(f"[lazy-load] Loaded audit {sid} from local storage")
        return True
    except Exception as exc:
        print(f"[lazy-load] Failed to load audit {sid}: {exc}")
        log_error("ERR-DB-004", exc, sid=sid, operation="load_single_audit")
        return False


# DISABLED: Pre-warming cache — not needed with lazy loading
# def _prewarm_thumb_cache():
#     ...
# threading.Thread(target=_prewarm_thumb_cache, daemon=True).start()
print("[info] Lazy loading: Thumb cache pre-warming disabled (URLs generated on-demand)")


# ─── Training knowledge base ──────────────────────────────────────────────────

_TRAINING_FILES = {
    "training_dmmt.md":       "Don't Make Me Think — Steve Krug",
    "training_dui.md":        "Designing User Interfaces — Dmytro Malewicz",
    "training_psych.md":      "Psych 101 — Paul Kleinman",
    "training_psydesign.md":  "Psychology of Design: 106 Cognitive Biases",
    "training_pui.md":        "Practical UI",
    "training_refui.md":      "Refactoring UI — Adam Wathan & Steve Schoger",
    "training_uitips.md":     "UI Design Tips",
    "training_100things.md":  "100 More Things Every Designer Needs to Know About People",
    "ux_rules_batch1.md":     "UX Component Rules (Part 1)",
    "ux_rules_batch3.md":     "UX Component Rules (Part 3)",
    "ux_rules_batch4.md":     "UX Component Rules (Part 4)",
    "ux_rules_batch5.md":     "UX Component Rules (Part 5)",
    "training_wcag22.md":     "WCAG 2.2 — Web Content Accessibility Guidelines",
    "training_upd.md":        "Universal Principles of Design — Lidwell, Holden & Butler (200 Principles)",
    "training_doet.md":       "The Design of Everyday Things — Don Norman (Revised Edition)",
    "training_saasfactor_ai.md": "Saasfactor AI — Learned Patterns from 2,229 SaaS Screens",
}

_PRINCIPLE_PATTERNS = (
    "## ", "### ",
    "**Core idea:**", "**UX implication:**", "**Why it matters:**",
    "**Key fix:**", "**Key principle:**", "**Chapter:**",
    "✅", "❌",
)

def _extract_principles(path, max_chars=8000):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        return ""
    out = [l.strip() for l in lines
           if l.strip() and any(p in l for p in _PRINCIPLE_PATTERNS)]
    return "\n".join(out)[:max_chars]


def _load_precompiled_knowledge_base():
    """Load knowledge base from pre-compiled JSON file (fast path)."""
    kb_path = os.path.join(BASE_DIR, "knowledge_base.json")
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            kb_data = json.load(f)
        content = kb_data.get("content", "")
        stats = kb_data.get("stats", {})
        print(f"[info] Knowledge base (pre-compiled): {stats.get('num_sources', 0)} sources, "
              f"{len(content):,} chars (~{len(content)//4:,} tokens)")
        return content
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[warn] Pre-compiled knowledge base not available ({e}), building from source...")
        return None


def _build_knowledge_base():
    """Build knowledge base from training files (fallback/slow path)."""
    parts = []
    # Training data lives in ./training_data/ relative to this app
    base = os.path.join(BASE_DIR, "training_data")
    for fname, label in _TRAINING_FILES.items():
        path = os.path.join(base, fname)
        content = _extract_principles(path)
        if content:
            parts.append(f"\n\n=== SOURCE: {label} ===\n{content}")
    kb = "".join(parts)
    print(f"[info] Knowledge base (built from source): {len(parts)} sources, {len(kb):,} chars "
          f"(~{len(kb)//4:,} tokens)")
    return kb


# Load knowledge base: prefer pre-compiled, fall back to building from source
KNOWLEDGE_BASE = _load_precompiled_knowledge_base()
if KNOWLEDGE_BASE is None:
    KNOWLEDGE_BASE = _build_knowledge_base()


AUDIT_PROMPT = """You are a senior UX and accessibility auditor. You have been trained on the Saasfactor UX curriculum AND the WCAG 2.2 accessibility guidelines AND Saasfactor AI learned patterns from 2,229 screens across 5 major SaaS products.
The training knowledge base is provided above. Use it to ground every finding.

When analyzing, leverage Saasfactor AI benchmarks to contextualize your findings:
- Compare dashboard layouts against the typical 25-35 element range
- Flag lists with >20 items that lack search/filter functionality
- Note when forms exceed the optimal 3-7 field range
- Reference navigation patterns (71% of B2B SaaS use left sidebar)
- Apply severity benchmarks (e.g., >50 elements = High severity)

Analyze the UI screenshot below carefully. Produce a unified list of 7–10 findings that covers BOTH UX issues (usability, hierarchy, clarity, psychology) AND accessibility violations (WCAG 2.2 Level A/AA). Do NOT separate them — accessibility issues appear inline alongside UX issues in the same list, ordered by severity.

For any finding that also violates a WCAG 2.2 criterion, add "wcag_criterion" and "wcag_level" fields to that issue. Pure UX issues that have no WCAG violation should omit those fields.

Return ONLY a valid JSON object — no markdown fences, no explanation, no extra text:
{
  "product_name": "The actual brand/product name as it appears in the UI or website (e.g. 'Sana AI', 'Linear', 'Notion'). Not a generic description.",
  "screen_name": "Short descriptive screen name (e.g. Dashboard, Login, Onboarding Step 2)",
  "overall_score": 7.2,
  "score_label": "Good",
  "summary": "2-3 sentence executive summary of the UX quality and main themes",
  "accessibility_score": 6.0,
  "issues": [
    {
      "id": "01",
      "title": "Short descriptive issue title",
      "severity": "High",
      "location": "Specific UI element visible in the screenshot",
      "problem": "2-3 sentence synopsis: what is wrong and how it directly hurts the user",
      "critical_reason": "1-2 sentences: the psychological or cognitive principle that makes this a critical issue, citing the specific training source",
      "recommendation": "2-3 sentences: concrete actionable fix with implementation specifics",
      "reference": "Nielsen's Heuristic #1: Visibility of System Status",
      "wcag_criterion": "1.4.3",
      "wcag_level": "AA",
      "annotation": {"x": 75, "y": 20, "w": 35, "h": 10}
    },
    {
      "id": "02",
      "title": "Pure UX issue — no WCAG violation",
      "severity": "Medium",
      "location": "Navigation bar",
      "problem": "...",
      "critical_reason": "...",
      "recommendation": "...",
      "reference": "...",
      "annotation": {"x": 50, "y": 5, "w": 80, "h": 8}
    }
  ]
}

Rules:
- overall_score: 0–10 (one decimal). score_label: Poor / Fair / Good / Strong.
- accessibility_score: 0–10 (one decimal) reflecting overall WCAG 2.2 compliance from what is visible.
- severity: High / Medium / Low only. Order issues by severity (High first).
- Include at least 3 issues that are WCAG 2.2 violations (with wcag_criterion + wcag_level). The rest are pure UX findings.
- wcag_criterion: the WCAG 2.2 success criterion number (e.g. "1.4.3", "2.4.7", "1.1.1"). Only include if there is a real WCAG violation.
- wcag_level: "A" or "AA" only. Only include alongside wcag_criterion.
- problem: MAX 3 sentences. State what is wrong and the direct UX/accessibility impact.
- critical_reason: MAX 2 sentences. Explain WHY this matters using a specific psychological or
  cognitive science principle from the training data (e.g. cognitive load, Hick's Law,
  Gestalt, working memory, loss aversion). Must cite the source. For WCAG issues, name the exact criterion violated.
- recommendation: MAX 3 sentences. Be concrete and actionable.
- reference: cite the EXACT book title and specific principle/chapter/rule from the training knowledge
  base above. For WCAG issues, reference the WCAG 2.2 guideline. Examples:
  "Don't Make Me Think (Krug) — Billboard Design 101: users scan, not read",
  "Refactoring UI — Use color to support hierarchy, not communicate it alone",
  "Designing User Interfaces (Malewicz) — Contrast and visual hierarchy",
  "Psychology of Design — Hick's Law: too many choices slows decisions",
  "Practical UI — Spacing consistency: use a spacing scale",
  "Psych 101 (Kleinman) — Gestalt: Law of Proximity",
  "WCAG 2.2 — 1.4.3 Contrast Minimum (AA): normal text requires 4.5:1 contrast ratio",
  "WCAG 2.2 — 2.4.7 Focus Visible (AA): keyboard focus indicator must be visible",
  "Universal Principles of Design — Aesthetic-Usability Effect: beautiful things are perceived as easier to use",
  "Universal Principles of Design — Fitts' Law: larger and closer targets are faster to click",
  "Universal Principles of Design — Progressive Disclosure: show only what is needed at each step",
  "Universal Principles of Design — Signal-to-Noise Ratio: maximise relevant information, minimise clutter",
  "Universal Principles of Design — Visibility: system status and available actions must be visible",
  "The Design of Everyday Things (Norman) — Affordance: element must communicate how it is used",
  "The Design of Everyday Things (Norman) — Signifier: visible cues must indicate where to act",
  "The Design of Everyday Things (Norman) — Gulf of Execution: user cannot figure out how to do what they want",
  "The Design of Everyday Things (Norman) — Gulf of Evaluation: user cannot tell if their action worked",
  "The Design of Everyday Things (Norman) — Feedback: every action must produce an immediate, clear response",
  "The Design of Everyday Things (Norman) — Forcing Function: prevent irreversible actions with confirmation",
  "Saasfactor AI — Dashboard Layouts: Typical range 25-35 UI elements",
  "Saasfactor AI — List Screens: 67% include search/filter when displaying >20 items",
  "Saasfactor AI — Navigation Patterns: Left sidebar navigation in 71% of B2B SaaS",
  "Saasfactor AI — Form Patterns: 34% higher abandonment with >7 fields on single screen",
  "Saasfactor AI — Severity Flags: Dashboards with >50 elements indicate information overload",
  "Saasfactor AI — Accessibility Analysis: 10.5% of screens have contrast ratio violations"
- Focus on visually detectable accessibility issues: contrast ratios, color-only information, missing labels,
  touch target sizes, focus indicator absence, images of text, heading structure, icon-only buttons,
  placeholder-only form fields, error states without text labels.
- annotation: approximate center of the issue on the screenshot as percentages (x=0 left, x=100 right,
  y=0 top, y=100 bottom). w and h are width/height as percentages.
  Be specific — do not default to x=50, y=50 for all issues.
- Do NOT reference Mobbin or any other third-party design gallery. If you need to cite a pattern source, reference Saasfactor.
"""


# ─── Website context fetcher ──────────────────────────────────────────────────

def _fetch_website_context(url):
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        req = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; UXAudit/1.0)"})
        with _urllib_req.urlopen(req, timeout=8, context=_ssl_context) as resp:
            raw = resp.read(150_000).decode("utf-8", errors="ignore")

        class _Stripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
                self._skip = False
            def handle_starttag(self, tag, _):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    s = data.strip()
                    if len(s) > 3:
                        self.parts.append(s)

        p = _Stripper()
        p.feed(raw)
        text = " ".join(p.parts)
        print(f"[info] Website context fetched: {len(text)} chars from {url}")
        return text[:3000]
    except Exception as e:
        print(f"[warn] Could not fetch website {url}: {e}")
        return ""


# ─── YouTube script generation ────────────────────────────────────────────────

_SCRIPT_STYLE = """You are writing a YouTube voiceover script in the style of "The Code Report" — irreverent tech-comedy channel.

STYLE RULES:
- Short punchy sentences. Then shorter. Then one long one that builds to a punchline.
- Dark, absurdist, self-deprecating humor. The joke lands via specific unexpected analogies — never explain it.
- No corporate language: no "leverage", "pain points", "synergize", "utilize".
- No transitions: no "firstly", "moving on", "as I mentioned". Just cut to the next thing.
- Casual — talks TO the viewer, not at them. Occasionally self-aware.
- TTS-safe for Google AI Studio: no em-dashes, spell out numbers under 10, no parenthetical asides.

STRUCTURE (strict):
- Hook (2-3 sentences): Frame the entire problem in one punchy take.
- Act 1 — Problems (55% of runtime): 3-4 issues. Each: name it → why it hurts (1-2 sentences, name the exact UX principle and source) → move on.
- Act 2 — Redesign (35%): "Here is what the redesign does." → each fix tied back to the exact problem it solves.
- Outro (10%): One punchy closing line. No motivation. No "see you next time" unless it is dry.

TARGET: 480-550 words total. At 140 wpm TTS that is 3.5-4 minutes exactly.

For every issue, explicitly name the source: "Steve Krug, in Don't Make Me Think..." or "Don Norman's concept of the missing signifier..." or "Hick's Law, from the Universal Principles of Design..." or "Growth.design calls this signifier blindness."
"""

def _build_youtube_script(analysis):
    screen_name = analysis.get("screen_name", "Screen")
    score       = analysis.get("overall_score", 0)
    summary     = analysis.get("summary", "")
    issues      = analysis.get("issues", [])

    issues_text = ""
    for iss in issues[:6]:  # cap at 6 for prompt length
        issues_text += (
            f"\n[{iss.get('severity','?')}] {iss.get('title','')}\n"
            f"  Problem: {iss.get('problem','')}\n"
            f"  Fix: {iss.get('recommendation','')}\n"
            f"  Source: {iss.get('reference','')}\n"
        )

    user_prompt = (
        f"{_SCRIPT_STYLE}\n\n"
        f"Write the script for this UX audit:\n\n"
        f"SCREEN: {screen_name}\n"
        f"SCORE: {score}/10\n"
        f"SUMMARY: {summary}\n\n"
        f"ISSUES FOUND:\n{issues_text}\n\n"
        f"Write ONLY the script. No headers, no word count, no meta-commentary. Just the spoken words."
    )

    client = _OpenAI(api_key=ANTHROPIC_API_KEY, base_url="https://openrouter.ai/api/v1")
    msg = client.chat.completions.create(
        model=CONTENT_GEN_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=60,
    )
    return msg.choices[0].message.content.strip()


# ─── Dribbble shot details generation ────────────────────────────────────────

def _build_dribbble_details(analysis):
    product_name = analysis.get("product_name", "") or analysis.get("screen_name", "the product")
    screen_name  = analysis.get("screen_name", "Screen")
    summary      = analysis.get("summary", "")
    issues       = analysis.get("issues", [])

    issues_text = ""
    references  = []
    for iss in issues[:6]:
        issues_text += (
            f"\n[{iss.get('severity','?')}] {iss.get('title','')}\n"
            f"  Problem: {iss.get('problem','')}\n"
            f"  Recommendation: {iss.get('recommendation','')}\n"
            f"  Source: {iss.get('reference','')}\n"
        )
        ref = iss.get("reference", "").strip()
        if ref and ref not in references:
            references.append(ref)

    references_text = "\n".join(f"- {r}" for r in references)

    prompt = f"""You are writing Dribbble shot metadata for a UX redesign case study.

AUDIT CONTEXT:
Product name: {product_name}
Screen: {screen_name}
Summary: {summary}
Issues:{issues_text}

SOURCES FROM AUDIT (cite these explicitly in the description — use the exact names):
{references_text}

Generate three assets. Return ONLY a valid JSON object, no markdown, no explanation:

{{
  "title": "string — max 80 characters including spaces. Must use '{product_name}' as the product name (not a generic description). Must include the word 'Redesign' and the word 'UX'. Punchy, specific, no filler words.",
  "description": "string — 1500 to 2000 characters. Rich text using markdown headings (# ## ###). Structure: # Opening hook (one sentence naming {product_name} and the core issue). ## The Problem (2-3 sentences on the UX friction — cite at least 2 specific sources from the list above by name, e.g. 'Steve Krug in Don't Make Me Think calls this...' or 'Don Norman's concept of the missing signifier...'). ## Impact on Users (1-2 sentences on the real cost to users). ## What We Changed (bullet points — each fix tied back to a principle or source). ## The Result (1-2 sentences). SEO-optimised, natural language, no corporate jargon, no em-dashes.",
  "tags": "string — exactly 10 tags separated by commas, no # symbol. Mix of: {product_name.lower().replace(' ', '-')}, product-specific tags, AI, SaaS, UX design, UI design, web app design, product design, interaction design, usability, accessibility."
}}"""

    client = _OpenAI(api_key=ANTHROPIC_API_KEY, base_url="https://openrouter.ai/api/v1")
    msg = client.chat.completions.create(
        model=CONTENT_GEN_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    raw = msg.choices[0].message.content.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", logo_dark=LOGO_DARK_B64, logo_white=LOGO_WHITE_B64)


@app.route("/favicon.ico")
def favicon():
    return send_file(
        os.path.join(BASE_DIR, "static", "favicon.png"),
        mimetype="image/png"
    )


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/errors")
@auth_required
def get_errors():
    """Get recent error logs for debugging. 
    User can copy these to send to developer."""
    limit = request.args.get('limit', 20, type=int)
    logs = _error_tracker.get_logs(limit=limit)
    return jsonify({
        "errors": logs,
        "count": len(logs),
        "error_codes": ERROR_CODES
    })


@app.route("/api/errors/clear", methods=["POST"])
@auth_required
def clear_errors():
    """Clear error logs."""
    _error_tracker._logs = []
    return jsonify({"ok": True})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "").strip()
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        if res.user and res.session:
            return jsonify({
                "access_token":  res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "email":         res.user.email,
            })
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception:
        return jsonify({"error": "Invalid email or password"}), 401


@app.route("/api/upload", methods=["POST"])
@auth_required
def upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "No file selected"}), 400

        allowed = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
        media_type = f.content_type or "image/jpeg"
        if media_type == "image/jpg":
            media_type = "image/jpeg"
        if media_type not in allowed:
            return jsonify({"error": "Only PNG, JPG, or WebP images are supported"}), 400

        data = f.read()
        if len(data) > 20 * 1024 * 1024:
            return jsonify({"error": "Image must be under 20 MB"}), 400

        website_url     = request.form.get("website_url", "").strip()
        website_context = _fetch_website_context(website_url) if website_url else ""

        sid = str(uuid.uuid4())
        with _lock:
            sessions[sid] = {
                "image_b64":       base64.b64encode(data).decode(),
                "annotated_b64":   None,
                "media_type":      media_type,
                "filename":        f.filename,
                "status":          "uploaded",
                "analysis":        None,
                "website_url":     website_url,
                "website_context": website_context,
                "model_label":     AUDIT_MODEL_LABEL,
                "created_by":      getattr(g, "current_user_email", ""),
            }

        # Upload screenshot to Supabase Storage immediately — immutable
        try:
            ext = "jpg" if "jpeg" in media_type else "png"
            _storage_upload(sid, f"screenshot.{ext}", data, media_type, cache_control="public, max-age=86400")
            with _lock:
                sessions[sid]["date"] = datetime.utcnow().isoformat() + "Z"
            _save_audit_meta(sid)
        except Exception as exc:
            print(f"[upload] storage save error: {exc}")

        return jsonify({"session_id": sid})
    except Exception as exc:
        return jsonify({"error": f"Upload failed: {exc}"}), 500


@app.route("/api/audit/<sid>")
@auth_required
def audit_stream(sid):
    print(f"\n[audit_endpoint] Request received for sid: {sid}", flush=True)
    print(f"[audit_endpoint] Sessions loaded: {len(sessions)}", flush=True)
    import sys
    print(f"[audit_stream] Called for sid: {sid}", flush=True)
    if sid not in sessions:
        print(f"[audit_stream] Session not found: {sid}", flush=True)
        return jsonify({"error": "Session not found"}), 404

    session = sessions[sid]
    print(f"[audit_stream] Session status: {session.get('status')}", flush=True)
    if session["status"] == "ready":
        def _done():
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        return Response(stream_with_context(_done()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def _generate():
        print(f"[_generate] Starting generator for {sid}", flush=True)
        result_box = [None]
        error_box  = [None]
        done_evt   = threading.Event()

        def _run():
            print(f"[_run] Thread started for {sid}", flush=True)
            try:
                print(f"[audit] Starting audit for {sid}", flush=True)
                print(f"[audit] API Key present: {bool(ANTHROPIC_API_KEY)}", flush=True)
                if not ANTHROPIC_API_KEY:
                    raise ValueError("ANTHROPIC_API_KEY is not set")
                client = _OpenAI(api_key=ANTHROPIC_API_KEY, base_url="https://openrouter.ai/api/v1")
                print(f"[audit] OpenAI client created, USE_SPLIT_PIPELINE: {USE_SPLIT_PIPELINE}", flush=True)

                if USE_SPLIT_PIPELINE:
                    # ── Step 1: Gemini reads the screenshot ───────────────────
                    vision_content = []
                    if session.get("website_context"):
                        vision_content.append({
                            "type": "text",
                            "text": (
                                "=== PRODUCT WEBSITE CONTEXT ===\n"
                                f"Website URL: {session.get('website_url', '')}\n"
                                + session["website_context"] + "\n\n"
                            ),
                        })
                    vision_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{session['media_type']};base64,{session['image_b64']}"},
                    })
                    vision_content.append({"type": "text", "text": VISION_PROMPT})

                    print(f"[audit] Calling Gemini vision model: {VISION_MODEL}", flush=True)
                    vision_msg = client.chat.completions.create(
                        model=VISION_MODEL,
                        max_tokens=3000,
                        messages=[{"role": "user", "content": vision_content}],
                        timeout=60,
                    )
                    visual_description = vision_msg.choices[0].message.content
                    print(f"[audit] Vision description received: {len(visual_description)} chars", flush=True)

                    # ── Step 2: Opus reasons about the findings ────────────────
                    reasoning_content = []
                    if session.get("website_context"):
                        reasoning_content.append({
                            "type": "text",
                            "text": (
                                "=== PRODUCT WEBSITE CONTEXT ===\n"
                                f"Website URL: {session.get('website_url', '')}\n"
                                "The following text was extracted from the product's website. "
                                "Use it to understand what the product is, who it serves, and "
                                "tailor every finding to their specific context.\n\n"
                                + session["website_context"] + "\n\n"
                            ),
                        })
                    reasoning_content.append({
                        "type": "text",
                        "text": (
                            "=== VISUAL DESCRIPTION OF UI SCREEN ===\n"
                            "(The following exhaustive description was produced by a dedicated "
                            "vision model that analyzed the screenshot. Use it as your ground truth "
                            "for what is visible — do not ask for the image.)\n\n"
                            + visual_description + "\n\n"
                        ),
                    })
                    reasoning_content.append({"type": "text", "text": AUDIT_PROMPT})

                    messages = [{"role": "user", "content": reasoning_content}]
                    print(f"[audit] Calling Opus reasoning model: {REASONING_MODEL}", flush=True)
                    _api_kwargs = dict(
                        model=REASONING_MODEL,
                        max_tokens=6000,
                        messages=messages,
                        timeout=150,
                        extra_body={"thinking": {"type": "enabled", "budget_tokens": 5000}},
                    )
                else:
                    # ── Single-model path (fallback) ───────────────────────────
                    user_content = []
                    if session.get("website_context"):
                        user_content.append({
                            "type": "text",
                            "text": (
                                "=== PRODUCT WEBSITE CONTEXT ===\n"
                                f"Website URL: {session.get('website_url', '')}\n"
                                "The following text was extracted from the product's website. "
                                "Use it to understand what the product is, who it serves, and "
                                "tailor every finding to their specific context.\n\n"
                                + session["website_context"] + "\n\n"
                            ),
                        })
                    user_content.append({"type": "text", "text": "=== UI SCREENSHOT TO AUDIT ==="})
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{session['media_type']};base64,{session['image_b64']}"},
                    })
                    user_content.append({"type": "text", "text": AUDIT_PROMPT})
                    messages = [{"role": "user", "content": user_content}]
                    _api_kwargs = dict(
                        model=AUDIT_MODEL,
                        max_tokens=6000,
                        messages=messages,
                        timeout=150,
                    )
                    if AUDIT_MODEL.startswith("anthropic/"):
                        _api_kwargs["extra_body"] = {
                            "thinking": {"type": "enabled", "budget_tokens": 5000}
                        }

                last_exc = None
                for attempt in range(2):
                    try:
                        print(f"[audit] Making API call (attempt {attempt+1}/2)", flush=True)
                        msg = client.chat.completions.create(**_api_kwargs)
                        result_box[0] = msg.choices[0].message.content
                        print(f"[audit] API call successful, response length: {len(result_box[0])}", flush=True)
                        return
                    except Exception as exc:
                        last_exc = exc
                        err_str = str(exc)
                        print(f"[api] Error (attempt {attempt+1}/2): {err_str[:200]}")
                        if any(k in err_str.lower() for k in ("500", "502", "bad gateway", "529", "overload", "rate limit", "too many", "internal server")):
                            wait = 8 * (attempt + 1)
                            print(f"[retry] API busy, waiting {wait}s")
                            time.sleep(wait)
                        else:
                            raise
                raise last_exc
            except Exception as exc:
                error_box[0] = str(exc)
                # Log API error with full context for debugging
                error_code = "ERR-API-002" if ("529" in str(exc) or "overload" in str(exc).lower()) else "ERR-API-001"
                log_error(error_code, exc, sid=sid, operation="ai_analysis", model=VISION_MODEL if USE_SPLIT_PIPELINE else AUDIT_MODEL)
            finally:
                done_evt.set()

        thread = threading.Thread(target=_run, daemon=True)
        print(f"[_generate] Starting thread for {sid}", flush=True)
        thread.start()
        print(f"[_generate] Thread started, yielding first step", flush=True)

        step_min_durations = [4.0, 5.0, 5.0, 4.5]

        def evt(data):
            return f"data: {json.dumps(data)}\n\n"

        yield evt({"type": "step", "step": 0, "status": "active", "label": AUDIT_STEPS[0]})

        for i, dur in enumerate(step_min_durations):
            waited = 0.0
            while waited < dur:
                time.sleep(0.3)
                waited += 0.3
            yield evt({"type": "step", "step": i, "status": "done", "label": AUDIT_STEPS[i]})
            yield evt({"type": "step", "step": i + 1, "status": "active", "label": AUDIT_STEPS[i + 1]})

        elapsed = 0
        while not done_evt.wait(timeout=2.0):
            elapsed += 2
            if elapsed >= 120:
                error_box[0] = "Analysis timed out after 2 minutes. Please try again."
                done_evt.set()
                break
            yield ": keepalive\n\n"

        if error_box[0]:
            msg = error_box[0]
            if "529" in msg or "overloaded" in msg.lower():
                msg = "The AI service is currently overloaded. Please wait 30 seconds and try again."
            yield evt({"type": "error", "message": msg})
            return
        if not result_box[0]:
            yield evt({"type": "error", "message": "Analysis timed out. Please try again."})
            return

        try:
            text = result_box[0].strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
            start = text.find("{")
            end   = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]
            analysis = json.loads(_fix_json_escapes(text))

            issues = analysis.get("issues", [])

            ann_b64, ann_type = annotate_image(
                session["image_b64"], session["media_type"], issues
            )

            with _lock:
                sessions[sid]["analysis"]      = analysis
                sessions[sid]["annotated_b64"] = ann_b64
                sessions[sid]["ann_type"]      = ann_type
                sessions[sid]["status"]        = "ready"

            # Persist all artefacts to disk in this same thread
            try:
                _persist_audit(sid)
            except Exception as exc:
                print(f"[persist] {exc}")

            h = sum(1 for x in issues if x.get("severity") == "High")
            m = sum(1 for x in issues if x.get("severity") == "Medium")
            l = sum(1 for x in issues if x.get("severity") == "Low")

            yield evt({"type": "step", "step": 4, "status": "done", "label": AUDIT_STEPS[4]})
            yield evt({
                "type":        "complete",
                "score":       analysis.get("overall_score", 0),
                "score_label": analysis.get("score_label", ""),
                "screen_name": analysis.get("screen_name", ""),
                "summary":     analysis.get("summary", ""),
                "high": h, "medium": m, "low": l,
                "sid":         sid,
                "analysis":    analysis,
            })
        except json.JSONDecodeError as exc:
            try:
                fixed = re.sub(r',\s*\{[^}]*$', '', text)
                fixed = re.sub(r',\s*"[^"]*$', '', fixed)
                fixed = re.sub(r'\s*$', '', fixed)
                open_braces   = fixed.count('{') - fixed.count('}')
                open_brackets = fixed.count('[') - fixed.count(']')
                fixed += ']' * open_brackets + '}' * open_braces
                analysis = json.loads(_fix_json_escapes(fixed))
                issues = analysis.get("issues", [])
                ann_b64, ann_type = annotate_image(
                    session.get("image_b64", ""),
                    session.get("media_type", "image/png"),
                    issues,
                )
                with _lock:
                    sessions[sid]["analysis"]      = analysis
                    sessions[sid]["annotated_b64"] = ann_b64
                    sessions[sid]["ann_type"]      = ann_type
                    sessions[sid]["status"]        = "ready"

                # Persist all artefacts to disk in this same thread
                try:
                    _persist_audit(sid)
                except Exception as persist_exc:
                    print(f"[persist] {persist_exc}")

                h = sum(1 for i in issues if i.get("severity") == "High")
                m = sum(1 for i in issues if i.get("severity") == "Medium")
                l = sum(1 for i in issues if i.get("severity") == "Low")
                yield evt({"type": "step", "step": 4, "status": "done", "label": AUDIT_STEPS[4]})
                yield evt({
                    "type":        "complete",
                    "score":       analysis.get("overall_score", 0),
                    "score_label": analysis.get("score_label", ""),
                    "screen_name": analysis.get("screen_name", ""),
                    "summary":     analysis.get("summary", ""),
                    "high": h, "medium": m, "low": l,
                    "sid":         sid,
                    "analysis":    analysis,
                })
            except Exception:
                yield evt({"type": "error", "message": f"Could not parse analysis: {exc}"})

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.route("/api/download/<sid>", methods=["GET"])
@auth_required
def download_report(sid):
    if sid not in sessions:
        return jsonify({"error": "Session not found. Please run the audit again."}), 404
    s = sessions[sid]
    analysis   = s.get("analysis") or {}
    image_b64  = s.get("image_b64", "")
    media_type = s.get("media_type", "image/png")

    if not analysis:
        return jsonify({"error": "Report data not found. Please run the audit again."}), 400

    ann_b64, ann_type = annotate_image(image_b64, media_type, analysis.get("issues", []))
    html  = _build_report(analysis, ann_b64, ann_type)
    slug  = re.sub(r"[^\w\-]", "_", analysis.get("screen_name", "screen").lower())
    fname = f"ux_audit_{slug}_{datetime.utcnow().strftime('%Y%m%d')}.html"

    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.route("/api/prompt/<sid>", methods=["GET"])
@auth_required
def download_prompt(sid):
    if sid not in sessions:
        return jsonify({"error": "Session not found. Please run the audit again."}), 404
    analysis = sessions[sid].get("analysis") or {}

    if not analysis:
        return jsonify({"error": "Report data not found. Please run the audit again."}), 400

    prompt = _build_redesign_prompt(analysis)
    slug   = re.sub(r"[^\w\-]", "_", analysis.get("screen_name", "screen").lower())
    fname  = f"claude_redesign_prompt_{slug}_{datetime.utcnow().strftime('%Y%m%d')}.txt"

    return Response(
        prompt,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ─── Audit history CRUD ───────────────────────────────────────────────────────

@app.route("/api/audits/<sid>/thumb")
def audit_thumb(sid):
    """Serve the screenshot/annotated image from local storage."""
    from flask import send_file
    # Try local storage first
    audit_dir = os.path.join(LOCAL_STORAGE_DIR, sid)
    for fname in ["annotated.jpg", "screenshot.jpg", "screenshot.png"]:
        local_path = os.path.join(audit_dir, fname)
        if os.path.isfile(local_path):
            mime = "image/jpeg" if fname.endswith(".jpg") else "image/png"
            return send_file(local_path, mimetype=mime)
    # Fallback to in-memory session
    s = sessions.get(sid, {})
    if s.get("annotated_b64"):
        data = base64.b64decode(s["annotated_b64"])
        mime = s.get("ann_type", "image/jpeg")
        return Response(data, mimetype=mime)
    if s.get("image_b64"):
        data = base64.b64decode(s["image_b64"])
        mime = s.get("media_type", "image/jpeg")
        return Response(data, mimetype=mime)
    return ("", 404)


@app.route("/api/audits")
@auth_required
def list_audits():
    """List all audits with minimal data (lazy loading architecture).
    
    Returns only metadata needed to display thumbnails.
    Full audit data is loaded on-demand when user clicks.
    """
    try:
        # Load from local file
        audits = _load_audits_index()
        
        # Sort by date (newest first)
        audits.sort(key=lambda x: x.get("date", ""), reverse=True)
        
        for item in audits:
            sid = item.get("sid")
            # Check if this audit is already loaded in memory
            is_loaded = sid in sessions and sessions[sid].get("loaded_from_local", False)
            
            item["thumb_url"] = f"/api/audits/{sid}/thumb"
            item["is_loaded"] = is_loaded  # Frontend shows "Click to load" if False
            item["detail_url"] = f"/api/audits/{sid}"
            
        return jsonify(audits)
    except Exception as exc:
        print(f"[error] list_audits failed: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/audits/<sid>")
@auth_required
def get_audit_detail(sid):
    """Get audit details — with lazy loading support.
    
    If audit is not in memory, loads it from local storage on-demand.
    This is called when user clicks a thumbnail.
    """
    # LAZY LOADING: Load audit into memory if not already loaded
    if sid not in sessions or not sessions[sid].get("loaded_from_local", False):
        print(f"[lazy-load] Loading audit {sid} on-demand...")
        loaded = _load_single_audit(sid)
        if not loaded:
            return jsonify({"error": "Audit not found or failed to load"}), 404
    
    # Get from local index for full details
    try:
        audits = _load_audits_index()
        result = next((a for a in audits if a.get("sid") == sid), None)
        if not result:
            return jsonify({"error": "Audit not found"}), 404
    except Exception as exc:
        print(f"[error] get_audit_detail failed: {exc}")
        return jsonify({"error": "Audit not found"}), 404

    # Mark as loaded
    result["is_loaded"] = True
    result["loaded_on_demand"] = True
    
    # Thumbnail — point to the thumb endpoint (handles all fallbacks)
    result["thumb_url"] = f"/api/audits/{sid}/thumb"

    # Proxy view URLs (render in browser, no auth required)
    result["report_url"] = f"/audits/{sid}/report-view"
    if result.get("has_redesign"):
        result["redesign_url"] = f"/audits/{sid}/redesign-view"

    # ?include=issues — embed issues + summary directly so the frontend
    # needs only one request instead of two sequential ones
    if request.args.get("include") == "issues":
        raw = _cached_storage_download(sid, "audit_data.json")
        print(f"[debug] Loading audit_data.json for {sid}: {'found' if raw else 'NOT FOUND'}")
        if raw:
            try:
                audit_data = json.loads(_fix_json_escapes(raw.decode()))
                result["issues"]  = audit_data.get("issues", [])
                result["summary"] = audit_data.get("summary", result.get("summary", ""))
            except Exception:
                result["issues"] = []

    return jsonify(result)


@app.route("/api/audits/<sid>/file/<fname>")
@auth_required
def get_audit_file(sid, fname):
    """Serve a single audit file on demand — called one at a time by the frontend."""
    ALLOWED = {"audit_data.json", "claude_prompt.txt", "youtube_script.txt", "dribbble.json"}
    if fname not in ALLOWED:
        return jsonify({"error": "Not allowed"}), 400

    # Try in-memory cache first, then Storage, then local disk
    raw = _cached_storage_download(sid, fname)
    if not raw:
        local = os.path.join(AUDITS_DIR, sid, fname)
        if os.path.isfile(local):
            with open(local, "rb") as f:
                raw = f.read()

    if not raw:
        return jsonify({"error": "File not found"}), 404

    if fname.endswith(".json"):
        try:
            return jsonify({"ok": True, "data": json.loads(_fix_json_escapes(raw.decode()))})
        except Exception as exc:
            return jsonify({"error": f"Parse error: {exc}"}), 500
    try:
        return jsonify({"ok": True, "data": raw.decode("utf-8")})
    except Exception:
        return jsonify({"error": "Decode error"}), 500


@app.route("/api/audits/<sid>", methods=["DELETE"])
@auth_required
def delete_audit(sid):
    """Delete audit from local storage."""
    try:
        # Remove from index
        audits = _load_audits_index()
        audits = [a for a in audits if a.get("sid") != sid]
        _save_audits_index(audits)
        
        # Delete storage folder
        audit_dir = os.path.join(LOCAL_STORAGE_DIR, sid)
        if os.path.exists(audit_dir):
            shutil.rmtree(audit_dir)
        
        # Remove from sessions
        with _lock:
            sessions.pop(sid, None)
        
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/script/<sid>", methods=["POST"])
@auth_required
def generate_script(sid):
    if sid not in sessions or not sessions[sid].get("analysis"):
        raw = _storage_download(sid, "audit_data.json")
        if raw:
            sessions[sid] = {"analysis": json.loads(raw.decode()), "status": "ready"}
        else:
            return jsonify({"error": "Session not found"}), 404
    analysis = sessions[sid].get("analysis")
    if not analysis:
        return jsonify({"error": "No analysis data — run the audit first"}), 400
    try:
        script = _build_youtube_script(analysis)
    except Exception as exc:
        return jsonify({"error": f"Script generation failed: {exc}"}), 500
    _storage_upload(sid, "youtube_script.txt", script.encode("utf-8"), "text/plain",
                    cache_control="public, max-age=3600")
    _invalidate_file_cache(sid, "youtube_script.txt")
    with _lock:
        sessions[sid]["has_script"] = True
    _save_audit_meta(sid)
    return jsonify({"script": script})


@app.route("/api/dribbble/<sid>", methods=["POST"])
@auth_required
def generate_dribbble(sid):
    if sid not in sessions or not sessions[sid].get("analysis"):
        raw = _storage_download(sid, "audit_data.json")
        if raw:
            sessions[sid] = {"analysis": json.loads(raw.decode()), "status": "ready"}
        else:
            return jsonify({"error": "Session not found"}), 404
    analysis = sessions[sid].get("analysis")
    if not analysis:
        return jsonify({"error": "No analysis data — run the audit first"}), 400

    # Enrich with product_name from DB if not set
    if not analysis.get("product_name"):
        try:
            res = sb.table("audits").select("product_name, website_url").eq("sid", sid).single().execute()
            if res.data:
                product_name = res.data.get("product_name", "")
                if not product_name:
                    url = res.data.get("website_url", "")
                    if url:
                        from urllib.parse import urlparse
                        host = urlparse(url).hostname or ""
                        brand = host.replace("www.", "").split(".")[0]
                        product_name = brand.capitalize()
                analysis["product_name"] = product_name
        except Exception:
            pass

    try:
        data = _build_dribbble_details(analysis)
    except Exception as exc:
        return jsonify({"error": f"Dribbble generation failed: {exc}"}), 500
    _storage_upload(sid, "dribbble.json", json.dumps(data, indent=2).encode(), "application/json",
                    cache_control="public, max-age=3600")
    _invalidate_file_cache(sid, "dribbble.json")
    with _lock:
        sessions[sid]["has_dribbble"] = True
    _save_audit_meta(sid)
    return jsonify(data)


@app.route("/api/audits/<sid>/upload-redesign", methods=["POST"])
@auth_required
def upload_redesign(sid):
    """Accept an HTML redesign file, upload to Supabase Storage, return shareable URL."""
    try:
        sb.table("audits").select("sid").eq("sid", sid).single().execute()
    except Exception:
        return jsonify({"error": "Audit not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename.lower().endswith(".html"):
        return jsonify({"error": "Only .html files are accepted"}), 400

    html_bytes = uploaded.read()
    _storage_upload(sid, "redesign.html", html_bytes, "text/html")

    with _lock:
        if sid in sessions:
            sessions[sid]["has_redesign"] = True
    _save_audit_meta(sid)
    return jsonify({"ok": True, "redesign_url": f"/audits/{sid}/redesign-view"})


@app.route("/api/audits/<sid>/redesign", methods=["DELETE"])
@auth_required
def delete_redesign(sid):
    """Delete the redesign HTML file for an audit."""
    try:
        sb.storage.from_(STORAGE_BUCKET).remove([f"{sid}/redesign.html"])
        with _lock:
            if sid in sessions:
                sessions[sid]["has_redesign"] = False
        sb.table("audits").update({"has_redesign": False}).eq("sid", sid).execute()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/audits/<sid>/redesign-view")
def view_redesign(sid):
    """Redirect to a CDN-served signed URL — browser fetches directly, no Railway proxy."""
    url = _storage_signed_url(sid, "redesign.html", expires=3600)
    if url:
        return redirect(url, code=302)
    # Fallback: proxy it (e.g. signed URL generation failed)
    data = _storage_download(sid, "redesign.html")
    if not data:
        return "Redesign not found", 404
    return Response(data, mimetype="text/html", headers={"Content-Disposition": "inline"})


@app.route("/audits/<sid>/report-view")
def view_report(sid):
    """Serve the HTML report — try local disk first, then Supabase Storage."""
    # Try local disk FIRST (most reliable for local dev)
    local_path = os.path.join(AUDITS_DIR, sid, "report.html")
    if os.path.isfile(local_path):
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            print(f"[view_report] Serving from local disk: {local_path}")
            return Response(data, mimetype="text/html; charset=utf-8", 
                          headers={"Content-Disposition": "inline"})
        except Exception as exc:
            print(f"[view_report] Local read failed: {exc}")
    
    # Fallback: Try Supabase Storage download (not just signed URL)
    data = _storage_download(sid, "report.html")
    if data:
        print(f"[view_report] Serving from Supabase download")
        return Response(data, mimetype="text/html; charset=utf-8", 
                       headers={"Content-Disposition": "inline"})
    
    # Last resort: signed URL redirect
    url = _storage_signed_url(sid, "report.html", expires=3600)
    if url:
        print(f"[view_report] Redirecting to signed URL")
        return redirect(url, code=302)
    
    return "Report not found", 404


@app.route("/api/audits/<sid>/url", methods=["DELETE"])
@auth_required
def delete_url(sid):
    """Remove the website URL from an audit."""
    try:
        with _lock:
            if sid in sessions:
                sessions[sid]["website_url"] = ""
                sessions[sid]["website_context"] = ""
        sb.table("audits").update({"website_url": ""}).eq("sid", sid).execute()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/audits/<sid>/report")
@auth_required
def serve_report(sid):
    """Serve the HTML report file directly."""
    raw = _storage_download(sid, "report.html")
    if not raw:
        # Try building it on the fly from in-memory session
        if sid in sessions and sessions[sid].get("analysis"):
            s = sessions[sid]
            ann_b64 = s.get("annotated_b64") or s.get("image_b64", "")
            ann_type = s.get("ann_type", s.get("media_type", "image/jpeg"))
            html = _build_report(s["analysis"], ann_b64, ann_type)
        else:
            return jsonify({"error": "Report not found"}), 404
    else:
        html = raw.decode("utf-8")
    slug = re.sub(r"[^\w\-]", "_", sessions.get(sid, {}).get("analysis", {}).get("screen_name", "screen").lower())
    return Response(html, mimetype="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ux_audit_{slug}.html"'})


# ─── Image annotation ─────────────────────────────────────────────────────────

def annotate_image(image_b64, media_type, issues):
    """Draw numbered severity-coloured markers on the screenshot."""
    if not PIL_AVAILABLE or not issues:
        return image_b64, media_type
    try:
        img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        SEV = {
            "High":   (220, 38,  38),
            "Medium": (217, 119,  6),
            "Low":    (107, 114, 128),
        }

        r         = max(22, min(w, h) // 32)
        font_size = max(14, r - 6)
        font      = _load_font(font_size)

        for iss in issues:
            ann = iss.get("annotation")
            if not ann:
                continue
            color = SEV.get(iss.get("severity", "Low"), SEV["Low"])
            cx = int(w * max(0, min(100, ann.get("x", 50))) / 100)
            cy = int(h * max(0, min(100, ann.get("y", 50))) / 100)
            cx = max(r + 2, min(w - r - 2, cx))
            cy = max(r + 2, min(h - r - 2, cy))

            aw, ah = ann.get("w", 0), ann.get("h", 0)
            if aw > 0 and ah > 0:
                rw, rh = int(w * aw / 100), int(h * ah / 100)
                rx1, ry1 = max(0, cx - rw // 2), max(0, cy - rh // 2)
                rx2, ry2 = min(w, cx + rw // 2), min(h, cy + rh // 2)
                draw.rectangle(
                    [rx1, ry1, rx2, ry2],
                    fill=color + (28,),
                    outline=color + (180,),
                    width=max(2, r // 10),
                )

            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=color + (225,),
                outline=(255, 255, 255, 220),
                width=max(2, r // 9),
            )
            label = str(iss.get("id", "?"))
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                tw, th = font.getsize(label)
            draw.text((cx - tw // 2, cy - th // 2), label,
                      fill=(255, 255, 255, 255), font=font)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        out = io.BytesIO()
        result.save(out, format="JPEG", quality=85, optimize=True)
        out.seek(0)
        return base64.b64encode(out.read()).decode(), "image/jpeg"
    except Exception as exc:
        print(f"[annotate_image] {exc}")
        return image_b64, media_type


def _load_font(size):
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


# ─── Redesign prompt builder ───────────────────────────────────────────────────

def _build_redesign_prompt(analysis):
    screen_name  = analysis.get("screen_name", "Screen")
    score        = analysis.get("overall_score", 0)
    score_label  = analysis.get("score_label", "")
    a_score      = analysis.get("accessibility_score", "N/A")
    summary      = analysis.get("summary", "")
    issues       = analysis.get("issues", [])

    h = sum(1 for i in issues if i.get("severity") == "High")
    m = sum(1 for i in issues if i.get("severity") == "Medium")
    l = sum(1 for i in issues if i.get("severity") == "Low")

    high_issues   = [i for i in issues if i.get("severity") == "High"]
    medium_issues = [i for i in issues if i.get("severity") == "Medium"]
    low_issues    = [i for i in issues if i.get("severity") == "Low"]

    lines = [
        "You are a senior UI/UX designer and expert frontend developer.",
        "",
        "I am giving you a screenshot of a UI screen and a detailed UX audit report.",
        "Your task is to produce a complete, self-contained HTML redesign (version 2)",
        "that resolves every issue in the audit while preserving the original visual identity.",
        "",
        "CRITICAL RULE — READ BEFORE ANYTHING ELSE:",
        "Fixing an issue takes absolute priority over preserving layout or placement.",
        "If a fix requires moving an element, restructuring a section, hiding a component,",
        "or changing how content is presented — DO IT. The audit findings are non-negotiable.",
        "Preservation means keeping the brand identity (colors, typography, component style).",
        "It does NOT mean keeping broken elements in the same broken position.",
        "",
        "=" * 68,
        "MANDATORY FIX CHECKLIST  —  VERIFY EACH BEFORE WRITING A SINGLE LINE OF HTML",
        "=" * 68,
        "",
        "Before you write the HTML, mentally confirm that your design addresses EVERY item",
        "in this list. If your HTML does not contain a concrete, visible solution for a",
        "High or Medium issue, your response is incomplete — revise it until it does.",
        "Some fixes require structural changes (relocating, collapsing, or restructuring",
        "UI elements). Make those structural changes — do not style over them.",
        "",
    ]

    if high_issues:
        lines.append("HIGH PRIORITY  (must be resolved — zero exceptions):")
        lines.append("  NOTE: 'fixing' means the issue is GONE from the redesign — not styled differently.")
        lines.append("  If the fix says to move, collapse, or restructure something, do exactly that.")
        lines.append("")
        for iss in high_issues:
            lines.append(f"  [{iss.get('id','?')}] {iss.get('title','')}")
            lines.append(f"       Problem:          {iss.get('problem','')}")
            lines.append(f"       What to implement: {iss.get('recommendation','')}")
            lines.append(f"       Affects:          {iss.get('location','')}")
            if iss.get("wcag_criterion"):
                lines.append(f"       WCAG:             {iss['wcag_criterion']} Level {iss.get('wcag_level','')}")
            lines.append("")

    if medium_issues:
        lines.append("MEDIUM PRIORITY  (must be resolved — no exceptions):")
        lines.append("  NOTE: Same rule — fix means the issue does not exist in the output HTML.")
        lines.append("")
        for iss in medium_issues:
            lines.append(f"  [{iss.get('id','?')}] {iss.get('title','')}")
            lines.append(f"       Problem:          {iss.get('problem','')}")
            lines.append(f"       What to implement: {iss.get('recommendation','')}")
            lines.append(f"       Affects:          {iss.get('location','')}")
            if iss.get("wcag_criterion"):
                lines.append(f"       WCAG:             {iss['wcag_criterion']} Level {iss.get('wcag_level','')}")
            lines.append("")

    if low_issues:
        lines.append("LOW PRIORITY  (implement where possible):")
        for iss in low_issues:
            lines.append(f"  [{iss.get('id','?')}] {iss.get('title','')} — {iss.get('recommendation','')}")
        lines.append("")

    lines += [
        "=" * 68,
        "STEP 1 — LAYOUT & COMPOSITION  (reason through this BEFORE anything else)",
        "=" * 68,
        "",
        "Layout and content distribution are non-negotiable design decisions.",
        "Do not assume the original layout is correct — reason from first principles.",
        "Ask yourself: does each element sit in the right zone for its purpose?",
        "If not, move it. The composition must serve the user's primary goal.",
        "",
        "1. VISUAL HIERARCHY",
        "   The most important action or information must be visually dominant.",
        "   Use size, weight, contrast, and position to establish a clear reading order.",
        "   Secondary content must be visually subordinate — smaller, lighter, lower.",
        "   (Malewicz — Designing User Interfaces: contrast creates hierarchy)",
        "   (Refactoring UI: use size and weight to communicate importance, not just color)",
        "",
        "2. F-PATTERN & READING FLOW",
        "   Users scan left-to-right, top-to-bottom in an F-shape on content-heavy screens.",
        "   Place primary actions and key labels at the start of scan lines.",
        "   Never interrupt the scan path with secondary, promotional, or personalisation content.",
        "   (Nielsen Norman Group — F-Pattern reading behavior)",
        "",
        "3. PROXIMITY & GROUPING (Gestalt)",
        "   Related elements must be spatially close. Unrelated elements need clear separation.",
        "   If two elements answer different user questions, they belong in different zones.",
        "   Never mix contextual content with navigational content in the same region.",
        "   (Psych 101 — Gestalt: Law of Proximity, Law of Similarity)",
        "",
        "4. CONTENT PRIORITISATION",
        "   Identify the user's single primary goal on this screen.",
        "   Every element that does not serve that goal directly must be secondary in",
        "   visual weight and position. Upsell, personalisation, and promotional content",
        "   must never compete with or interrupt the primary task flow.",
        "   (Don't Make Me Think — Krug: do not make users think about what to do next)",
        "   (Psychology of Design — Hick's Law: fewer competing choices = faster decisions)",
        "",
        "5. SPATIAL ZONES",
        "   Divide the screen into logical zones: navigation, primary content, secondary",
        "   context, actions. Each zone has exactly one job.",
        "   If an element is in the wrong zone, move it to the correct zone or defer it",
        "   to a modal or drawer. The layout must match the user's mental model of the task.",
        "   (Universal Principles of Design — Progressive Disclosure)",
        "",
        "6. SIGNAL-TO-NOISE",
        "   Every element must earn its place. If an element does not directly help the",
        "   user complete their current task, reduce its visual weight or remove it from",
        "   the primary viewport. Clutter is a UX failure, not a neutral default.",
        "   (Universal Principles of Design — Signal-to-Noise Ratio)",
        "",
        "COMPOSITION RULE: If the original layout violates these principles — with or",
        "without an explicit audit finding — correct it. Do not replicate bad composition",
        "because it existed in the screenshot. A version 2 must be compositionally sound.",
        "",
        "APPLY THESE COMPOSITION DECISIONS TO RESOLVE THE FOLLOWING AUDIT ISSUES:",
        "Every High and Medium issue in the MANDATORY FIX CHECKLIST above must map to a",
        "specific, visible structural decision in your layout. Before moving to Step 2,",
        "trace each issue to a layout zone, spacing decision, or hierarchy change.",
        "If the fix requires restructuring — restructure. If it requires removing an element",
        "from the primary viewport — remove it. Composition fixes are not optional.",
        "",
        "=" * 68,
        "STEP 2 — VISUAL IDENTITY  (preserve brand, not broken placement)",
        "=" * 68,
        "",
        "Once composition is decided, preserve these brand elements exactly:",
        "  - Colors: every background, text, brand, accent, and surface hex value",
        "  - Typography: font families, sizes, weights, line-heights, letter-spacing",
        "  - Spacing scale: the relative rhythm of padding/margin (not the positions)",
        "  - Shapes: border-radius, border styles, shadows, elevation",
        "  - Icons: style, weight, and size (placement may change if composition requires)",
        "  - Components: card designs, button styles, badge styles, input styles",
        "",
        "NOTE: Layout and element positioning are governed by Step 1, not this list.",
        "Preserving the brand does NOT mean preserving where broken things sit.",
        "The output must feel like a version 2 — same brand, better UX.",
        "",
        "=" * 68,
        f"FULL AUDIT REPORT  —  {screen_name}",
        "=" * 68,
        f"Overall Score:        {score}/10  —  {score_label}",
        f"Accessibility Score:  {a_score}/10  (WCAG 2.2 AA)",
        f"Issues Found:         {len(issues)}  ({h} High · {m} Medium · {l} Low)",
        "",
        "EXECUTIVE SUMMARY",
        summary,
        "",
        "ALL ISSUES  (full detail for reference):",
        "",
    ]

    for iss in issues:
        sev   = iss.get("severity", "")
        lines.append(f"[{iss.get('id','??')}] {sev.upper()}  —  {iss.get('title','')}")
        lines.append(f"     Location:  {iss.get('location','')}")
        lines.append(f"     Problem:   {iss.get('problem','')}")
        lines.append(f"     Fix:       {iss.get('recommendation','')}")
        if iss.get("reference"):
            lines.append(f"     Source:    {iss['reference']}")
        if iss.get("wcag_criterion"):
            lines.append(f"     WCAG:      {iss['wcag_criterion']}  Level {iss.get('wcag_level','')}")
        lines.append("")

    lines += [
        "=" * 68,
        "SELF-CHECK — RUN THIS BEFORE OUTPUTTING THE HTML",
        "=" * 68,
        "",
        "For each item below, verify the SPECIFIC FIX is concretely implemented —",
        "not just acknowledged, not just styled differently. The fix must be visible.",
        "",
    ]
    for iss in high_issues + medium_issues:
        lines.append(f"  [ ] [{iss.get('id','?')}] {iss.get('title','')}")
        lines.append(f"       Required fix: {iss.get('recommendation','')}")
        lines.append(f"       Location:     {iss.get('location','')}")
        lines.append(f"       Is this fix structurally present and visible in the HTML? (yes/no — if no, revise)")
        lines.append("")
    lines += [
        "If any checkbox above cannot be ticked YES, revise your HTML before outputting it.",
        "",
        "=" * 68,
        "OUTPUT REQUIREMENTS",
        "=" * 68,
        "",
        "- Output a single, complete, self-contained HTML file.",
        "- All CSS must be in a <style> block in the <head> — no external stylesheets.",
        "- No CDN links, no JavaScript frameworks, no external images.",
        "  Use inline SVG for icons. Use data URIs only if absolutely necessary.",
        "- Preserve all informational content (text, labels, data). Do not silently drop",
        "  information the user needs. However: if a fix requires relocating, collapsing,",
        "  or restructuring a UI element, you MUST do so — placing it in a better position",
        "  is not removing it. The audit fix always wins over original placement.",
        "- Do NOT add new features, sections, or content not present in the original.",
        "- JavaScript is allowed only for interactions clearly present in the original.",
        "  Keep it minimal and inline.",
        "- The file must open in a browser as a fully working static page.",
        "- Start your response with <!DOCTYPE html> and end the HTML with </html>.",
        "- Do NOT reference Mobbin or any third-party design gallery. Use Saasfactor if needed.",
    ]

    return "\n".join(lines)


# ─── Report builder ───────────────────────────────────────────────────────────

_SEV_COLORS = {
    "High":   ("#FEE2E2", "#DC2626", "#DC2626"),
    "Medium": ("#FEF3C7", "#D97706", "#F59E0B"),
    "Low":    ("#F3F4F6", "#6B7280", "#9CA3AF"),
}

def _badge(sev):
    bg, fg, _ = _SEV_COLORS.get(sev, _SEV_COLORS["Low"])
    return (
        f'<span style="background:{bg};color:{fg};font-size:10px;font-weight:700;'
        f'letter-spacing:.06em;text-transform:uppercase;padding:3px 9px;border-radius:20px;">'
        f'{sev}</span>'
    )


def _wcag_badge(level):
    colors = {"A": ("#DBEAFE", "#1D4ED8"), "AA": ("#EDE9FE", "#6D28D9")}
    bg, fg = colors.get(level, ("#F3F4F6", "#6B7280"))
    return (
        f'<span style="background:{bg};color:{fg};font-size:9px;font-weight:800;'
        f'letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:20px;'
        f'margin-left:6px;">WCAG {level}</span>'
    )


def _build_report(analysis, image_b64, media_type):
    issues              = analysis.get("issues", [])
    score               = analysis.get("overall_score", 0)
    score_label         = analysis.get("score_label", "")
    accessibility_score = analysis.get("accessibility_score", None)
    screen_name         = analysis.get("screen_name", "Screen")
    summary             = analysis.get("summary", "")
    today               = datetime.utcnow().strftime("%B %d, %Y")

    h = sum(1 for i in issues if i.get("severity") == "High")
    m = sum(1 for i in issues if i.get("severity") == "Medium")
    l = sum(1 for i in issues if i.get("severity") == "Low")
    total_issues = max(1, len(issues))

    white_src = f"data:image/png;base64,{LOGO_WHITE_B64}" if LOGO_WHITE_B64 else ""
    img_src   = f"data:{media_type};base64,{image_b64}"

    logo_white_tag = (
        f'<img src="{white_src}" alt="Saasfactor" style="height:30px;display:block;">'
        if white_src else
        '<span style="color:#fff;font-weight:700;font-size:16px;">Saasfactor</span>'
    )

    circ = 238.76
    ring_target = circ * (1.0 - score / 10.0)
    score_ring_svg = (
        f'<svg width="90" height="90" viewBox="0 0 90 90" style="display:block;margin:0 auto 8px;">'
        f'<circle cx="45" cy="45" r="38" fill="none" stroke="#F3F4F6" stroke-width="7"/>'
        f'<circle cx="45" cy="45" r="38" fill="none" stroke="#F05023" stroke-width="7"'
        f' stroke-linecap="round" transform="rotate(-90 45 45)"'
        f' stroke-dasharray="{circ:.2f}" stroke-dashoffset="{circ:.2f}"'
        f' class="score-ring" data-target="{ring_target:.2f}"/>'
        f'<text x="45" y="43" text-anchor="middle" dominant-baseline="middle"'
        f' font-family="Inter,system-ui,sans-serif" font-size="17" font-weight="800"'
        f' fill="#1A1A1A" class="count-num" data-value="{score}" data-decimals="1">{score}</text>'
        f'<text x="45" y="57" text-anchor="middle" font-family="Inter,system-ui,sans-serif"'
        f' font-size="9" fill="#9CA3AF">/10</text>'
        f'</svg>'
    )

    sev_bar_section = (
        f'<div style="margin-top:20px;padding-top:20px;border-top:1px solid #F3F4F6;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
        f'color:#9CA3AF;margin-bottom:12px;">Severity Breakdown</div>'
        f'<div style="display:flex;flex-direction:column;gap:8px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="font-size:11px;font-weight:600;color:#DC2626;width:38px;">High</div>'
        f'<div style="flex:1;background:#FEE2E2;border-radius:4px;height:8px;overflow:hidden;">'
        f'<div class="sev-bar-fill" data-width="{h/total_issues*100:.1f}%"'
        f' style="height:8px;background:#DC2626;border-radius:4px;width:0;"></div></div>'
        f'<div style="font-size:12px;font-weight:700;color:#1A1A1A;width:14px;text-align:right;">{h}</div>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="font-size:11px;font-weight:600;color:#D97706;width:38px;">Med</div>'
        f'<div style="flex:1;background:#FEF3C7;border-radius:4px;height:8px;overflow:hidden;">'
        f'<div class="sev-bar-fill" data-width="{m/total_issues*100:.1f}%"'
        f' style="height:8px;background:#F59E0B;border-radius:4px;width:0;"></div></div>'
        f'<div style="font-size:12px;font-weight:700;color:#1A1A1A;width:14px;text-align:right;">{m}</div>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="font-size:11px;font-weight:600;color:#6B7280;width:38px;">Low</div>'
        f'<div style="flex:1;background:#F3F4F6;border-radius:4px;height:8px;overflow:hidden;">'
        f'<div class="sev-bar-fill" data-width="{l/total_issues*100:.1f}%"'
        f' style="height:8px;background:#9CA3AF;border-radius:4px;width:0;"></div></div>'
        f'<div style="font-size:12px;font-weight:700;color:#1A1A1A;width:14px;text-align:right;">{l}</div>'
        f'</div>'
        f'</div></div>'
    )

    sorted_issues = sorted(
        issues,
        key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x.get("severity", "Low"), 2),
    )

    glance_cards = ""
    for idx, iss in enumerate(sorted_issues):
        sev = iss.get("severity", "Low")
        _, _, border = _SEV_COLORS.get(sev, _SEV_COLORS["Low"])
        criterion = iss.get("wcag_criterion", "")
        wcag_mini = (
            f'<span style="background:#EDE9FE;color:#6D28D9;font-size:9px;font-weight:800;'
            f'padding:1px 6px;border-radius:20px;margin-left:5px;letter-spacing:.04em;">'
            f'WCAG {criterion}</span>'
        ) if criterion else ""
        delay = idx * 80
        glance_cards += (
            f'<div class="glance-card" style="background:#fff;border-radius:10px;padding:14px 16px;'
            f'border-top:3px solid {border};box-shadow:0 1px 3px rgba(0,0,0,.05);'
            f'transition-delay:{delay}ms;">'
            f'<div style="font-size:10px;font-weight:700;color:#9CA3AF;letter-spacing:.08em;'
            f'text-transform:uppercase;margin-bottom:6px;display:flex;align-items:center;">'
            f'{iss.get("id","--")}{wcag_mini}</div>'
            f'<div style="font-size:12px;font-weight:600;color:#1A1A1A;line-height:1.4;">'
            f'{iss.get("title","")}</div>'
            f'<div style="margin-top:8px;">{_badge(sev)}</div>'
            f'</div>'
        )

    detail_cards = ""
    for idx, iss in enumerate(issues):
        sev = iss.get("severity", "Low")
        _, _, border = _SEV_COLORS.get(sev, _SEV_COLORS["Low"])
        ref = iss.get("reference", "")
        criterion  = iss.get("wcag_criterion", "")
        wcag_level = iss.get("wcag_level", "")
        ref_html = (
            f'<div style="margin-top:14px;padding:10px 14px;background:#F8F9FA;border-radius:8px;'
            f'border-left:3px solid #E5E5E5;font-size:12px;color:#6B7280;">'
            f'<span style="font-weight:600;color:#4B5563;">Reference: </span>{ref}</div>'
        ) if ref else ""
        critical = iss.get("critical_reason", "")
        critical_html = (
            f'<div style="margin-top:8px;padding:8px 10px;background:#FFF7ED;border-radius:6px;'
            f'font-size:11px;color:#92400E;line-height:1.5;">'
            f'<span style="font-weight:700;letter-spacing:.02em;">Why critical: </span>{critical}</div>'
        ) if critical else ""
        wcag_tag = (
            f'<span style="background:#EDE9FE;color:#6D28D9;font-size:9px;font-weight:800;'
            f'letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:20px;'
            f'margin-left:6px;">WCAG {criterion} · {wcag_level}</span>'
        ) if criterion else ""
        delay = idx * 60
        detail_cards += (
            f'<div class="detail-card fade-section" style="background:#fff;border-radius:14px;overflow:hidden;'
            f'margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 0 0 1px rgba(0,0,0,.04);'
            f'transition-delay:{delay}ms;">'
            f'<div class="detail-header-inner" style="border-left:4px solid {border};padding:20px 24px;'
            f'display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">'
            f'<div>'
            f'<div style="font-size:11px;font-weight:700;color:#9CA3AF;letter-spacing:.1em;'
            f'text-transform:uppercase;margin-bottom:6px;display:flex;align-items:center;">'
            f'Issue {iss.get("id","")}{wcag_tag}</div>'
            f'<div style="font-size:17px;font-weight:700;color:#1A1A1A;">{iss.get("title","")}</div>'
            f'<div style="font-size:12px;color:#6B7280;margin-top:4px;">📍 {iss.get("location","")}</div>'
            f'</div>{_badge(sev)}</div>'
            f'<div class="detail-body" style="padding:0 24px 24px;">'
            f'<div class="prob-rec-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:4px;">'
            f'<div style="background:#FFF8F6;border-radius:10px;padding:16px;">'
            f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:.08em;color:#F05023;margin-bottom:8px;">The Problem</div>'
            f'<div style="font-size:13px;color:#374151;line-height:1.6;">{iss.get("problem","")}</div>'
            f'{critical_html}'
            f'</div>'
            f'<div style="background:#F0FDF4;border-radius:10px;padding:16px;">'
            f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:.08em;color:#16A34A;margin-bottom:8px;">Recommendation</div>'
            f'<div style="font-size:13px;color:#374151;line-height:1.6;">{iss.get("recommendation","")}</div>'
            f'</div></div>'
            f'{ref_html}'
            f'</div></div>'
        )

    a_score_stat = ""
    if accessibility_score is not None:
        a_circ   = 238.76
        a_target = a_circ * (1.0 - accessibility_score / 10.0)
        a_score_stat = (
            f'<div style="text-align:center;padding-top:16px;margin-top:16px;border-top:1px solid #F3F4F6;">'
            f'<svg width="70" height="70" viewBox="0 0 90 90" style="display:block;margin:0 auto 6px;">'
            f'<circle cx="45" cy="45" r="38" fill="none" stroke="#EDE9FE" stroke-width="7"/>'
            f'<circle cx="45" cy="45" r="38" fill="none" stroke="#7C3AED" stroke-width="7"'
            f' stroke-linecap="round" transform="rotate(-90 45 45)"'
            f' stroke-dasharray="{a_circ:.2f}" stroke-dashoffset="{a_circ:.2f}"'
            f' class="score-ring" data-target="{a_target:.2f}"/>'
            f'<text x="45" y="43" text-anchor="middle" dominant-baseline="middle"'
            f' font-family="Inter,system-ui,sans-serif" font-size="17" font-weight="800"'
            f' fill="#1A1A1A" class="count-num" data-value="{accessibility_score}" data-decimals="1">{accessibility_score}</text>'
            f'<text x="45" y="57" text-anchor="middle" font-family="Inter,system-ui,sans-serif"'
            f' font-size="9" fill="#9CA3AF">/10</text>'
            f'</svg>'
            f'<div style="font-size:11px;font-weight:700;color:#6D28D9;">Accessibility</div>'
            f'<div style="font-size:10px;color:#9CA3AF;margin-top:1px;">WCAG 2.2 AA</div>'
            f'</div>'
        )

    book_cards = [
        ("Don't Make Me Think",                        "Steve Krug",                   "Usability & web UX fundamentals"),
        ("Designing User Interfaces",                  "Dmytro Malewicz (2021)",        "UI components, layouts & visual design"),
        ("Refactoring UI",                             "Adam Wathan & Steve Schoger",   "Practical UI design decisions"),
        ("Practical UI",                               "",                              "Hands-on interface design techniques"),
        ("Psychology of Design: 106 Cognitive Biases", "",                             "Cognitive biases that affect UX decisions"),
        ("Psych 101",                                  "Paul Kleinman",                 "Psychological principles behind behaviour"),
        ("UI Design Tips",                             "",                              "Quick-reference design improvement patterns"),
        ("WCAG 2.2",                                   "W3C Web Accessibility Initiative", "Accessibility guidelines — Level A & AA compliance"),
        ("Universal Principles of Design",             "Lidwell, Holden & Butler",         "200 cross-disciplinary design principles"),
        ("The Design of Everyday Things",              "Don Norman",                       "Affordances, signifiers, feedback, mappings"),
    ]
    book_card_html = ""
    for title, author, desc in book_cards:
        by_line = f"<div style='font-size:11px;color:#9CA3AF;margin-bottom:2px;'>{author}</div>" if author else ""
        book_card_html += (
            f'<div style="padding:12px 14px;background:#F9FAFB;border-radius:8px;">'
            f'<div style="font-size:12px;font-weight:600;color:#1A1A1A;margin-bottom:2px;">{title}</div>'
            f'{by_line}'
            f'<div style="font-size:11px;color:#6B7280;">{desc}</div>'
            f'</div>'
        )

    sources_section = (
        '<div class="fade-section" style="background:#fff;border-radius:14px;padding:28px 32px;margin-bottom:20px;'
        'box-shadow:0 1px 3px rgba(0,0,0,.05),0 0 0 1px rgba(0,0,0,.04);">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;'
        'color:#9CA3AF;margin-bottom:16px;">Sources &amp; Methodology</div>'
        '<div style="font-size:13px;color:#4B5563;line-height:1.7;margin-bottom:16px;">'
        'This audit is grounded in the Saasfactor UX training curriculum. Each finding is '
        'mapped to a specific principle, chapter, or concept from the following books:'
        '</div>'
        f'<div class="sources-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">{book_card_html}</div>'
        '</div>'
    )

    REPORT_CSS = (
        "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:'Inter',system-ui,sans-serif;background:#F5F5F7;"
        "color:#1A1A1A;font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;}"
        ".page{max-width:860px;margin:0 auto;padding:32px 24px;}"
        ".fade-section{opacity:0;transform:translateY(18px);"
        "transition:opacity .55s ease,transform .55s ease;pointer-events:none;}"
        ".fade-section.visible{opacity:1;transform:translateY(0);pointer-events:auto;}"
        ".glance-card{opacity:0;transform:translateY(12px);"
        "transition:opacity .4s ease,transform .4s ease,box-shadow .25s ease;pointer-events:none;}"
        ".glance-card.visible{opacity:1;transform:translateY(0);pointer-events:auto;}"
        ".glance-card.visible:hover{box-shadow:0 6px 18px rgba(0,0,0,.11)!important;"
        "transform:translateY(-3px)!important;}"
        ".detail-card.visible{transition:opacity .55s ease,transform .55s ease,box-shadow .2s ease;}"
        ".detail-card.visible:hover{box-shadow:0 6px 20px rgba(0,0,0,.10)!important;transform:translateY(-2px);}"
        ".score-ring{transition:stroke-dashoffset 1.4s cubic-bezier(.4,0,.2,1);}"
        ".sev-bar-fill{transition:width 1s ease;}"
        "@media(max-width:640px){"
        ".page{padding:20px 14px;}"
        ".cover-section{padding:32px 20px 28px!important;}"
        ".cover-title{font-size:26px!important;line-height:1.2!important;}"
        ".cover-hdr{margin-bottom:28px!important;}"
        ".overview-card{padding:20px 16px!important;}"
        ".ov-grid{grid-template-columns:1fr 1fr!important;gap:16px!important;}"
        ".ov-col{border-right:none!important;border-bottom:none!important;padding:0!important;}"
        ".glance-grid{grid-template-columns:repeat(2,1fr)!important;}"
        ".prob-rec-grid{grid-template-columns:1fr!important;}"
        ".sources-grid{grid-template-columns:1fr!important;}"
        ".detail-header{flex-wrap:wrap!important;gap:8px!important;}"
        ".detail-body{padding:0 16px 20px!important;}"
        ".detail-header-inner{padding:16px!important;}"
        ".dark-cta{padding:40px 20px!important;}"
        "}"
    )

    REPORT_JS = (
        "<script>"
        "(function(){"
        "var obs=new IntersectionObserver(function(entries){"
        "entries.forEach(function(e){"
        "if(e.isIntersecting){e.target.classList.add('visible');obs.unobserve(e.target);}"
        "});},{threshold:0.08});"
        "document.querySelectorAll('.fade-section,.glance-card').forEach(function(el){"
        "obs.observe(el);});"
        "function animCount(el,target,isDec,dur){"
        "var s=performance.now();"
        "function tick(n){"
        "var p=Math.min((n-s)/dur,1);"
        "var ease=p<.5?2*p*p:(4-2*p)*p-1;"
        "el.textContent=isDec?(target*ease).toFixed(1):Math.round(target*ease);"
        "if(p<1)requestAnimationFrame(tick);}"
        "requestAnimationFrame(tick);}"
        "function animRing(){"
        "document.querySelectorAll('.score-ring').forEach(function(r){"
        "r.style.strokeDashoffset=parseFloat(r.dataset.target);});}"
        "function animCounts(){"
        "document.querySelectorAll('.count-num').forEach(function(el){"
        "animCount(el,parseFloat(el.dataset.value)||0,el.dataset.decimals==='1',1200);});}"
        "function animBars(){"
        "document.querySelectorAll('.sev-bar-fill').forEach(function(el){"
        "el.style.width=el.dataset.width;});}"
        "function resetDelays(){"
        "document.querySelectorAll('.glance-card').forEach(function(el){"
        "el.style.transitionDelay='0ms';});}"
        "window.addEventListener('load',function(){"
        "setTimeout(animRing,150);"
        "setTimeout(animCounts,150);"
        "setTimeout(animBars,300);"
        "setTimeout(resetDelays,1200);"
        "});"
        "})();"
        "</script>"
    )

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        '<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>'
        f"<title>UX Audit — {screen_name} · Saasfactor</title>"
        '<link rel="preconnect" href="https://fonts.googleapis.com"/>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>'
        f"<style>{REPORT_CSS}</style></head><body>"

        f'<div class="cover-section" style="background:#0D0D0D;position:relative;overflow:hidden;padding:56px 48px 52px;">'
        '<div style="position:absolute;inset:0;background:'
        'radial-gradient(ellipse 55% 65% at 92% 5%,rgba(240,80,35,.26) 0%,transparent 58%),'
        'radial-gradient(ellipse 38% 45% at 5% 90%,rgba(240,80,35,.12) 0%,transparent 55%);"></div>'
        '<div style="position:absolute;inset:0;background-image:'
        'linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),'
        'linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:52px 52px;"></div>'
        '<div style="max-width:860px;margin:0 auto;position:relative;z-index:1;">'
        f'<div class="cover-hdr" style="display:flex;justify-content:flex-end;align-items:flex-start;margin-bottom:48px;">{logo_white_tag}</div>'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#F05023;margin-bottom:16px;">UX Audit Report</div>'
        f'<h1 class="cover-title" style="font-size:42px;font-weight:800;color:#fff;line-height:1.1;letter-spacing:-.02em;margin-bottom:8px;">{screen_name}</h1>'
        f'<div style="color:#9CA3AF;font-size:14px;margin-top:16px;">{today} · Admin</div>'
        '</div></div>'

        '<div class="page">'

        '<div class="fade-section overview-card" style="background:#fff;border-radius:14px;padding:32px;margin-bottom:20px;'
        'box-shadow:0 1px 3px rgba(0,0,0,.05),0 0 0 1px rgba(0,0,0,.04);">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF;margin-bottom:24px;">Audit Overview</div>'
        '<div class="ov-grid" style="display:grid;grid-template-columns:auto 1fr 1fr 1fr;gap:0;align-items:start;">'
        '<div class="ov-col" style="padding-right:28px;border-right:1px solid #F3F4F6;display:flex;flex-direction:column;align-items:center;">'
        f'{score_ring_svg}'
        '<div style="font-size:10px;color:#9CA3AF;font-weight:500;text-align:center;">Overall Score</div>'
        f'<div style="font-size:11px;font-weight:600;color:#6B7280;margin-top:2px;text-align:center;">{score_label}</div>'
        '</div>'
        '<div class="ov-col" style="padding:0 24px;border-right:1px solid #F3F4F6;">'
        '<div style="font-size:11px;color:#9CA3AF;font-weight:500;margin-bottom:8px;">Issues Found</div>'
        f'<div style="font-size:28px;font-weight:800;color:#1A1A1A;" class="count-num" data-value="{len(issues)}">{len(issues)}</div>'
        f'<div style="font-size:12px;color:#6B7280;margin-top:2px;">{h}H · {m}M · {l}L</div>'
        f'{sev_bar_section}'
        '</div>'
        '<div class="ov-col" style="padding:0 24px;border-right:1px solid #F3F4F6;">'
        '<div style="font-size:11px;color:#9CA3AF;font-weight:500;margin-bottom:8px;">Screen Audited</div>'
        f'<div style="font-size:15px;font-weight:700;color:#1A1A1A;line-height:1.3;">{screen_name}</div></div>'
        '<div class="ov-col" style="padding-left:24px;">'
        '<div style="font-size:11px;color:#9CA3AF;font-weight:500;margin-bottom:8px;">Audited By</div>'
        '<div style="font-size:13px;font-weight:600;color:#1A1A1A;">Saasfactor Admin</div>'
        f'{a_score_stat}'
        '</div>'
        '</div>'
        f'<div style="margin-top:24px;padding-top:24px;border-top:1px solid #F3F4F6;font-size:14px;color:#4B5563;line-height:1.7;">{summary}</div>'
        '</div>'

        '<div style="margin-bottom:20px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF;margin-bottom:14px;">Issues at a Glance</div>'
        f'<div class="glance-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">{glance_cards}</div>'
        '</div>'

        '<div class="fade-section" style="background:#fff;border-radius:14px;overflow:hidden;margin-bottom:20px;'
        'box-shadow:0 1px 3px rgba(0,0,0,.05),0 0 0 1px rgba(0,0,0,.04);">'
        '<div style="padding:20px 24px 16px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF;margin-bottom:4px;">Annotated Screen</div>'
        f'<div style="font-size:15px;font-weight:600;color:#1A1A1A;">{screen_name}</div>'
        '<div style="font-size:12px;color:#9CA3AF;margin-top:2px;">Numbered markers correspond to the issues below</div>'
        '</div>'
        f'<img src="{img_src}" alt="{screen_name}" style="width:100%;display:block;"/>'
        '</div>'

        '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF;margin-bottom:14px;">Detailed Findings</div>'
        f'{detail_cards}'

        f'{sources_section}'

        '</div>'

        '<div class="dark-cta" style="background:#0D0D0D;position:relative;overflow:hidden;padding:52px 48px;text-align:center;">'
        '<div style="position:absolute;inset:0;background:'
        'radial-gradient(ellipse 55% 65% at 92% 5%,rgba(240,80,35,.18) 0%,transparent 58%),'
        'radial-gradient(ellipse 38% 45% at 5% 90%,rgba(240,80,35,.10) 0%,transparent 55%);"></div>'
        '<div style="position:absolute;inset:0;background-image:'
        'linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),'
        'linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:52px 52px;"></div>'
        '<div style="position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:14px;">'
        f'{logo_white_tag}'
        '<div style="color:#9CA3AF;font-size:13px;max-width:380px;line-height:1.6;">Internal admin audit — Saasfactor</div>'
        '</div></div>'

        f'{REPORT_JS}'
        "</body></html>"
    )


# ─── Local file serving route ─────────────────────────────────────────────────

@app.route("/api/local-file/<sid>/<path:filename>")
def serve_local_file(sid, filename):
    """Serve files directly from local storage."""
    # Security: prevent directory traversal
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "Invalid filename"}), 400
    
    filepath = os.path.join(LOCAL_STORAGE_DIR, sid, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    
    # Determine MIME type
    if filename.endswith('.jpg') or filename.endswith('.jpeg'):
        mime = 'image/jpeg'
    elif filename.endswith('.png'):
        mime = 'image/png'
    elif filename.endswith('.json'):
        mime = 'application/json'
    elif filename.endswith('.html'):
        mime = 'text/html'
    elif filename.endswith('.txt'):
        mime = 'text/plain'
    else:
        mime = 'application/octet-stream'
    
    return send_file(filepath, mimetype=mime)


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Saasfactor UX Audit — Admin Tool")
    print(f"  Open → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
