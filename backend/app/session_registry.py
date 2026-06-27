import asyncio
import time
from typing import Dict, Any, Optional

class SessionState:
    __slots__ = (
        "session_id", "stream_id", "session_type", "source_type", 
        "worker_node", "ffmpeg_pid", "tenant_id", "node_id", 
        "codec", "resolution", "fps", "viewer_count", 
        "last_heartbeat", "created_at"
    )

    def __init__(
        self, session_id: str, stream_id: str, session_type: str, source_type: str,
        worker_node: Optional[str] = None, ffmpeg_pid: Optional[int] = None,
        tenant_id: Optional[str] = None, node_id: Optional[str] = None,
        codec: Optional[str] = None, resolution: Optional[str] = None,
        fps: Optional[int] = None, initial_viewers: int = 1
    ):
        self.session_id = session_id
        self.stream_id = stream_id
        self.session_type = session_type # "live" | "playback"
        self.source_type = source_type   # "direct" | "cloud" | "local"
        self.worker_node = worker_node
        self.ffmpeg_pid = ffmpeg_pid
        self.tenant_id = tenant_id
        self.node_id = node_id
        self.codec = codec
        self.resolution = resolution
        self.fps = fps
        self.viewer_count = initial_viewers
        self.last_heartbeat = time.time()
        self.created_at = time.time()

class SessionRegistry:
    _sessions: Dict[str, SessionState] = {} # session_id -> SessionState
    _stream_sessions: Dict[str, list] = {}  # stream_id -> list of session_ids
    _lock = asyncio.Lock()

    @classmethod
    async def register_session(cls, session: SessionState) -> None:
        """Registers a new active media session."""
        async with cls._lock:
            cls._sessions[session.session_id] = session
            if session.stream_id not in cls._stream_sessions:
                cls._stream_sessions[session.stream_id] = []
            if session.session_id not in cls._stream_sessions[session.stream_id]:
                cls._stream_sessions[session.stream_id].append(session.session_id)
            print(f"[session_registry] Registered {session.session_type} session {session.session_id} "
                  f"for {session.stream_id} (source: {session.source_type}, viewers: {session.viewer_count})")

    @classmethod
    async def unregister_session(cls, session_id: str) -> Optional[SessionState]:
        """Removes an active media session."""
        async with cls._lock:
            session = cls._sessions.pop(session_id, None)
            if session:
                if session.stream_id in cls._stream_sessions:
                    try:
                        cls._stream_sessions[session.stream_id].remove(session_id)
                        if not cls._stream_sessions[session.stream_id]:
                            cls._stream_sessions.pop(session.stream_id)
                    except ValueError:
                        pass
                print(f"[session_registry] Unregistered session {session_id} for {session.stream_id}")
            return session

    @classmethod
    async def get_session(cls, session_id: str) -> Optional[SessionState]:
        """Retrieves a session state by ID."""
        async with cls._lock:
            return cls._sessions.get(session_id)

    @classmethod
    async def get_sessions_for_stream(cls, stream_id: str) -> list[SessionState]:
        """Retrieves all session states associated with a specific stream ID."""
        async with cls._lock:
            session_ids = cls._stream_sessions.get(stream_id, [])
            return [cls._sessions[sid] for sid in session_ids if sid in cls._sessions]

    @classmethod
    async def update_heartbeat(cls, session_id: str) -> bool:
        """Updates the last heartbeat timestamp of an active session."""
        async with cls._lock:
            session = cls._sessions.get(session_id)
            if session:
                session.last_heartbeat = time.time()
                return True
            return False

    @classmethod
    async def rename_session(cls, old_session_id: str, new_session_id: str) -> bool:
        """Renames an active session key in the registry."""
        async with cls._lock:
            session = cls._sessions.pop(old_session_id, None)
            if session:
                session.session_id = new_session_id
                cls._sessions[new_session_id] = session
                if session.stream_id in cls._stream_sessions:
                    try:
                        cls._stream_sessions[session.stream_id].remove(old_session_id)
                        cls._stream_sessions[session.stream_id].append(new_session_id)
                    except ValueError:
                        pass
                return True
            return False

    @classmethod
    async def get_all_sessions(cls) -> list[SessionState]:
        """Returns a copy of all active sessions."""
        async with cls._lock:
            return list(cls._sessions.values())
