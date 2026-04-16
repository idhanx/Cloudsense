# CloudSense — Security, Dead Code & Optimization Review

## Critical Security Issues

### 1. Hardcoded JWT fallback secret (auth.py)
`JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-please-change-in-production-12345678")`
If JWT_SECRET is not set in env, tokens are signed with a known public string.

### 2. MOSDAC credentials written to disk in plaintext (app.py, api/mosdac.py)
`config.json` is written with username/password in plaintext. On a shared server this is readable by any process.

### 3. analysis_id path traversal (api/upload.py download endpoint)
`analysis_id` from URL is used directly in `os.path.join(OUTPUT_DIR, analysis_id, filename)` with no sanitization. A crafted `analysis_id` like `../../etc/passwd` could escape the output directory.

### 4. Bare `except: pass` swallows all errors silently (db.py, core/database.py)
Multiple places use `except: pass` or `except: continue` — hides bugs and security issues.

### 5. Dashboard stats use hardcoded 300K surface temp (db.py get_dashboard_stats)
`(300 - avg_bt) / 6.5` — inconsistent with the fixed 288K in inference_engine.py.

## Dead Code

### 6. backend/app.py is entirely dead
`main.py` is the actual entrypoint (used by render.yaml: `uvicorn main:app`). `app.py` duplicates all routes and is never imported or run. It's ~400 lines of dead code.

### 7. backend/config.py (root-level) is dead
`core/config.py` is the active config. The root `config.py` uses pydantic_settings with a different schema and is never imported by main.py or any api/ module.

### 8. backend/mosdac_manager.py is dead
`MosdacManager` class is defined but never imported or used anywhere. The MOSDAC flow goes directly through `api/mosdac.py` → `mdapi.py`.

### 9. `get_analysis_metadata` / `save_analysis_metadata` in db.py are dead
Never called from any route or module.

### 10. `get_analysis_results` in db.py / core/database.py is dead
Never called from any route.

### 11. `get_analysis` in db.py / core/database.py is dead
Never called from any route.

### 12. Double static mount in app.py (dead anyway)
`/static/output` and `/output` both mount the same directory — redundant even if app.py were active.

## Optimization Issues

### 13. New DB connection per query (db.py, core/database.py)
Every function opens and closes a new SQLite connection. Should use a connection pool or at minimum a module-level connection with thread safety.

### 14. `get_dashboard_stats` in db.py uses wrong lapse rate reference
Uses 300K instead of 288K (ISA standard) — inconsistent with inference_engine.py fix.

### 15. `get_all_recent_clusters` bare except hides parse errors
`except: continue` — should at minimum log the error.

### 16. Rate limiter memory leak
`RateLimiter.requests` dict grows unbounded — old client IPs are never evicted, only their timestamps are cleaned. Under high traffic this leaks memory.

### 17. `IMAGE_EXTENSIONS` defined twice in api/upload.py
Defined at module level and again inside `upload_file()`.
