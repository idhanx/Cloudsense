"""
CloudSense — Database Module
Supports both SQLite (dev) and Neon PostgreSQL (production).
Neon Auth is used for user management, so 'user_id' is stored as TEXT.
"""

import os
import json
import sqlite3
from typing import Dict, List

from core.config import settings
import logging
logger = logging.getLogger(__name__)

# ─── Determine DB backend from URL ───
_is_postgres = settings.DATABASE_URL.startswith("postgresql")


def _get_sqlite_path() -> str:
    """Extract file path from sqlite:/// URL."""
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return os.path.join(settings.BASE_DIR, "cloudsense.db")


# ═══════════════════════════════════════════════════
# PostgreSQL backend (Neon)
# ═══════════════════════════════════════════════════
if _is_postgres:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise ImportError("Install psycopg2-binary for PostgreSQL: pip install psycopg2-binary")

    def _get_pg_conn():
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.autocommit = False
        return conn

    def init_db():
        conn = _get_pg_conn()
        cur = conn.cursor()
        
        # We no longer manage users locally. user_id is a TEXT string from Neon Auth.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                filename TEXT NOT NULL,
                file_path TEXT,
                source TEXT DEFAULT 'manual_upload',
                status TEXT DEFAULT 'pending',
                upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                results TEXT,
                metadata TEXT
            )
        """)
        
        # Migration: ensure user_id is TEXT if it already existed as INTEGER
        try:
            cur.execute("ALTER TABLE analyses ALTER COLUMN user_id TYPE TEXT")
        except Exception as e:
            conn.rollback()
            try:
                cur.execute("ALTER TABLE analyses ADD COLUMN user_id TEXT")
            except Exception:
                conn.rollback()
                pass

        cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_ts ON analyses(upload_timestamp)")
        conn.commit()
        cur.close()
        conn.close()

    def _row_to_dict(row, columns):
        if row is None:
            return None
        return dict(zip(columns, row))

    def create_analysis(analysis_id, filename, file_path=None, source="manual_upload", user_id=None):
        """Create a new analysis record in the database."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO analyses (id, user_id, filename, file_path, source) VALUES (%s, %s, %s, %s, %s)",
                (analysis_id, user_id, filename, file_path, source),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Database error creating analysis {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_analysis_status(analysis_id, status):
        """Update analysis status (pending -> processing -> complete/failed)."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE analyses SET status = %s WHERE id = %s", (status, analysis_id))
            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Database error updating status for {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_analysis(analysis_id):
        """Retrieve a single analysis record by ID."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM analyses WHERE id = %s", (analysis_id,))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            cur.close()
            return _row_to_dict(row, cols)
        except Exception as e:
            logger.error(f"Database error retrieving analysis {analysis_id}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_recent_analyses(limit=10):
        """Get most recent analyses with optional limit."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM analyses ORDER BY upload_timestamp DESC LIMIT %s", (limit,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()
            results = []
            for row in rows:
                d = _row_to_dict(row, cols)
                d["analysis_id"] = d.get("id", "")
                results.append(d)
            return results
        except Exception as e:
            logger.error(f"Database error retrieving recent analyses: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def save_analysis_results(analysis_id, results):
        """Save inference results as JSON."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE analyses SET results = %s WHERE id = %s", (json.dumps(results), analysis_id))
            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Database error saving results for {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_analysis_results(analysis_id):
        """Retrieve inference results for an analysis (as dict)."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT results FROM analyses WHERE id = %s", (analysis_id,))
            row = cur.fetchone()
            cur.close()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError as je:
                    logger.error(f"Invalid JSON in results for {analysis_id}: {je}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Database error retrieving results for {analysis_id}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_dashboard_stats():
        """Get dashboard statistics from recent analyses."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as total_analyses,
                       SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as completed
                FROM analyses
            """)
            row = cur.fetchone()
            
            # Get TCC stats from results
            cur.execute("""
                SELECT results FROM analyses 
                WHERE status = 'complete' AND results IS NOT NULL
                ORDER BY upload_timestamp DESC LIMIT 100
            """)
            results_rows = cur.fetchall()
            cur.close()
            
            total_tccs = 0
            min_bt = None
            total_area = 0
            
            for r in results_rows:
                if r[0]:
                    try:
                        data = json.loads(r[0])
                        total_tccs += data.get("tcc_count", 0)
                        total_area += data.get("total_area_km2", 0)
                        
                        # Find minimum BT from detections
                        for det in data.get("detections", []):
                            bt = det.get("min_bt")
                            if bt and (min_bt is None or bt < min_bt):
                                min_bt = bt
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse results in dashboard stats: {e}")
    
            return {
                "total_analyses": row[0] if row else 0,
                "completed_analyses": row[1] if row else 0,
                "active_tccs": total_tccs,
                "min_brightness_temp": min_bt,
                "total_area_km2": total_area
            }
        except Exception as e:
            logger.error(f"Database error retrieving dashboard stats: {e}", exc_info=True)
            # Return safe defaults instead of crashing
            return {
                "total_analyses": 0,
                "completed_analyses": 0,
                "active_tccs": 0,
                "min_brightness_temp": None,
                "total_area_km2": 0,
                "error": str(e)
            }
        finally:
            conn.close()

    def get_all_recent_clusters(limit=50):
        """Get all recent cluster detections from analyses."""
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, filename, results, upload_timestamp 
                FROM analyses 
                WHERE status = 'complete' AND results IS NOT NULL
                ORDER BY upload_timestamp DESC LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()
            
            clusters = []
            for row in rows:
                d = _row_to_dict(row, cols)
                if d.get("results"):
                    try:
                        results = json.loads(d["results"]) if isinstance(d["results"], str) else d["results"]
                        for det in results.get("detections", []):
                            clusters.append({
                                "analysis_id": d["id"],
                                "filename": d["filename"],
                                "timestamp": d["upload_timestamp"],
                                "cluster_id": det.get("cluster_id"),
                                "track_id": det.get("track_id"),
                                "classification": det.get("classification"),
                                "min_bt": det.get("min_bt"),
                                "area_km2": det.get("area_km2"),
                                "centroid_lat": det.get("centroid_lat"),
                                "centroid_lon": det.get("centroid_lon")
                            })
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse cluster results for {d['id']}: {e}")
            
            return clusters
        except Exception as e:
            logger.error(f"Database error retrieving clusters: {e}", exc_info=True)
            raise
        finally:
            conn.close()

# ═══════════════════════════════════════════════════
# SQLite backend (development)
# ═══════════════════════════════════════════════════
else:
    _DB_PATH = _get_sqlite_path()

    def _get_conn():
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db():
        conn = _get_conn()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                filename TEXT NOT NULL,
                file_path TEXT,
                source TEXT DEFAULT 'manual_upload',
                status TEXT DEFAULT 'pending',
                upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                results TEXT,
                metadata TEXT
            )
        """)
        
        # ── Migration: add user_id column if missing (existing DBs) ──
        try:
            c.execute("SELECT user_id FROM analyses LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Migrating: adding user_id column to analyses table")
            c.execute("ALTER TABLE analyses ADD COLUMN user_id TEXT")
        conn.commit()
        conn.close()

    def create_analysis(analysis_id, filename, file_path=None, source="manual_upload", user_id=None):
        """Create a new analysis record in the database."""
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO analyses (id, user_id, filename, file_path, source) VALUES (?, ?, ?, ?, ?)",
                (analysis_id, user_id, filename, file_path, source),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error creating analysis {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_analysis_status(analysis_id, status):
        """Update analysis status (pending -> processing -> complete/failed)."""
        conn = _get_conn()
        try:
            conn.execute("UPDATE analyses SET status = ? WHERE id = ?", (status, analysis_id))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error updating status for {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_analysis(analysis_id):
        """Retrieve a single analysis record by ID."""
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving analysis {analysis_id}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_recent_analyses(limit=10):
        """Get most recent analyses with optional limit."""
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM analyses ORDER BY upload_timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["analysis_id"] = d.get("id", "")
                results.append(d)
            return results
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving recent analyses: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def save_analysis_results(analysis_id, results):
        """Save inference results as JSON."""
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE analyses SET results = ? WHERE id = ?",
                (json.dumps(results), analysis_id),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error saving results for {analysis_id}: {e}", exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_analysis_results(analysis_id):
        """Retrieve inference results for an analysis (as dict)."""
        conn = _get_conn()
        try:
            row = conn.execute("SELECT results FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            if row and row["results"]:
                try:
                    return json.loads(row["results"])
                except json.JSONDecodeError as je:
                    logger.error(f"Invalid JSON in results for {analysis_id}: {je}")
                    return None
            return None
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving results for {analysis_id}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_dashboard_stats():
        """Get dashboard statistics from recent analyses."""
        conn = _get_conn()
        try:
            # Get basic counts
            row = conn.execute("""
                SELECT COUNT(*) as total_analyses,
                       SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as completed
                FROM analyses
            """).fetchone()
            
            # Get TCC stats from results
            results_rows = conn.execute("""
                SELECT results FROM analyses 
                WHERE status = 'complete' AND results IS NOT NULL
                ORDER BY upload_timestamp DESC LIMIT 100
            """).fetchall()
            
            total_tccs = 0
            min_bt = None
            total_area = 0
            
            for r in results_rows:
                if r["results"]:
                    try:
                        data = json.loads(r["results"])
                        total_tccs += data.get("tcc_count", 0)
                        total_area += data.get("total_area_km2", 0)
                        
                        # Find minimum BT from detections
                        for det in data.get("detections", []):
                            bt = det.get("min_bt")
                            if bt and (min_bt is None or bt < min_bt):
                                min_bt = bt
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse results in dashboard stats: {e}")

            return {
                "total_analyses": row["total_analyses"] if row else 0,
                "completed_analyses": row["completed"] if row else 0,
                "active_tccs": total_tccs,
                "min_brightness_temp": min_bt,
                "total_area_km2": total_area
            }
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving dashboard stats: {e}", exc_info=True)
            # Return safe defaults instead of crashing
            return {
                "total_analyses": 0,
                "completed_analyses": 0,
                "active_tccs": 0,
                "min_brightness_temp": None,
                "total_area_km2": 0,
                "error": str(e)
            }
        finally:
            conn.close()

    def get_all_recent_clusters(limit=50):
        """Get all recent cluster detections from analyses."""
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT id, filename, results, upload_timestamp 
                FROM analyses 
                WHERE status = 'complete' AND results IS NOT NULL
                ORDER BY upload_timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
            
            clusters = []
            for row in rows:
                d = dict(row)
                if d.get("results"):
                    try:
                        results = json.loads(d["results"]) if isinstance(d["results"], str) else d["results"]
                        for det in results.get("detections", []):
                            clusters.append({
                                "analysis_id": d["id"],
                                "filename": d["filename"],
                                "timestamp": d["upload_timestamp"],
                                "cluster_id": det.get("cluster_id"),
                                "track_id": det.get("track_id"),
                                "classification": det.get("classification"),
                                "min_bt": det.get("min_bt"),
                                "area_km2": det.get("area_km2"),
                                "centroid_lat": det.get("centroid_lat"),
                                "centroid_lon": det.get("centroid_lon")
                            })
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse cluster results for {d['id']}: {e}")
            
            return clusters
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving clusters: {e}", exc_info=True)
            raise
        finally:
            conn.close()
