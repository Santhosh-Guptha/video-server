import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any

# Default policies
DEFAULT_POLICIES = {
    "stream_policy.yaml": {
        "live_stream_profile": "NORMAL",
        "enable_adaptive_profile": True,
        "focus_view_profile": "HD",
        "grid_view_profile": "NORMAL",
        "mobile_view_profile": "MOBILE"
    },
    "transcoder_policy.yaml": {
        "max_active_transcoders": 10,
        "transcoder_vcodec": "libx264",
        "transcoder_preset": "ultrafast",
        "transcoder_tune": "zerolatency",
        "hw_acceleration_enabled": False,
        "hw_acceleration_type": "cuda",
        "max_streams_per_gpu": 8
    },
    "playback_policy.yaml": {
        "playback_profile": "HD",
        "playback_allow_normal_fallback": True,
        "playback_allow_mobile_fallback": False,
        "playback_speeds": [0.5, 1.0, 2.0, 4.0, 8.0],
        "enable_playback_transcoding": True
    },
    "recording_policy.yaml": {
        "enable_recording": True,
        "record_hd_only": True,
        "record_normal": False,
        "record_mobile": False,
        "segment_time_seconds": 60
    },
    "ai_policy.yaml": {
        "enable_ai_analytics": True,
        "ai_fps_limit": 10,
        "ai_inference_engine": "local",
        "ai_cluster_url": "http://localhost:8999"
    },
    "watchdog_policy.yaml": {
        "camera_ping_interval_seconds": 120,
        "camera_ping_timeout_seconds": 5,
        "enable_rtsp_health_check": True
    },
    "client_policy.yaml": {
        "capabilities": {
            "safari": {"supports_h265": True, "supports_h264": True},
            "chrome": {"supports_h265": False, "supports_h264": True},
            "firefox": {"supports_h265": False, "supports_h264": True},
            "android_native": {"supports_h265": True, "supports_h264": True},
            "ios_native": {"supports_h265": True, "supports_h264": True},
            "desktop_client": {"supports_h265": True, "supports_h264": True}
        }
    },
    "security_policy.yaml": {
        "api_key_secret": "vms_secure_secret_key",
        "tenant_header": "X-Tenant-ID",
        "node_header": "X-Node-ID",
        "token_expiry_hours": 24
    },
    "session_policy.yaml": {
        "max_webrtc_sessions_per_camera": 100,
        "webrtc_connection_timeout_seconds": 10,
        "transcoder_grace_period_seconds": 60,
        "heartbeat_interval_seconds": 15
    },
    "cluster_policy.yaml": {
        "cloud_gateway_url": "http://localhost:8500",
        "backup_gateway_url": "http://localhost:8501",
        "cloud_enabled": True,
        "connection_timeout_seconds": 5,
        "fallback_timeout_seconds": 3
    },
    "monitoring_policy.yaml": {
        "enable_prometheus": True,
        "prometheus_port": 8000,
        "metrics_history_days": 7,
        "log_level": "INFO"
    },
    "storage_policy.yaml": {
        "enable_retention": True,
        "default_retention_days": 30,
        "enable_low_disk_eviction": True,
        "low_disk_space_threshold_gb": 5.0,
        "target_free_space_gb": 10.0
    }
}


class PolicyLoader:
    _policies: Dict[str, Dict[str, Any]] = {}
    _config_dir: Path = Path(__file__).parent / "configs"

    @classmethod
    def initialize(cls):
        """Creates config directory and writes default policies if missing, then loads them."""
        os.makedirs(cls._config_dir, exist_ok=True)
        for filename, default_data in DEFAULT_POLICIES.items():
            filepath = cls._config_dir / filename
            if not filepath.exists():
                try:
                    with open(filepath, "w") as f:
                        yaml.dump(default_data, f, default_flow_style=False)
                    print(f"[policy] Wrote default policy file: {filepath}")
                except Exception as e:
                    print(f"[policy] Error writing default policy {filename}: {e}")
            cls.load_policy(filename)

    @classmethod
    def load_policy(cls, filename: str):
        """Loads a single policy file from disk or falls back to defaults."""
        filepath = cls._config_dir / filename
        if filepath.exists():
            try:
                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        cls._policies[filename] = data
                        return
            except Exception as e:
                print(f"[policy] Failed to parse {filename}: {e}. Using internal defaults.")
        
        # Fallback to internal default dictionary
        cls._policies[filename] = DEFAULT_POLICIES.get(filename, {})

    @classmethod
    def get(cls, policy_file: str, key: str, default: Any = None) -> Any:
        """Retrieves a configuration key from a specific policy file."""
        if not cls._policies:
            cls.initialize()
        
        policy = cls._policies.get(policy_file)
        if policy is None:
            # Try to load if not cached
            cls.load_policy(policy_file)
            policy = cls._policies.get(policy_file, {})
        
        return policy.get(key, DEFAULT_POLICIES.get(policy_file, {}).get(key, default))


# Initialize on import
PolicyLoader.initialize()
