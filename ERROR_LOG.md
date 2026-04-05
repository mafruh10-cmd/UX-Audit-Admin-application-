# UX Audit Admin — Error Log

Tracks all errors reported and their resolutions. Updated every time a new error is fixed.

---

## [2026-03-28] Invalid \escape in JSON parse

**Error:**
```
Could not parse analysis: Invalid \escape: line 27 column 235 (char 2665)
```

**Cause:**
Claude's audit response sometimes includes raw backslashes inside JSON strings (e.g. `\s`, `\p`, `\e` from CSS selectors or file paths in issue descriptions). These are not valid JSON escape sequences and cause `json.loads()` to throw.

**Resolution:**
Added `_fix_json_escapes(text)` helper in `app.py` (near top, after `AUDITS_DIR` block). It scans the raw JSON string character by character and doubles any backslash not followed by a valid JSON escape character (`" \ / b f n r t u`). Applied in:
- Primary parse: `json.loads(_fix_json_escapes(text))`
- Truncation-recovery fallback: `json.loads(_fix_json_escapes(fixed))`

**Commit:** `5e89c85`

---

## [2026-04-05] Thumbnails 404 + Detail view "No issues data available"

**Symptoms:**
- All audit card thumbnails showing as broken images (404)
- Detail view showed score/badges (from DB) but "No issues data available" (no `analysis`)
- Affected both localhost and Railway after server restart

**Cause (two combined issues):**
1. `supabase>=2.0.0` (unpinned) — `run.sh` runs `pip install` on every start, which upgraded supabase-py to 2.28.3. The newer version raises a `StorageApiError` exception for 404s in `create_signed_url` instead of returning an error dict. The code caught these silently but returned `""`, so all thumbnails fell through to 404.
2. Concurrent thumbnail requests on page load (22 audits × 3 Storage calls each = up to 66 simultaneous HTTP requests) caused `[Errno 35] Resource temporarily unavailable` (macOS EAGAIN / socket buffer exhaustion).
3. On Railway specifically: `_storage_download` used supabase-py's `download()` method which failed in the Railway environment (httpx/TLS difference vs localhost), while `create_signed_url` worked fine.

**Resolution:**
- `requirements.txt`: Pinned `supabase==2.28.3` to prevent silent upgrades
- `_storage_signed_url`: Added in-memory cache with 50-min TTL — eliminates the concurrent request flood on page load
- `_storage_signed_url`: Suppressed noisy 404 log lines for missing files (expected for pre-migration audits)
- `audit_thumb`: Added 3-tier fallback: Storage signed URL → local disk → in-memory session
- `_storage_download`: Replaced supabase-py `download()` with signed URL + `urllib.urlopen()` (same mechanism proven to work); kept `download()` as secondary fallback
- `get_audit_detail`: Added `_load_file()` helper with Storage + local disk fallback for `audit_data.json`, scripts, and `dribbble.json`

**Commits:** `a0b7591`, `77ebdf6`

---

## [2026-03-28] API Error 500 — Internal Server Error

**Error:**
```
API Error: 500 {"type":"error","error":{"type":"api_error","message":"Internal server error"},"request_id":"req_011CZVdhuaZSTqbHmszTnoTj"}
```

**Cause:**
Model slug in code was `anthropic/claude-sonnet-4-6` (dash between 4 and 6). OpenRouter requires dot notation: `anthropic/claude-sonnet-4.5`. The invalid model name caused OpenRouter to return a 500 instead of a 404. Secondary issue: retry logic only caught `502`, `529`, `overload` — a `500` hit the `else: raise` path immediately with no retry.

**Resolution:**
- Changed all three `model=` references from `anthropic/claude-sonnet-4-6` to `anthropic/claude-sonnet-4.5`
- Added `"500"` and `"internal server"` to the retry condition string list
- Enabled extended thinking on main audit call: `budget_tokens=8000`, `max_tokens=12000`, `timeout=150`

**Commit:** `4a410f8`

---
