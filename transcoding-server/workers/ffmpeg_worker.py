import asyncio
import time
from typing import Dict, Any, Optional
from scheduler.gpu_scheduler import GPUScheduler

class TranscoderProcess:
    __slots__ = ("process", "stream_id", "session_type", "gpu_index", "viewers", "last_viewer_time", "startup_time")

    def __init__(self, process: asyncio.subprocess.Process, stream_id: str, session_type: str, gpu_index: Optional[int] = None):
        self.process = process
        self.stream_id = stream_id
        self.session_type = session_type # "live" | "playback"
        self.gpu_index = gpu_index
        self.viewers = 1
        self.last_viewer_time = time.time()
        self.startup_time = time.time()

class TranscodingWorkerPool:
    # Separate pools for Live and Playback sessions to prevent playback disk/decode load from blocking live
    _live_pool: Dict[str, TranscoderProcess] = {}      # stream_id -> TranscoderProcess
    _playback_pool: Dict[str, TranscoderProcess] = {}  # stream_id_range -> TranscoderProcess
    _lock = asyncio.Lock()
    _idle_grace_period: int = 60 # seconds

    @classmethod
    async def start_transcoder(
        cls,
        stream_id: str,
        session_id: str,
        source_url: str,
        target_url: str,
        session_type: str = "live",
        node_id: str = "default"
    ) -> bool:
        """
        Starts a transcoding session. Reuses existing transcoders if they are already running,
        incrementing the viewer count. Otherwise, spawns a new FFmpeg process.
        """
        pool = cls._live_pool if session_type == "live" else cls._playback_pool
        # For playback, we use the node_id + stream_id + timeframe key to group viewers watching the same segment
        session_key = f"{node_id}_{stream_id}" if session_type == "live" else f"{node_id}_{stream_id}_{session_id}"

        async with cls._lock:
            state = pool.get(session_key)
            if state and state.process.returncode is None:
                # Reuse existing running process
                state.viewers += 1
                state.last_viewer_time = time.time()
                print(f"[worker_pool] Reusing {session_type} transcoder for {session_key} (viewers: {state.viewers})")
                return True

            # Allocate GPU index dynamically
            gpu_idx = await GPUScheduler.allocate_gpu()
            
            # Formulate FFmpeg command
            # GPU hardware NVENC if GPU allocated, else libx264 CPU
            if gpu_idx is not None:
                cmd = [
                    "ffmpeg", "-y",
                    "-rtsp_transport", "tcp",
                    "-i", source_url,
                    "-an",
                    "-c:v", "h264_nvenc",
                    "-gpu", str(gpu_idx),
                    "-preset", "p1",
                    "-tune", "low-latency",
                    "-pix_fmt", "yuv420p",
                    "-g", "25",
                    "-keyint_min", "25",
                    "-sc_threshold", "0",
                    "-bf", "0",
                    "-f", "rtsp",
                    "-rtsp_transport", "tcp",
                    target_url
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-rtsp_transport", "tcp",
                    "-i", source_url,
                    "-an",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-tune", "zerolatency",
                    "-pix_fmt", "yuv420p",
                    "-g", "25",
                    "-keyint_min", "25",
                    "-sc_threshold", "0",
                    "-bf", "0",
                    "-f", "rtsp",
                    "-rtsp_transport", "tcp",
                    target_url
                ]

            print(f"[worker_pool] Spawning {session_type} FFmpeg process: {' '.join(cmd)}")
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Log stderr asynchronously to catch stream start stutters
                async def log_errors(p, key):
                    try:
                        while True:
                            line = await p.stderr.readline()
                            if not line:
                                break
                            print(f"[ffmpeg:{key}] {line.decode().strip()}")
                    except Exception:
                        pass
                asyncio.create_task(log_errors(proc, session_key))
                
                pool[session_key] = TranscoderProcess(proc, stream_id, session_type, gpu_idx)
                return True
            except Exception as e:
                print(f"[worker_pool] Error spawning FFmpeg for {session_key}: {e}")
                # Release GPU allocation on startup error
                await GPUScheduler.release_gpu(gpu_idx)
                return False

    @classmethod
    async def stop_transcoder(cls, stream_id: str, session_id: str, session_type: str = "live", node_id: str = "default") -> bool:
        """Decrements viewer count. Spawns a background task to check for idle shutdowns."""
        pool = cls._live_pool if session_type == "live" else cls._playback_pool
        session_key = f"{node_id}_{stream_id}" if session_type == "live" else f"{node_id}_{stream_id}_{session_id}"

        async with cls._lock:
            state = pool.get(session_key)
            if not state:
                return False
            
            state.viewers = max(0, state.viewers - 1)
            state.last_viewer_time = time.time()
            print(f"[worker_pool] Disconnected viewer from {session_key} (remaining viewers: {state.viewers})")
            
            if state.viewers <= 0:
                # Spawn non-blocking background shutdown helper
                asyncio.create_task(cls._delayed_cleanup(session_key, session_type))
            return True

    @classmethod
    async def _delayed_cleanup(cls, session_key: str, session_type: str):
        """Waits for the grace period and terminates the FFmpeg process if no new viewers joined."""
        await asyncio.sleep(cls._idle_grace_period)
        pool = cls._live_pool if session_type == "live" else cls._playback_pool

        async with cls._lock:
            state = pool.get(session_key)
            if not state or state.viewers > 0:
                # Viewer reconnected or already cleaned up
                return
            
            # Kill process
            if state.process.returncode is None:
                try:
                    state.process.terminate()
                    await asyncio.wait_for(state.process.wait(), timeout=3.0)
                except Exception:
                    try:
                        state.process.kill()
                    except:
                        pass
            
            # Release GPU resource
            await GPUScheduler.release_gpu(state.gpu_index)
            pool.pop(session_key, None)
            print(f"[worker_pool] Cleaned up idle {session_type} transcoder for {session_key} after grace period.")

    @classmethod
    async def get_worker_status(cls) -> Dict[str, Any]:
        """Compiles active streams, viewer counts, and pool states."""
        async with cls._lock:
            live_streams = [
                {"stream_id": k, "gpu_index": v.gpu_index, "viewers": v.viewers, "uptime_s": int(time.time() - v.startup_time)}
                for k, v in cls._live_pool.items() if v.process.returncode is None
            ]
            playback_streams = [
                {"session_key": k, "gpu_index": v.gpu_index, "viewers": v.viewers, "uptime_s": int(time.time() - v.startup_time)}
                for k, v in cls._playback_pool.items() if v.process.returncode is None
            ]
            return {
                "live_worker_count": len(live_streams),
                "playback_worker_count": len(playback_streams),
                "live_active_sessions": live_streams,
                "playback_active_sessions": playback_streams
            }
