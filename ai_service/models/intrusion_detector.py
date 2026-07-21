from typing import List, Dict, Any, Optional
from ..schemas import DetectionResult, IntrusionZone, BoundingBox, Point2D

def is_point_in_polygon(point: Point2D, polygon: List[Point2D]) -> bool:
    """Ray-casting algorithm to check if a 2D point is inside a polygon."""
    num_vertices = len(polygon)
    if num_vertices < 3:
        return False

    inside = False
    p1 = polygon[0]

    for i in range(num_vertices + 1):
        p2 = polygon[i % num_vertices]
        p1_x = p1.x if hasattr(p1, "x") else p1.get("x", 0.0)
        p1_y = p1.y if hasattr(p1, "y") else p1.get("y", 0.0)
        p2_x = p2.x if hasattr(p2, "x") else p2.get("x", 0.0)
        p2_y = p2.y if hasattr(p2, "y") else p2.get("y", 0.0)

        if point.y > min(p1_y, p2_y):
            if point.y <= max(p1_y, p2_y):
                if point.x <= max(p1_x, p2_x):
                    if p1_y != p2_y:
                        xinters = (point.y - p1_y) * (p2_x - p1_x) / (p2_y - p1_y) + p1_x
                    if p1_x == p2_x or point.x <= xinters:
                        inside = not inside
        p1 = p2

    return inside

class IntrusionDetector:
    def check_breaches(
        self,
        detections: List[DetectionResult],
        zones: List[Any]
    ) -> List[Dict[str, Any]]:
        breaches = []
        
        # Resolve zone objects or dicts
        enabled_zones = []
        for z in zones:
            is_enabled = z.enabled if hasattr(z, "enabled") else z.get("enabled", True)
            if is_enabled:
                enabled_zones.append(z)

        if not enabled_zones:
            return breaches

        for det in detections:
            # Bottom center point of the bounding box represents footstep/contact point
            det_bbox = det.bbox
            bottom_center = Point2D(
                x=(det_bbox.xmin + det_bbox.xmax) / 2.0,
                y=det_bbox.ymax
            )

            for zone in enabled_zones:
                zone_poly = zone.polygon if hasattr(zone, "polygon") else zone.get("polygon", [])
                
                # Check point format
                polygon_pts = []
                for pt in zone_poly:
                    if isinstance(pt, dict):
                        polygon_pts.append(Point2D(x=pt.get("x", 0.0), y=pt.get("y", 0.0)))
                    else:
                        polygon_pts.append(pt)

                if is_point_in_polygon(bottom_center, polygon_pts):
                    z_id = zone.zone_id if hasattr(zone, "zone_id") else zone.get("zone_id")
                    z_name = zone.name if hasattr(zone, "name") else zone.get("name", "Zone")
                    
                    breaches.append({
                        "detection_id": det.id,
                        "label": det.label,
                        "confidence": det.confidence,
                        "bbox": {
                            "xmin": det_bbox.xmin,
                            "ymin": det_bbox.ymin,
                            "xmax": det_bbox.xmax,
                            "ymax": det_bbox.ymax
                        },
                        "zone_id": z_id,
                        "zone_name": z_name,
                        "breach_point": {"x": bottom_center.x, "y": bottom_center.y}
                    })

        return breaches
