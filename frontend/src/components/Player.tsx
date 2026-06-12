import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import { AlertCircle, Loader2, Maximize2, Volume2, VolumeX, Play, X } from 'lucide-react'

type PlayerProps = {
  src?: string
  posterLabel?: string
  isFocused?: boolean
  onClose?: () => void
  onFocus?: () => void
  minimal?: boolean
}

export function Player({ src, posterLabel, isFocused, onClose, onFocus, minimal }: PlayerProps) {
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
        liveSyncDuration: 1.5,
        liveMaxLatencyDuration: 3,
        maxBufferLength: 4,
        maxMaxBufferLength: 8
      })
      hlsRef.current = hls
      hls.loadSource(src)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))
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
    <div className={`playerShell ${isFocused ? 'focused' : ''} ${minimal ? 'minimalMode' : ''}`} onClick={onFocus} style={{ cursor: onFocus ? 'pointer' : 'default' }}>
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
            <span className="chip">HLS</span>
            <span className="chip">Low latency</span>
          </div>
        </div>
      )}

      <div className="playerViewport">
        {minimal && (
          <div className="minimalCameraLabel">
            {posterLabel ?? 'Live feed'}
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
              zIndex: 11,
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
            <div className="overlayText">Buffering stream…</div>
          </div>
        )}
        <video ref={videoRef} className="videoEl" controls={!minimal} autoPlay playsInline muted={muted} />
        <div className="fakeStamp">LIVE</div>
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
          <span>If the stream is black, the camera may still be loading or the HLS playlist may not be ready yet.</span>
        </div>
      )}
    </div>
  )
}
