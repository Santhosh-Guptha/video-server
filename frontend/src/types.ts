export type CameraStream = {
  id: string
  camera_id: string
  stream_id: string
  profile_type: 'MAIN' | 'SUB' | 'MOBILE'
  resolution: string
  fps: number
  codec: string
  bitrate?: number | null
  stream_url: string
  status: 'REGISTERED' | 'CONNECTING' | 'ONLINE' | 'DEGRADED' | 'RECONNECTING' | 'OFFLINE' | 'ERROR'
  error_message?: string | null
  always_on?: boolean
  transcode?: boolean
  created_at: string
  updated_at: string
}

export type Camera = {
  id: string
  pk?: number // Backward compatibility
  source_camera_id?: number | null
  stream_id: string // Primary stream shortcut
  name: string
  stream_type: string // Primary stream type shortcut
  rtsp_url?: string | null
  fps?: number | null
  width?: number | null
  height?: number | null
  archive_type?: string | null
  active: boolean
  transcode: boolean
  bitrate?: number | null
  camera_type?: string | null
  decode_type?: string | null
  server_http_port?: number | null
  make?: string | null
  synced_from_api?: boolean
  camera_source?: 'UPSTREAM' | 'LOCAL'
  is_read_only?: boolean
  raw_json: string
  streams: CameraStream[]
  created_at: string
  updated_at: string
}

export type RecordingSegment = {
  id: number
  stream_id: string
  camera_name: string
  file_path: string
  start_ts: number
  end_ts: number
}
