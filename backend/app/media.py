import asyncio
import os
from pathlib import Path

from .config import settings


class StreamProcess:
    def __init__(
        self,
        stream_id: str,
        ffmpeg_proc: asyncio.subprocess.Process
    ):
        self.stream_id = stream_id
        self.proc = ffmpeg_proc
        self.subscribers: set[asyncio.Queue] = set()
        self.stop_event = asyncio.Event()


class MediaManager:

    def __init__(self) -> None:
        self.streams: dict[str, StreamProcess] = {}

    async def start_rtsp_stream(
        self,
        stream_id: str,
        rtsp_url: str,
        recording_dir: str,
        hls_dir: str
    ) -> None:

        existing = self.streams.get(stream_id)

        if (
            existing
            and existing.proc
            and existing.proc.returncode is None
        ):
            print(f"[media] Stream already running: {stream_id}")
            return

        # --------------------------------------------------
        # Fix RTSP URL
        # --------------------------------------------------

        rtsp_url = (rtsp_url or "").strip()

        if not rtsp_url:
            raise Exception("RTSP URL is empty")

        if not rtsp_url.startswith(
            ("rtsp://", "rtsps://")
        ):
            rtsp_url = f"rtsp://{rtsp_url}"

        print(
            f"[media] Starting stream "
            f"{stream_id} -> {rtsp_url}"
        )

        # --------------------------------------------------
        # Directories
        # --------------------------------------------------

        stream_record_dir = (
            Path(recording_dir) / stream_id
        )

        stream_hls_dir = (
            Path(hls_dir) / stream_id
        )

        stream_record_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        stream_hls_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # --------------------------------------------------
        # Outputs
        # --------------------------------------------------

        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        (stream_record_dir / today_str).mkdir(parents=True, exist_ok=True)
        (stream_record_dir / tomorrow_str).mkdir(parents=True, exist_ok=True)

        segment_path = str(
            stream_record_dir /
            "%Y-%m-%d" /
            "%Y%m%d_%H%M%S_%03d.mp4"
        )

        playlist = str(
            stream_hls_dir /
            "index.m3u8"
        )

        master = str(
            stream_hls_dir /
            "master.m3u8"
        )

        tee_output = (
            f"[f=hls:"
            f"hls_time=1:"
            f"hls_list_size=5:"
            f"hls_flags=delete_segments+omit_endlist:"
            f"master_pl_name={os.path.basename(master)}]"
            f"{playlist}"
            f"|"
            f"[f=segment:"
            f"segment_time={settings.segment_time_seconds}:"
            f"reset_timestamps=1:"
            f"strftime=1]"
            f"{segment_path}"
        )

        # --------------------------------------------------
        # FFmpeg
        # --------------------------------------------------

        cmd = [
            settings.ffmpeg_path,

            "-hide_banner",
            "-loglevel",
            "warning",

            "-rtsp_transport",
            "tcp",

            "-stimeout",
            "10000000",

            "-use_wallclock_as_timestamps",
            "1",

            "-fflags",
            "+genpts+nobuffer",

            "-probesize",
            "100000",

            "-analyzeduration",
            "100000",

            "-vsync",
            "1",

            "-i",
            rtsp_url,

            "-map",
            "0:v:0?",

            "-map",
            "0:a:0?",

            "-c:v",
            "libx264",

            "-preset",
            "ultrafast",

            "-tune",
            "zerolatency",

            "-pix_fmt",
            "yuv420p",

            "-g",
            "15",

            "-c:a",
            "aac",

            "-ar",
            "44100",

            "-b:a",
            "128k",

            "-f",
            "tee",

            tee_output
        ]

        print(
            "[media] FFmpeg command:\n"
            + " ".join(cmd)
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        self.streams[stream_id] = StreamProcess(
            stream_id,
            proc
        )

        asyncio.create_task(
            self._log_stderr(stream_id)
        )

        asyncio.create_task(
            self._watch_process(stream_id)
        )

    async def stop(
        self,
        stream_id: str
    ) -> None:

        sp = self.streams.get(stream_id)

        if not sp:
            return

        try:

            print(
                f"[media] Stopping stream "
                f"{stream_id}"
            )

            sp.stop_event.set()

            sp.proc.terminate()

            await asyncio.wait_for(
                sp.proc.wait(),
                timeout=5
            )

        except Exception:

            try:
                sp.proc.kill()
            except Exception:
                pass

        self.streams.pop(
            stream_id,
            None
        )

    async def _watch_process(
        self,
        stream_id: str
    ) -> None:

        sp = self.streams.get(stream_id)

        if not sp:
            return

        rc = await sp.proc.wait()

        print(
            f"[media] Stream exited "
            f"{stream_id}, rc={rc}"
        )

    async def _log_stderr(
        self,
        stream_id: str
    ) -> None:

        sp = self.streams.get(stream_id)

        if not sp:
            return

        if not sp.proc.stderr:
            return

        while True:

            line = await sp.proc.stderr.readline()

            if not line:
                break

            print(
                f"[ffmpeg:{stream_id}] "
                f"{line.decode(errors='ignore').strip()}"
            )


media_manager = MediaManager()
