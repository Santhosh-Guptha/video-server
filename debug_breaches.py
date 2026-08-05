import sys
import os
import json

sys.path.append("/opt/video-server")

from ai_service.database import init_db, get_db_connection, get_intrusion_zones
from ai_service.models.intrusion_detector import IntrusionDetector, is_point_in_polygon
from ai_service.schemas import DetectionResult, BoundingBox, Point2D

def main():
    print("AI Database Debugger")
    print(f"Python: {sys.executable}")
    
    # 1. Init DB
    print("\n1. Initializing Database...")
    init_db()
    
    # 2. Get DB Connection and print structure
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(intrusion_zones)")
    columns = [dict(row) for row in cursor.fetchall()]
    print("\n2. intrusion_zones Schema:")
    for col in columns:
        print(f" - {col['name']} ({col['type']})")
        
    # 3. Query all zones
    cursor.execute("SELECT * FROM intrusion_zones")
    rows = [dict(row) for row in cursor.fetchall()]
    print(f"\n3. Total intrusion zones in DB: {len(rows)}")
    for r in rows:
        print(f" - Name: {r.get('name')}, Enabled: {r.get('enabled')}, Type: {r.get('zone_type') or 'intrusion'}")
        print(f"   Polygon JSON: {r.get('polygon_json')}")
        
    cursor.execute("SELECT COUNT(*) FROM ai_events")
    count_evts = cursor.fetchone()[0]
    print(f"Total AI events in DB: {count_evts}")
        
    # 4. Try get_intrusion_zones
    zones = get_intrusion_zones("RNS1001C2_HD")
    print(f"\n4. Active zones for camera RNS1001C2_HD: {len(zones)}")
    for z in zones:
        print(f" - Name: {z['name']}, Type: {z.get('zone_type')}, Enabled: {z.get('enabled')}")
        
    # 5. Check mock breach
    if zones:
        first_zone = zones[0]
        detector = IntrusionDetector()
        
        # Create a mock detection that is inside the first point of the polygon
        poly_pts = first_zone["polygon"]
        if poly_pts:
            # Let's calculate the centroid of the polygon to test containment
            cx = sum(p["x"] for p in poly_pts) / len(poly_pts)
            cy = sum(p["y"] for p in poly_pts) / len(poly_pts)
            print(f"\n5. Testing breach check with polygon centroid: ({cx:.3f}, {cy:.3f})")
            
            mock_det = DetectionResult(
                id="test-1",
                label="Person",
                class_name="person",
                confidence=0.90,
                bbox=BoundingBox(
                    xmin=cx - 0.05,
                    ymin=cy - 0.10,
                    xmax=cx + 0.05,
                    ymax=cy # Bottom edge is at cy
                ),
                track_id=1,
                attributes={}
            )
            
            breaches = detector.check_breaches([mock_det], [first_zone])
            print(f"   Breaches triggered: {len(breaches)}")
            for b in breaches:
                print(f"    - Breach in zone: {b['zone_name']} for {b['label']}")
        else:
            print("\n5. First zone has no polygon points.")
    else:
        print("\n5. No zones defined to test breach containment.")
        
    print("\n6. Testing process_and_emit & save_ai_event...")
    from ai_service.events.event_manager import event_manager
    from ai_service.database import save_ai_event, get_recent_ai_events
    
    test_evt = {
        "event_id": "evt-direct-test-123",
        "camera_id": "RNS1001C2_HD",
        "camera_name": "Camera RNS1001C2_HD",
        "event_type": "test_event",
        "timestamp": 1234567.0,
        "formatted_time": "2026-07-21 12:00:00",
        "confidence": 0.99,
        "label": "Test Alert",
        "bbox": {"xmin": 0.1, "ymin": 0.1, "xmax": 0.2, "ymax": 0.2},
        "zone_id": None,
        "details": {},
        "snapshot_url": ""
    }
    try:
        save_ai_event(test_evt)
        print("   Direct save_ai_event call succeeded!")
    except Exception as e:
        print(f"   Direct save_ai_event call FAILED: {e}")
        
    recent = get_recent_ai_events()
    print(f"Recent AI events from DB: {len(recent)}")
    for r in recent:
        print(f" - Event: {r['label']} ({r['event_type']}) at {r['formatted_time']}")
        
    conn.close()

if __name__ == "__main__":
    main()
