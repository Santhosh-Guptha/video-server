/**
 * usePolicy — Fetches and caches the active VMS backend policy.
 *
 * The backend policy (vms_policy.py) is the single source of truth for:
 * - Which stream profile to use for live view (HD/NORMAL/MOBILE)
 * - Which stream profile to use for playback
 * - Playback speeds available
 * - Timeline zoom default
 * - WebRTC / HLS fallback behavior
 *
 * The UI must NEVER hardcode stream selection logic.
 * All routing decisions flow from this hook.
 */

import { useEffect, useState, useCallback } from 'react'
import type { Camera, CameraStream } from '../types'

export type LivePolicy = {
  profile: string
  adaptive_enabled: boolean
  focus_view_profile: string
  grid_view_profile: string
  mobile_view_profile: string
  resolved_1x1: string        // ProfileType string: "MAIN" | "SUB" | "MOBILE"
  resolved_grid: string
}

export type PlaybackPolicy = {
  profile: string
  resolved_profile_type: string  // "MAIN" | "SUB" | "MOBILE"
  allow_normal_fallback: boolean
  allow_mobile_fallback: boolean
  speeds: number[]
  timeline_default_zoom: string
  timeline_merge_threshold: number
}

export type VMSPolicy = {
  live: LivePolicy
  playback: PlaybackPolicy
  webrtc: {
    enabled: boolean
    hls_fallback: boolean
    max_sessions: number
    connection_timeout: number
  }
  recording: {
    record_hd_only: boolean
    record_normal: boolean
    record_mobile: boolean
    enabled_profiles: string[]
    segment_duration_seconds: number
    enable_recording: boolean
    retention_enabled: boolean
    retention_days: number
  }
  transcoding: {
    h265_enabled: boolean
    vcodec: string
    preset: string
    tune: string
    idle_timeout: number
    max_transcoders: number
  }
}

// Default policy used while loading or if backend is unreachable
const DEFAULT_POLICY: VMSPolicy = {
  live: {
    profile: 'NORMAL',
    adaptive_enabled: true,
    focus_view_profile: 'HD',
    grid_view_profile: 'NORMAL',
    mobile_view_profile: 'MOBILE',
    resolved_1x1: 'MAIN',
    resolved_grid: 'SUB',
  },
  playback: {
    profile: 'HD',
    resolved_profile_type: 'MAIN',
    allow_normal_fallback: true,
    allow_mobile_fallback: false,
    speeds: [0.5, 1.0, 2.0, 4.0, 8.0],
    timeline_default_zoom: '24h',
    timeline_merge_threshold: 5,
  },
  webrtc: { enabled: true, hls_fallback: true, max_sessions: 100, connection_timeout: 10 },
  recording: {
    record_hd_only: true, record_normal: false, record_mobile: false,
    enabled_profiles: ['MAIN'], segment_duration_seconds: 60,
    enable_recording: true, retention_enabled: true, retention_days: 30,
  },
  transcoding: {
    h265_enabled: true, vcodec: 'libx264', preset: 'ultrafast',
    tune: 'zerolatency', idle_timeout: 60, max_transcoders: 10,
  },
}

/**
 * Resolves the correct stream_id for a camera based on the active policy.
 *
 * @param cam        - Camera object with .streams array
 * @param profileType - Target ProfileType from policy: "MAIN" | "SUB" | "MOBILE"
 * @returns          - The stream_id to use, with fallback chain
 */
export function resolveStreamId(cam: Camera, profileType: string): string {
  if (!cam.streams || cam.streams.length === 0) return cam.stream_id

  // Exact match
  const exact = cam.streams.find((s: CameraStream) => s.profile_type === profileType)
  if (exact) return exact.stream_id

  // Fallback chain: MAIN → SUB → MOBILE → primary
  const fallbackOrder = ['MAIN', 'SUB', 'MOBILE']
  for (const fb of fallbackOrder) {
    const s = cam.streams.find((s: CameraStream) => s.profile_type === fb)
    if (s) return s.stream_id
  }

  return cam.stream_id
}

/**
 * Resolves the correct stream for live viewing based on active policy.
 *
 * @param cam        - Camera object
 * @param policy     - The active VMSPolicy
 * @param layoutSize - Number of cameras currently in the grid (0 = unknown)
 */
export function resolveLiveStreamId(cam: Camera, policy: VMSPolicy, layoutSize: number = 0): string {
  let targetProfile: string
  if (layoutSize === 1) {
    targetProfile = policy.live?.resolved_1x1 || 'MAIN'
  } else if (layoutSize > 1) {
    targetProfile = policy.live?.resolved_grid || 'SUB'
  } else {
    targetProfile = policy.live?.resolved_1x1 || 'MAIN'
  }
  return resolveStreamId(cam, targetProfile)
}

/**
 * Resolves the correct stream for playback based on active policy.
 *
 * @param cam    - Camera object
 * @param policy - The active VMSPolicy
 */
export function resolvePlaybackStreamId(cam: Camera, policy: VMSPolicy): string {
  const targetProfile = policy.playback.resolved_profile_type

  const exact = cam.streams?.find((s: CameraStream) => s.profile_type === targetProfile)
  if (exact) return exact.stream_id

  // Normal fallback
  if (policy.playback.allow_normal_fallback) {
    const sub = cam.streams?.find((s: CameraStream) => s.profile_type === 'SUB')
    if (sub) return sub.stream_id
  }

  // Final fallback: any MAIN, then primary
  const main = cam.streams?.find((s: CameraStream) => s.profile_type === 'MAIN')
  if (main) return main.stream_id

  return cam.stream_id
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function usePolicy() {
  const [policy, setPolicy] = useState<VMSPolicy>(DEFAULT_POLICY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchPolicy = useCallback(async () => {
    try {
      const res = await fetch('/api/policy')
      if (!res.ok) throw new Error(`Policy fetch failed: ${res.status}`)
      const data = await res.json() as VMSPolicy
      setPolicy(data)
      setError(null)
    } catch (e) {
      console.warn('[usePolicy] Failed to fetch backend policy, using defaults:', e)
      setError(e instanceof Error ? e.message : 'Policy fetch failed')
      // Keep using DEFAULT_POLICY — app remains functional
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPolicy()
  }, [fetchPolicy])

  return { policy, loading, error, refetch: fetchPolicy }
}
