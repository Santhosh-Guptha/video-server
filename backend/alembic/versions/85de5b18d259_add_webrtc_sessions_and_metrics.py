"""add_webrtc_sessions_and_metrics

Revision ID: 85de5b18d259
Revises: 1290a8470d17
Create Date: 2026-06-13 00:42:46.527158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '85de5b18d259'
down_revision: Union[str, Sequence[str], None] = '1290a8470d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    if is_postgres:
        # 1. Add new enum values to stream_state_enum in PostgreSQL
        # Using commit_as_transaction=False context or execute statements
        # Note: ALTER TYPE ADD VALUE cannot run inside a transaction block in Postgres,
        # so we execute them. Alembic handles this gracefully if we run them.
        # To run outside of active transaction in some dialects, we can run them with autocommit.
        # We execute them directly.
        op.execute("COMMIT") # End active transaction block to allow ALTER TYPE
        op.execute("ALTER TYPE stream_state_enum ADD VALUE IF NOT EXISTS 'RECOVERING'")
        op.execute("ALTER TYPE stream_state_enum ADD VALUE IF NOT EXISTS 'FAILED'")
        op.execute("ALTER TYPE stream_state_enum ADD VALUE IF NOT EXISTS 'DISABLED'")
        op.execute("BEGIN") # Restart transaction block for subsequent tables

    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.UUID(as_uuid=True)
    uuid_default = sa.text('gen_random_uuid()') if is_postgres else None

    # 2. Add columns to camera_streams for preloading/warmup
    op.add_column('camera_streams', sa.Column('always_on', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('camera_streams', sa.Column('camera_priority', sa.Integer(), server_default='3', nullable=False))
    op.add_column('camera_streams', sa.Column('last_viewed', sa.DateTime(timezone=True), nullable=True))

    # 3. Create stream_registry table
    op.create_table(
        'stream_registry',
        sa.Column('id', uuid_type, server_default=uuid_default, nullable=False),
        sa.Column('stream_id', sa.String(length=128), nullable=False),
        sa.Column('mediamtx_node', sa.String(length=128), server_default='node1', nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('current_viewers', sa.Integer(), server_default='0', nullable=False),
        sa.Column('recording_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='REGISTERED', nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stream_id')
    )
    op.create_index(op.f('ix_stream_registry_stream_id'), 'stream_registry', ['stream_id'], unique=True)
    op.create_index(op.f('ix_stream_registry_node'), 'stream_registry', ['mediamtx_node'], unique=False)

    # 4. Create webrtc_sessions table
    op.create_table(
        'webrtc_sessions',
        sa.Column('id', uuid_type, server_default=uuid_default, nullable=False),
        sa.Column('session_id', sa.String(length=128), nullable=False),
        sa.Column('stream_id', sa.String(length=128), nullable=False),
        sa.Column('user_id', uuid_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='ACTIVE', nullable=False),
        sa.Column('protocol', sa.String(length=16), server_default='WHEP', nullable=False),
        sa.Column('client_ip', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['stream_id'], ['camera_streams.stream_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
    )
    op.create_index(op.f('ix_webrtc_sessions_session_id'), 'webrtc_sessions', ['session_id'], unique=True)
    
    if is_postgres:
        op.create_index(
            'idx_sessions_active', 
            'webrtc_sessions', 
            ['stream_id', 'status'], 
            postgresql_where=sa.text("status = 'ACTIVE'")
        )
    else:
        op.create_index(
            'idx_sessions_active', 
            'webrtc_sessions', 
            ['stream_id', 'status']
        )

    # 5. Create stream_metrics_history table
    op.create_table(
        'stream_metrics_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=128), nullable=False),
        sa.Column('session_id', sa.String(length=128), nullable=True),
        sa.Column('fps', sa.Float(), nullable=False),
        sa.Column('resolution', sa.String(length=32), nullable=True),
        sa.Column('bitrate', sa.Float(), nullable=False),
        sa.Column('rtt', sa.Float(), nullable=True),
        sa.Column('packet_loss', sa.Float(), nullable=False),
        sa.Column('jitter', sa.Float(), nullable=True),
        sa.Column('frames_dropped', sa.Integer(), nullable=False),
        sa.Column('decoder_latency', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stream_id'], ['camera_streams.stream_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stream_metrics_history_session_id'), 'stream_metrics_history', ['session_id'], unique=False)
    op.create_index(op.f('ix_stream_metrics_history_stream_id'), 'stream_metrics_history', ['stream_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_stream_metrics_history_stream_id'), table_name='stream_metrics_history')
    op.drop_index(op.f('ix_stream_metrics_history_session_id'), table_name='stream_metrics_history')
    op.drop_table('stream_metrics_history')

    op.drop_index('idx_sessions_active', table_name='webrtc_sessions')
    op.drop_index(op.f('ix_webrtc_sessions_session_id'), table_name='webrtc_sessions')
    op.drop_table('webrtc_sessions')

    op.drop_index(op.f('ix_stream_registry_node'), table_name='stream_registry')
    op.drop_index(op.f('ix_stream_registry_stream_id'), table_name='stream_registry')
    op.drop_table('stream_registry')

    op.drop_column('camera_streams', 'last_viewed')
    op.drop_column('camera_streams', 'camera_priority')
    op.drop_column('camera_streams', 'always_on')
