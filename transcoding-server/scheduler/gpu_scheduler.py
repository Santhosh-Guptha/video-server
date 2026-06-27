import asyncio
import subprocess
from typing import Dict, Any, List, Optional

class GPUMetrics:
    __slots__ = ("index", "temperature", "utilization", "used_vram", "total_vram", "encoder_util", "decoder_util", "session_count")

    def __init__(self, index: int, temp: int, util: int, used_vram: int, total_vram: int, enc_util: int, dec_util: int):
        self.index = index
        self.temperature = temp
        self.utilization = util
        self.used_vram = used_vram
        self.total_vram = total_vram
        self.encoder_util = enc_util
        self.decoder_util = dec_util
        self.session_count = 0

class GPUScheduler:
    _gpus: List[GPUMetrics] = []
    _lock = asyncio.Lock()
    _max_sessions_per_gpu: int = 8
    _max_gpu_temp: int = 85

    @classmethod
    async def update_metrics(cls) -> None:
        """Polls nvidia-smi dynamically and parses GPU utilization, VRAM, and temp."""
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,temperature.gpu,utilization.gpu,memory.used,memory.total,utilization.encoder,utilization.decoder",
            "--format=csv,noheader,nounits"
        ]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            if proc.returncode == 0:
                lines = stdout.decode().strip().split("\n")
                async with cls._lock:
                    new_gpus = []
                    for line in lines:
                        if not line.strip():
                            continue
                        parts = [int(p.strip()) for p in line.split(",")]
                        if len(parts) >= 7:
                            gpu = GPUMetrics(
                                index=parts[0],
                                temp=parts[1],
                                util=parts[2],
                                used_vram=parts[3],
                                total_vram=parts[4],
                                enc_util=parts[5],
                                dec_util=parts[6]
                            )
                            # Keep session counts if they were tracked
                            for old_gpu in cls._gpus:
                                if old_gpu.index == gpu.index:
                                    gpu.session_count = old_gpu.session_count
                                    break
                            new_gpus.append(gpu)
                    cls._gpus = new_gpus
            else:
                # nvidia-smi failed (e.g. no driver/hardware). Fallback to simulated CPU mode
                await cls._set_cpu_only_mode()
        except Exception:
            # nvidia-smi command not found. Fallback to CPU mode
            await cls._set_cpu_only_mode()

    @classmethod
    async def _set_cpu_only_mode(cls):
        """Sets internal metrics to indicate CPU-only transcoding."""
        async with cls._lock:
            # Clear GPU list, causing scheduler to fallback to CPU
            cls._gpus = []

    @classmethod
    async def allocate_gpu(cls) -> Optional[int]:
        """
        Selects the least loaded GPU for a new transcoding session.
        Returns: GPU index (int) or None (indicating CPU fallback).
        """
        # First, query current GPU status
        await cls.update_metrics()
        
        async with cls._lock:
            if not cls._gpus:
                return None # CPU fallback

            selected_gpu: Optional[GPUMetrics] = None
            for gpu in cls._gpus:
                # Capacity checks
                if gpu.session_count >= cls._max_sessions_per_gpu:
                    continue
                if gpu.temperature >= cls._max_gpu_temp:
                    continue
                
                # Load balance: pick the GPU with lowest session count, lowest memory utilization
                if selected_gpu is None:
                    selected_gpu = gpu
                else:
                    if gpu.session_count < selected_gpu.session_count:
                        selected_gpu = gpu
                    elif gpu.session_count == selected_gpu.session_count:
                        # Tie break: pick lowest VRAM utilization ratio
                        old_ratio = selected_gpu.used_vram / max(1, selected_gpu.total_vram)
                        new_ratio = gpu.used_vram / max(1, gpu.total_vram)
                        if new_ratio < old_ratio:
                            selected_gpu = gpu
            
            if selected_gpu is not None:
                selected_gpu.session_count += 1
                print(f"[scheduler] Allocated GPU {selected_gpu.index} (active sessions: {selected_gpu.session_count})")
                return selected_gpu.index
            
            return None # Fallback to CPU if all GPUs are at max capacity

    @classmethod
    async def release_gpu(cls, gpu_index: Optional[int]) -> None:
        """Decrements the session counter for the given GPU index."""
        if gpu_index is None:
            return
        async with cls._lock:
            for gpu in cls._gpus:
                if gpu.index == gpu_index:
                    gpu.session_count = max(0, gpu.session_count - 1)
                    print(f"[scheduler] Released GPU {gpu_index} (active sessions: {gpu.session_count})")
                    break

    @classmethod
    async def get_cluster_status(cls) -> List[Dict[str, Any]]:
        """Returns details about all GPUs in the cluster."""
        await cls.update_metrics()
        async with cls._lock:
            return [
                {
                    "gpu_index": gpu.index,
                    "temperature_c": gpu.temperature,
                    "utilization_pct": gpu.utilization,
                    "used_vram_mb": gpu.used_vram,
                    "total_vram_mb": gpu.total_vram,
                    "encoder_util_pct": gpu.encoder_util,
                    "decoder_util_pct": gpu.decoder_util,
                    "active_sessions": gpu.session_count
                }
                for gpu in cls._gpus
            ]
