import { useEffect, useState, lazy, Suspense } from 'react'

import { AlertCircle, Loader2, Maximize2, Volume2, VolumeX, Play, X } from 'lucide-react'
import { WebRTCPlayer } from './WebRTCPlayer'
const HLSPlayer = lazy(() => import('./HLSPlayer').then(module => ({ default: module.HLSPlayer })))

type PlayerProps = {
  src?: string
  posterLabel?: string
  isFocused?: boolean
  onClose?: () => void
  onFocus?: () => void
  minimal?: boolean
}

export function Player({ src, posterLabel, isFocused, onClose, onFocus, minimal }: PlayerProps) {
  const [useWebRTC, setUseWebRTC] = useState(true)

  // Reset WebRTC try status if src changes
  useEffect(() => {
    setUseWebRTC(true)
  }, [src])

  // Extract stream_id from src, e.g. /api/streams/cam_12_MAIN/live/index.m3u8
  const match = src ? src.match(/\/api\/streams\/([^/]+)\/live/) : null
  const streamId = match ? decodeURIComponent(match[1]) : undefined

  if (useWebRTC && streamId) {
    return (
      <WebRTCPlayer
        streamId={streamId}
        posterLabel={posterLabel}
        isFocused={isFocused}
        minimal={minimal}
        onClose={onClose}
        onFocus={onFocus}
        onFallbackToHls={() => {
          console.log(`[Player] WebRTC failed. Falling back to HLS for stream: ${streamId}`);
          setUseWebRTC(false);
        }}
      />
    )
  }

  // Fallback HLS Player Code
  return <Suspense fallback={<div className="playerShell" role="status">Loading video player…</div>}><HLSPlayer src={src} posterLabel={posterLabel} isFocused={isFocused} onClose={onClose} onFocus={onFocus} minimal={minimal} /></Suspense>
}
