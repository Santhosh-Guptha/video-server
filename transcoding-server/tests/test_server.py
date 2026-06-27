import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scheduler.gpu_scheduler import GPUScheduler, GPUMetrics
from workers.ffmpeg_worker import TranscodingWorkerPool

@pytest.mark.asyncio
async def test_gpu_scheduler_fallback():
    """Verify that GPUScheduler falls back to CPU if no GPUs are available."""
    GPUScheduler.update_metrics = AsyncMock()
    GPUScheduler._gpus = []
    
    gpu_idx = await GPUScheduler.allocate_gpu()
    assert gpu_idx is None # Should fallback to CPU

@pytest.mark.asyncio
async def test_gpu_scheduler_allocation():
    """Verify GPU scheduling allocations and load balancing logic."""
    GPUScheduler.update_metrics = AsyncMock()
    # Setup two mock GPUs
    GPUScheduler._gpus = [
        GPUMetrics(index=0, temp=50, util=10, used_vram=1000, total_vram=8000, enc_util=5, dec_util=5),
        GPUMetrics(index=1, temp=60, util=20, used_vram=2000, total_vram=8000, enc_util=10, dec_util=10)
    ]
    
    # First allocation: should pick GPUMetrics index 0 because it has fewer sessions (0) and lower VRAM/utilization
    allocated_1 = await GPUScheduler.allocate_gpu()
    assert allocated_1 == 0
    assert GPUScheduler._gpus[0].session_count == 1

    # Second allocation: should pick GPUMetrics index 1 because index 0 has session_count = 1, and index 1 has session_count = 0
    allocated_2 = await GPUScheduler.allocate_gpu()
    assert allocated_2 == 1
    assert GPUScheduler._gpus[1].session_count == 1

    # Release GPUMetrics 0
    await GPUScheduler.release_gpu(0)
    assert GPUScheduler._gpus[0].session_count == 0

@pytest.mark.asyncio
async def test_worker_pool_viewer_counter():
    """Verify viewer counter increment and delayed cleanup in worker pool."""
    # Mock subprocess creation
    mock_proc = AsyncMock()
    mock_proc.returncode = None
    
    # Mock asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = AsyncMock(return_value=mock_proc)
    
    # Start live transcoder session
    success = await TranscodingWorkerPool.start_transcoder(
        stream_id="stream_abc",
        session_id="viewer_1",
        source_url="rtsp://localhost:8554/stream_abc",
        target_url="rtsp://localhost:8554/stream_abc_h264",
        session_type="live"
    )
    
    assert success is True
    assert "stream_abc" in TranscodingWorkerPool._live_pool
    assert TranscodingWorkerPool._live_pool["stream_abc"].viewers == 1
    
    # Add a second viewer
    success2 = await TranscodingWorkerPool.start_transcoder(
        stream_id="stream_abc",
        session_id="viewer_2",
        source_url="rtsp://localhost:8554/stream_abc",
        target_url="rtsp://localhost:8554/stream_abc_h264",
        session_type="live"
    )
    assert success2 is True
    assert TranscodingWorkerPool._live_pool["stream_abc"].viewers == 2

    # Disconnect one viewer
    await TranscodingWorkerPool.stop_transcoder(
        stream_id="stream_abc",
        session_id="viewer_1",
        session_type="live"
    )
    assert TranscodingWorkerPool._live_pool["stream_abc"].viewers == 1
