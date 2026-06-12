from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Camera(Base):
    __tablename__ = "cameras"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_camera_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    stream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    stream_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    rtsp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    transcode: Mapped[bool] = mapped_column(Boolean, default=False)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camera_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decode_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    server_http_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RecordingSegment(Base):
    __tablename__ = "recording_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    camera_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    end_ts: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
