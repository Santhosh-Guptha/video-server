import os
import json
import sqlite3
import time
from typing import List, Optional, Dict, Any

DB_FILE = os.path.join(os.path.dirname(__file__), "ai_events.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create AI Events Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_events (
        event_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        camera_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        formatted_time TEXT NOT NULL,
        confidence REAL NOT NULL,
        label TEXT NOT NULL,
        bbox_json TEXT NOT NULL,
        zone_id TEXT,
        details_json TEXT,
        snapshot_url TEXT
    )
    """)

    # Create Intrusion Zones Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS intrusion_zones (
        zone_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        name TEXT NOT NULL,
        polygon_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1
    )
    """)

    # Create Camera Subscriptions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_subscriptions (
        camera_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        stream_url TEXT NOT NULL,
        active_models_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        sampling_fps INTEGER NOT NULL DEFAULT 5
    )
    """)

    # Alter intrusion_zones table if migration columns don't exist
    try:
        cursor.execute("ALTER TABLE intrusion_zones ADD COLUMN zone_type TEXT DEFAULT 'intrusion'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE intrusion_zones ADD COLUMN direction TEXT DEFAULT 'both'")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()

def save_ai_event(event_dict: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO ai_events (
        event_id, camera_id, camera_name, event_type, timestamp, formatted_time,
        confidence, label, bbox_json, zone_id, details_json, snapshot_url
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event_dict["event_id"],
        event_dict["camera_id"],
        event_dict["camera_name"],
        event_dict["event_type"],
        event_dict["timestamp"],
        event_dict["formatted_time"],
        event_dict["confidence"],
        event_dict["label"],
        json.dumps(event_dict["bbox"]),
        event_dict.get("zone_id"),
        json.dumps(event_dict.get("details", {})),
        event_dict.get("snapshot_url")
    ))
    conn.commit()
    conn.close()

def get_recent_ai_events(limit: int = 50, camera_id: Optional[str] = None, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM ai_events"
    params = []
    conditions = []
    
    if camera_id:
        conditions.append("camera_id = ?")
        params.append(camera_id)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        item = dict(row)
        item["bbox"] = json.loads(item["bbox_json"])
        item["details"] = json.loads(item["details_json"]) if item["details_json"] else {}
        del item["bbox_json"]
        del item["details_json"]
        results.append(item)
    return results

def save_intrusion_zone(zone_dict: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO intrusion_zones (
        zone_id, camera_id, name, polygon_json, enabled, zone_type, direction
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        zone_dict["zone_id"],
        zone_dict["camera_id"],
        zone_dict["name"],
        json.dumps(zone_dict["polygon"]),
        1 if zone_dict.get("enabled", True) else 0,
        zone_dict.get("zone_type", "intrusion"),
        zone_dict.get("direction", "both")
    ))
    conn.commit()
    conn.close()

def get_intrusion_zones(camera_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if camera_id:
        cursor.execute("SELECT * FROM intrusion_zones WHERE camera_id = ?", (camera_id,))
    else:
        cursor.execute("SELECT * FROM intrusion_zones")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        item = dict(row)
        item["polygon"] = json.loads(item["polygon_json"])
        item["enabled"] = bool(item["enabled"])
        # Handle cases where existing DB has NULL or missing values for newer columns
        item["zone_type"] = item.get("zone_type") or "intrusion"
        item["direction"] = item.get("direction") or "both"
        del item["polygon_json"]
        results.append(item)
    return results

def delete_intrusion_zone(zone_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM intrusion_zones WHERE zone_id = ?", (zone_id,))
    conn.commit()
    conn.close()
