import time
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models import RecordingSegment
from .redis_client import redis_client

class LocalMemoryCache:
    def __init__(self):
        self._cache = {}

    def get(self, key: str):
        if key in self._cache:
            val, expire = self._cache[key]
            if time.time() < expire:
                return val
            else:
                self._cache.pop(key, None)
        return None

    def set(self, key: str, value, expire_seconds: int):
        self._cache[key] = (value, time.time() + expire_seconds)

local_memory_cache = LocalMemoryCache()

class PlaybackTimelineService:
    @staticmethod
    async def get_daily_timeline(session: AsyncSession, stream_id: str, date_str: str) -> dict:
        """
        Generates the daily timeline containing merged segments, gaps, and coverage stats.
        Results are cached in Redis (60s TTL) with an in-memory TTL fallback.
        """
        cache_key = f"vms:timeline:{stream_id}:{date_str}"
        
        # 1. Attempt to fetch from Redis cache
        if redis_client:
            try:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                print(f"[timeline_service] Redis get error: {e}. Reading from local cache.")
        
        # 2. Attempt to fetch from Local Memory Cache
        cached_data = local_memory_cache.get(cache_key)
        if cached_data:
            return cached_data

        # 3. Cache Miss: Compute from Database
        # Parse the start and end timestamps of the day in local/system time
        try:
            dt_start = datetime.strptime(date_str, "%Y-%m-%d")
            day_start_ts = dt_start.timestamp()
            day_end_ts = day_start_ts + 86400.0
        except ValueError as e:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.") from e

        # Query all segments overlapping with this day
        stmt = (
            select(RecordingSegment)
            .where(RecordingSegment.stream_id == stream_id)
            .where(RecordingSegment.end_ts >= day_start_ts)
            .where(RecordingSegment.start_ts <= day_end_ts)
            .order_by(RecordingSegment.start_ts.asc())
        )
        res = await session.execute(stmt)
        raw_segments = list(res.scalars().all())

        # Collect raw segment metrics
        segment_count = len(raw_segments)
        first_recording_ts = raw_segments[0].start_ts if segment_count > 0 else None
        last_recording_ts = raw_segments[-1].end_ts if segment_count > 0 else None

        # Clamp segment boundaries to the selected day
        clamped_segments = []
        for row in raw_segments:
            s = max(row.start_ts, day_start_ts)
            e = min(row.end_ts, day_end_ts)
            if s < e:
                clamped_segments.append((s, e))

        # Merge contiguous segments (5-second threshold)
        merged_segments = []
        merge_threshold = 5.0

        for s, e in clamped_segments:
            if not merged_segments:
                merged_segments.append([s, e])
            else:
                last = merged_segments[-1]
                if s - last[1] <= merge_threshold:
                    last[1] = max(last[1], e)
                else:
                    merged_segments.append([s, e])

        # Detect gaps
        gaps = []
        if not merged_segments:
            gaps.append({
                "start_ts": day_start_ts,
                "end_ts": day_end_ts,
                "duration": 86400.0
            })
        else:
            # Check gap before first segment
            if merged_segments[0][0] > day_start_ts:
                gaps.append({
                    "start_ts": day_start_ts,
                    "end_ts": merged_segments[0][0],
                    "duration": merged_segments[0][0] - day_start_ts
                })
            
            # Check gaps between consecutive segments
            for i in range(len(merged_segments) - 1):
                prev_end = merged_segments[i][1]
                next_start = merged_segments[i+1][0]
                if next_start > prev_end:
                    gaps.append({
                        "start_ts": prev_end,
                        "end_ts": next_start,
                        "duration": next_start - prev_end
                    })
            
            # Check gap after last segment
            if merged_segments[-1][1] < day_end_ts:
                gaps.append({
                    "start_ts": merged_segments[-1][1],
                    "end_ts": day_end_ts,
                    "duration": day_end_ts - merged_segments[-1][1]
                })

        # Calculate metrics
        gap_duration = sum(g["duration"] for g in gaps)
        recorded_duration = max(0.0, 86400.0 - gap_duration)
        coverage_percent = round((recorded_duration / 86400.0) * 100.0, 2)

        # Build response structure
        timeline_payload = {
            "segments": [
                {"start_ts": seg[0], "end_ts": seg[1], "duration": seg[1] - seg[0]}
                for seg in merged_segments
            ],
            "gaps": gaps,
            "coverage_percent": coverage_percent,
            "recorded_duration": round(recorded_duration, 1),
            "gap_duration": round(gap_duration, 1),
            "segment_count": segment_count,
            "first_recording_ts": first_recording_ts,
            "last_recording_ts": last_recording_ts
        }

        # 4. Save to caches
        if redis_client:
            try:
                await redis_client.set(cache_key, json.dumps(timeline_payload), ex=60)
            except Exception as e:
                print(f"[timeline_service] Redis set error: {e}")
        local_memory_cache.set(cache_key, timeline_payload, 60)

        return timeline_payload
