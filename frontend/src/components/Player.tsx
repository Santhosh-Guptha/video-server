import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import { AlertCircle, Loader2, Maximize2, Volume2, VolumeX, Play, X } from 'lucide-react'
import { WebRTCPlayer } from './WebRTCPlayer'

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
      <div 
        className={`playerShell ${isFocused ? 'focused' : ''} ${minimal ? 'minimalMode' : ''}`} 
        onClick={onFocus} 
        style={{ cursor: onFocus ? 'pointer' : 'default', width: '100%', height: '100%' }}
      >
        {onClose && !minimal && (
          <button
            className="playerCloseBtn"
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onClose()
            }}
            title="Deselect camera"
            style={{ position: 'absolute', top: '16px', right: '16px', zIndex: 12 }}
          >
            <X size={16} />
          </button>
        )}
        {onClose && minimal && (
          <button
            className="playerCloseBtn"
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onClose()
            }}
            title="Deselect camera"
            style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              zIndex: 12,
              background: 'rgba(15, 23, 42, 0.75)',
              backdropFilter: 'blur(4px)',
              border: '1px solid rgba(148, 163, 184, 0.15)',
              color: '#fca5a5'
            }}
          >
            <X size={14} />
          </button>
        )}
        <WebRTCPlayer
          streamId={streamId}
          posterLabel={posterLabel}
          isFocused={isFocused}
          minimal={minimal}
          onFallbackToHls={() => {
            console.log(`[Player] WebRTC failed. Falling back to HLS for stream: ${streamId}`);
            setUseWebRTC(false);
          }}
        />
      </div>
    )
  }

  // Fallback HLS Player Code
  return <HLSPlayer src={src} posterLabel={posterLabel} isFocused={isFocused} onClose={onClose} onFocus={onFocus} minimal={minimal} />
}

type HLSPlayerProps = {
  src?: string
  posterLabel?: string
  isFocused?: boolean
  onClose?: () => void
  onFocus?: () => void
  minimal?: boolean
}

function HLSPlayer({ src, posterLabel, isFocused, onClose, onFocus, minimal }: HLSPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const hlsRef = useRef<Hls | null>(null)
  const [muted, setMuted] = useState(true)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return
    setLoaded(false)

    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }

    const onCanPlay = () => setLoaded(true)
    video.addEventListener('canplay', onCanPlay)

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      video.play().catch(() => {})
    } else if (Hls.isSupported()) {
      const hls = new Hls({
        lowLatencyMode: true,
        backBufferLength: 30,
        liveDurationInfinity: true,
        liveSyncDuration: 3.0,
        liveMaxLatencyDuration: 6.0,
        maxBufferLength: 10,
        maxMaxBufferLength: 20
      })
      hlsRef.current = hls
      hls.loadSource(src)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))
      
      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              console.warn('[HLSPlayer] Fatal network error, trying to recover...', data);
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              console.warn('[HLSPlayer] Fatal media error, trying to recover...', data);
              hls.recoverMediaError();
              break;
            default:
              console.error('[HLSPlayer] Unrecoverable error:', data);
              hls.destroy();
              break;
          }
        }
      })
    }

    return () => {
      video.removeEventListener('canplay', onCanPlay)
      if (hlsRef.current) {
        hlsRef.current.destroy()
        hlsRef.current = null
      }
    }
  }, [src])

  useEffect(() => {
    const video = videoRef.current
    if (video) video.muted = muted
  }, [muted])

  return (
    <div className={`playerShell ${isFocused ? 'focused' : ''} ${minimal ? 'minimalMode' : ''}`} onClick={onFocus} style={{ cursor: onFocus ? 'pointer' : 'default', width: '100%', height: '100%' }}>
      {!minimal && (
        <div className="playerHeader">
          <div>
            <div className="eyebrow">{posterLabel ?? 'Live feed'}</div>
            <h3 className="panelTitle">Real-time camera view</h3>
          </div>
          <div className="playerChips" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {onClose && (
              <button
                className="playerCloseBtn"
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onClose()
                }}
                title="Deselect camera"
              >
                <X size={16} />
              </button>
            )}
            <span className="chip chipLive"><span className="dotPulse" />Live</span>
            <span className="chip" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', borderColor: 'rgba(245, 158, 11, 0.3)' }}>HLS (Fallback)</span>
            <span className="chip">Low latency</span>
          </div>
        </div>
      )}

      <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', background: '#090d16' }}>
        {minimal && (
          <div className="minimalCameraLabel" style={{ zIndex: 11 }}>
            {posterLabel ?? 'Live feed'}
            <span style={{ marginLeft: '6px', fontSize: '9px', opacity: 0.8, color: '#fbbf24' }}>HLS</span>
          </div>
        )}
        {minimal && onClose && (
          <button
            className="playerCloseBtn"
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onClose()
            }}
            title="Deselect camera"
            style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              zIndex: 12,
              background: 'rgba(15, 23, 42, 0.75)',
              backdropFilter: 'blur(4px)',
              border: '1px solid rgba(148, 163, 184, 0.15)',
              color: '#fca5a5'
            }}
          >
            <X size={14} />
          </button>
        )}
        {!loaded && (
          <div className="playerOverlay">
            <Loader2 className="spin" size={18} />
            <div className="overlayText">Buffering HLS stream…</div>
          </div>
        )}
        <video ref={videoRef} className="videoEl" controls={!minimal} autoPlay playsInline muted={muted} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
        <div className="fakeStamp" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span className="recordingDot" style={{ marginRight: '0' }} /> LIVE
        </div>
      </div>

      {!minimal && (
        <div className="playerControls">
          <button className="miniBtn" type="button" onClick={() => setMuted(m => !m)}>
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <button className="miniBtn" type="button" onClick={() => videoRef.current?.play().catch(() => {})}>
            <Play size={16} /> Play
          </button>
          <button className="miniBtn" type="button" onClick={() => videoRef.current?.requestFullscreen?.()}>
            <Maximize2 size={16} /> Fullscreen
          </button>
          <div className="playerHint">{src ? src.replace(window.location.origin, '') : 'No stream selected'}</div>
        </div>
      )}

      {!minimal && (
        <div className="playerFooter">
          <AlertCircle size={14} />
          <span>Using standard HLS fallback due to WebRTC unavailability or user override.</span>
        </div>
      )}
    </div>
  )
}
