import type { Camera, RecordingSegment } from '../types'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export async function fetchCameras(): Promise<Camera[]> {
  const res = await fetch('/api/cameras?sync=false')
  if (!res.ok) throw new Error(`Failed to fetch cameras: ${res.status}`)
  return res.json()
}

export async function syncCameras(): Promise<{ total: number; created_or_updated: number; source: string }> {
  const res = await fetch('/api/cameras/sync', { method: 'POST', headers: JSON_HEADERS })
  if (!res.ok) throw new Error(`Failed to sync cameras: ${res.status}`)
  return res.json()
}

export async function startLive(streamId: string) {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}/live/start`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to start live: ${res.status}`)
  return res.json()
}

export async function stopLive(streamId: string) {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}/live/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to stop live: ${res.status}`)
  return res.json()
}

export async function fetchRecordings(streamId: string): Promise<RecordingSegment[]> {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}/recordings`)
  if (!res.ok) throw new Error(`Failed to fetch recordings: ${res.status}`)
  return res.json()
}

export async function fetchPlayback(streamId: string, startTs: number, endTs: number): Promise<RecordingSegment[]> {
  const res = await fetch(`/api/playback/${encodeURIComponent(streamId)}?start_ts=${startTs}&end_ts=${endTs}`)
  if (!res.ok) throw new Error(`Failed to fetch playback: ${res.status}`)
  return res.json()
}

export async function createCamera(payload: any): Promise<Camera> {
  const res = await fetch('/api/cameras', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to create camera')
  }
  return res.json()
}

export async function updateCamera(streamId: string, payload: any): Promise<Camera> {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to update camera')
  }
  return res.json()
}

export async function deleteCamera(streamId: string): Promise<any> {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}`, {
    method: 'DELETE'
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to delete camera')
  }
  return res.json()
}

export async function getSystemSettings(): Promise<{ use_upstream_cameras: boolean }> {
  const res = await fetch('/api/settings')
  if (!res.ok) {
    throw new Error('Failed to fetch settings')
  }
  return res.json()
}

export async function updateSystemSettings(useUpstreamCameras: boolean): Promise<any> {
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ use_upstream_cameras: useUpstreamCameras })
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to update settings')
  }
  return res.json()
}

export async function testRtspConnection(rtspUrl: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch('/api/cameras/test-rtsp', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ rtsp_url: rtspUrl })
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to test RTSP connection')
  }
  return res.json()
}

export async function applyUpstreamConfig(streamId: string): Promise<any> {
  const res = await fetch(`/api/cameras/${encodeURIComponent(streamId)}/apply-upstream-config`, {
    method: 'POST',
    headers: JSON_HEADERS
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to apply upstream configuration')
  }
  return res.json()
}

