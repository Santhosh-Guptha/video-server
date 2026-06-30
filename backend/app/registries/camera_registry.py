import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Camera, CameraStream

class CameraRegistry:
    @staticmethod
    async def get_camera(camera_id: uuid.UUID, session: AsyncSession) -> Optional[Camera]:
        """Fetch a physical camera details from database."""
        stmt = select(Camera).where(Camera.id == camera_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_active_cameras(session: AsyncSession) -> List[Camera]:
        """Retrieve all active physical cameras."""
        from sqlalchemy.orm import selectinload
        stmt = select(Camera).where(Camera.active == True).options(selectinload(Camera.streams))
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_camera_status(camera_id: uuid.UUID, status: str, session: AsyncSession) -> None:
        """Update physical camera health status (ONLINE, OFFLINE, ERROR, etc.)."""
        camera = await CameraRegistry.get_camera(camera_id, session)
        if camera:
            camera.status = status
            await session.commit()
            print(f"[camera_registry] Camera {camera.name} ({camera_id}) status updated to {status}")
