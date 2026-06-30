from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import CameraStream, StreamState, StreamRegistry as StreamRegistryModel
from ..redis_client import RedisManager

class StreamRegistry:
    @staticmethod
    async def get_stream(stream_id: str, session: AsyncSession) -> Optional[CameraStream]:
        """Fetch stream details by its unique identifier."""
        stmt = select(CameraStream).where(CameraStream.stream_id == stream_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_camera_streams(camera_id: str, session: AsyncSession) -> List[CameraStream]:
        """Get all streams associated with a physical camera."""
        stmt = select(CameraStream).where(CameraStream.camera_id == camera_id)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_stream_state(stream_id: str, state: str, error_message: Optional[str], session: AsyncSession) -> None:
        """Atomically transitions stream pipeline status and updates Redis cache."""
        stream = await StreamRegistry.get_stream(stream_id, session)
        if stream:
            stream.status = state
            stream.error_message = error_message
            
            # Sync to StreamRegistryModel as well
            stmt_reg = select(StreamRegistryModel).where(StreamRegistryModel.stream_id == stream_id)
            reg_res = await session.execute(stmt_reg)
            reg = reg_res.scalar_one_or_none()
            if reg:
                reg.status = state
            await session.commit()
            
            # Sync to Redis cache
            await RedisManager.set_stream_state(stream_id, state, error_message)
            print(f"[stream_registry] Stream {stream_id} state updated to {state}")
