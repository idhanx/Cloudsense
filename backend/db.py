"""
CloudSense Database Module
Simple SQLite database for user authentication and analysis tracking.
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudsense.db")


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Analyses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT,
            source TEXT DEFAULT 'manual_upload',
            status TEXT DEFAULT 'pending',
            upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            results TEXT,
            metadata TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


# ==================== USER FUNCTIONS ====================

def create_user(username: str, email: str, password_hash: str) -> Optional[int]:
    """Create a new user. Returns user_id or None if exists."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


# ==================== ANALYSIS FUNCTIONS ====================

def create_analysis(analysis_id: str, filename: str, file_path: str = None, source: str = 'manual_upload'):
    """Create a new analysis record."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO analyses (id, filename, file_path, source) VALUES (?, ?, ?, ?)',
        (analysis_id, filename, file_path, source)
    )
    conn.commit()
    conn.close()


def update_analysis_status(analysis_id: str, status: str):
    """Update analysis status."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'UPDATE analyses SET status = ? WHERE id = ?',
        (status, analysis_id)
    )
    conn.commit()
    conn.close()


def get_analysis(analysis_id: str) -> Optional[Dict]:
    """Get analysis by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM analyses WHERE id = ?', (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_recent_analyses(limit: int = 10) -> List[Dict]:
    """Get recent analyses."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM analyses ORDER BY upload_timestamp DESC LIMIT ?',
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        d = dict(row)
        # Frontend expects 'analysis_id' but DB column is 'id'
        d['analysis_id'] = d.get('id', '')
        results.append(d)
    return results


def save_analysis_results(analysis_id: str, results: Any):
    """Save analysis results as JSON."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'UPDATE analyses SET results = ? WHERE id = ?',
        (json.dumps(results), analysis_id)
    )
    conn.commit()
    conn.close()


def get_analysis_results(analysis_id: str) -> Optional[Any]:
    """Get analysis results."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT results FROM analyses WHERE id = ?', (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['results']:
        return json.loads(row['results'])
    return None


def save_analysis_metadata(analysis_id: str, metadata: Dict):
    """Save analysis metadata as JSON."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'UPDATE analyses SET metadata = ? WHERE id = ?',
        (json.dumps(metadata), analysis_id)
    )
    conn.commit()
    conn.close()


def get_analysis_metadata(analysis_id: str) -> Optional[Dict]:
    """Get analysis metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT metadata FROM analyses WHERE id = ?', (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['metadata']:
        return json.loads(row['metadata'])
    return None


def get_dashboard_stats() -> Dict:
    """Get aggregated stats for the dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Active TCCs (Total clusters detected in all analyses)
    # This is an approximation. Ideally we'd look at the *latest* analysis only or handle time series.
    # For now, let's return the stats from the MOST RECENT analysis to show "current" state.
    
    cursor.execute('SELECT results FROM analyses ORDER BY upload_timestamp DESC LIMIT 1')
    row = cursor.fetchone()
    
    stats = {
        "active_tccs": 0,
        "min_bt": 0.0,
        "avg_cloud_height": 0.0,
        "mean_radius": 0.0
    }
    
    if row and row['results']:
        try:
            results = json.loads(row['results'])
            detections = results.get('detections', [])
            
            stats["active_tccs"] = len(detections)
            
            if detections:
                min_bts = [d.get('min_bt', 0) for d in detections]
                radii = [d.get('radius_km', 0) for d in detections]
                
                stats["min_bt"] = min(min_bts) if min_bts else 0
                stats["mean_radius"] = sum(radii) / len(radii) if radii else 0
                
                # Approximate cloud top height from BT (simple lapse rate approximation)
                # Height ~ (SurfaceTemp - BT) / LapseRate
                # Ensuring positive height
                avg_bt = sum(d.get('mean_bt', 0) for d in detections) / len(detections)
                stats["avg_cloud_height"] = max(0, (300 - avg_bt) / 6.5) 
                
        except Exception as e:
            print(f"Error parsing dashboard stats: {e}")
            
    conn.close()
    return stats


def get_all_recent_clusters(limit: int = 50) -> List[Dict]:
    """Get a list of all detected clusters from recent analyses."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get last 5 analyses
    cursor.execute('SELECT id, upload_timestamp, results, filename FROM analyses ORDER BY upload_timestamp DESC LIMIT 5')
    rows = cursor.fetchall()
    conn.close()
    
    all_clusters = []
    
    for row in rows:
        if row['results']:
            try:
                results = json.loads(row['results'])
                detections = results.get('detections', [])
                timestamp = row['upload_timestamp']
                
                for d in detections:
                    cluster = {
                        "id": f"TCC-{d.get('cluster_id')}",
                        "analysis_id": row['id'],
                        "centroidLat": d.get('centroid_lat'),
                        "centroidLon": d.get('centroid_lon'),
                        "avgBT": d.get('mean_bt'),
                        "minBT": d.get('min_bt'),
                        "radius": d.get('radius_km'),
                        "area": d.get('area_km2'),
                        "status": "active", # Placeholder
                        "source": row['filename'],
                        "lastUpdate": timestamp,
                        "intensity": (300 - d.get('min_bt', 300)) / 100 # Normalize 0-1
                    }
                    all_clusters.append(cluster)
            except:
                continue
                
    return all_clusters[:limit]