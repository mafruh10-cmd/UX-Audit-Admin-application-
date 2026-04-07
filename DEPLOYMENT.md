# 🚀 Deployment Guide - UX Audit Admin

## Railway + Supabase Deployment

---

## Step 1: Supabase Configuration

### 1.1 Database Setup
1. Go to https://supabase.com/dashboard
2. Select your project (or create new)
3. Go to **Database** → **Tables**
4. Ensure `audits` table exists with these columns:
   - `sid` (text, primary key)
   - `date` (timestamptz)
   - `product_name` (text)
   - `screen_name` (text)
   - `overall_score` (float)
   - `score_label` (text)
   - `accessibility_score` (float)
   - `filename` (text)
   - `website_url` (text)
   - `high` (int)
   - `medium` (int)
   - `low` (int)
   - `total_issues` (int)
   - `has_script` (boolean)
   - `has_dribbble` (boolean)
   - `has_redesign` (boolean)
   - `status` (text)
   - `model_label` (text)
   - `created_by` (text)

### 1.2 Storage Setup
1. Go to **Storage** → **New Bucket**
2. Create bucket named: `ux-audits`
3. Set **Public** to: `false` (private bucket)
4. Go to **Policies** → **New Policy**
5. Add policy for `service_role`:
   - Allow all operations for service_role

### 1.3 Get API Keys
1. Go to **Project Settings** → **API**
2. Copy:
   - `URL` (e.g., `https://xxxxx.supabase.co`)
   - `service_role` secret (NOT the anon key)

---

## Step 2: Railway Deployment

### 2.1 Create Railway Account
1. Go to https://railway.app
2. Sign up/login with GitHub

### 2.2 Deploy from GitHub
1. Click **New Project**
2. Select **Deploy from GitHub repo**
3. Choose your `UX-Audit-Admin-application-` repository
4. Railway will auto-detect Python and deploy

### 2.3 Environment Variables
Add these in Railway Dashboard → Variables:

```
ANTHROPIC_API_KEY=sk-or-v1-xxxxxxxx
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_URL=https://xxxxx.supabase.co
ENVIRONMENT=production
PORT=5001
```

### 2.4 Custom Domain (Optional)
1. Go to **Settings** → **Domains**
2. Click **Custom Domain**
3. Add your domain

---

## Step 3: Post-Deployment Checks

### 3.1 Health Check
```bash
curl https://your-railway-url.up.railway.app/api/health
# Should return: {"ok":true}
```

### 3.2 Test Authentication
1. Open the app in browser
2. Login with Supabase credentials
3. Check browser console for errors

### 3.3 Test Audit Flow
1. Upload a screenshot
2. Verify audit generates
3. Check Supabase Storage for files
4. Verify DB entries in `audits` table

---

## Potential Issues & Fixes

### Issue 1: Supabase Storage 403 Error
**Symptom:** `new row violates row-level security policy`
**Fix:** Ensure bucket policy allows service_role access

### Issue 2: OpenRouter API 401 Error
**Symptom:** `User not found` or 401 errors
**Fix:** 
- Verify OpenRouter API key is valid
- Check key has credits at https://openrouter.ai/settings/credits

### Issue 3: Database Connection Timeout
**Symptom:** Slow page loads, 504 errors
**Fix:** 
- Check Supabase project region matches Railway region
- Enable connection pooling in Supabase

### Issue 4: CORS Errors
**Symptom:** Browser blocks API requests
**Fix:** Already handled in code with `flask-cors`

### Issue 5: Memory Issues on Railway
**Symptom:** App crashes during audit
**Fix:** 
- Upgrade Railway plan for more RAM
- Or reduce `max_tokens` in API calls

---

## Monitoring

### Railway Logs
- Dashboard → Deployments → View Logs
- Check for `[audit]` logs during audit generation

### Supabase Logs
- Dashboard → Logs → API/Database/Storage

### OpenRouter Usage
- https://openrouter.ai/activity
- Monitor API usage and costs

---

## Rollback Plan

If deployment fails:
1. Check Railway deployment logs
2. Verify all environment variables are set
3. Test locally with production keys first
4. Revert to previous commit if needed
