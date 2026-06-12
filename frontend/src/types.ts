export type Camera = {
  pk: number
  source_camera_id: number
  stream_id: string
  name: string
  stream_type: string
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
  raw_json: string
}

export type RecordingSegment = {
  id: number
  stream_id: string
  camera_name: string
  file_path: string
  start_ts: number
  end_ts: number
}
