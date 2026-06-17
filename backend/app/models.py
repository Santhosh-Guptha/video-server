import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum, text, CHAR, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class GUID(TypeDecorator):
    """
    Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise CHAR(36), storing as string.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            return value

class StreamState(str, enum.Enum):
    REGISTERED = "REGISTERED"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    OFFLINE = "OFFLINE"
    FAILED = "FAILED"
    DISABLED = "DISABLED"

class ProfileType(str, enum.Enum):
    MAIN = "MAIN"
    SUB = "SUB"
    MOBILE = "MOBILE"

class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    source_camera_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    make: Mapped[str | None] = mapped_column(String(128), nullable=True)
    synced_from_api: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    streams: Mapped[list["CameraStream"]] = relationship("CameraStream", back_populates="camera", cascade="all, delete-orphan")

class CameraStream(Base):
    __tablename__ = "camera_streams"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    profile_type: Mapped[ProfileType] = mapped_column(Enum(ProfileType, name="profile_type_enum"), nullable=False)
    resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    fps: Mapped[int] = mapped_column(Integer, nullable=False)
    codec: Mapped[str] = mapped_column(String(16), default="H264")
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True) # in kbps
    stream_url: Mapped[str] = mapped_column(Text, nullable=False) # Source RTSP or PUSH publisher url
    stream_mode: Mapped[str] = mapped_column(String(16), default="AUTO", nullable=False)
    stream_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_push_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pull_failed_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[StreamState] = mapped_column(Enum(StreamState, name="stream_state_enum"), default=StreamState.REGISTERED, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    always_on: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    camera_priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_viewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    camera: Mapped[Camera] = relationship("Camera", back_populates="streams")
    segments: Mapped[list["RecordingSegment"]] = relationship("RecordingSegment", back_populates="stream", cascade="all, delete-orphan")
    webrtc_sessions: Mapped[list["WebRTCSession"]] = relationship("WebRTCSession", back_populates="stream", cascade="all, delete-orphan")

class RecordingSegment(Base):
    __tablename__ = "recording_segments"
    __table_args__ = (
        UniqueConstraint("stream_id", "file_path", name="idx_recording_segment_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[str] = mapped_column(String(128), ForeignKey("camera_streams.stream_id", ondelete="CASCADE"), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False) # Epoch time (seconds)
    end_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)

    # Relationships
    stream: Mapped[CameraStream] = relationship("CameraStream", back_populates="segments")

class WebRTCSession(Base):
    __tablename__ = "webrtc_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    stream_id: Mapped[str] = mapped_column(String(128), ForeignKey("camera_streams.stream_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE") # ACTIVE, CLOSED, TIMEOUT
    protocol: Mapped[str] = mapped_column(String(16), default="WHEP") # WHEP / WHIP
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    stream: Mapped[CameraStream] = relationship("CameraStream", back_populates="webrtc_sessions")

class StreamMetricHistory(Base):
    __tablename__ = "stream_metrics_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[str] = mapped_column(String(128), ForeignKey("camera_streams.stream_id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    fps: Mapped[float] = mapped_column(Float, default=0.0)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bitrate: Mapped[float] = mapped_column(Float, default=0.0) # in kbps
    rtt: Mapped[float | None] = mapped_column(Float, nullable=True) # in ms
    packet_loss: Mapped[float] = mapped_column(Float, default=0.0)
    jitter: Mapped[float | None] = mapped_column(Float, nullable=True)
    frames_dropped: Mapped[int] = mapped_column(Integer, default=0)
    decoder_latency: Mapped[float | None] = mapped_column(Float, nullable=True) # in ms
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)

class StreamRegistry(Base):
    __tablename__ = "stream_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    stream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    mediamtx_node: Mapped[str] = mapped_column(String(128), default="node1", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False) # RTSP_PULL, EDGE_PUSH, WEBRTC_PUBLISH
    current_viewers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="REGISTERED", nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)


class EdgeConnection(Base):
    __tablename__ = "edge_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), default=datetime.utcnow)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_frame_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bytes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="CONNECTED", nullable=False)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)


class StreamTranscoder(Base):
    __tablename__ = "stream_transcoders"

    stream_id: Mapped[str] = mapped_column(String(128), primary_key=True, nullable=False)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="INACTIVE", nullable=False)  # ACTIVE, INACTIVE, CRASHED, STARTING
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
