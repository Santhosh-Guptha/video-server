"""initial_schema

Revision ID: 1290a8470d17
Revises: 
Create Date: 2026-06-12 22:27:30.370563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1290a8470d17'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    if is_postgres:
        # Ensure pgcrypto is enabled for gen_random_uuid() if needed
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

        # 1. Create custom enum types in PostgreSQL if they do not exist
        # Note: checkfirst=True prevents failure if run on a DB where they already exist
        profile_type_enum = postgresql.ENUM('MAIN', 'SUB', 'MOBILE', name='profile_type_enum')
        profile_type_enum.create(bind, checkfirst=True)

        stream_state_enum = postgresql.ENUM(
            'REGISTERED', 'CONNECTING', 'ONLINE', 'DEGRADED', 'RECONNECTING', 'OFFLINE', 'ERROR',
            name='stream_state_enum'
        )
        stream_state_enum.create(bind, checkfirst=True)

    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.UUID(as_uuid=True)
    uuid_default = sa.text('gen_random_uuid()') if is_postgres else None

    # 2. Create cameras table
    op.create_table(
        'cameras',
        sa.Column('id', uuid_type, server_default=uuid_default, nullable=False),
        sa.Column('source_camera_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_camera_id')
    )
    op.create_index(op.f('idx_cameras_active'), 'cameras', ['active'], unique=False)
    op.create_index(op.f('idx_cameras_name'), 'cameras', ['name'], unique=False)

    # 3. Create camera_streams table
    op.create_table(
        'camera_streams',
        sa.Column('id', uuid_type, server_default=uuid_default, nullable=False),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stream_id', sa.String(length=128), nullable=False),
        sa.Column('profile_type', sa.Enum('MAIN', 'SUB', 'MOBILE', name='profile_type_enum'), nullable=False),
        sa.Column('resolution', sa.String(length=32), nullable=False),
        sa.Column('fps', sa.Integer(), nullable=False),
        sa.Column('codec', sa.String(length=16), server_default='H264', nullable=False),
        sa.Column('bitrate', sa.Integer(), nullable=True),
        sa.Column('stream_url', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('REGISTERED', 'CONNECTING', 'ONLINE', 'DEGRADED', 'RECONNECTING', 'OFFLINE', 'ERROR', name='stream_state_enum'), server_default='REGISTERED', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_id')
    )
    op.create_index(op.f('idx_camera_streams_status'), 'camera_streams', ['status'], unique=False)

    # 4. Create recording_segments table
    op.create_table(
        'recording_segments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=128), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('start_ts', sa.Float(), nullable=False),
        sa.Column('end_ts', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stream_id'], ['camera_streams.stream_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('idx_recording_segments_stream_id'), 'recording_segments', ['stream_id'], unique=False)
    op.create_index(op.f('idx_recording_segments_start_ts'), 'recording_segments', ['start_ts'], unique=False)
    op.create_index(op.f('idx_recording_segments_end_ts'), 'recording_segments', ['end_ts'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('recording_segments')
    op.drop_table('camera_streams')
    op.drop_table('cameras')
    
    op.execute('DROP TYPE IF EXISTS profile_type_enum CASCADE')
    op.execute('DROP TYPE IF EXISTS stream_state_enum CASCADE')
