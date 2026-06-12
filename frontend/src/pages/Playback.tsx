import { useState, useEffect, useRef } from 'react'
import { Calendar, PlayCircle, Film, Loader2, AlertCircle, FileVideo } from 'lucide-react'

type Props = {
  streamId?: string
  cameraName?: string
}

export function Playback({ streamId, cameraName }: Props) {
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('00:00')
  const [streamUrl, setStreamUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // Fetch available dates when camera changes
  useEffect(() => {
    if (!streamId) {
      setAvailableDates([])
      setSelectedDate('')
      setStreamUrl('')
      setHasSearched(false)
      return
    }

    async function loadAvailableDates() {
      setLoading(true)
      try {
        const res = await fetch(`/api/playback/${encodeURIComponent(streamId!)}/available-dates`)
        if (res.ok) {
          const dates: string[] = await res.json()
          setAvailableDates(dates)
          if (dates.length > 0) {
            // Default to latest date
            setSelectedDate(dates[dates.length - 1])
          } else {
            setSelectedDate('')
          }
        }
      } catch (e) {
        console.error('Failed to load dates:', e)
      } finally {
        setLoading(false)
      }
    }

    loadAvailableDates()
    setStreamUrl('')
    setHasSearched(false)
  }, [streamId])

  // Load the continuous MP4 stream
  function handleLoadStream() {
    if (!streamId || !selectedDate || !selectedTime) return

    // Construct timestamp from date + time
    const localDateTimeStr = `${selectedDate}T${selectedTime}`
    const startTs = Math.floor(new Date(localDateTimeStr).getTime() / 1000)
    // Stream up to 24 hours of recording in one contiguous session
    const endTs = startTs + 24 * 3600

    const url = `/api/playback/${encodeURIComponent(streamId)}/stream.mp4?start_ts=${startTs}&end_ts=${endTs}`
    setStreamUrl(url)
    setHasSearched(true)

    // Force load the new source in video player
    if (videoRef.current) {
      videoRef.current.load()
    }
  }

  return (
    <section className="content" id="playback">
      <div className="panelHead">
        <div>
          <div className="eyebrow">Seamless Continuous Playback</div>
          <h2 className="panelTitle">{cameraName ?? 'Select a Camera'}</h2>
          <div className="panelSub">
            {streamId ? `Stream ID: ${streamId}` : 'Choose a camera feed from the Dashboard to start'}
          </div>
        </div>
      </div>

      {streamId ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Minimal Controls Bar */}
          <div className="controlsBar" style={{ margin: 0, padding: '14px 20px' }}>
            {availableDates.length > 0 ? (
              <div className="controlGroup" style={{ flexWrap: 'wrap', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="controlLabel" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Calendar size={14} /> Date:
                  </span>
                  <select
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '12px',
                      border: '1px solid rgba(148,163,184,0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.9rem',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    {availableDates.map((d) => {
                      // Format YYYY-MM-DD nicely
                      const dateObj = new Date(d)
                      const formatted = dateObj.toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric'
                      })
                      return (
                        <option key={d} value={d}>
                          {formatted}
                        </option>
                      )
                    })}
                  </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="controlLabel">Time:</span>
                  <input
                    type="time"
                    value={selectedTime}
                    onChange={(e) => setSelectedTime(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '12px',
                      border: '1px solid rgba(148,163,184,0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.9rem',
                      outline: 'none'
                    }}
                  />
                </div>

                <button
                  className="primaryBtn"
                  onClick={handleLoadStream}
                  disabled={loading}
                  style={{ borderRadius: '12px', padding: '9px 18px', fontSize: '0.86rem' }}
                >
                  {loading ? <Loader2 className="spin" size={14} /> : 'Play Continuous Video'}
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '0.9rem' }}>
                <AlertCircle size={16} />
                No recordings indexed yet for this camera.
              </div>
            )}
          </div>

          {/* Continuous Player Viewport */}
          {streamUrl ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '18px', maxWidth: '960px', margin: '0 auto', width: '100%' }}>
              <div className="playerShell" style={{ padding: '14px' }}>
                <div className="playerHeader" style={{ padding: '0 0 10px' }}>
                  <div>
                    <span className="eyebrow">Continuous Playback Timeline</span>
                    <h3 className="panelTitle" style={{ fontSize: '1.05rem', margin: '4px 0 0' }}>
                      Streaming from: {new Date(`${selectedDate}T${selectedTime}`).toLocaleString()}
                    </h3>
                  </div>
                  <div className="playerChips">
                    <span className="chip chipLive" style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', borderColor: 'rgba(96,165,250,0.2)' }}>
                      <Film size={12} /> Continuous Mux
                    </span>
                  </div>
                </div>

                <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', borderRadius: '20px' }}>
                  <video
                    ref={videoRef}
                    className="videoEl"
                    controls
                    autoPlay
                    playsInline
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  >
                    <source src={streamUrl} type="video/mp4" />
                    Your browser does not support the video tag.
                  </video>
                </div>

                <div className="playerFooter" style={{ marginTop: '12px' }}>
                  <AlertCircle size={14} />
                  <span>The timeline above represents all segments stitched together. You can freely seek or scrub through the video timeline.</span>
                </div>
              </div>
            </div>
          ) : (
            hasSearched && (
              <div className="emptyState" style={{ padding: '40px 20px' }}>
                <FileVideo size={42} style={{ color: '#64748b' }} />
                <h3 style={{ marginTop: '12px' }}>No recordings found</h3>
                <p style={{ marginTop: '6px' }}>Try selecting another date or time.</p>
              </div>
            )
          )}
        </div>
      ) : (
        <div className="emptyState" style={{ padding: '40px 20px' }}>
          <FileVideo size={42} style={{ color: '#64748b' }} />
          <h3 style={{ marginTop: '12px' }}>No camera selected</h3>
          <p style={{ marginTop: '6px' }}>Go to the Dashboard tab to select a camera to load recorded video history.</p>
        </div>
      )}
    </section>
  )
}
