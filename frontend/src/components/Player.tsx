import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import { AlertCircle, Loader2, Maximize2, Volume2, VolumeX, Play } from 'lucide-react'

type PlayerProps = {
  src?: string
  posterLabel?: string
}

export function Player({ src, posterLabel }: PlayerProps) {
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
      const hls = new Hls({ lowLatencyMode: true, backBufferLength: 30, liveDurationInfinity: true })
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
    <div className="playerShell">
      <div className="playerHeader">
        <div>
          <div className="eyebrow">{posterLabel ?? 'Live feed'}</div>
          <h3 className="panelTitle">Real-time camera view</h3>
        </div>
        <div className="playerChips">
          <span className="chip chipLive"><span className="dotPulse" />Live</span>
          <span className="chip">HLS</span>
          <span className="chip">Low latency</span>
        </div>
      </div>

      <div className="playerViewport">
        {!loaded && (
          <div className="playerOverlay">
            <Loader2 className="spin" size={18} />
            <div className="overlayText">Buffering stream…</div>
          </div>
        )}
        <video ref={videoRef} className="videoEl" controls autoPlay playsInline muted={muted} />
        <div className="fakeStamp">LIVE</div>
      </div>

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

      <div className="playerFooter">
        <AlertCircle size={14} />
        <span>If the stream is black, the camera may still be loading or the HLS playlist may not be ready yet.</span>
      </div>
    </div>
  )
}
