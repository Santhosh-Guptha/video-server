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
        if point.y > min(p1.y, p2.y):
            if point.y <= max(p1.y, p2.y):
                if point.x <= max(p1.x, p2.x):
                    if p1.y != p2.y:
                        xinters = (point.y - p1.y) * (p2.x - p1.x) / (p2.y - p1.y) + p1.x
                    if p1.x == p2.x or point.x <= xinters:
                        inside = not inside
        p1 = p2

    return inside

class IntrusionDetector:
    def check_breaches(
        self,
        detections: List[DetectionResult],
        zones: List[IntrusionZone]
    ) -> List[Dict[str, Any]]:
        breaches = []
        enabled_zones = [z for z in zones if z.enabled]
        if not enabled_zones:
            return breaches

        for det in detections:
            # Bottom center point of the bounding box represents footstep/contact point
            bottom_center = Point2D(
                x=(det.bbox.xmin + det.bbox.xmax) / 2.0,
                y=det.bbox.ymax
            )

            for zone in enabled_zones:
                polygon_pts = [Point2D(x=pt["x"], y=pt["y"]) if isinstance(pt, dict) else pt for pt in zone.polygon]
                if is_point_in_polygon(bottom_center, polygon_pts):
                    breaches.append({
                        "detection_id": det.id,
                        "label": det.label,
                        "confidence": det.confidence,
                        "bbox": det.bbox.model_dump(),
                        "zone_id": zone.zone_id,
                        "zone_name": zone.name,
                        "breach_point": {"x": bottom_center.x, "y": bottom_center.y}
                    })

        return breaches
