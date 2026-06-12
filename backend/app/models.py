import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum, text, CHAR
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
    RECONNECTING = "RECONNECTING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"

class ProfileType(str, enum.Enum):
    MAIN = "MAIN"
    SUB = "SUB"
    MOBILE = "MOBILE"

class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4
    )
    source_camera_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    streams: Mapped[list["CameraStream"]] = relationship("CameraStream", back_populates="camera", cascade="all, delete-orphan")

class CameraStream(Base):
    __tablename__ = "camera_streams"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
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
    status: Mapped[StreamState] = mapped_column(Enum(StreamState, name="stream_state_enum"), default=StreamState.REGISTERED, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    camera: Mapped[Camera] = relationship("Camera", back_populates="streams")
    segments: Mapped[list["RecordingSegment"]] = relationship("RecordingSegment", back_populates="stream", cascade="all, delete-orphan")

class RecordingSegment(Base):
    __tablename__ = "recording_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[str] = mapped_column(String(128), ForeignKey("camera_streams.stream_id", ondelete="CASCADE"), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False) # Epoch time (seconds)
    end_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow)

    # Relationships
    stream: Mapped[CameraStream] = relationship("CameraStream", back_populates="segments")
