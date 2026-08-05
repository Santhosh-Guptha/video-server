export type NvrBrand = 'hikvision' | 'dahua' | 'uniview' | 'onvif' | 'custom';

export type StreamMode = 'local' | 'remote';

export type StreamQuality = 'main' | 'sub';

export interface CameraConfig {
  id?: number;
  name: string;
  location: string; // e.g. "Godown Section A", "Main Gate"
  localIp: string; // e.g. "192.168.1.50"
  remoteHost: string; // e.g. "godown.ddns.net" or Public IP
  rtspPort: number; // Default 554
  httpPort: number; // Default 80 or 8000
  username: string;
  password: string; // Stored locally on mobile device
  channel: number; // Default 1
  nvrBrand: NvrBrand;
  streamQuality: StreamQuality;
  isNvr: boolean; // True if connected to NVR, False if standalone IP Camera
  activeMode?: StreamMode;
  createdAt: string;
  updatedAt: string;
}

export interface UserAuth {
  id?: number;
  username: string;
  pinHash: string; // PBKDF2/SHA256 hashed PIN
  authEnabled: boolean;
  biometricEnabled: boolean;
  lastLogin?: string;
}

export interface PlaybackParams {
  cameraId: number;
  startDate: string; // YYYY-MM-DD
  startTime: string; // HH:mm:ss
  endDate: string; // YYYY-MM-DD
  endTime: string; // HH:mm:ss
  speed: number; // 0.5, 1, 2, 4, 8, 16
}

export interface PlaybackTimelineEvent {
  id: string;
  startTime: string; // HH:mm
  endTime: string; // HH:mm
  type: 'motion' | 'continuous' | 'alarm';
  title: string;
}
