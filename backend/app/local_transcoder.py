import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .transcoder import transcoder_manager

class LocalTranscoder:
    @classmethod
    async def start_session(
        cls,
        stream_id: str,
        session_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> str:
        """
        Ensures a local transcoder is running for the stream.
        Returns the transcoded path name (e.g. '{stream_id}_h264').
        """
        print(f"[local_transcoder] Starting local session {session_id} for stream {stream_id}")
        # Call the existing TranscoderManager
        transcoded_path = await transcoder_manager.ensure_transcoder(
            stream_id, db_session, increment_viewer=True
        )
        return transcoded_path

    @classmethod
    async def stop_session(
        cls,
        stream_id: str,
        session_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> None:
        """
        Registers a viewer disconnect, allowing the local transcoder to shut down after its grace period.
        """
        print(f"[local_transcoder] Stopping local session {session_id} for stream {stream_id}")
        await transcoder_manager.register_viewer_disconnect(stream_id, db_session)

    @classmethod
    async def get_status(cls, stream_id: str) -> dict:
        """Returns the local status of a transcoding stream."""
        from .transcoder import TranscoderManager
        async with TranscoderManager._lock:
            state = TranscoderManager._transcoders.get(stream_id)
            if state:
                return {
                    "stream_id": stream_id,
                    "active": state.process.returncode is None,
                    "viewers": state.active_viewers,
                    "startup_time": state.startup_time.isoformat() if state.startup_time else None
                }
            return {"stream_id": stream_id, "active": False, "viewers": 0}
